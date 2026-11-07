# FactSet export: cash-flow fields (Terminal Value Lab)

Recorded 2026-11-06 because the original `ai_valuation` screen was lost and its formulas
had not been written down. These formulas reproduce the ValuationLab exports exactly.

## Screen setup

- FactSet Universal Screening, one criterion: **Exchange Country Name = United States**
  (~33k rows). The old ValuationLab exports had this filter (all 32,807 rows of the 2019 file
  are UNITED STATES). Without it the screen returns ~150k global rows and FactSet left the
  last-added columns empty ("-" / #N/A) or serving earlier results.
- Criteria options: Exclude Inactive Securities **unchecked** (keeps delisted firms);
  Exclude Secondary Listings and Exclude Non-Equity Securities checked.
- One file per valuation year: `data/raw/factset_tv_YYYY.xlsx`, YYYY = 2016 … 2026.
  Replace `YYYY0615` in every formula with that year (e.g. `20190615`).

| Heading | Formula |
|---|---|
| Entity ID | `FSYM_ENTITY_ID` |
| SIC Code | `FF_SIC_CODE` |
| Fiscal Period End Date | `FF_FISCAL_DATE(ANN_R,YYYY0615,RP,DATE)` |
| Capital Expend CF | `FF_CAPEX(ANN_R,YYYY0615,RP,USD)` |
| Net Cash Flow -Oper | `FF_OPER_CF(ANN_R,YYYY0615,RP,USD)` |
| Int on Debt Expense | `FF_INT_EXP_DEBT(ANN_R,YYYY0615,RP,USD)` |
| Total Income Taxes | `FF_INC_TAX(ANN_R,YYYY0615,RP,USD)` |
| Pretax Income | `FF_PTX_INC(ANN_R,YYYY0615,RP,USD)` |
| Deprec Deplete & Amort Exp-CF | `FF_DEP_EXP_CF(ANN_R,YYYY0615,RP,USD)` |
| Total Current Assets | `FF_ASSETS_CURR(ANN_R,YYYY0615,RP,USD)` |
| Total Current Liabs | `FF_LIABS_CURR(ANN_R,YYYY0615,RP,USD)` |
| Stock Option Cash Flow | `FF_STK_OPT_CF(ANN_R,YYYY0615,RP,USD)` |
| Net Sales | `FF_SALES(ANN_R,YYYY0615,RP,USD)` |

`ANN_R` = annual, restated. `RP` = "Latest Preliminary Reported Period" alignment.

**Equivalent, and the original ValuationLab method:** put the fiscal-year label `YYYY-1`
instead of the date (file 2017 → `FF_SALES(ANN_R,2016,RP,USD)`). FactSet labels fiscal years
that end in January–May with the prior year (Oracle's May-2017 year = "2016"), so label
`YYYY-1` selects year-ends from June YYYY-1 to early June YYYY, the same rows as `YYYY0615`
(checked on ORCL, NKE, FDX, WMT, NVDA, AAPL). **Never use `YYYY`**: that is the next fiscal
year, not yet reported at the valuation date (look-ahead; the checker caught it on 2026-11-07).

## Working procedure (settled 2026-11-07, file 2017)

New screen per year; paste the 13 formulas with **Add New**; wait until FactSet has filled
every column (columns fill left to right; the last one, Stock Option Cash Flow, comes last;
AAPL must show a number there) and only then export. Exporting earlier gave empty (#N/A)
columns or values left over from the previous year's formulas.

## Stale-column trap (seen 2026-11-06, file 2016)

Editing a formula's date in place can leave FactSet serving the previous results for that
column: the Parameters tab showed `20160615` for all columns, yet six columns exported
FY2018 values (identical to the 2019 file). Deleting those columns and re-adding them with
**Add New** fixed it. Before each export, check a known value in Results (AAPL FY2015
income taxes = 19,121; FY2018 = 13,372). `scripts/check_tv_exports.py` flags any column
identical across two files.

## Why June 15, not June 30

The date argument selects the latest fiscal period that **ended** on or before the date; it
is not a report-date cutoff. With `20190630`, June-30 year-end firms (e.g. MSFT) returned
the fiscal year ending that same day, which was not yet reported: look-ahead. The old
ValuationLab exports contain year-ends up to about June 1–3 only, and `YYYY0615`
reproduces them.

## Verification (FY2018 statements, file 2019)

Matched to `valuation-lab/data/raw/factset_2019.xlsx` on Entity ID, keeping for each entity
the row with the most non-missing values (an entity can have several security rows, some empty):

- Fiscal Period End Date: 8,117 pairs, 99.99% identical
- Net Sales: 100.00% within 0.5%
- Capital Expend CF: 7,996 pairs, 100.00% within 0.5%
- ValuationLab FY2018 panel: 2,831 of 2,832 firms found (missing: INDV, 133TLR-E).
  Coverage of new fields: CFO 97.5%, interest 93.4%, taxes 97.6%, pretax 97.6%,
  D&A 93.4%, current assets 97.6%, current liabilities 97.5%, SBC 85.8%.
