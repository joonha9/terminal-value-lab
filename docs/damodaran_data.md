# Discount-rate data (Damodaran + FRED), downloaded 2026-11-07

All free. Raw files in `data/raw/damodaran/` and `data/raw/fred_dgs10.csv`; tidy tables built by
`scripts/build_damodaran.py` into `data/processed/`.

## Point-in-time rule

Fiscal year t is valued on June 30 of t+1. For t we use only what was public by then:

| Input | Source file | Key for fiscal year t |
|---|---|---|
| Risk-free | FRED DGS10 (daily) | last obs. in June t+1 |
| ERP (main) | `ERPbymonth.xlsx`, column "ERP (T12m)" | month start June 1, t+1 |
| ERP (robustness) | `histimpl.xls`, "Implied ERP (FCFE)" | row Year = t (published Jan t+1) |
| Industry unlevered beta | `betas{tt}.xls`, tt = t mod 100 (2025 → current `betas.xls`) | `vintage_t = t` |
| Default spread by rating | `bondspreads24.xlsx` (2015–2025 labels) + current `ratings.xls` (2026) | label year t+1 |
| Coverage → rating | current `ratings.xls`: "large non-financial" block (mkt cap > $5B) and the separate "smaller and riskier non-financial" block lower in the sheet. The block beside the large table is for **financial-service firms** and is not used. | same for all years |

**File-name trap:** `betasYY.xls` is the January YY+1 release (`betas16.xls` = 2017-01-05). The
build script asserts each file's "Date updated" equals January t+1.

Coverage thresholds are identical in the 2021, 2024 and 2026 rating files, so one table is used.
Spread labels: "Spread 2016" = January 2016 release (bondspreads16 carries labels 2016 and 2015).
The `bondspreads24` file says "Date updated 2024-01-05" but contains a 2025 column. The label
year, not that cell, is taken as the release year.

## Industry mapping (firm → Damodaran industry, 96 groups)

`indname.xls` (current, Jan 2026) lists ~48k global firms with Damodaran industry, ticker and
Capital IQ SIC code. Mapping, in order:

1. **Ticker** match to US-listed firms (NYSE / Nasdaq / NYSEAM), kept only if name similarity
   ≥ 0.6 (99% of ticker hits pass). Covers **62.1% of panel rows**.
2. Otherwise **FactSet SIC4 → majority industry among the ticker-matched firms**, then SIC3,
   SIC2: 35.6% / 1.5% / 0.6% of rows. The mapping is built in FactSet SIC space because Capital
   IQ SIC codes agree with FactSet SIC4 for only 35% of matched firms.
3. Otherwise "Total Market (without financials)": 0.1%.

Quality (leave-one-out on matched firms): SIC4 mapping picks the exact industry 62% of the time,
but the beta error is small: |β_pred − β_true| median 0.00, mean 0.056, p90 0.16 (cross-industry
SD of unlevered beta is 0.22). About 0.3 pp of cost of equity on average.

Limitations to disclose:
- Classification is the 2026 snapshot applied to all years (membership look-ahead; the betas
  themselves are point-in-time).
- Delisted firms are mostly mapped by SIC (they are not in the current list).
- Jan-2016 release (t = 2015) has no "Total Market (without financials)" row; use "Total
  Market" for the 0.1% market-fallback firms in that year.
- "Retail (Online)" exists only through the Jan-2023 release; the current list never assigns it.

## Values at the valuation date

| t | DGS10 | ERP (June, T12m) | ERP (Jan, FCFE) | BBB spread | Market unlevered β (cash-adj.) |
|---|---|---|---|---|---|
| 2015 | 1.49% | 6.12% | 6.12% | 2.25% | 0.73* |
| 2016 | 2.31% | 5.29% | 5.69% | 1.60% | 0.85 |
| 2017 | 2.85% | 5.06% | 5.08% | 1.27% | 0.90 |
| 2018 | 2.00% | 5.93% | 5.96% | 2.00% | 1.00 |
| 2019 | 0.66% | 5.45% | 5.20% | 1.56% | 1.01 |
| 2020 | 1.45% | 4.10% | 4.72% | 1.71% | 0.86 |
| 2021 | 2.98% | 5.07% | 4.24% | 1.59% | 1.04 |
| 2022 | 3.81% | 5.25% | 5.94% | 2.00% | 1.12 |
| 2023 | 4.36% | 4.27% | 4.60% | 1.47% | 0.97 |
| 2024 | 4.24% | 4.23% | 4.33% | 1.20% | 0.98 |
| 2025 | 4.44% | 4.31% | 4.23% | 1.11% | 0.90 |

\* incl. financials (see above).

## WACC recipe (to implement in the panel module)

- β_L = β_U,cash-adj × (1 + (1 − τ) × D/E_market), τ = marginal 25% (Damodaran's choice; robustness: the effective rate from our data).
- k_e = DGS10 + β_L × ERP.
- Coverage = EBIT / interest → rating → spread; k_d = DGS10 + spread; after-tax × (1 − τ).
- WACC = E/(D+E) × k_e + D/(D+E) × k_d(1 − τ), E = market cap, D = total debt (panel).
- Fallback (robustness): Treasury + 5%, β = 1.

Industry cost-of-capital files `wacc{tt}.xls` are also downloaded, as a check on our WACCs.

## Industry EV/EBITDA (added for Phase 1)

`vebitda{tt}.xls` (Jan 2014 – Jan 2026 releases; current taxonomy from the Jan-2014 release)
→ `multiples_by_vintage.csv`. Aggregate multiple (sum EV / sum EBITDA). From the Jan-2018
release there are two blocks, "only positive EBITDA firms" and "all firms". We use "all
firms", and the single block before that. The 5-year average for t uses releases t−4…t,
with at least 2; t = 2015 and 2016 have only 3 and 4 releases.
