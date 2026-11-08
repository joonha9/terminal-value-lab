# Phase 4 procedure: validation and test (drafted 2026-11-07, not yet frozen)

This note turns protocol v1.1 §6 and §8, and `docs/phase3_design.md` §6, into code
(`tvlab/phase4.py`, `scripts/phase4.py`). Where the protocol leaves a choice open, the choice is
stated here **before** validation is opened. Validation and test have not been read: the unseal
log `results/unseal_log.jsonl` does not exist yet. Two independent reviews were run before the
freeze; see `docs/errors_and_fixes.md` §I.4.

## 1. Order of operations

1. **Finalists frozen (done 2026-11-07).** `scripts/phase3_finalists.py` writes
   `results/phase3/finalists.json` (exploration only):
   - agent: 15, the 3 best per run with distinct fingerprints;
   - random: 15;
   - unconditional: 3.
2. **Independent code reviews (done 2026-11-07)**, of the Phase 3 shared code and of the
   Phase 4 code. No high-severity findings. Medium findings were fixed or disclosed (§I.4).
3. **Freeze commit and tag.** The commit includes the code, this note and
   `docs/phase4_pins.json`, which holds the SHA-256 of `finalists.json` and of the 5 input data
   files. Results and data are git-ignored (licensed), so only hashes are committed.
4. **Validation, opened once:** `python3 -P scripts/phase4.py validation`. It writes
   `results/phase4/validation.json` and `chosen.json`.
5. **Commit validation's hashes:** the two printed SHA-256s go into
   `docs/phase4_pins.json["validation"]`.
6. **Test, opened once:** `python3 -P scripts/phase4.py test`. It writes `results/phase4/test.json`.

**Guards in real runs** (`scripts/phase4.py`). Before anything is unsealed, the script refuses to
continue unless all of these hold:
- the git tree is clean, with no untracked files;
- `finalists.json` and the data files match `phase4_pins.json`;
- every finalist validates, keeps its hash, and re-grades on exploration to its frozen score and
  fingerprint;
- the stage's output does not exist;
- the split has no entries in the unseal log. After a crash, a rerun needs
  `--acknowledge-prior-unseal`, and the earlier entries are copied into the output and disclosed.

At test, these must also hold:
- validation's output hashes match the committed ones;
- the chosen recipes are finalists and equal validation's choices;
- the best single method equals validation's;
- the code files, data files and package versions equal those recorded at validation.

**Unsealed reads.** The GBMs are fitted before unsealing. Every read of a sealed split is logged
before its data are touched: truth M at horizon 5, truth D, truth M at horizon 3, and one read
per §8 truth-M variant. Outputs are written to temporary files and renamed at the end.

**Dry run.** `--dry-run` runs both stages with exploration in place of the sealed split, never
unseals, and writes to `results/phase4_dryrun/`. Its numbers are a pipeline check only, not
evidence:
- selection is in-sample;
- the GBMs predict their own training data;
- the earlier-deal sensitivity drops every deal.

## 2. Choices the protocol leaves open

| # | Item | Choice | Why |
|---|---|---|---|
| 1 | "Common sample" for T1–T5 (truth M) | Windows where every Phase 1 core method is defined (11 methods, `CORE_M`) | Same rule that produced every exploration number in the protocol. A Damodaran multiple missing at t (e.g. around the Jan-2018 definition change) therefore shrinks T1–T5's sample, as in Phase 1 |
| 2 | Common sample for T1D–T5D | All truth-D windows where `CORE_D` is defined, without requiring a clean D′. `CORE_D` = Phase 1b's 7 methods + Damodaran at t + the log blend (needed by T4D and T5D). On exploration the extra two exclude no window | Protocol §3: D′ is used only for T7 |
| 3 | Common sample for T7 | `CORE_D` defined **and** a clean D′ (announced after June 30 of L+1) | Same firms and fundamentals under both truths, as in Phase 1b |
| 4 | T3 terciles | Cut points of WACC_t − 2.5% at the 1/3 and 2/3 quantiles of the test's own sample (low = at or below the 1/3 cut, high = above the 2/3 cut), held fixed within the bootstrap. Statistic: [med abs e_G − med abs e_E] in low minus the same in high, where E = FF12 exit | Same aggregation (difference of medians) as every other test |
| 5 | T4 sample | Cyclical FF12 (Enrgy, Chems, Manuf, Durbl) within the common sample | Protocol H3 list |
| 6 | T5 "best pure method" | The better of Gordon g 2.5% and the FF12 exit by median abs e on the same split's common sample, held fixed within the bootstrap | Protocol: "best of {Gordon g2.5, FF12 exit}" |
| 7 | T7 statistic | (own − Damodaran-industry median abs e) under D′, minus the same under D, on the same windows. H7 predicts a negative value | Protocol "rank change" as a single difference |
| 8 | One-sided p | Share of the 2,000 bootstrap statistics on the wrong side of 0, ties counted against H, floored at 1/2,000. Every test uses its own seed-0 stream. A non-finite statistic stops the run | Protocol v1.1 §6 |
| 9 | Holm | Step-down over the 14 tests at 5%, with adjusted p reported. Checked against statsmodels | Protocol v1.1 §6 |
| 10 | Ties in choices | Finalists: list order in `finalists.json` (run a1→a5, then rank), not id order. Single methods: the order of `phase3.SINGLE_METHODS`. Exact ties are common, because a median ignores changes away from the middle (exploration had several) | Design §6.2, "earlier id", made explicit |
| 11 | Best single method (T8a) | Lowest median abs e on the pooled exploration + validation evaluation sets, under the recipe convention | Design §4.2 |
| 12 | GBM gain share | Both GBMs are fitted once on the exploration evaluation set. Share = (FF12 − rule) / (FF12 − GBM) on test. If the GBM does not beat the FF12 exit, the share is reported as **undefined**. An out-of-year check on exploration (fit 2015, predict 2016, and the reverse) had the GBM worse than the FF12 exit, so this outcome is likely | Design §4.4 does not cover a negative denominator |
| 13 | Protocol §8 robustness | Computed in the same opening, reported only, as T1 and T2 point estimates with CIs for each truth-M variant, and T1D and T2D for each truth-D variant (details below). Horizon 3 also gets T1–T5. An empty subsample is recorded as "skipped" instead of stopping the run | Avoids a second opening |
| 14 | Chosen recipes against truth D | Scored on the D evaluation set (FF12 exit at L defined), recipe convention | Design §2.1: description, not a test |
| 15 | Common-sample and ITT metrics for chosen recipes | Median abs e and bias of the recipe and of the best single method where that method is defined. ITT hit rate over all graded M windows. The recipe misses only where the FF12 exit is also undefined; the single method misses wherever it is undefined | Protocol v1.1 §7 |

**§8 variants.**
- Truth M:
  - without the outcome-quality filter at t+5;
  - statements at least 90 days old;
  - excluding `mcap_jump_suspect` at t or t+5;
  - annual ERP (WACC recomputed as in `panel.add_wacc`);
  - without the quality screen;
  - survivors only;
  - Treasury + 5% (Gordon);
  - FCF ex-SBC (Gordon).
- Truth D:
  - low-leverage targets (|net claims| < 20% of market cap);
  - the old double-count deal-EV definition;
  - cash deals (100% cash);
  - PE buyers.
- **Overlap of deals across splits (added after review).** Splits are cut by start year t, so
  the same acquisition can be graded under truth D in more than one split. The number of
  windows whose deal was already graded in an earlier split is reported. T1D–T5D and T7 are
  also reported without them.

## 3. Exploration replication (code check, 2026-11-07)

Phase 4 code run on exploration reproduces the Phase 1 numbers:
- **Core method table:** e.g. Gordon 0.542 / +0.199, FF12 0.416, own 0.366 on 2,213 windows.
- **T1:** +0.126 [0.098, 0.155].
- **T5:** +0.018 [−0.006, 0.037].
- **T7 sample:** 211 windows of 124 firms. D: own 0.366, Damodaran-industry 0.362. D′: own
  0.254, Damodaran-industry 0.320.

Further checks:
- `phase4.raw_methods` equals `methods.predict_all` on every graded exploration window.
- The truth-D table's single-method columns equal `methods.predict_all`, and its 3-year FCF
  average ends at L.
- The T8 bootstrap equals `phase3.boot_diff` exactly (asserted).
- The §8 baseline path reproduces the main T1/T2 exactly (asserted).

Differences from earlier quoted figures, none of which is a code change:
- **T4 on exploration is −0.049 (cyclical FF12 only).** The −0.013 in
  `docs/phase1_exploration.md` is the same contrast over all industries.
- **T1D–T5D use 397 exploration windows (item 2), not the 211 of Phase 1b.** On 397 windows,
  Gordon scores 0.570 and the FF12 exit 0.377. H8 quoted 0.646 and 0.436 on the 211.
- **Truth-D windows:** the current data give 814 graded acquired exploration windows. The
  protocol table says 815. No filter stage gives 815: there are 836 in the window, 816 with deal
  EV > 0, and 834 with `quality_ok` at L. The 815 is most likely a count from before the deal-EV
  fix. The Phase 1b results reproduce exactly.
- **"Without the outcome-quality filter" changes nothing on exploration.** It adds 11 graded
  windows, none of which is in the core common sample.

## 4. Known limitations, disclosed before opening

- **Percentile thresholds.** A firm exactly on a percentile can be misclassified by float
  rounding, for example 57.99999999999999 against `above_pct 58`: about one firm per split.
  The grading code is left unchanged, so validation and test are scored exactly like the
  search.
- **Damodaran 5-year average.** The 2013 Damodaran release uses an older industry list, so for
  17 industries `dam_5yavg` at t = 2017 averages 4 releases, not 5. The release-to-year mapping
  was re-confirmed by the review (vebitda17 = January 2018 release).
- **Truth-D overlap across splits** (§2): disclosed and given a sensitivity analysis.

## 5. Expectations stated before opening

- **T8a** (agent − own multiple): about −0.06 on exploration, so likely to reject.
- **T8b** (agent − random): about −0.02 on exploration.
- **T8c** (agent − best recipe without a split): −0.014 on exploration. The design already noted
  that exit-vs-exit CIs have a half-width of about 0.02, so T8c may well be null.
- **All exploration values are in-sample after selection,** so out-of-sample differences should
  be smaller.
- **The GBM gain share** is likely to be undefined (§2 item 12).
