# Errors, traps and corrections log

Started 2026-11-07, updated as the project goes on. This is the single place that records
everything that went wrong: our own bugs, traps in the data sources, design flaws found before
the protocol freeze, findings that were withdrawn, and documentation errors. It exists so the
write-up and website can report the project honestly. Wrong turns are part of the result, and
several of them changed headline numbers.

Each entry records:
- **Type:** *bug* (our code), *data trap* (source behaves unexpectedly), *design* (method
  flaw), or *doc* (a written number or statement was wrong).
- **Found by:** how it was caught.
- **Impact:** what it changed, with before → after numbers where they exist.
- **Fix:** what was done, and where it is recorded (file or commit).

Validation (t = 2017–18) and test (t = 2019–20) windows had not been graded when any of these
were found. Every fix below was made on exploration data only.

---

## A. Data collection: FactSet cash-flow exports

**A1. Lost screen definition** (2026-11-06; *process*)
- **What:** The FactSet screen used for the earlier ValuationLab exports was lost, and its
  formulas had never been written down.
- **Fix:** The formulas were reconstructed and verified against the old exports (fiscal
  year-ends 99.99% identical, sales and capex 100% within 0.5%). They are now written down
  in full in `docs/factset_export.md`.
- **Lesson:** write down every export recipe the day it is made.

**A2. Global screen gives empty columns** (2026-11-06; *data trap*)
- **What:** Without a country filter, the screen returns about 150k global rows. FactSet then
  left the last-added columns empty ("-" or #N/A), or served earlier results in them.
- **Fix:** One criterion, Exchange Country Name = United States (about 33k rows), as in the old
  exports.

**A3. Stale columns after editing a formula in place** (2026-11-06, file 2016; *data trap*)
- **What:** The Parameters tab showed the 2016 date for every column, yet six columns exported
  FY2018 values, identical to the 2019 file.
- **Found by:** comparing values across files.
- **Fix:** Delete the column and re-add it with "Add New". Before each export, check a known
  value (Apple income taxes). `scripts/check_tv_exports.py` now flags any column that is
  identical across two files.

**A4. Exporting before FactSet finishes** (2026-11-07; *data trap*)
- **What:** Columns fill left to right. An early export gave #N/A columns, or values left over
  from the previous year's formulas.
- **Fix:** Wait until the last column (Stock Option Cash Flow) is filled; Apple must show a
  number there. Recorded in `docs/factset_export.md`.

**A5. Look-ahead from the June-30 date** (2026-11-06; *data trap → would have been a bug*)
- **What:** The date argument selects the latest fiscal period that *ended* by that date, not
  one that had been *reported*. With `YYYY0630`, firms with June-30 year-ends (e.g. Microsoft)
  returned the fiscal year ending that same day, which was not yet public on the valuation date.
- **Fix:** Use `YYYY0615`. It reproduces the old exports, whose year-ends run up to about
  June 1–3.

**A6. Look-ahead from the fiscal-year label** (2026-11-07; *bug, caught*)
- **What:** In the label form of the formula, `YYYY` is the next fiscal year. It was not yet
  reported at the valuation date. The correct label is `YYYY − 1`.
- **Found by:** `scripts/check_tv_exports.py`, which compares fiscal year-end, sales and capex
  with the ValuationLab exports.
- **Fix:** Re-exported. All 11 files pass the checker.

**A7. Several security rows per company** (*data trap*)
- **What:** One company can appear on several security rows, some of them empty.
- **Fix:** Keep the row with the most non-missing values (`tvlab/panel.py::_read_tv`).

---

## B. Discount-rate data: Damodaran and FRED

**B1. Beta file names are one year off** (*data trap*)
- **What:** `betasYY.xls` is the January YY+1 release; for example `betas16.xls` is dated
  2017-01-05. Reading the name literally would use a beta published after the valuation date.
- **Fix:** `scripts/build_damodaran.py` asserts that each file's "Date updated" is January t+1.

**B2. Wrong rating table for small firms** (*data trap → bug, HIGH severity*)
- **What:** The block printed beside Damodaran's large-firm coverage → rating table in
  `ratings.xls` is for **financial-service** firms. The table for small non-financial firms
  ("smaller and riskier") sits lower in the sheet. The first version used the financial-firms
  block for every firm with market cap ≤ $5B.
- **Found by:** independent code review before the protocol freeze (2026-11-07).
- **Impact:** small firms got ratings that were too high, so their cost of debt was too low.
  - Together with C2, WACC rose by about 0.35 pp on average after the fix.
  - Gordon's bias against truth M fell from +0.250 to +0.199.
  - The Gordon − FF12 exit gap fell from +0.161 [0.124, 0.189] to +0.126 [0.098, 0.155].
  - See G for all affected numbers.
- **Fix:** commit `d657ca2`. The build script now asserts the AAA thresholds (8.5 for large
  firms, 12.5 for small firms).

**B3. Default-spread file has a misleading date cell** (*data trap*)
- **What:** `bondspreads24.xlsx` says "Date updated 2024-01-05" but contains a 2025 column.
- **Fix:** The column label year is taken as the release year (`docs/damodaran_data.md`).

**B4. Missing market row in one release** (*data trap*)
- **What:** The January 2016 release (t = 2015) has no "Total Market (without financials)" row.
- **Fix:** Use "Total Market" for the 0.1% of firms that fall back to the market beta in that
  year. Disclosed.

**B5. Damodaran multiple definition changes between years** (*data trap*)
- **What:** From the January 2018 release, `vebitda` files have two blocks: positive-EBITDA
  firms and all firms. Earlier releases have one block.
- **Fix:** Use "all firms" from 2018 on. The break falls between the exploration and validation
  years, which matters for H3/T4; it is disclosed in protocol §10.

**B6. Percent stored as text** (*data trap*)
- **What:** Some cells in the monthly ERP file hold percentages as text.
- **Fix:** Parsed explicitly (commit `facc3a8`).

**B7. Two SIC systems disagree** (*data trap*)
- **What:** Capital IQ SIC codes in Damodaran's firm list agree with FactSet SIC4 for only 35%
  of matched firms.
- **Fix:** The firm → Damodaran industry mapping is built in FactSet SIC space: majority
  industry among ticker-matched firms. Leave-one-out beta error: median 0.00, p90 0.16.

---

## C. Panel construction and data quality

**C1. About 5% of FactSet market caps are wrong** (*data trap*, found in Phase 0 QA)
- **What:** Three kinds of bad market caps:
  - reverse-split mis-scaling (one firm-year shows a market cap of $710 quadrillion; 801
    year-to-year jumps exceed 100×);
  - OTC shells with less than $1M of assets priced above $100M;
  - de-SPAC years that pair pre-merger statements with the post-merger market cap.
- **Fix:** Screen `quality_ok`: total assets ≥ $10M and market cap / assets ≤ 100. It uses only
  data at that date. Applied at t, and at t+5 for truth M.
  - Residual smaller mis-scalings are caught by `mcap_jump_suspect` (robustness only, since it
    looks at the next year).
- **Open:** the same flaw sits in the ValuationLab universe. Its effect on ValuationLab's
  published errors has not been measured.

**C2. Debt with zero interest rated AAA** (*bug*)
- **What:** Coverage = EBIT / interest. With interest recorded as 0 but debt outstanding,
  coverage was infinite, so the firm got the top rating.
- **Found by:** independent code review, 2026-11-07.
- **Fix:** Debt with missing or zero interest now gets the median rating (BBB). 12% of rows
  carry this BBB. Commit `d657ca2`.

**C3. Data gaps counted as exits** (*bug*)
- **What:** Windows with no row at t+5 were marked "exited" even when the firm reappears in the
  data later.
- **Found by:** independent code review.
- **Fix:** New status "gap". These windows are neither graded nor counted as exits.

**C4. Statements may not have been public on the valuation date** (*design, disclosed*)
- **What:** About 2% of start rows have a fiscal year-end less than 90 days before June 30.
- **Fix:** Added `stmt_age_days` and a robustness check requiring at least 90 days.

---

## D. Exits and deal prices (FactSet M&A)

**D1. "Company Type Current" drops acquired targets** (*data trap*)
- **What:** Filtering targets by their current company type keeps only firms that are still
  public. Acquired firms are, by definition, no longer public, so the screen returned only 341
  deals.
- **Fix:** Use Company Type **At Deal**. That returns 12,184 deals.

**D2. 10,000-row download limit** (*data trap*)
- **Fix:** Download in two parts, deals completed 2014–19 and 2020–26.

**D3. MergerStat company fields give the latest deal in any role** (*data trap*)
- **What:** For example, Red Hat and Twitter show 2025 deals in which they were not the target.
  These fields cannot identify takeovers.
- **Fix:** Not used. Exits come from target-side deals only.

**D4. Deal EV counted debt twice** (*bug, HIGH impact; result withdrawn*)
- **What:** FactSet's transaction value already includes **gross debt** assumed. The first
  version added net debt on top.
- **Found by:** a check of the implied equity premium by leverage bin. The correct definition
  should give a flat premium. The equity-only reading rose from 0.32 to 1.12 with leverage;
  equity + gross debt was nearly flat, 0.10–0.29.
- **Impact:** the Phase 1b result "Gordon is unbiased against deal prices" (bias +0.016)
  was an artifact.
  - After the fix, Gordon's bias against deals was +0.317.
  - After B2 and C2, it is +0.133.
  - The result is withdrawn and recorded in `docs/phase1_exploration.md`.
- **Fix:** deal EV = transaction value − cash + minority interest + preferred. When the
  transaction value is ≤ debt, the equity-only rule applies (commit `4090168`).
  - The definition was chosen on deals from all years.
  - It was then re-checked on exploration-window deals only (428 deals); the same reading wins
    (spread 0.14 vs 0.88 and 0.29). See `scripts/check_deal_ev_definition.py`.
  - In 44 deals, cash exceeds the transaction value, which gives deal EV ≤ 0. They drop out of
    truth D and are reported.

**D5. Duplicate column after a merge** (*bug*)
- **What:** `build_exits.py` produced a duplicate `last_fy` column.
- **Fix:** commit `89dcc01`.

**D6. Grading at L = t is circular** (*design*)
- **What:** If an acquired firm's last pre-deal year L equals t, the "own multiple" exit uses
  EV_t, and truth D′ is close to EV_t. Agreement would then be built in.
- **Fix:** Require t < L < t+5 (`scripts/explore_acquisitions.py`, protocol §3).

---

## E. Design corrections before the protocol freeze

**E1. H6 was mechanical** (*design*)
- **What:** "Gordon's bias is smaller against D than against D′" holds for every method by
  construction: bias against D = bias against D′ − deal premium.
- **Fix:** H6 and T6 dropped, protocol v1 (2026-11-07).

**E2. Sales growth missing in the exploration years** (*design*)
- **What:** The panel starts in FY2015. So 1-year growth is missing for every t = 2015 window,
  and 3-year growth is missing for t = 2015–17.
- **Fix:** Sales growth removed from the recipe language (protocol §7).

**E3. Hit rate and bootstrap did not match the protocol** (*bug*)
- **What:** The first scripts computed the hit rate only over defined windows, and used fewer
  bootstrap repetitions.
- **Fix:** Intention-to-treat hit rate (an undefined method counts as a miss) and 2,000
  repetitions.

**E4. Truth M selects on the outcome** (*design, disclosed*)
- **What:** Requiring `quality_ok` at t+5 filters on the outcome.
- **Fix:** T1 and T2 are reported with and without this filter (protocol §8).

**E5. H1 and H2 reversed in exploration** (*design*)
- **What:** The pre-stated H1 ("Gordon undervalues") and H2 ("Gordon is best in stable
  industries") both came out opposite.
- **Fix:** Both were relabelled [expl] and restated in the observed direction. They are tested
  only on validation and test data, and the originals are kept in protocol §5.

---

## F. Independent code review before the freeze (2026-11-07)

A fresh reviewer, given the code and not our conclusions, found B2 (high severity), C2 and C3,
and the E3 mismatch. It also triggered the disclosures for E4, C4, the industry-snapshot
issue, B5 and the missing preferred stock. All Phase 1 numbers were recomputed afterwards
(commit `d657ca2`). The same step is repeated before each freeze; see I for Phase 3.

---

## G. Withdrawn or revised findings (before → after)

Exploration, t = 2015–16. Gordon = FCF_t+5, g 2.5%, firm WACC.

| Finding | First version | After deal-EV fix (D4) | Final, after B2 + C2 |
|---|---|---|---|
| Gordon bias, truth M (common sample) | +0.250 | — | **+0.199** |
| Gordon median abs e, truth M | 0.577 | — | 0.542 |
| Gordon − FF12 exit, median abs e (truth M) | +0.161 [0.124, 0.189] | — | **+0.126 [0.098, 0.155]** |
| 50/50 blend − FF12 exit | +0.044 [0.018, 0.066] | — | +0.023 [−0.001, 0.048] (n.s.) |
| Gordon bias, truth D (deal EV) | **+0.016 ("unbiased")** | +0.317 | **+0.133** |
| Gordon median abs e, truth D | 0.570 | 0.716 | 0.646 |
| Gordon bias, truth D′ (pre-announcement market EV) | +0.409 | +0.409 | +0.201 |
| FF12 exit bias, truth D | −0.235 | — | −0.025 |

The direction of the main result (exit beats Gordon) never changed. Its size shrank by about
a fifth. One headline ("Gordon prices deals without bias") was wrong and is withdrawn.

---

## H. Documentation errata (found 2026-11-07, while preparing Phase 3)

**H-1. Frozen protocol, H8, quotes a stale number** (*doc*)
- **What:** `docs/protocol.md` H8 says "Exploration: 0.436 vs 0.716". The 0.716 is Gordon's
  error against truth D *before* the rating-table fix (B2). The revised value is **0.646**
  (`docs/phase1_exploration.md` §4). The FF12 value, 0.436, is correct.
- **Status:** it affects only the disclosure text, not a test or a decision rule. v1 was left
  untouched (tag `protocol-v1`). The number is corrected in **protocol v1.1** (2026-11-07,
  changelog item 5).

**H-2. Plan status line quotes the pre-fix gap** (*doc*)
- **What:** `docs/plan.md` §8 said "beat Gordon by 0.16 (CI 0.12–0.19)". The revised value is
  0.126 (CI 0.098–0.155).
- **Status:** corrected in plan.md (not a frozen file).

---

## I. Phase 3 (agent search setup)

The Phase 3 code (recipe language, grader, benchmarks, agent harness) was written on
2026-11-07. It ran without runtime errors. All 16 tests passed on the first run, including a
check that the recipe leaves reproduce the Phase 1 method values exactly.

Before the first agent run, two independent reviews were run on 2026-11-07. Each reviewer was
a fresh agent given the code and documents but not our conclusions, with access to exploration
data only:
- one on code correctness and leakage;
- one on the design against the frozen protocol.

Every finding below was re-checked by running code before it was acted on.

### I.1 Design flaws (design review)

**I-1. An unconditional blend beats every benchmark** (*design, HIGH*)
- **What:** One recipe with no split at all scores **0.368**: 0.8 × own-multiple exit + 0.2 ×
  Gordon (3-yr avg FCF, g 4%, Treasury + 5%), in levels. It beats:
  - the best single method (0.415);
  - the traits-only GBM ceiling (0.406);
  - the best of 1,000 random recipes (0.390 at the time).
- **Confirmed by:** an exhaustive search over all 95 single leaves and all 169,670 two-part
  blends.
- **Why it matters:**
  - T8(a) compares the agent with the best *single §4 method*. An agent that merely tuned blend
    weights would pass it without discovering any conditional rule, yet Q3 asks about
    *conditional* rules.
  - The "share of the traits-only GBM gain captured" would be about 175%, which is meaningless.
- **Fix:**
  - New benchmark: **best recipe without a split** (exhaustive grid of single leaves and
    2-part blends; top 3 distinct kept for validation, like the finalists).
  - It is shown to the proposers as the bar to beat.
  - How it enters the tests is a protocol decision; see `docs/phase3_design.md` §6.
- **Exploration finding worth reporting in its own right:** shrinking the firm's own multiple
  toward a cash-flow value beats either method alone, by 0.047 in median |e|.

**I-2. Agents were not isolated** (*design, HIGH*; both reviewers)
- **What:** The first harness design let each subagent read the prompt file and write its own
  reply. A subagent with file and shell access could:
  - call the grader (unlimited hidden evaluations, so the budget means nothing);
  - read the random-search pool, other runs' archives or the docs (calendar years);
  - call `build_table(..., unseal=True)` and reach validation or test data;
  - as the critic, read scores, so it would no longer be blind.
- **Fix:**
  - Proposers and critics run as a dedicated subagent type, `tv-text-only`, with every file,
    shell, search, web and MCP tool disallowed and CLAUDE.md omitted.
  - The orchestrator pastes each brief and saves the reply.
  - Every raw reply is logged (`replies.jsonl`).
  - Each run records the model, the agent definition and a hash of the code and benchmark
    files.
  - Every unsealed table build is appended to `results/unseal_log.jsonl`.
  - Isolation is tested before the first run (see the design doc).

**I-3. "No free scale factor" was overstated** (*doc*)
- **What:** g (0–4%) and blend weights are strong level levers. Gordon's bias moves from
  −0.43 to +0.39 across the g grid, and a small Gordon weight shifts a blend's level.
- **Why it matters:** an LLM that knows the post-2021 rate path could pick levels for
  non-cross-sectional reasons.
- **Fix:**
  - The claim is corrected.
  - The critic now rejects mechanisms that appeal to time periods, macro events or rate paths.
  - The prompt says "other samples", not "later periods".
  - Finalists' exploration, validation and test biases will be reported side by side.

**I-4. The Phase 4 inference plan was incomplete** (*design*)
- **What was unspecified:**
  - p-values for Holm;
  - the family size;
  - which split enters Holm;
  - the H5 decision rule;
  - tie rules and the bootstrap seed.
- **Fix:** proposed in `docs/phase3_design.md` §6, to be fixed before validation is opened.

**I-5. The fallback convention and Damodaran break were not labelled** (*doc*)
- **What:** The FF12-exit fallback and the fixed evaluation set differ from the protocol's
  "common sample" convention. Also, the fallback routes on outcome-year definedness
  (FCF_t+5 sign, ROIC_t+5 > g), and one undefined blend part sends the whole blend to the
  fallback.
- **Checked on exploration:** this is not exploitable. A 0.95 own + 0.05 value-driver "trick"
  scores 0.4147 against own's 0.4149.
- **Damodaran break:** the definition change (errors log B5) falls exactly between exploration
  and validation, so it also affects the `dam_t` and `dam_5yavg` leaves.
- **Fix:** both are labelled in the design doc and stated in the prompt (blend fallback).
  Finalists' fallback shares and their use of Damodaran leaves will be reported.

### I.2 Code bugs (code review; each reproduced before fixing)

**I-6. Re-running a stage after a crash duplicated archive records** (*bug, medium*)
- **What:** Records were appended one by one, and the state was saved at the end. A crash
  mid-stage (e.g. a verdict with `"reason": null`) left records written. A re-run appended
  them again under the same ids, and `select()` could then pick the same recipe twice.
- **Fix:** A stage now builds all records first and writes them together with the state
  change. Already-archived ids are skipped, and `select()` and `funnel()` are unique by id.
  Covered by a regression test.

**I-7. Verdict parsing** (*bug, medium*)
- **What:**
  - "Approved" or "Approve " counted as rejections.
  - A 1-based index silently shifted every verdict.
  - A missing or non-numeric index crashed the step.
- **Fix:** Verdict words are normalised. The verdict set must be exactly indices 0..n−1, or the
  reply is set aside, logged and the critic re-run.

**I-8. The search denominator was not fully recorded** (*bug, medium*)
- **What:** Proposals beyond 6 were dropped without a record. Unparseable replies were simply
  re-run, which is a free resample.
- **Fix:** Extra proposals are archived as `over_budget`, and every reply (parsed or not) is
  logged.

**I-9. Functionally identical recipes counted as new** (*bug, medium*)
- **What:** These spellings were not canonicalised:
  - clause order;
  - FF12 list order;
  - `0` vs `0.0`;
  - `-0.0` vs `0`;
  - blend parts that become equal after rounding.

  Do-nothing splits (`then` = `else`) and repeated clauses were also accepted.
- **Fix:**
  - Fuller canonical form, plus semantic checks.
  - A **behaviour fingerprint** (hash of the rounded predictions on the evaluation set).
    Finalists must have distinct fingerprints, for agents and random runs alike.

**I-10. Tied percentiles create empty branches** (*bug, low*)
- **What:** About half of firms have zero R&D. All of them share percentile ≈ 25, so
  `rnd_intensity below_pct < 25` selects nobody. 146 of 1,000 random recipes had an empty
  branch.
- **Fix:**
  - The trait description now warns about this.
  - The archive shows each recipe's share of firms per leaf, so empty branches are visible.
  - The prompt's description of the percentile population is corrected (clean universe,
    ≥ $100M at the valuation date).

**I-11. Smaller code issues** (*bug, low*)
- The validator raised `TypeError` instead of `RecipeError` on malformed types.
- JSON parsing failed on triple backticks inside a string.
- The cached table was returned as a shared mutable object.
- A column named `eval` shadowed a DataFrame method.
- A process-wide warning filter was set.
- A hit rate was labelled as if it were the protocol's ITT hit rate.

All fixed; the regression tests are in `tests/test_phase3.py` (32 tests).

**I-12. Proposer text could leak scores to the critic** (*design, low*)
- **Fix:** The proposer is told not to quote scores or ids. Score-like numbers (e.g. 0.415)
  are masked in the critic brief.

### I.3 Random-search pool regenerated (disclosure)

The random pool was generated three times on 2026-11-07, always with seed 2026. Each was seen
before the agent runs. The scores were never used to change the generator.

| Version | Change | Median | Best of 30 (mean) | Best of 1,000 |
|---|---|---|---|---|
| v1 | first draft | 0.485 | 0.416 | 0.390 |
| v2 | stricter validator (no do-nothing splits or repeated clauses): the same seed draws a different pool | 0.489 | 0.415 | 0.390 |
| **v3 (final)** | generator covers the whole language: percentiles 5–95 (was deciles); raw thresholds at any percentile of the clean universe (was deciles of the outcome-selected evaluation set); FF12 sets of 1–10 (was 1–4) | **0.486** | **0.414** | **0.379** |

The final pool's SHA-1 is recorded in `baselines_explore.json` (`random.pool_sha1`).

---

## J. What the record says about process

- **Automated checkers catch look-ahead that eyeballing misses.**
  `scripts/check_tv_exports.py` caught A6. The year-assertion in `build_damodaran.py` guards
  B1.
- **Independent review before each freeze pays off.** The pre-freeze review found the
  highest-impact bug of the project (B2), after the results had already been written up once.
- **Sanity checks on economic plausibility find definition errors.** The flat-premium test
  exposed D4. A "too good" result (Gordon exactly unbiased against deals) was the symptom.
- **Numbers are recomputed and re-documented after every fix.** Stale copies still slip
  through (H-1, H-2), so every number quoted in a summary should be traced to its source table
  before publication.
