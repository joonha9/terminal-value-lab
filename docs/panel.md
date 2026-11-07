# Phase 0 panel: definitions and QA (2026-11-07)

Code: `tvlab/panel.py`; build + QA: `python3 -P terminal-value-lab/scripts/build_panel.py`.
Outputs (git-ignored) in `data/processed/`: `firm_years.pkl`, `windows_h5.pkl`, `windows_h3.pkl`.

## Construction

1. **Wide panel.** ValuationLab exports FY2015–2025, read with ValuationLab's own reader and
   filters (ordinary shares, non-financial, statements ≤ 18 months old) **without** the $100M
   floor: 61,874 firm-years. `in_universe` (mkt cap ≥ $100M) reproduces
   `panel_with_holdout.pkl` exactly: 33,606 rows, 0 differences, EV and EBITDA identical.
   Firms that shrink below $100M keep their t+5 outcome row.
2. **Cash-flow fields** from `factset_tv_YYYY.xlsx` merged on Entity ID and FY. Coverage in
   the universe: CFO ≥ 99.8% every year, interest 89–98%, taxes/pretax ~100%, SBC 77–89%.
   Fiscal year-ends agree with ValuationLab in 100% of rows.
3. **Definitions**
   - Tax rate = income tax / pretax income clipped to [0, 0.40]. When pretax ≤ 0, use the
     federal statutory rate (35% to FY2017, 21% from FY2018). Median 21%.
   - Unlevered FCF = CFO + interest × (1 − tax) − capex. Missing interest = 0 (6.8% of rows;
     5.9% have debt). FCF-ex-SBC subtracts stock-based compensation.
   - NOPAT = EBIT × (1 − tax). FF12 from SIC (Ken French definitions).
   - Check: simple FCF (EBITDA − tax on EBIT − capex, no working capital) has Spearman 0.83
     with our FCF/sales; medians are 4.9% and 5.6% of sales.
4. **WACC** at June 30 of t+1, as in `docs/damodaran_data.md`. Marginal tax τ = 40% for
   t ≤ 2016 and 25% after (TCJA known by June 2018). D/E uses market cap and total debt.
   Coverage = EBIT / interest gives a synthetic rating (large firms: market cap > $5B).
   No debt gives AAA. Debt with missing or zero interest gives BBB. Small firms use Damodaran's
   "smaller and riskier" table (AAA above coverage 12.5). The first version wrongly used the
   financial-services table; fixed 2026-11-07.
   Median WACC by year (after the rating-table fix): 7.6, 7.1, 7.8, 8.4, 6.8, 5.1, 8.2, 10.0,
   8.8, 8.6, 8.5% (t = 2015…2025).
   By FF12: Utils 5.7% (lowest) to Hlth 8.8% (highest). No row has WACC < rf.
   Rating mix: AAA 27%, D 25%, BBB 15% (BBB includes debt with missing or zero interest, 12%). D arises when EBIT < 0. That is Damodaran's mechanics, and the
   debt weight is usually small. β_L > 3 for 2.7% of rows.
5. **Windows.** One row per (firm, t) for firms in the universe at t, holding realized FCF
   t+1…t+H and fundamentals and EV at t+H. Status at t+H: survived (≥ $100M), shrank (< $100M),
   or exited (no row).

## Data-quality flag (new finding)

`MktVal Co` cannot be trusted for about 5% of universe rows (1,695). Three cases:
- **Reverse-split mis-scaling**: e.g. JAGX FY2017 market cap = $710 quadrillion; FOXO, DUO,
  ADIS, DCX, MMEX similar. 801 firm-to-firm-year jumps exceed 100×.
- **Shells**: OTC firms with < $1M of assets priced above $100M.
- **De-SPAC years**: statements of the pre-merger company paired with the post-merger
  market cap (e.g. Nikola, Canoo, Hyzon FY2019–20).

Rule `quality_ok` = total assets ≥ $10M **and** market cap / total assets ≤ 100. Each rule
alone catches 1,606 / 1,330 rows, 1,241 by both. It uses only data at the date of the row.
Proposed protocol: require `quality_ok` at t. Drop windows whose t+5 row fails it (85 windows;
mostly mis-scaled outcome EVs). Report both numbers. The same flaw sits in the ValuationLab
universe; its effect on ValuationLab's published errors is not yet measured.

Possible fix later: correct market caps from FMP (paid subscription) historical market cap.

## Sample (horizon 5)

| t | universe | survived | shrank | exited | complete FCF path |
|---|---|---|---|---|---|
| 2015 | 2,749 | 1,948 | 87 | 714 | 2,024 |
| 2016 | 2,770 | 1,902 | 198 | 670 | 2,088 |
| 2017 | 2,908 | 1,934 | 283 | 691 | 2,202 |
| 2018 | 2,832 | 1,905 | 266 | 661 | 2,157 |
| 2019 | 2,775 | 1,882 | 252 | 641 | 2,125 |
| 2020 | 3,810 | 2,200 | 430 | 1,180 | 2,618 |

Clean windows (quality ok at t and at t+5): exploration 5,322, validation 5,420, test 5,998.
In 8,605 clean windows both FCF and EBITDA at t+5 are positive (both TV methods defined).
The t = 2020 cohort has more exits (42%); it includes the 2021 de-SPAC wave.
Horizon 3 (robustness, t = 2015–2022): 24,795 windows, 23,329 clean.
