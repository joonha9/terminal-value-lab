# Phase 1 exploration results (revised 2026-11-07)

**Exploration split only:** start years t = 2015–16, outcome EV at June 2021 / June 2022.
Validation and test windows were not graded. Code: `tvlab/methods.py`,
`scripts/explore_phase1.py`, `scripts/explore_acquisitions.py`. Tables are in `results/phase1/`
(git-ignored).

**Revision note.** All numbers below were recomputed after the pre-freeze code review
(section 5). The two fixes that move results:
1. Small firms' synthetic ratings had used Damodaran's financial-services coverage table.
2. Zero interest with debt had been rated AAA.
Both made the cost of debt too low. WACC rises by about 0.35 pp on average, and Gordon's
overvaluation shrinks.
A separate fix to the deal-EV definition (debt was counted twice) withdrew an earlier
"Gordon is unbiased against deal prices" result.

## 1. Sample

- 5,334 windows pass the quality screen at t. 1,306 exited (no later row). 80 have a suspect
  outcome, EV ≤ 0, or a data gap. That leaves **3,948 graded** windows.
- Exit rate is highest in Enrgy (37%), Telcm (33%), Utils (30%) and BusEq (27%), and lowest in
  Durbl (13%) and Manuf (14%).
- At t+5, FCF ≤ 0 in 24.5% of windows and EBITDA ≤ 0 in 17.2%.
- **Common sample:** 2,213 windows (56%) where every core method is defined.

## 2. Main comparison: truth M = market EV at t+5 (common sample)

`hit_rate_itt` = share of windows with |e| < ln 1.25; an undefined method counts as a miss.

| Method | Median abs e | Bias | Hit rate |
|---|---|---|---|
| Gordon, FCF_t+5, g 2.5%, WACC | 0.542 | +0.199 | 22% |
| Gordon, 3-yr avg FCF | 0.491 | +0.064 | 25% |
| Value driver, RONIC = ROIC | 0.596 | −0.281 | 20% |
| Value driver, RONIC = r | 0.562 | −0.428 | 21% |
| Exit, FF12 median EV/EBITDA at t | 0.416 | −0.040 | 29% |
| Exit, Damodaran-industry median | 0.396 | −0.044 | 30% |
| **Exit, own EV/EBITDA at t** | **0.366** | −0.037 | 33% |
| Exit, Damodaran aggregate at t | 0.408 | −0.118 | 28% |
| Exit, Damodaran 5-yr average | 0.395 | −0.100 | 29% |
| 50/50 blend (levels) | 0.439 | +0.125 | 28% |
| 50/50 blend (geometric) | 0.433 | +0.076 | 29% |
| Ref: FF12 multiple at t+5 (look-ahead) | 0.388 | +0.128 | 31% |
| Ref: Gordon with WACC at t+5 (look-ahead) | 0.583 | +0.309 | 20% |
| Ref: EV_t (no change) | 0.495 | −0.419 | 22% |

Firm-clustered bootstrap, 2,000 reps. Each row is the difference in median abs e, 95% CI;
negative means the first method is better.

| Contrast | Difference | 95% CI |
|---|---|---|
| Gordon − FF12 exit | **+0.126** | [0.098, 0.155] |
| Own multiple − FF12 exit | −0.050 | [−0.073, −0.029] |
| Levels blend − FF12 exit | +0.023 | [−0.001, 0.048] |
| Geometric blend − FF12 exit | +0.018 | [−0.006, 0.037] |
| Damodaran 5-yr − Damodaran at t | −0.013 | [−0.026, −0.002] |
| 3-yr FCF − 1-yr FCF (Gordon) | −0.051 | [−0.076, −0.026] |
| Value driver − Gordon | +0.054 | [0.018, 0.084] |
| Damodaran-industry − FF12 | −0.020 | [−0.038, −0.006] |

## 3. Against the pre-stated hypotheses

- **H1 (Gordon undervalues): opposite.** Gordon overvalues: bias +0.20 on the common sample,
  +0.11 on its own sample. Its implied EV/EBITDA is 15.7 against an actual 13.0. The growth
  rate implied by actual EV and FCF is 1.9%, below 2.5%. Bias is about 0 at g = 2%, but median
  abs e stays at about 0.56, so dispersion, not level, is Gordon's main problem.
- **H2 (Gordon best in stable industries): reversed.** Gordon minus exit, by industry:
  - Worst for Gordon: Utils +0.37, Telcm +0.31, Durbl +0.27, Shops +0.26.
  - Best for Gordon: Enrgy −0.23 (Gordon wins) and Chems −0.03.
  - Utilities have the lowest WACC (5.5%) and so the smallest r − g. This is formula
    convexity, not industry stability.
- **H3 (long-run multiple in cyclicals): supported in Energy.** Enrgy error falls from 0.83 to
  0.54. Overall the gain is small but its CI excludes 0. The Damodaran series starts in 2013,
  so t = 2015–16 average only 3–4 releases.
- **H4 (blends beat pure methods): not supported.** The blends do no better than the FF12
  exit, and both CIs include 0.

## 4. Second truth: acquisition prices (Phase 1b)

Acquired firms are graded at their last pre-deal year L, with t < L < t+5. The comparison
uses the **same 211 firms and the same fundamentals** under two truths:
- **D** = deal EV: FactSet transaction value, which includes gross debt, minus cash
  (`docs/exits.md`).
- **D′** = market EV at June 30 of L+1, before the deal was announced.

| Method | D: median abs e | D: bias | D′: median abs e | D′: bias |
|---|---|---|---|---|
| Gordon, g 2.5%, WACC | 0.646 | +0.133 | 0.527 | +0.201 |
| Gordon, 3-yr avg FCF | 0.602 | +0.067 | 0.570 | +0.154 |
| Exit, FF12 median | 0.436 | −0.025 | 0.365 | +0.116 |
| Exit, Damodaran-industry median | **0.362** | +0.052 | 0.320 | +0.129 |
| Exit, own multiple at t | 0.366 | −0.039 | **0.254** | +0.076 |
| Exit, Damodaran 5-yr avg | 0.384 | −0.103 | 0.317 | +0.036 |
| 50/50 blend | 0.538 | +0.126 | 0.416 | +0.223 |

The deal premium over the pre-announcement market EV is a median ln 0.15 (IQR −0.05 to 0.35).

- **Exit multiples beat Gordon under both truths,** so the main result is not a product of
  grading against market prices.
- The bias gap between D and D′ is mechanical: for every method, bias against D equals bias
  against D′ minus the deal premium.
- The own multiple is best against the market and nearly tied for best against deals (0.366
  vs 0.362).
- PE and strategic buyers show no clear difference.
- The sample is small (211).

## 5. Checks done before freezing

- **Rate change:** Gordon with the outcome-year WACC overvalues more (+0.31), so the 2016→2021
  rate moves do not explain the bias.
- **Deal-EV definition:** chosen by a flat implied equity premium across leverage. The test
  picks the same reading on exploration-window deals alone (428 deals, spread 0.14) as on all
  years (spread 0.19).
- **Residual market-cap errors:** 1–2% of windows. They become a robustness exclusion.
- **Independent code review** (2026-11-07). Fixed:
  1. Small-firm rating table (high severity).
  2. Zero interest with debt rated AAA.
  3. Exited windows where the firm reappears are now marked "gap".
  4. ITT hit rate and 2,000 bootstrap reps, matching the protocol.

  Disclosed or added to robustness:
  - outcome-quality filter on truth M;
  - statements less than 90 days old at the valuation date;
  - FF12 and Damodaran industries are snapshots;
  - the Damodaran multiple definition changes between the Jan-2017 and Jan-2018 releases;
  - preferred stock is missing in the panel.

## 6. Caveats

- There is one rate regime: firms are valued in 2016–17 and graded in 2021–22.
- Perfect foresight on outcome-year fundamentals. A single year's FCF is noisy (the 3-year
  average helps).
- About 25% of windows exit. Most exits are acquisitions, graded separately under truth D.
