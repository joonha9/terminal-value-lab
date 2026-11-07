# Phase 1 exploration results (2026-11-07)

**Exploration split only:** start years t = 2015–16, outcome EV at June 2021 / June 2022.
Validation and test windows were not graded. Code: `tvlab/methods.py`,
`scripts/explore_phase1.py`. Tables are in `results/phase1/` (git-ignored CSVs).
Nothing below is frozen.

## Sample

- 5,334 windows pass the quality screen at t. Of these, 1,313 exited (no t+5 row), and 73
  have a suspect outcome or EV ≤ 0. That leaves **3,948 graded** windows.
- Exit rate by industry: Enrgy 38%, Telcm 34%, Utils 30%, BusEq 27%. Lowest are Durbl 13%
  and Manuf 14%.
- At t+5, FCF ≤ 0 in 24.5% of windows and EBITDA ≤ 0 in 17.2%. Gordon is defined for 74%
  of graded windows, the industry exit multiple for 83%.
- **Common sample:** 2,209 windows (56% of graded) where every core method is defined.

## Main comparison (common sample, median |ln(TV / EV_t+5)|)

| Method | Median abs error | Bias (median ln) | Within ±25% |
|---|---|---|---|
| Gordon, FCF_t+5, g 2.5%, WACC | 0.577 | **+0.250** | 21% |
| Gordon, 3-yr avg FCF | 0.523 | +0.123 | 23% |
| Value driver, RONIC = ROIC | 0.595 | −0.237 | 21% |
| Value driver, RONIC = r | 0.553 | −0.404 | 21% |
| Exit, FF12 median EV/EBITDA at t | 0.417 | −0.040 | 29% |
| Exit, Damodaran-industry median (our panel) | 0.397 | −0.044 | 30% |
| **Exit, firm's own EV/EBITDA at t** | **0.366** | −0.036 | 33% |
| Exit, Damodaran aggregate multiple at t | 0.409 | −0.117 | 28% |
| Exit, Damodaran 5-yr average multiple | 0.396 | −0.100 | 29% |
| 50/50 blend (levels), Gordon + FF12 exit | 0.460 | +0.155 | 27% |
| 50/50 blend (geometric) | 0.447 | +0.109 | 28% |
| Ref: actual FF12 multiple at t+5 (look-ahead) | 0.388 | +0.128 | 31% |
| Ref: EV_t, no change | 0.495 | −0.419 | 22% |

Firm-clustered bootstrap, 95% CIs (difference in median |e|; negative = first method better):
- Gordon − FF12 exit: **+0.161 [0.124, 0.189]**
- Own multiple − FF12 exit: −0.050 [−0.073, −0.029]
- Blend − FF12 exit: +0.044 [0.018, 0.066]
- Damodaran 5-yr avg − Damodaran at t: −0.013 [−0.026, −0.002]
- 3-yr avg FCF − 1-yr FCF (Gordon): −0.054 [−0.079, −0.024]

## Against the pre-stated hypotheses

- **H1 (standard Gordon undervalues): opposite.** Gordon overvalues. Its implied EV/EBITDA
  is 16.5 against an actual 13.0 at t+5. WACC at t was low (median 6.8%; 10-yr Treasury
  1.5–2.3%). With g = 2.5%, r − g is only about 4.3 pp. The market-implied growth from actual EV
  and FCF is 1.6%, below 2.5%. In the r × g grid, bias is about 0 at g = 2% (or g = 2.5% with
  r + 1 pp). Even then median |e| is 0.57, so most of Gordon's error is dispersion, not level.
- **H2 (Gordon best in stable industries): reversed.** Gordon does worst relative to exit in
  Utils (+0.53), Telcm (+0.43), Durbl and Shops. It does best in Enrgy, where it beats exit
  by 0.21. Low-WACC industries (utilities, WACC 4.3%) have the smallest r − g, so Gordon
  inflates there. That is the formula's convexity, not the industry's stability.
- **H3 (long-run multiple beats current multiple in cyclicals): supported in Energy.** Enrgy
  median |e| falls from 0.83 to 0.54. Exit multiples at t (2015–16) were high because EBITDA
  was depressed, and applied to recovered t+5 EBITDA they overvalue (bias +0.58). Overall
  gain is small but its CI excludes 0. Caveat: the Damodaran series starts in 2013, so the
  "5-yr" average uses 3–4 releases for t = 2015–16.
- **H4 (blends beat both pure methods): not supported.** A fixed 50/50 blend inherits Gordon's
  bias. Conditional weights are the agents' job (H5).

## Other observations

- The firm's own multiple at t beats any industry median. Firm-specific multiples persist
  for five years.
- Knowing the future industry multiple (look-ahead reference) improves the FF12 exit by only
  0.03. Multiple drift is a small part of exit error; dispersion around the industry median
  is most of it.
- Gordon with Treasury + 5% (no cross-sectional WACC) has lower error than with the firm WACC
  (0.557 vs 0.617, own samples). Firm-level WACC variation does not help Gordon here. It adds
  explosions where WACC is low.
- The value-driver formula undervalues (RONIC = ROIC: −0.24), the mirror image of FCF-Gordon
  overvaluing.

## Caveats

- One rate regime: valued in 2016–17 at low rates, graded at June 2021 (market peak) and June
  2022 (after the rate shock). Gordon's results depend on r − g, so validation (outcomes
  2023–24) may differ in level.
- Perfect foresight on year-t+5 fundamentals. A single year's FCF is noisy, which penalizes
  Gordon more than EBITDA-based exits (the 3-year average helps).
- Graded only where the outcome exists; 25% of windows exited. Intention-to-treat rules for
  undefined cases are still to be set in the protocol (Phase 2).

## Implications for Phase 2

1. Building blocks for agent recipes: r − g floor/spread conditions, FCF smoothing, own vs
   industry multiple, long-run multiple for cyclicals, conditional blend weights.
2. Report Gordon both with WACC and with Treasury + 5%; the WACC choice matters a lot.
3. Pre-register the ITT rule for undefined cases, the quality screen, and the common-sample
   vs own-sample reporting.

## Phase 1b: acquisition prices as a second truth (exploration years)

`scripts/explore_acquisitions.py`. Acquired firms have no t+5 statements, so they are graded at
the last pre-deal fiscal year L, with t < L < t+5. L = t is excluded because there the firm's
own multiple equals the market truth by construction. Multiples, g and WACC still come from t.
On the **same 211 firms with the same fundamentals**, two truths:
- A = deal EV (deal equity + net claims)
- B = market EV at June 30 of L+1, before the deal was announced

| Method | A: median abs | A: bias | B: median abs | B: bias |
|---|---|---|---|---|
| Gordon, g 2.5%, WACC | 0.570 | **+0.016** | 0.656 | **+0.409** |
| Gordon, 3-yr avg FCF | 0.552 | −0.019 | 0.677 | +0.310 |
| Exit, FF12 median | 0.412 | −0.235 | 0.365 | +0.116 |
| Exit, Damodaran-industry median | **0.373** | −0.248 | 0.320 | +0.129 |
| Exit, own multiple at t | 0.433 | −0.315 | **0.254** | +0.076 |
| Exit, Damodaran 5-yr avg | 0.421 | −0.335 | 0.317 | +0.036 |
| 50/50 blend | 0.446 | −0.027 | 0.534 | +0.315 |

The deal premium over the pre-announcement market EV is ln 0.40 (median), with IQR 0.19–0.57.

Observations:
- **Gordon is unbiased against deal prices and overvalues market prices by about the same
  amount as the premium (+0.41 vs 0.40).** Standard practitioner Gordon inputs reproduce the
  level at which control changes hands, not the minority market price. Caveat: targets may be
  selected precisely because the market priced them below DCF value.
- Exit multiples still have the lowest dispersion under both truths. After removing each
  method's own bias, Gordon's error is 0.56–0.59 and the exits' is 0.22–0.36.
- **The ranking depends on the truth.** The firm's own multiple is best against the market
  (0.254) but only 4th against deals (0.433). Industry medians are best against deals. Acquirers
  look less like the firm's own market history than the market does.
- Against PE buyers, Gordon's disadvantage is half as large (0.06 vs 0.13 for strategic
  buyers). The sample is small (155 / 374).

Caveat: small common sample (211). This is exploration only.
