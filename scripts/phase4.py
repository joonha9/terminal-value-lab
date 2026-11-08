"""Phase 4: open validation once, then test once (protocol v1.1 sections 6 and 8;
docs/phase4_procedure.md).

    python3 -P scripts/phase4.py validation     # opens validation (once)
    #   then record the printed SHA-256s in docs/phase4_pins.json ("validation") and commit
    python3 -P scripts/phase4.py test           # opens test (once)
    python3 -P scripts/phase4.py validation --dry-run   # exploration stands in; nothing unsealed
    python3 -P scripts/phase4.py test --dry-run

Real runs refuse to start unless:
- the git working tree is clean (no uncommitted or untracked files outside ignored paths);
- results/phase3/finalists.json and the data files match the SHA-256s committed in
  docs/phase4_pins.json, and the finalists re-grade on exploration to their frozen scores;
- the split has never been unsealed (results/unseal_log.jsonl), unless --acknowledge-prior-unseal
  is given, in which case the earlier entries are copied into the output;
- for test: validation's outputs match the SHA-256s committed after validation, the chosen
  recipes are finalists and equal validation's choices, and code and package versions equal
  those recorded at validation.
Everything that does not need sealed data (checks, GBM fits) runs before anything is unsealed.
Dry runs write to results/phase4_dryrun/ and never unseal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tvlab import panel as P    # noqa: E402
from tvlab import phase3 as P3  # noqa: E402
from tvlab import phase4 as Q   # noqa: E402
from tvlab import recipes as R  # noqa: E402

FINALISTS = ROOT / "results" / "phase3" / "finalists.json"
PINS = ROOT / "docs" / "phase4_pins.json"
CODE_FILES = sorted([*(ROOT / "tvlab").glob("*.py"), ROOT / "scripts" / "phase4.py", ROOT / "scripts" / "phase3_finalists.py"])


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git_state() -> dict:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
    st = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True)
    return {"head": head.stdout.strip(), "dirty": bool(st.stdout.strip())}


def environment() -> dict:
    import pandas
    import sklearn
    return {"code_sha256": {str(p.relative_to(ROOT)): sha(p) for p in CODE_FILES},
            "data_sha256": {f: sha(P.PROC / f) for f in Q.DATA_FILES},
            "packages": {"python": sys.version.split()[0], "numpy": np.__version__,
                         "pandas": pandas.__version__, "sklearn": sklearn.__version__}}


def write_all(out: Path, objs: dict[str, dict], last: str) -> dict[str, str]:
    """Write JSON files via temporary names, renaming `last` at the end (its existence marks
    the stage as done)."""
    texts = {n: json.dumps(o, indent=1, sort_keys=True, default=float) + "\n" for n, o in objs.items()}
    for n, t in texts.items():
        (out / (n + ".tmp")).write_text(t)
    for n in sorted(texts, key=lambda n: n == last):
        (out / (n + ".tmp")).replace(out / n)
    return {n: hashlib.sha256(t.encode()).hexdigest() for n, t in texts.items()}


def check_finalists(fin: dict, T_e) -> dict[str, list[dict]]:
    """Every finalist validates, keeps its hash, and re-grades on exploration to its frozen
    score (and fingerprint where stored). Fails before anything is unsealed."""
    out = {k: fin[k] for k in ("agent", "random", "unconditional")}
    for group in out.values():
        for f in group:
            tree = R.validate(f["recipe"])
            assert R.recipe_hash(tree) == f["hash"], f["id"]
            s = P3.grade(tree, T_e, detail=False)
            assert abs(s["median_abs"] - f["explore_median_abs"]) < 1e-12, (f["id"], s["median_abs"])
            if "fingerprint" in f:
                assert s["fingerprint"] == f["fingerprint"], f["id"]
    return out


def choose(group: list[dict], scores: dict[str, dict]) -> dict:
    """Lowest validation median |e|; ties go to the earlier entry of finalists.json (run, then rank)."""
    order = {f["id"]: i for i, f in enumerate(group)}
    return min(group, key=lambda f: (scores[f["id"]]["median_abs"], order[f["id"]]))


def fit_gbms(T_e) -> dict:
    out = {}
    for name, wm in (("traits_only", False), ("traits_methods", True)):
        model = P3.gbm_fit(T_e, wm)
        assert model.n_iter_ == P3.GBM_PARAMS["max_iter"], "GBM stopped early"
        out[name] = (model, wm)
    return out


def score_gbms(gbms: dict, T) -> dict:
    out = {}
    for name, (model, wm) in gbms.items():
        s = P3.score_pred(P3.gbm_predict(model, T, wm), np.zeros(len(T), dtype=bool), T, detail=False)
        s.pop("fingerprint", None)
        out[name] = s
    return out


def stage_validation(a, split: str, unseal: bool, out: Path, prior: list) -> None:
    fin_text = FINALISTS.read_bytes()
    fin = json.loads(fin_text)
    T_e = Q.m_table("exploration")
    cand = check_finalists(fin, T_e)
    gbms = fit_gbms(T_e)
    TD_e, _ = Q.d_table("exploration")
    env = environment()
    # ---------------- unseal: the only point where validation data are read
    T_v = Q.m_table(split, 5, unseal)
    TD_v, counts = Q.d_table(split, unseal)
    T3_v = Q.m_table(split, 3, unseal)
    scores = {g: {f["id"]: Q.score_recipe(f["recipe"], T_v) for f in fs} for g, fs in cand.items()}
    chosen = {g: choose(fs, scores[g]) for g, fs in cand.items()}
    best_single, pooled = Q.pooled_best_single([T_e, T_v])
    res = {
        "split": split, "finalists_sha256": hashlib.sha256(fin_text).hexdigest(), "git": git_state(),
        "environment": env, "prior_unseal_entries": prior,
        "finalist_scores": scores,
        "single_methods": {k: Q.score_recipe(t, T_v) for k, t in P3.SINGLE_METHODS.items()},
        "gbm": score_gbms(gbms, T_v),
        "best_single_pooled_exploration_validation": {"method": best_single, "scores": pooled},
        "chosen": {g: {"id": c["id"], "hash": c["hash"], "compact": c["compact"],
                       "validation_median_abs": scores[g][c["id"]]["median_abs"],
                       "explore_median_abs": c["explore_median_abs"]} for g, c in chosen.items()},
        "replication": Q.replication(T_v, TD_v, T3_v, counts),
        "robustness": Q.robustness(split, unseal, T_v, TD_v, set(TD_e["id"])),
        "d_deal_ids": sorted(set(TD_v["id"].astype(str))),  # for the overlap sensitivity at test
    }
    vtext = json.dumps(res, indent=1, sort_keys=True, default=float) + "\n"
    ch = {"finalists_sha256": res["finalists_sha256"], "validation_sha256": hashlib.sha256(vtext.encode()).hexdigest(),
          "best_single": {"method": best_single, "recipe": P3.SINGLE_METHODS[best_single]},
          **{g: {"id": c["id"], "hash": c["hash"], "recipe": c["recipe"], "compact": c["compact"]}
             for g, c in chosen.items()}}
    h = write_all(out, {"chosen.json": ch, "validation.json": res}, last="validation.json")
    assert h["validation.json"] == ch["validation_sha256"]
    print(f"validation.json sha256 {h['validation.json']}\nchosen.json     sha256 {h['chosen.json']}")
    for g, c in res["chosen"].items():
        print(f"  chosen {g:13s} {c['id']:12s} val {c['validation_median_abs']:.4f} (expl {c['explore_median_abs']:.4f})")
    print(f"  best single (expl+val pooled): {best_single} {pooled[best_single]:.4f}")
    for k, t in res["replication"]["tests"].items():
        print(f"  {k:4s} {t['stat']:+.3f} [{t['ci95'][0]:+.3f}, {t['ci95'][1]:+.3f}] p1={t['p_one_sided']:.4f} n={t['n']}")


def stage_test(a, split: str, unseal: bool, out: Path, prior: list, pins: dict | None) -> None:
    ch_p, v_p = out / "chosen.json", out / "validation.json"
    if pins is not None:  # real run: validation outputs must match the hashes committed after validation
        pv = pins.get("validation") or {}
        if pv.get("validation_sha256") != sha(v_p) or pv.get("chosen_sha256") != sha(ch_p):
            sys.exit("validation.json / chosen.json do not match docs/phase4_pins.json['validation']: commit them first")
    ch, val = json.loads(ch_p.read_text()), json.loads(v_p.read_text())
    fin = json.loads(FINALISTS.read_text())
    if ch["finalists_sha256"] != sha(FINALISTS) or val["finalists_sha256"] != sha(FINALISTS):
        sys.exit("finalists.json changed since validation")
    if ch["validation_sha256"] != sha(v_p):
        sys.exit("validation.json changed since it was written")
    env = environment()
    if pins is not None:
        for k in ("code_sha256", "data_sha256", "packages"):
            if env[k] != val["environment"][k]:
                sys.exit(f"{k} differs from validation: {env[k]} vs {val['environment'][k]}")
    T_e = Q.m_table("exploration")
    cand = check_finalists(fin, T_e)
    trees = {}
    for g in ("agent", "random", "unconditional"):
        f = {x["id"]: x for x in cand[g]}.get(ch[g]["id"])
        if f is None or f["hash"] != ch[g]["hash"] or val["chosen"][g]["id"] != ch[g]["id"] \
                or R.recipe_hash(R.validate(ch[g]["recipe"])) != f["hash"]:
            sys.exit(f"chosen {g} recipe is not the finalist chosen at validation")
        trees[g] = R.validate(f["recipe"])
    best = val["best_single_pooled_exploration_validation"]["method"]
    if ch["best_single"]["method"] != best or ch["best_single"]["recipe"] != P3.SINGLE_METHODS[best]:
        sys.exit("best single method differs from validation")
    single = P3.SINGLE_METHODS[best]
    gbms = fit_gbms(T_e)
    TD_e, _ = Q.d_table("exploration")
    earlier_d = set(TD_e["id"].astype(str)) | set(val["d_deal_ids"])
    # ---------------- unseal: the only point where test data are read
    T_t = Q.m_table(split, 5, unseal)
    TD_t, counts = Q.d_table(split, unseal)
    T3_t = Q.m_table(split, 3, unseal)
    rep = Q.replication(T_t, TD_t, T3_t, counts)
    tests = dict(rep["tests"])
    tests["T8a"] = Q.t8(trees["agent"], single, T_t, "best single " + best)
    tests["T8b"] = Q.t8(trees["agent"], trees["random"], T_t, "chosen random " + ch["random"]["id"])
    tests["T8c"] = Q.t8(trees["agent"], trees["unconditional"], T_t, "chosen unconditional " + ch["unconditional"]["id"])
    hl = Q.holm({k: tests[k]["p_one_sided"] for k in Q.HOLM_FAMILY})
    depth = R.depth(trees["agent"])
    h5 = hl["T8a"]["reject"] and hl["T8b"]["reject"]
    gb = score_gbms(gbms, T_t)
    ff12 = Q.score_recipe(P3.SINGLE_METHODS["E_ff12_med"], T_t)["median_abs"]
    rec = {g: Q.score_recipe(t, T_t) for g, t in trees.items()}
    res = {
        "split": split, "git": git_state(), "environment": env, "prior_unseal_entries": prior,
        "chosen_sha256": sha(ch_p), "validation_sha256": sha(v_p),
        "tests": tests, "holm": hl,
        "decisions": {"H5_supported": h5, "conditional_gain": h5 and hl["T8c"]["reject"] and depth > 0,
                      "agent_depth": depth,
                      "note": "depth 0 => reported as no conditional gain" if depth == 0 else ""},
        "robustness_h3": rep["robustness_h3"], "describe": rep["describe"],
        "robustness": Q.robustness(split, unseal, T_t, TD_t, earlier_d),
        "chosen_on_test": rec, "gbm": gb, "ff12_median_abs": ff12,
        "share_of_gbm_gain": {g: {k: Q.gain_share(ff12, rec[g]["median_abs"], v["median_abs"]) for k, v in gb.items()}
                              for g in trees},
        "chosen_vs_truth_D": {g: Q.score_recipe(t, TD_t) for g, t in trees.items()},
        "chosen_common_and_itt": {g: Q.common_and_itt(t, single, T_t) for g, t in trees.items()},
        "damodaran_leaf_share": {g: Q.dam_leaf_share(t, T_t) for g, t in trees.items()},
        "finalists_on_exploration": {g: {f["id"]: Q.score_recipe(f["recipe"], T_e) for f in fs} for g, fs in cand.items()},
        "finalists_on_test": {g: {f["id"]: Q.score_recipe(f["recipe"], T_t) for f in fs} for g, fs in cand.items()},
        "funnels": fin["funnels"],
    }
    h = write_all(out, {"test.json": res}, last="test.json")
    print(f"test.json sha256 {h['test.json']}")
    for k in Q.HOLM_FAMILY:
        t = tests[k]
        print(f"  {k:4s} {t['stat']:+.3f} [{t['ci95'][0]:+.3f}, {t['ci95'][1]:+.3f}] p1={t['p_one_sided']:.4f} "
              f"holm={hl[k]['p_holm']:.4f} {'REJECT' if hl[k]['reject'] else ''}")
    print("  decisions:", res["decisions"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["validation", "test"])
    ap.add_argument("--dry-run", action="store_true", help="exploration stands in for the sealed split")
    ap.add_argument("--acknowledge-prior-unseal", action="store_true",
                    help="proceed although the split was unsealed before (e.g. after a crash); disclosed in the output")
    a = ap.parse_args()
    if a.dry_run:
        split, unseal, out, pins = "exploration", False, ROOT / "results" / "phase4_dryrun", None
        out.mkdir(parents=True, exist_ok=True)
        if a.stage == "validation":
            for f in ("validation.json", "chosen.json", "test.json"):
                (out / f).unlink(missing_ok=True)
        prior = []
    else:
        split, unseal, out = a.stage, True, ROOT / "results" / "phase4"
        out.mkdir(parents=True, exist_ok=True)
        if git_state()["dirty"]:
            sys.exit("git working tree is not clean (uncommitted or untracked files): commit first")
        pins = json.loads(PINS.read_text())
        if pins["finalists_sha256"] != sha(FINALISTS):
            sys.exit("results/phase3/finalists.json does not match docs/phase4_pins.json")
        for f, h in pins["data_sha256"].items():
            if sha(P.PROC / f) != h:
                sys.exit(f"data/processed/{f} does not match docs/phase4_pins.json")
        if (out / f"{a.stage}.json").exists():
            sys.exit(f"REFUSE: {a.stage} was already opened ({out / (a.stage + '.json')})")
        if a.stage == "test" and not (out / "validation.json").exists():
            sys.exit("validation has not been opened yet")
        prior = Q.prior_unseals(split)
        if prior and not a.acknowledge_prior_unseal:
            sys.exit(f"{split} was unsealed before ({len(prior)} log entries); rerun with "
                     "--acknowledge-prior-unseal to proceed and disclose it")
    if a.stage == "validation":
        stage_validation(a, split, unseal, out, prior)
    else:
        stage_test(a, split, unseal, out, prior, pins)


if __name__ == "__main__":
    main()
