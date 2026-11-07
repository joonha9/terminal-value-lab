"""Agent search loop (protocol v1 section 7): proposer -> blind critic -> deterministic grader -> archive.

Agents are Claude Code subagents (no paid API) WITHOUT tools: the orchestrating session passes
the prompt text written here and saves the reply text to disk (docs/phase3_design.md section 5).
This module writes prompts, validates and de-duplicates proposals, applies the critic's
verdicts, grades approved recipes on exploration windows (truth M), and archives every attempt
(including over-budget proposals and unparseable replies), so the search denominator is known.

Each stage is written atomically: all records of a stage are built first and appended in one
write together with the state change, so re-running a stage after an error cannot duplicate
records (code review 2026-11-07).

Leakage control: prompts never name firms, tickers or calendar years.

Run layout: results/phase3/agent_runs/<run>/
  config.json  state.json  archive.jsonl  replies.jsonl (every raw reply, incl. failed parses)
  genNN/proposer_prompt.md  proposals.txt  pending.json  critic_prompt.md  verdicts.txt
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from . import phase3 as P3
from . import recipes as R

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "phase3" / "agent_runs"
DEFAULT_CONFIG = {"generations": 5, "proposals_per_generation": 6, "critic": True,
                  "show_unconditional": True}
SELECTION_RULE = ("per run, the 3 graded recipes with the lowest exploration median |e| and distinct "
                  "behaviour fingerprints (ties: earlier id)")
CODE_FILES = ["tvlab/agents.py", "tvlab/recipes.py", "tvlab/phase3.py", "tvlab/methods.py", "tvlab/panel.py",
              "scripts/agent_step.py", "config/tv-text-only.md"]


class ReplyError(ValueError):
    """A reply that cannot be applied as given: the agent is asked again (and the attempt is logged)."""


@lru_cache(maxsize=1)
def baselines() -> dict:
    return json.loads((ROOT / "results/phase3/baselines_explore.json").read_text())


def code_hash() -> str:
    h = hashlib.sha1()
    for f in CODE_FILES + ["results/phase3/baselines_explore.json"]:
        h.update((ROOT / f).read_bytes())
    return h.hexdigest()[:12]


def grade_explore(tree: dict) -> dict:
    return P3.grade(tree)


# ---------------------------------------------------------------- run state
class Run:
    def __init__(self, name: str, config: dict | None = None):
        self.dir = RUNS / name
        self.name = name
        if config is not None:
            self.dir.mkdir(parents=True, exist_ok=False)
            (self.dir / "config.json").write_text(json.dumps(
                {**DEFAULT_CONFIG, **config, "created": datetime.now().isoformat(timespec="seconds"),
                 "code_hash": code_hash(), "selection_rule": SELECTION_RULE}, indent=1))
            self.save_state({"generation": 0, "stage": "new"})
        self.config = json.loads((self.dir / "config.json").read_text())

    @property
    def state(self) -> dict:
        return json.loads((self.dir / "state.json").read_text())

    def save_state(self, s: dict) -> None:
        tmp = self.dir / "state.json.tmp"
        tmp.write_text(json.dumps(s))
        tmp.replace(self.dir / "state.json")

    def gen_dir(self, g: int) -> Path:
        d = self.dir / f"gen{g:02d}"
        d.mkdir(exist_ok=True)
        return d

    def archive(self) -> list[dict]:
        f = self.dir / "archive.jsonl"
        return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []

    def commit(self, records: list[dict], state: dict) -> None:
        """Append a stage's records (skipping ids already archived) and save the new state."""
        have = {(a["id"], a["status"]) for a in self.archive()}
        new = [r for r in records if (r["id"], r["status"]) not in have]
        with open(self.dir / "archive.jsonl", "a") as f:
            f.write("".join(json.dumps(r, default=float) + "\n" for r in new))
        self.save_state(state)

    def log_reply(self, g: int, kind: str, text: str, ok: bool, error: str = "") -> None:
        with open(self.dir / "replies.jsonl", "a") as f:
            f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "generation": g,
                                "kind": kind, "ok": ok, "error": error, "text": text}) + "\n")


# ---------------------------------------------------------------- prompt pieces
def dsl_text() -> str:
    traits = "\n".join(f"  - {k}: {v}" for k, v in R.TRAITS.items())
    flags = "\n".join(f"  - {k}: {v}" for k, v in R.FLAGS.items())
    return f"""RECIPE LANGUAGE
A recipe is a decision tree (at most {R.MAX_DEPTH} levels of splits, so at most 8 leaves).
  node  = LEAF  or  {{"if": [clause, clause?], "then": node, "else": node}}
  All clauses in "if" (1 or 2) must hold for "then"; otherwise "else". "then" and "else" must differ.

CLAUSES (traits of the firm at the valuation date t; a missing trait makes the clause false)
  {{"var": TRAIT, "below_pct": P}} or {{"var": TRAIT, "above_pct": P}}
      percentile of the firm among the year's sample firms (US-listed non-financials with market
      cap >= $100M at the valuation date and clean data), P an integer 5-95; tied firms share one
      percentile
  {{"var": TRAIT, "below": x}} or {{"var": TRAIT, "above": x}}     raw value (units below)
  {{"var": "ff12", "in": [...]}}   Fama-French 12 industry, from {R.FF12}
                                  (NoDur consumer non-durables, Durbl durables, Manuf manufacturing,
                                  Enrgy oil/gas/coal, Chems chemicals, BusEq business equipment and
                                  software, Telcm telecom, Utils utilities, Shops retail/wholesale/
                                  services, Hlth healthcare, Other)
  {{"var": "fcf_positive"}} or {{"var": "ebitda_positive"}}   sign flags (use "else" for the negation)
TRAITS
{traits}
FLAGS
{flags}

LEAVES (every leaf predicts enterprise value at t+5; the horizon is fixed)
  {{"method": "exit", "multiple": M}}       EV/EBITDA multiple known at t  x  EBITDA in year t+5
      M = "ff12"       median EV/EBITDA of the firm's FF12 industry at t
          "damind"     median of its (finer, ~90 groups) Damodaran industry at t, in our panel
          "own"        the firm's own EV/EBITDA at t (needs EBITDA_t > 0)
          "dam_t"      Damodaran's published industry multiple at t
          "dam_5yavg"  average of Damodaran's published industry multiple over up to 5 years to t
  {{"method": "gordon", "cash_flow": C, "g": g, "r": R}}   C_(t+5) x (1+g) / (r - g)
      C = "fcf" (unlevered FCF of year t+5) | "fcf_3yavg" (average of years t+3..t+5) |
          "fcf_ex_sbc" (FCF minus stock-based compensation)
      g = 0 to 0.04 in steps of 0.005;  R = "wacc" (firm WACC at t) | "rf_plus_5" (10-yr Treasury + 5%)
      undefined if the cash flow <= 0 or r - g < 1 pp
  {{"method": "value_driver", "ronic": N, "g": g, "r": R}}  NOPAT_(t+5) (1+g)(1 - g/RONIC) / (r - g)
      N = "roic" (the firm's ROIC in year t+5) | "r" (RONIC = r, i.e. NOPAT(1+g)/r)
      undefined if NOPAT <= 0, RONIC <= g or r - g < 1 pp
  {{"method": "blend", "space": "log" | "level", "parts": [{{"weight": w, "leaf": LEAF}}, ...]}}
      2-3 different non-blend leaves, weights 0.05-0.95 in steps of 0.05 summing to 1;
      "log" = weighted geometric mean, "level" = weighted arithmetic mean

HOW RECIPES ARE SCORED (perfect foresight on fundamentals)
  Every formula receives the firm's REALIZED year-t+5 FCF / EBITDA / NOPAT, so cash-flow
  forecasting error is removed and only the terminal-value formula is graded. Multiples, g and
  discount rates use only information available at t.
  Truth = the firm's market enterprise value 5 years later (mid-year after fiscal year t+5).
  e = ln(predicted / truth). Score = median |e| (lower is better).
  FALLBACK: if a leaf is undefined for a firm (e.g. Gordon with negative FCF), the FF12 exit is
  used for that firm; for a blend, if ANY part is undefined the whole blend falls back to the
  FF12 exit. Firms where the FF12 exit is undefined (EBITDA_(t+5) <= 0) are not scored, so every
  recipe is scored on the same {baselines()['n_eval']:,} firm-windows (US non-financials, market
  cap >= $100M at the valuation date, one sample period).
"""


def _bench_text(show_unconditional: bool) -> str:
    b = baselines()
    s = b["single"]
    lines = ["  Single methods (score = median |e|, bias = median e, hit = share with |e| < ln 1.25,",
             "  fb = share using the FF12 fallback):"]
    for k in sorted(s, key=lambda k: s[k]["median_abs"]):
        lines.append(f"    {k:20s} score {s[k]['median_abs']:.3f}  bias {s[k]['bias']:+.3f}  "
                     f"hit {s[k]['hit_rate_eval']:.1%}  fb {s[k]['fallback_share']:.1%}  "
                     f"= {R.leaf_text(R.validate(P3.SINGLE_METHODS[k]))}")
    if show_unconditional:
        u = b["unconditional"]["top3"][0]
        lines.append(f"  Best recipe WITHOUT any split (exhaustive search over every single leaf and every")
        lines.append(f"  2-part blend): score {u['explore']['median_abs']:.3f}  bias {u['explore']['bias']:+.3f}  "
                     f"= {u['compact']}")
        lines.append("  A recipe with splits is only interesting if it beats this.")
    g = b["gbm"]
    lines.append("  Black-box ceilings (gradient-boosted trees, out-of-fold; not interpretable):")
    lines.append(f"    GBM adjusting the FF12 exit from the traits only:            score {g['traits']['median_abs']:.3f}")
    lines.append(f"    GBM also given each method's log ratio to the FF12 exit:     score {g['traits+methods']['median_abs']:.3f}")
    d = b["diagnostics"]
    names = P3.DIAG_METHODS
    lines.append("\n  By FF12 industry: median |e| / bias for " + ", ".join(names))
    for f, v in sorted(d["by_ff12"].items(), key=lambda kv: -kv[1]["n"]):
        cells = "  ".join(f"{v[k][0]:.2f}/{v[k][1]:+.2f}" for k in names)
        lines.append(f"    {f:6s} n={v['n']:4d}  {cells}")
    lines.append("\n  By tercile of each trait (scored firms): median |e| for " + ", ".join(names))
    for c, v in d["by_tercile"].items():
        cuts = ", ".join(f"{x:g}" for x in v["cuts"])
        cells = " | ".join(f"{bk} " + " ".join(f"{v[bk][k]:.2f}" for k in names) for bk in ("low", "mid", "high"))
        lines.append(f"    {c:19s} cuts [{cuts}]  {cells}")
    return "\n".join(lines)


def _ff12_line(s: dict) -> str:
    return ", ".join(f"{k} {v['median_abs']:.2f}" for k, v in sorted(s["by_ff12"].items(), key=lambda kv: -kv[1]["n"]))


def proposer_prompt(run: Run, g: int) -> str:
    k = run.config["proposals_per_generation"]
    arch = run.archive()
    graded = sorted([a for a in arch if a["status"] == "graded"], key=lambda a: a["explore"]["median_abs"])
    lines = [f"  [{a['id']}] score {a['explore']['median_abs']:.3f} | bias {a['explore']['bias']:+.3f} | "
             f"fallback {a['explore']['fallback_share']:.1%} | share of firms per leaf "
             f"{'/'.join(f'{x:.0%}' for x in a['explore']['leaf_share'])}\n      {a['compact']}\n"
             f"      by FF12: {_ff12_line(a['explore'])}\n      mechanism: {a['mechanism']}" for a in graded]
    failed = [f"  [{a['id']}] {a['status']}: {a.get('reason', '')[:240]}" for a in arch if a["status"] != "graded"][-15:]
    critic_note = ("An independent referee, who sees your mechanism but no scores, will reject proposals without a\n"
                   "specific economic reason, near-copies of earlier recipes (e.g. one threshold moved slightly),\n"
                   "or mechanisms that appeal to particular time periods, macro events or interest-rate paths.\n"
                   if run.config.get("critic", True) else "")
    return f"""You are a valuation researcher. A DCF's terminal value is usually computed with either the
Gordon growth formula or an exit multiple, and practitioners disagree about which to use when.
Your job is to discover short, interpretable recipes that say WHICH terminal-value method (and
which parameters) to use FOR WHICH KIND OF FIRM, so the terminal value lands as close as possible
to what the firm turns out to be worth.

TASK
Propose exactly {k} NEW recipes (generation {g} of {run.config['generations']}). Recipes are scored on one
sample. The best recipes will later be tested ONCE on other samples you will never see, so prefer
recipes with a clear economic reason that should hold in any sample over fragile tweaks that fit
noise. A practitioner should be able to read your recipe and apply it by hand. A split earns its
place only if the firms it separates genuinely call for different methods.

{dsl_text()}
BENCHMARKS (same firm-windows, same score)
{_bench_text(run.config.get("show_unconditional", True))}

ARCHIVE: your earlier graded recipes ({len(graded)} graded)
{chr(10).join(lines) if lines else "  (none yet)"}

FAILED OR REJECTED ATTEMPTS (most recent 15)
{chr(10).join(failed) if failed else "  (none)"}

Each proposal needs:
  - "name": a short name
  - "mechanism": the economic reason the chosen method fits the firms on each branch (2-3 sentences)
  - "prediction": a falsifiable expectation in words, e.g. "beats the best recipe without splits,
    mainly through lower error in industry X"
  - "recipe": the recipe tree
Do not quote scores or recipe ids in "mechanism" or "prediction" (the referee must stay blind).
{critic_note}
Do not use any knowledge of specific firms or of what markets did in particular years: the recipe
sees only the traits above. Reply with ONLY this JSON, no other text:
{{"proposals": [{{"name": "...", "mechanism": "...", "prediction": "...", "recipe": {{...}}}}]}}
"""


_SCORE_LIKE = re.compile(r"(?<![\w.])[01]\.\d{3,}(?![\w.])")


def _blind(text: str) -> str:
    """Mask score-like numbers (e.g. 0.415) so proposer text cannot leak scores to the critic."""
    return _SCORE_LIKE.sub("[number removed]", str(text))


def critic_prompt(run: Run, pending: list[dict]) -> str:
    tried = "\n".join(f"  [{a['id']}] {a['compact']}" for a in run.archive()
                      if a["status"] in ("graded", "rejected")) or "  (none)"
    props = "\n\n".join(f"  ({i}) {_blind(p['name'])}\n      recipe: {p['compact']}\n      mechanism: {_blind(p['mechanism'])}\n"
                        f"      prediction: {_blind(p['prediction'])}" for i, p in enumerate(pending))
    n = len(pending)
    return f"""You are an independent referee for a valuation research project. A proposer has submitted
recipes that choose a terminal-value method (Gordon growth, exit multiple, value driver or a blend)
depending on a firm's traits. You decide which may be tested. You do NOT see any results: judge
only the logic.

{dsl_text()}
Approve a proposal only if ALL hold:
  1. The mechanism is a specific, economically sensible reason why the chosen method (and
     parameters) should value the firms on each branch better.
  2. The recipe actually implements that mechanism (traits, directions, thresholds and leaves match it).
  3. It is not a trivial variant of a recipe already tried (listed below): moving one threshold
     or one weight slightly, or swapping one parameter, is trivial; a new split, a new economic
     idea or a different method on a branch for a stated reason is not.
  4. The prediction is falsifiable.
  5. The mechanism does not appeal to particular time periods, macro events or interest-rate
     paths; it must be a cross-sectional reason that would hold in any sample period.
Reject otherwise, with a one-sentence reason the proposer can learn from.

RECIPES ALREADY TRIED (no scores shown)
{tried}

PROPOSALS (indices 0 to {n - 1})
{props}

Give exactly one verdict for each index 0 to {n - 1}. Reply with ONLY this JSON, no other text:
{{"verdicts": [{{"index": 0, "verdict": "approve" or "reject", "reason": "..."}}]}}
"""


# ---------------------------------------------------------------- loop steps
def parse_json_reply(text: str) -> dict:
    s = text.strip()
    try:
        out = json.loads(s)
    except json.JSONDecodeError:
        if "```" in s:
            m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, flags=re.S)
            if m:
                s = m.group(1)
        i, j = s.find("{"), s.rfind("}")
        out = json.loads(s[i:j + 1])
    if not isinstance(out, dict):
        raise ValueError("reply is not a JSON object")
    return out


def register_proposals(run: Run, reply: dict, g: int) -> tuple[list[dict], list[dict]]:
    """Validate and de-duplicate a proposer reply. Returns (records to archive now, pending for
    the critic). Nothing is written here."""
    known = {a["hash"] for a in run.archive() if a.get("hash")}
    props = reply.get("proposals")
    if not isinstance(props, list):
        raise ReplyError("'proposals' must be a list")
    k = run.config["proposals_per_generation"]
    now = datetime.now().isoformat(timespec="seconds")
    archive_now, pending = [], []
    for i, p in enumerate(props):
        rid = f"g{g:02d}-{i + 1:02d}"
        if not isinstance(p, dict):
            archive_now.append({"id": rid, "generation": g, "time": now, "status": "invalid",
                                "reason": "proposal is not a JSON object", "raw": p})
            continue
        rec = {"id": rid, "generation": g, "proposer": "claude-code-subagent", "time": now,
               "name": str(p.get("name") or ""), "mechanism": str(p.get("mechanism") or ""),
               "prediction": str(p.get("prediction") or ""), "raw": p.get("recipe")}
        if i >= k:
            archive_now.append({**rec, "status": "over_budget", "reason": f"more than {k} proposals"})
            continue
        try:
            tree = R.validate(p.get("recipe"))
        except R.RecipeError as e:
            archive_now.append({**rec, "status": "invalid", "reason": str(e)})
            continue
        h = R.recipe_hash(tree)
        rec.update(hash=h, recipe=tree, compact=R.compact(tree), depth=R.depth(tree))
        if h in known:
            archive_now.append({**rec, "status": "duplicate", "reason": "identical to an archived recipe"})
            continue
        known.add(h)
        pending.append(rec)
    return archive_now, pending


def check_verdicts(reply: dict | None, n: int) -> dict[int, dict]:
    """Exactly one verdict per index 0..n-1, each approve or reject; otherwise ReplyError."""
    if reply is None:
        return {i: {"verdict": "approve", "reason": "(no critic in this condition)"} for i in range(n)}
    vs = reply.get("verdicts")
    if not isinstance(vs, list):
        raise ReplyError("'verdicts' must be a list")
    out = {}
    for v in vs:
        if not isinstance(v, dict):
            raise ReplyError("each verdict must be an object")
        try:
            i = int(v.get("index"))
        except (TypeError, ValueError):
            raise ReplyError(f"bad index {v.get('index')!r}") from None
        word = str(v.get("verdict") or "").strip().lower()
        if word.startswith("approv"):
            word = "approve"
        elif word.startswith("reject"):
            word = "reject"
        else:
            raise ReplyError(f"verdict for index {i} is neither approve nor reject: {v.get('verdict')!r}")
        if i in out:
            raise ReplyError(f"two verdicts for index {i}")
        out[i] = {"verdict": word, "reason": str(v.get("reason") or "")}
    if set(out) != set(range(n)):
        raise ReplyError(f"verdict indices {sorted(out)} do not match proposals 0..{n - 1}")
    return out


def grade_verdicts(pending: list[dict], verdicts: dict[int, dict]) -> list[dict]:
    out = []
    for i, rec in enumerate(pending):
        v = verdicts[i]
        rec = {**rec, "critic": v["verdict"], "critic_reason": v["reason"]}
        if v["verdict"] != "approve":
            rec.update(status="rejected", reason="critic: " + v["reason"])
        else:
            rec.update(status="graded", explore=grade_explore(rec["recipe"]))
        out.append(rec)
    return out


def select(records: list[dict], k: int = 3) -> list[dict]:
    """Finalists: the k best graded recipes with distinct behaviour fingerprints (ties: earlier id)."""
    graded = {r["id"]: r for r in records if r["status"] == "graded"}
    ordered = sorted(graded.values(), key=lambda r: (r["explore"]["median_abs"], r["id"]))
    return P3.top_distinct(ordered, k, key=lambda r: 0)


def funnel(arch: list[dict]) -> dict:
    last = {}
    for a in arch:  # one status per id (the latest)
        last[a["id"]] = a["status"]
    keys = ("graded", "rejected", "invalid", "duplicate", "over_budget")
    return {"proposed": len(last), **{k: sum(s == k for s in last.values()) for k in keys}}
