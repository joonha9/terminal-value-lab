# Q4 design: does the Gordon-vs-market gap predict stock returns? (DRAFT, not frozen)

Drafted 2026-11-07, after the v1 study closed (`docs/phase4_results.md`). Q4 is a separate
pre-registration (protocol v1 §1). **Returns have not been downloaded or looked at.**
Decisions still open are marked **[decide]**.

**Author decisions (2026-11-07):**
1. Holdout: option A, the full sample frozen in advance plus a live test.
2. S2 is reported only; it is not a hypothesis.
3. Delisting: −30% for performance delistings (Shumway), with robustness at 0% and −100%.
   §6 explains how performance delistings are identified.

## 1. Question and why it is interesting

v1 found that Gordon misses market EV five years later most badly where r − g is small (T3:
+0.57 on test). Two readings are possible:
1. **Formula error.** The 1/(r − g) term is convex, so small errors in WACC blow up the value.
   The market is right, and Gordon is wrong.
2. **Market mispricing.** Low-WACC firms really are worth more than the market pays, and the
   gap closes through returns.

Returns separate the two. Under reading 1, the discount-rate part of the gap carries no
information about returns. Under reading 2, it predicts them.

**The gap decomposes exactly.** With g fixed (2.5%):

    GAP = ln(Gordon_t / EV_t) = ln(FCF_t / EV_t) + ln((1 + g) / (WACC_t − g))
                                 cash-flow yield     discount-rate part

The first term is a known value signal (cash-flow yield). "Beyond known factors" therefore
means: beyond cash-flow yield, value, size, momentum, profitability, investment and beta.

## 2. Signals (point-in-time, valuation date June 30 of t+1)

All inputs are from the existing panel and are known at the valuation date:
- FCF and EV of fiscal year t, under the June-15 reporting rule;
- WACC_t built from June t+1 inputs.

Unlike v1, **no outcome-year fundamentals are used**: no perfect foresight.

| Signal | Definition | Role |
|---|---|---|
| S1 GAP | ln(Gordon_t / EV_t), Gordon = FCF_t (1+g)/(WACC_t − g), g = 2.5% | primary |
| S1a yield part | ln(FCF_t / EV_t) | decomposition |
| S1b discount-rate part | ln((1+g)/(WACC_t − g)) | decomposition |
| S2 TV disagreement | ln(Gordon_t / FF12-exit_t), FF12 exit = industry median EV/EBITDA × EBITDA_t | reported only (decided), independent of the firm's price |
| S3 implied g | g* solving Gordon = EV_t: (WACC·EV − FCF)/(EV + FCF) | reported only |

Defined where FCF_t > 0 and WACC_t − g ≥ 1 pp (the v1 rule). Coverage is reported.

## 3. Hypotheses (draft)

- **H9 [pre]:** S1 GAP predicts higher returns. In Fama-MacBeth, its slope is positive
  controlling for size, book-to-market, momentum (12-1), gross profitability, asset growth and
  beta.
- **H10 [pre]:** GAP's predictive power comes from its yield part, not its discount-rate part.
  - Test with S1a and S1b in the same regression, plus the controls.
  - The S1a slope is > 0. The S1b slope is two-sided, with the formula-error reading predicting
    0.
  - Because "no effect" cannot be proven, S1b's CI is reported against an economically small
    band of ±0.25% a month for the rank-scaled slope (a long-short spread). Power for this
    equivalence check is low (see §5), so an inconclusive answer is likely and will be reported
    as such.
- S2 (TV disagreement) is reported with the same regressions, outside the test family.

## 4. Sample and timing

- **Universe:** the v1 panel universe at t (US non-financials, market cap ≥ $100M at June 30 of
  t+1, `quality_ok`).
- **Formation:** each June 30 of t+1 for t = 2015 … 2024 (10 formations), with an annual hold
  from July t+1 to June t+2. The t = 2025 formation (June 2026) is included as a partial year.
- **Return months:** July 2016 to the latest full month, about 124 months.
- **Momentum** needs returns from June 2015.

### Holdout strategy (decided: A)

| Option | Description | For | Against |
|---|---|---|---|
| **A. Full sample, frozen in advance + live test (recommended)** | Freeze the whole design before downloading returns; run once on 2016–2026; then test the frozen spec live on the June 2027 and later formations | Returns are genuinely unseen; uses all ~124 months; live test is a true holdout | Fundamentals and EVs were seen in v1 (disclosed); one shot |
| B. Time split | e.g. 2016–20 explore, 2021–23 validate, 2024–26 test | Mirrors v1 | About 3 years per split, so Fama-MacBeth has little power |
| C. Backfill first | Export FactSet FY2005–2014 as well and split by time | 20 years, two rate regimes | Large export job (all fundamentals); Damodaran multiples start in 2013 (needed only for S2) |

## 5. Tests (draft)

1. **Fama-MacBeth:** monthly cross-sectional regressions of the next month's excess return on
   the signals and controls. Signals and controls are cross-sectional ranks scaled to
   [−0.5, 0.5], so slopes read as a long-short spread. Newey-West standard errors (lag 6) on
   the time series of slopes.
2. **Portfolio sorts:** quintiles of S1 each June, equal- and value-weighted (June market cap).
   Report the Q5 − Q1 return and its alpha on FF5 + momentum, with Newey-West errors.
3. **Multiple testing:** Holm across 3 statistics: H9 (S1 > 0), H10a (S1a > 0) and H10b
   (S1b ≠ 0, two-sided).
4. **Power, stated in advance:** with about 124 months and a long-short volatility of about
   3% a month, the standard error of a mean monthly spread is about 0.27%. Only spreads of
   about 0.55% a month or more are reliably detectable.

## 6. Data needed

| Data | Source | Status |
|---|---|---|
| Fundamentals, EV, WACC at t | existing panel (`data/processed/firm_years.pkl`) | have |
| Monthly total returns (with dividends), USD, June 2015 – latest, **including inactive / delisted firms** | FactSet (Universal Screening or the Excel add-in) | **to export** |
| Delisting outcomes | `data/processed/exits.csv` (acquired / inactive / listed) | have |
| FF5 + momentum factors, risk-free rate (monthly) | Kenneth French data library (free) | to download |
| Book equity, total assets, gross profit, beta | panel | have |

**Delisting returns (decided).**
- Acquired firms: the return through the last trading month, as reported by FactSet.
- **Performance delistings** with no final return: −30% in the delisting month (Shumway 1997).
  Robustness at 0% and −100%.
- **Open item:** `exits.csv` "inactive" is not the same as failure. It includes corporate
  reorganisations; for example, Match Group and IAC (2020) are "inactive" with large market
  caps. A rule that identifies performance delistings must be fixed before freezing. The
  options depend on what the FactSet probe returns:
  - a delisting-reason field, if FactSet has one;
  - otherwise a proxy fixed in advance, such as last price below $1, or market cap down more
    than 50% over the final 12 months.

## 7. Checks before freezing

- Recompute S1 and confirm it reproduces v1's Gordon at t on the same rows. (v1 used FCF_t+5;
  only the cash-flow year differs.)
- Return-data checker: compare FactSet monthly returns with price changes for 10 large firms;
  confirm delisted firms appear; confirm no return month precedes the formation date.
- Independent code review before the first run on returns, as in v1.

## 8. Disclosure

- Fundamentals and EVs for all years were used in v1, including the market EV five years
  after each t. That is a different object from monthly returns, but related: v1's T2/T3 show
  how Gordon_t+5 relates to EV_t+5.
- The v1 test period showed a market-wide fall in multiples between 2020–21 and 2025–26.
