# Phase 3 design: TV recipes, benchmarks and agent search

Drafted 2026-11-07 and revised the same day after two independent reviews (code and design;
see `docs/errors_and_fixes.md` §I). **Status: frozen 2026-11-07 together with protocol v1.1
(tag `protocol-v1.1`), before the first agent run.** The author's decisions on the four open
items are recorded in §8.

This document fixes the implementation details that protocol v1 §7 leaves open. Items labelled
**[addition]** or **[clarification]** went into protocol v1.1. The exception is the
traits + methods GBM, which is reported only.

Everything here uses exploration windows only (t = 2015–16). Validation and test stay sealed
in code: `tvlab.phase3.build_table` raises `PermissionError` for them unless `unseal=True`, and
every unsealed build is appended to `results/unseal_log.jsonl`.

## 0. What Phase 3 asks

Practitioners pick a terminal-value method by habit: Gordon growth or an exit multiple, with a
"reasonable" g or the industry multiple. Q3 asks whether an AI agent can write short,
interpretable rules ("recipes") that say which method and parameters to use for which kind of
firm, and whether those rules beat:
- (a) the best single method;
- (b) random search with the same budget.

It also asks how much of a black-box model's gain the rules capture.

The loop follows SignalLab (Liu, Liu, Liu & Mei 2026), as in Comps Range Lab:
- a proposer writes a recipe with a mechanism and a falsifiable prediction;
- a blind critic approves or rejects it on logic alone;
- a deterministic grader scores it;
- every attempt is archived.

## 1. File map and reproduction

| File | Role |
|---|---|
| `tvlab/recipes.py` | Recipe language: validator (schema and semantic checks), canonical form and hash, evaluation (`predict`, with per-row leaf index), text rendering, random-recipe generator |
| `tvlab/phase3.py` | Grading table per split (truth, traits, percentile ranks, every leaf's prediction); scoring and behaviour fingerprint; firm-clustered bootstrap; GBM ceiling; unconditional grid; diagnostics shown to agents; sealing and unseal log |
| `tvlab/agents.py` | Run state, proposer and critic prompts, proposal registration, verdict checks, atomic stage commits, finalist selection |
| `scripts/phase3_baselines.py` | Benchmarks on exploration → `results/phase3/baselines_explore.json`, `random_pool.jsonl` |
| `scripts/agent_step.py` | Creates runs and advances each run one stage; logs every reply |
| `tests/test_phase3.py` | 32 tests: validator, canonicalisation, routing and fallback, leaf values equal Phase 1 methods, sealing, verdict checks, idempotent stages, distinct finalists |
| `config/tv-text-only.md` | The tool-less subagent definition used for proposers and critics. The active copy is `../.claude/agents/tv-text-only.md`, and the two must be identical (checked by a test) |

Results live in `results/phase3/`. Like all data, they are git-ignored because they derive from
FactSet.

**Reproduce:**
```
python3 -P scripts/phase3_baselines.py      # ~25 s on 8 cores
python3 -P -m pytest tests -q
```
Environment: Python 3.13.2, pandas 2.2.3, numpy 2.4.6, scikit-learn 1.9.1, Claude Code 2.1.288.

## 2. What is graded

### 2.1 Truth and windows

- **Truth M** only, because T8 is defined on M: market EV at June 30 of t+6.
- **Graded windows:** the same 3,948 exploration windows as Phase 1. The firm passes
  `quality_ok` at t, did not exit by t+5, passes `quality_ok` at t+5, and has EV_t+5 > 0.
- **Why not truth D in the search:** T8 is on M, and the acquired sample is small (815
  windows; about 210 where every method is defined). Two truths would need a weighting rule the
  protocol does not give. The chosen recipe is reported against truth D at validation and test
  as a description, not a test.

### 2.2 Evaluation set and fallback [clarification]

- **Problem:** each method is undefined for some firms.
  - Gordon needs FCF_t+5 > 0 and r − g ≥ 1 pp.
  - Exit multiples need EBITDA_t+5 > 0.
  - The own multiple also needs EBITDA_t > 0.

  The protocol's metric is "median |e| on the common sample (all compared methods defined)".
  For recipes that mix methods by firm, "all compared methods defined" has no single meaning.
- **Rule:**
  1. **Evaluation set** = the 3,266 graded windows (83%) where the FF12 exit is defined. Every
     recipe, benchmark and random rule is scored on exactly these rows.
  2. If a recipe's leaf is undefined for a window, that window uses the **FF12 exit**. For a
     blend, if *any* part is undefined, the whole blend falls back; there is no renormalisation
     over the defined parts. The prompt states this.
  3. The fallback share is recorded for every recipe and shown to the proposer.
- **Excluded:** 682 graded windows (17%), 99.9% of them because EBITDA_t+5 ≤ 0.
- **Why the FF12 exit:** it is defined wherever any EBITDA-based method is; it is the simplest
  practitioner default; and it is the base the protocol's GBM adjusts.
- **Alternatives considered:**
  - *Common sample per recipe:* it changes with the recipe, so recipes would not be comparable.
  - *Intention-to-treat miss:* it has no value for median |e|.
  - *Fixed penalty:* arbitrary.
- **Side effect, disclosed:** definedness depends on outcome-year numbers (FCF_t+5 sign,
  ROIC_t+5 > g). The fallback is therefore an implicit split on t+5 information, which the
  trait language otherwise forbids.
  - Checked on exploration: it is not exploitable. A 0.95 × own + 0.05 × value-driver blend,
    which sends 34% of firms to the fallback, scores 0.4147 against own's 0.4149.
  - All single-method benchmarks get the same rule.
- **Also reported at Phase 4:** the chosen recipes on the protocol's own metrics (common sample
  with the compared method; ITT hit rate over all graded windows).

### 2.3 Score

- e = ln(predicted / truth). **Score = median |e| on the evaluation set**; lower is better.
- Also recorded:
  - bias (median e);
  - `hit_rate_eval` (share with |e| < ln 1.25 on the evaluation set; *not* the protocol's ITT
    hit rate);
  - fallback share;
  - per-FF12 median |e| and bias;
  - share of evaluation firms reaching each leaf;
  - a **behaviour fingerprint**: a hash of the rounded log predictions on the evaluation set,
    so recipes that predict identically are recognised as one.
- **No cross-validation inside exploration.** A recipe has no fitted parameters, so its
  exploration score is a measurement, not an in-sample fit. Overfitting enters through
  selection among many recipes, and validation handles that.

## 3. Recipe language (`tvlab/recipes.py`)

### 3.1 Shape

- A decision tree with **at most 3 levels of splits**, so at most 8 leaves. That matches the
  protocol's "≤ 3 levels".
- A split is `{"if": [clause, clause?], "then": node, "else": node}`. Its clauses are joined
  with AND, and `then` ≠ `else`.
- **A missing trait makes a clause false,** so the window goes to "else".

### 3.2 Clauses: traits at t only

| Trait | Definition |
|---|---|
| log_sales, log_assets | natural log, USD millions |
| ebitda_margin, ebit_margin | / sales |
| roic | EBIT × (1 − 25%) / (equity + debt − cash) |
| net_debt_to_ebitda | missing when EBITDA ≤ 0 |
| debt_to_assets | total debt / total assets |
| rnd_intensity | R&D / sales; 0 when none is reported (about half of firms) |
| capex_intensity | capex / sales |
| wacc_minus_g | WACC_t − 2.5% |

- **Thresholds** are either a within-year **percentile** (an integer 5–95) or a **raw value**.
- **Percentiles are point-in-time:** computed over the clean universe at t
  (`in_universe & quality_ok`), not over the graded windows, so a rank does not depend on
  survival to t+5.
  - Ties take the average rank. All zero-R&D firms share percentile ≈ 25, so a
    `below_pct` < 25 selects nobody; the prompt says so.
- **Why both kinds:** percentiles transfer across years whose levels drift. Raw values carry
  economic meaning: the r − g convexity behind H2 is about the absolute spread, and "net
  debt > 3× EBITDA" is how practitioners talk.
- **Categorical and flags:** FF12 membership (a non-empty proper subset), `fcf_positive` and
  `ebitda_positive` at t.
- **Sales growth is excluded** (protocol §7; errors log E2).
- **Never shown to recipes:** names, tickers, dates, and the firm's market value or price. The
  own multiple enters only as a leaf.

### 3.3 Leaves

| Leaf | Formula | Parameters |
|---|---|---|
| `exit` | multiple at t × EBITDA_t+5 | `ff12`, `damind` (Damodaran industry median in our panel), `own`, `dam_t` (Damodaran published), `dam_5yavg` |
| `gordon` | CF_t+5 (1+g) / (r − g) | CF: `fcf`, `fcf_3yavg` (t+3..t+5), `fcf_ex_sbc`; g ∈ {0, 0.5, …, 4%}; r: `wacc`, `rf_plus_5` |
| `value_driver` | NOPAT_t+5 (1+g)(1 − g/RONIC) / (r − g) | RONIC: `roic` (year t+5) or `r`; same g and r grids |
| `blend` | weighted geometric (`log`) or arithmetic (`level`) mean | 2–3 different non-blend leaves; weights in 0.05 steps summing to 1 |

- **g grid wider than §4.** Protocol §4 fixes the named methods at g ∈ {2, 2.5, 3%}; a recipe
  may choose 0–4%. §7 allows "method + parameters", and the §4 methods themselves are unchanged.
- **Level levers exist (corrected after review).** A recipe cannot multiply a method by a free
  constant, but g and blend weights move levels strongly. Gordon (3-yr FCF, Treasury + 5%) has
  bias −0.43 at g = 0% and +0.39 at g = 4%, and a 20% Gordon weight shifts a blend's level.
  - Risk: an LLM that knows the post-2021 rate path could choose levels for non-cross-sectional
    reasons.
  - Mitigations: the critic rejects mechanisms that appeal to time periods, macro events or
    rate paths (§5.3), and finalists' exploration, validation and test biases are reported side
    by side.
- **Damodaran definition break.** Damodaran's published multiples change definition between
  the January 2017 and January 2018 releases (errors log B5). That is exactly the
  exploration/validation boundary, so `dam_t` and `dam_5yavg` leaves face a regime change, and
  validation-year `dam_5yavg` averages across the break. Finalists' use of these leaves is
  reported.

### 3.4 Validation and identity

- `validate()` checks the schema strictly and lists every violation in one message; the
  proposer sees it next generation. Any malformed type raises `RecipeError`, never a crash.
- **Semantic checks:** no `then` = `else`, no repeated clause, no blend parts that are equal
  after canonicalisation.
- **Canonical form:**
  - g, weights and raw thresholds are rounded or cast to float, and −0.0 becomes 0;
  - AND-clauses, FF12 lists and blend parts are sorted.

  Its SHA-1 is the recipe's identity. Exact duplicates are archived as "duplicate" without
  grading.
- **Behaviour fingerprint** (§2.3): finalists must have distinct fingerprints. Near-duplicates
  that differ in behaviour are the critic's job.

## 4. Benchmarks (`results/phase3/baselines_explore.json`)

### 4.1 Results (exploration evaluation set, n = 3,266)

| Benchmark | Score (median abs e) | Bias |
|---|---|---|
| **Best recipe without a split [addition]**: 0.8 × own exit + 0.2 × Gordon(3-yr FCF, g 4%, Treasury + 5%), levels | **0.368** | +0.057 |
| Best 2-part blend of exits only: 0.6 × own + 0.4 × Damodaran-industry, logs | 0.390 | |
| **Best single §4 method: own EV/EBITDA exit** | **0.415** | −0.097 |
| Damodaran 5-yr / Damodaran-industry median / FF12 exit | 0.441 / 0.442 / 0.459 | |
| Damodaran exit at t | 0.460 | −0.213 |
| 50/50 blends, Gordon + FF12 (log / level) | 0.466 / 0.471 | |
| Best Gordon (3-yr avg FCF, g 2.5%, WACC) / standard Gordon (FCF, g 2.5%, WACC) | 0.525 / 0.556 | |
| Value driver (RONIC = ROIC / = r) | 0.633 / 0.653 | |
| Random recipes: median of 1,000 | 0.486 | |
| Random: best of 30 (mean of 10,000 resampled searches; 5–95%) | 0.414 (0.392–0.435) | |
| Random runs 1–5: best of each block of 30 | 0.419, 0.392, 0.379, 0.409, 0.415 | |
| Random: best of all 1,000 | 0.379 | |
| **GBM ceiling, traits only (protocol)** | **0.406** | +0.004 |
| **GBM, traits + methods [addition]** | **0.312** | 0.000 |

What these numbers say before any agent runs:
1. **Blending already wins.** Shrinking the firm's own multiple toward a cash-flow value beats
   the own multiple by 0.047 in median |e| (firm-clustered 95% CI 0.029 to 0.062). It also
   beats every random recipe of 1,000 and the traits-only GBM. This is a Phase 3 exploration
   finding in its own right.
2. **The real test of conditional rules is therefore the unconditional blend (0.368), not the
   best single method.** Against the traits-only GBM, the unconditional blend already
   "captures" 170% of the gain, so that ratio is uninformative. Against the traits + methods
   GBM it captures 62%. That leaves room, 0.368 → 0.312, for conditional rules.
3. Only 1.6% of random recipes beat the own multiple.

### 4.2 Single methods

- Every protocol §4 candidate, written as a one-leaf recipe with the same fallback
  (`phase3.SINGLE_METHODS`). These 15 are the H5(a) candidate set:
  - Gordon FCF at g 2 / 2.5 / 3%;
  - Gordon 3-yr FCF at g 2.5%;
  - Gordon FCF ex-SBC at g 2.5%;
  - Gordon FCF at g 2.5% with Treasury + 5%;
  - value driver with RONIC = ROIC, and with RONIC = r;
  - FF12, Damodaran-industry, own, Damodaran-at-t and Damodaran-5-yr exits;
  - 50/50 level blend and 50/50 log blend.

  Look-ahead references are never candidates.
- **For H5(a)/T8:** the best single method is the one with the lowest median |e| on the pooled
  exploration + validation evaluation set (protocol §5 H5). Ties go to the earlier method in the
  list above.

### 4.3 Random search

- **Pool:** 1,000 recipes from the whole language with no economic knowledge (seed 2026;
  `recipes.random_recipe`).
  - Depth 0/1/2/3 with weights 1 / 3 / 3.5 / 2.5. Each subtree stops early with probability 0.3.
  - Leaves are exit / Gordon / value driver / blend with weights 4 / 3 / 1 / 2, and all
    parameters are uniform on their grids.
  - Clauses are trait / FF12 / flag with weights 7 / 2 / 1:
    - percentile thresholds are uniform 5–95;
    - raw thresholds are drawn at a uniform 5–95 percentile of the trait over the clean
      exploration universe;
    - FF12 sets have 1–10 industries.
- **Random run k** = pool rules 30(k−1)+1 … 30k, for k = 1..5. Each matches agent run k in
  budget and finalist rule.
- **The budget is generous to random.** All 30 random rules are graded, while invalid,
  duplicate or rejected agent proposals still use up the agent's 30.
- **Proposers never see random results.**
- The pool was regenerated twice before being frozen; see errors log §I.3. The final pool's
  SHA-1 is recorded.

### 4.4 GBM ceiling

- **Model:** scikit-learn `HistGradientBoostingRegressor`, absolute-error loss.
  Hyperparameters were fixed before the first fit and never tuned: 300 iterations, learning
  rate 0.05, 15 leaves, at least 40 per leaf, L2 1.0, random_state 0. FF12 is a native
  categorical feature, and early stopping is off.
- **Target:** ln(truth / FF12 exit); prediction = FF12 exit × exp(ŷ) (protocol §7).
- **Exploration:** 5-fold out of fold with GroupKFold by firm. **Validation and test:** fitted
  once on all exploration windows.
- **Traits only (protocol, primary):** recipe traits, flags and FF12.
- **Traits + methods [addition]:** also ln(method / FF12 exit) for the own,
  Damodaran-industry, Damodaran-at-t and Damodaran-5-yr exits, and Gordon FCF, Gordon 3-yr FCF
  and the value driver. Recipes use the same information through their leaves.
  - **When and why added:** after seeing that the traits-only GBM barely beats the own multiple
    (0.406 vs 0.415), during Phase 3 setup and before any agent run.
- **Share of gain captured** = (FF12 exit − rule) / (FF12 exit − GBM). It is reported for both
  GBMs and against the unconditional blend. Values above 100% are reported as "exceeds the
  ceiling", which means that ceiling is uninformative.

### 4.5 Best recipe without a split [addition]

- **Grid:** every single leaf (95) and every 2-part blend of different leaves, at weights
  0.05–0.95 in log and level space: 169,765 recipes in all. Each is scored exactly like a recipe
  (`phase3.unconditional_grid`).
- 3-part blends were left out for cost (about 24 million combinations). This is disclosed; a
  3-part blend could still beat the 2-part best.
- **Kept for Phase 4:** the top 3 with distinct fingerprints. They are chosen on validation
  exactly like the finalists. On exploration they are all "0.75–0.8 × own + 0.2–0.25 × Gordon
  3-yr FCF at g 3–4%, Treasury + 5%" (0.3683, 0.3684, 0.3688).
- **Shown to proposers** as "the best recipe without any split; a recipe with splits is only
  interesting if it beats this" (decided 2026-11-07).

## 5. Agent loop (`tvlab/agents.py`, `scripts/agent_step.py`)

### 5.1 Budget, roles, isolation

- **5 independent runs (a1–a5) × 5 generations × 6 proposals = 150 proposals.** Runs never
  see each other's archives.
- **Isolation (added after review).** Every proposer and critic call is a fresh subagent of
  type `tv-text-only` (`config/tv-text-only.md`, active copy in `../.claude/agents/`):
  - every file, shell, search, web, agent and MCP tool is disallowed, and CLAUDE.md is omitted;
  - the orchestrating session pastes the brief inline and saves the reply text as
    `proposals.txt` or `verdicts.txt`;
  - the subagent therefore cannot run the grader, read the random pool, other runs or the docs,
    or reach sealed data.
- **Isolation test (before run a1):** a `tv-text-only` agent is asked to list its tools, read a
  repo file and run a command. All three must fail, and the transcript is saved in
  `results/phase3/isolation_check.md`. This needs a Claude Code restart, because the agent
  folder did not exist at session start.
- **Session model:** Claude Opus 5.5 (`claude-opus-5-5`), recorded in each run's config. No paid
  API is used.
- **Records per run** (`config.json`): model, agent definition, creation time, selection rule,
  and a SHA-1 over the harness code and the benchmark file (`code_hash`).
- **Operating rules:**
  - No manual edits to prompts or replies.
  - A reply that cannot be parsed or applied is set aside (`*.rejected-N.txt`), logged in
    `replies.jsonl`, and the same brief is re-run. Every re-run is visible in the log.
  - A stage either completes fully (archive records and state written together) or changes
    nothing.

### 5.2 What the proposer sees

1. The task and the full recipe language, including the fallback and blend rule.
2. Single-method scores with bias, `hit_rate_eval` and fallback share.
3. The best recipe without a split.
4. Both GBM scores, labelled as non-interpretable ceilings.
5. Exploration diagnostics for 5 key methods: median |e| and bias by FF12, and median |e| by
   tercile of every trait. These are computed on the evaluation set, which is outcome-selected;
   that is acceptable in exploration.
6. Its own archive: every graded recipe with score, bias, fallback share, share of firms per
   leaf, per-FF12 score and mechanism.
7. Its 15 most recent failed attempts (invalid, duplicate, rejected or over budget), with
   reasons.

Each proposal gives a name, a mechanism (the economic reason, branch by branch), a falsifiable
prediction in words, and the recipe. The proposer is told:
- not to quote scores or ids in its text;
- not to use knowledge of specific firms or years.

Up to 6 proposals per generation are graded; any beyond that are archived as `over_budget`.

### 5.3 What the critic sees

- The language, the proposals (with score-like numbers masked), and the recipes already tried
  **without scores**.
- It approves only if all of these hold:
  1. the mechanism is specific and economically sensible;
  2. the recipe implements it;
  3. it is not a trivial variant of an earlier recipe;
  4. the prediction is falsifiable;
  5. the mechanism does not appeal to time periods, macro events or rate paths.
- It must return exactly one verdict per index 0..n−1. Anything else is set aside and the
  critic is re-run.

### 5.4 Leakage control

- No firm names, tickers or calendar years in any prompt; this is checked on the rendered
  prompts. The data are "one sample", and later tests are on "other samples".
- **Residual risks (disclosed):**
  - the WACC − g tercile cuts (about 4–5 pp) and the by-FF12 biases hint at the era;
  - an LLM may know broad market history from 2020 to 2025;
  - the predictions are falsifiable statements, but they are only archived, not scored.

### 5.5 Mechanics

```
python3 -P scripts/agent_step.py --new a1 a2 a3 a4 a5     # writes gen-1 proposer briefs
# orchestrator: for each brief, launch tv-text-only with the brief text; save reply to proposals.txt
python3 -P scripts/agent_step.py --runs a1 a2 a3 a4 a5    # validate, write critic briefs
# orchestrator: launch tv-text-only critics; save replies to verdicts.txt
python3 -P scripts/agent_step.py --runs a1 a2 a3 a4 a5    # grade, write next proposer briefs
# ... 5 generations
```

## 6. Selection and Phase 4 plan (fixed before the search)

### 6.1 Finalists

1. **Agent finalists:** per run, the 3 graded recipes with the lowest exploration median |e|
   and distinct fingerprints (ties: earlier id). That gives 15. If a run has fewer than 3
   distinct graded recipes, it contributes what it has.
2. **Random finalists:** the same rule per random run, giving 15 (stored in the benchmark
   file).
3. **Unconditional finalists:** the top 3 distinct of the grid (§4.5).

### 6.2 Validation (opened once)

- Score all finalists, all 15 single methods and both GBMs (fitted on exploration).
- Choose:
  - the one agent recipe, the one random recipe and the one unconditional recipe with the
    lowest validation median |e|;
  - the best single method on exploration + validation (§4.2).
- Ties go to the earlier id.

### 6.3 Test (opened once)

| Statistic | Difference in median abs e on the test evaluation set | Status |
|---|---|---|
| T8a | chosen agent recipe − best single method | protocol |
| T8b | chosen agent recipe − chosen random recipe | protocol |
| T8c | chosen agent recipe − chosen unconditional recipe | protocol v1.1, in the Holm family |

- Inference uses a firm-clustered bootstrap, 2,000 reps, seed 0 (`phase3.boot_diff`).
- Also reported, not as tests:
  - share of GBM gain captured (both GBMs);
  - the chosen recipe against truth D;
  - the chosen recipe on the protocol's common-sample and ITT metrics;
  - finalists' exploration, validation and test biases;
  - fallback shares and use of Damodaran leaves;
  - each run's funnel (proposed, graded, rejected, invalid, duplicate, over budget).

### 6.4 Inference details (decided 2026-11-07; protocol v1.1 §6)

The protocol says "Holm across T1–T8 at 5%" and "T1–T5 also on truth D". It does not say how
p-values are computed or which split's results enter Holm. Decided:
- **p-values:** every hypothesis is directional, so p is one-sided: the share of the 2,000
  bootstrap differences on the wrong side of 0 (for T8, the share ≥ 0), floored at 1/2,000.
- **Family:**
  - T1–T5, T1D–T5D, T7, T8a, T8b: m = 13;
  - plus T8c: m = 14.
- **Which split:** Holm decisions are made on **test**. T8 can only be run on test, because
  finalists are chosen on validation. Validation results for T1–T7 are reported in full as a
  replication step, without Holm.
- **H5 decision rule:** H5 is supported if T8a and T8b both reject after Holm. A conditional
  gain is claimed only if T8c also rejects. If the chosen agent recipe has no split (depth 0),
  it can still pass T8a/T8b as frozen, but it is reported as "no conditional gain".
- **Power, stated in advance:** exploration CIs for exit-vs-exit differences have half-width
  about 0.02, so T8b and T8c may well be null.

## 7. Not in scope

- No long single search and no ablations (no critic, no archive). If added later, they are
  labelled exploratory.
- Horizon-3 windows are not used in the search.
- The realistic variant (forecast fundamentals) is not part of Phase 3.

## 8. Decisions (made by the author, 2026-11-07)

1. **Protocol version:** yes, protocol **v1.1** is issued with a dated changelog covering §2.2,
   §4.5, T8c, §6.4, agent isolation and the H8 erratum.
2. **T8c:** inside the Holm family (m = 14).
3. **The unconditional best (0.368) is shown to proposers.**
4. **Inference details** as in §6.4.

## 9. Changelog

- 2026-11-07: first draft.
- 2026-11-07: revised after independent code and design reviews (errors log §I):
  - agent isolation;
  - unconditional benchmark;
  - harness robustness and canonicalisation;
  - random generator covers the whole language;
  - corrected level-lever claim;
  - fallback and Damodaran-break disclosures;
  - inference plan proposed.
- 2026-11-07: author decisions recorded (§8); frozen with protocol v1.1.
