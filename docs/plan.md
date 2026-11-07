# Terminal Value Lab: research plan (draft, 2026-11-07)

Status: data collected and verified, including discount-rate data (2026-11-07). The three
decisions in section 9 are made. Design not yet frozen. Nothing has been estimated on outcomes.

## 1. Questions

- **Q1.** Which terminal-value (TV) formula, Gordon growth or exit multiple, better predicts a
  firm's actual enterprise value five years later? Overall, by industry, and by firm type.
- **Q2.** Can AI agents (SignalLab design: Liu, Liu, Liu & Mei 2026) write interpretable
  conditional TV rules ("which method, with which parameters, for which firms") that beat the
  best single method and random search with the same budget?
- **Q3 (secondary).** Full DCF at t (realized FCF t+1..t+5 + TV) against market EV at t.
  Shows the circularity of exit multiples: they borrow the market's multiple, so grading
  against today's price mechanically favours them. This is why Q3 is not the main test.

## 2. Data (done)

- ValuationLab panel (`../valuation-lab`, `panel_with_holdout.pkl`): FY2015–2025, 33,606
  firm-years, US-listed non-financials, market value ≥ $100M at the valuation date (June 30 of
  t+1), delisted firms kept.
- New FactSet cash-flow fields, `data/raw/factset_tv_YYYY.xlsx`, YYYY = 2016–2026 (FY YYYY-1):
  CFO, interest on debt, income taxes, pretax income, D&A (cash flow), current assets,
  current liabilities, stock-based compensation, plus FYE / sales / capex for reconciliation.
  Formulas and pitfalls: `docs/factset_export.md`. All 11 files pass
  `scripts/check_tv_exports.py` (FYE, sales, capex match ValuationLab exports ~100%).
- First merge (2026-11-07): CFO coverage 99.9% of panel rows.
  - Unlevered FCF = CFO + interest × (1 − t) − capex, t = income tax / pretax income clipped to
    [0, 0.4], 21% when pretax ≤ 0. CFO already contains the cash-flow-statement change in
    working capital, so balance-sheet ΔNWC is only a diagnostic (no short-term debt field;
    acquisitions distort it).
  - FCF ≤ 0 in 39% of firm-years; EBITDA ≤ 0 in 32%.
  - 5-year windows: start FY2015–2020, 1,900–2,200 firms each; 10,918 complete 5-year FCF paths.
  - Attrition to t+5 within the panel: 29–42% (acquired, delisted, or below $100M).
- Known gaps: Apple and some others stop reporting interest separately (FY2024+): treat as 0
  or estimate.
- Discount-rate data (2026-11-07, done): FRED DGS10, Damodaran monthly + annual implied ERP,
  US industry betas (Jan 2016–Jan 2026 releases), default spreads by rating, coverage → rating
  table, industry WACC files, and firm → industry mapping (62% ticker, 38% SIC). Tables in
  `data/processed/`, built by `scripts/build_damodaran.py`; details and point-in-time keys
  in `docs/damodaran_data.md`.

## 3. Main test: TV forecast against actual EV at t+5

At start year t, compute TV at t+5 and compare with actual EV at t+5 (ValuationLab EV
definition, market data June of t+6).

- **Perfect foresight (primary):** use realized FCF and EBITDA of year t+5, so cash-flow
  forecasting error drops out and only the TV formula is graded. Multiples, g and discount
  rate use information available at t only.
- **Realistic variant (secondary):** forecast year-t+5 fundamentals from information at t.

| Method | Variants (also the agents' building blocks) |
|---|---|
| Gordon | g ∈ {2, 2.5, 3%}; FCF: year t+5, 3-year average, minus SBC, value-driver NOPAT × (1 − g/ROIC) |
| Exit multiple | industry median EV/EBITDA at t; firm's own multiple at t; 5-year average industry multiple (mean reversion); ValuationLab agent peer recipe |
| Blend | w × Gordon + (1 − w) × Exit |
| Reference only (look-ahead) | actual industry multiple at t+5: measures how much error comes from multiple drift |

- Discount rate (proposed, practitioner-style WACC, all free data, no price data needed):
  - risk-free: 10-year Treasury at the valuation date (FRED DGS10);
  - ERP: Damodaran implied ERP for that year (histimpl);
  - beta: Damodaran US industry unlevered beta from the vintage published at t (annual
    archive, January releases), relevered with the firm's market D/E and tax rate;
  - cost of debt: rf + spread from Damodaran's interest-coverage → synthetic-rating table
    (or interest / total debt from our data as a check);
  - weights: market cap and total debt (already in the panel).
  Use only the Damodaran vintage available at t (no look-ahead). Industry mapping done
  (96 groups; see `docs/damodaran_data.md`). Robustness: Treasury + 5% (beta = 1).
  A price-based Beta/WACC lab stays a later extension.
- Score: median |ln(TV / EV_{t+5})| (same scale as ValuationLab); also median signed error
  (bias) and share of firms where the method is defined.
- Undefined cases (FCF ≤ 0 for Gordon, EBITDA ≤ 0 for exit): intention-to-treat, i.e. a fixed
  penalty or a pre-declared fallback, never silent exclusion (else each method picks easy firms).
- Industries reported on Fama-French 12 (built from SIC); SIC2 too sparse (59 groups).
- Diagnostics practitioners use: Gordon-implied exit multiple and exit-implied perpetual growth.

## 4. Hypotheses (directions fixed before exploration)

- H1. Standard Gordon (g 2.5%) undervalues: its implied multiple is below market multiples.
- H2. Gordon does relatively best in stable, low-growth, FCF-positive industries (utilities,
  staples) and worst in high-growth / high-R&D industries.
- H3. In cyclical industries, a long-run average multiple beats the multiple at t (mean reversion).
- H4. Blends beat either pure method (forecast combination).
- H5. Agents' conditional rules beat the best single method and random search (same budget).

## 5. Sample split

| Part | Start t | Outcome t+5 | Note |
|---|---|---|---|
| Exploration | FY2015–16 | FY2020–21 | free use |
| Validation | FY2017–18 | FY2022–23 | open once |
| Test | FY2019–20 | FY2024–25 | outcome years were opened before as ValuationLab / Comps Range Lab holdout: disclose |

- Prospective test: freeze finalists and evaluate on FY2026+ data when available (true
  out-of-sample; the limitation the SignalLab paper itself names).
- Overlapping windows: firm-clustered bootstrap. Robustness: 3-year windows (t = FY2015–22).

## 6. Survivorship

1. Do not apply the $100M filter at t+5 (keep shrunken survivors; use raw exports).
2. Report attrition by method and industry.
3. Sensitivity: inverse-probability weighting from a survival model.
4. No acquisition prices: stated limitation (FactSet M&A data possible later).
5. FMP (already paid, no new cost) can classify exits: delisted-company list (delisting date)
   and M&A records → acquired vs failed vs shrank below $100M. Not needed for the core test;
   use only for exit classification, and never mix FMP fundamentals into FactSet numbers
   without a reconciliation check. FMP prices are also the source for the return-signal
   extension and a Beta/WACC lab (check delisted-ticker coverage first).

## 7. Agents (same architecture as ValuationLab / Comps Range Lab)

- TV-recipe DSL: JSON, conditions on firm traits (≤ 2–3 levels) → method + parameters;
  deterministic validator.
- Loop: proposer (mechanism + falsifiable prediction) → blind critic → deterministic grader →
  archive. Claude Code subagents only (no paid API).
- 5 runs × 30 proposals; optionally a 150-proposal long search (ValuationLab ablation found
  30-proposal gains came from prior knowledge).
- Benchmarks: practitioner Gordon, industry exit, 50/50 blend, random search (same budget),
  GBM ceiling (share of GBM gain captured, as in Comps Range Lab).
- LLM leakage risk: agents know 2020–25 history (e.g. 2021 tech multiples). Recipes see
  only firm traits, never names or dates; consider a de-identified check.

## 8. Phases

Phase 0 done 2026-11-07: `tvlab/panel.py`, `docs/panel.md`. New finding: about 5% of
universe market caps are untrustworthy (reverse-split mis-scaling, shells, de-SPAC
mismatches). The `quality_ok` flag is applied as the sample screen (user agreed 2026-11-07);
it is written into the protocol at Phase 2.

Phase 1 done 2026-11-07 (exploration years only): `docs/phase1_exploration.md`. Exit
multiples beat Gordon by 0.16 in median |ln error| (CI 0.12–0.19). H1 came out opposite
(Gordon overvalues at the low rates of 2016–17) and H2 reversed (Gordon worst where WACC is
low). H3 is supported in Energy. A fixed 50/50 blend does not help (H4).

| Phase | Work | Est. |
|---|---|---|
| 0 Panel | merge module, FCF / tax / FF12 definitions, QA (CFO vs EBITDA − capex − tax, outliers), Treasury rate, Damodaran ERP / industry betas / spread table (vintages FY2015–25) + SIC mapping | 1–2 days |
| 1 Explore | exploration years only: errors by method, industry patterns, Gordon-implied multiples, g / r sensitivity | 1–2 days |
| 2 Protocol | freeze hypotheses, tests T1–T4, statistics; push | 0.5 day |
| 3 Agent runs | 5 runs + random control + GBM; freeze finalists | 1–2 days |
| 4 Validate → test | each opened once | 0.5 day |
| 5 Write-up | README, site, portfolio entry | 1 day |


## 9. Decisions (made 2026-11-07)

1. Grading: actual EV at t+5 is primary; market EV at t is secondary (Q3). **Yes.**
2. Discount rate: Damodaran-based WACC (section 3). **Yes**; Treasury + 5% as robustness.
3. FY2024–25 outcomes are the test set, with disclosure that they were opened before. **Yes.**
4. Pre-2015 FactSet history (FY2005–14) for more rate regimes: **No** (too costly; decided
   2026-11-07). Disclose that the sample is post-2015 and mostly low-rate. The r − g
   mechanism is tested cross-sectionally (low- vs high-WACC firms within a year) and across
   cohorts (rf 0.7–2.9% at t; outcomes 2020–25). Horizon-3 windows reach t = 2022.
5. Exit classification and acquisition prices: FactSet (not FMP). **Done 2026-11-07**
   (`docs/exits.md`): of 2,589 leavers, 1,411 were acquired, 783 are inactive with no deal,
   and 343 are still listed. 79% of exited 5-year windows are acquisitions with an observed
   price. How they enter grading is a Phase 2 decision.

## 10. Extensions toward a deeper study

1. **TV disagreement / market-implied growth as a return signal** (most promising): does the
   Gordon-vs-exit gap or implied g predict future stock returns? Fits the SignalLab
   evaluation pipeline (Fama-MacBeth) directly. Needs monthly returns (FMP, already paid, or FactSet).
2. **Decomposing DCF error:** cash-flow forecast vs TV vs discount rate, by adding a
   Beta/WACC lab and a forecast lab.
3. **Prospective test** of frozen rules on FY2026–27 data.
4. **LLM look-ahead leakage:** agent performance on named vs de-identified data.

Pick 1 or 2 as the next extension after the main test; register 3 when finalists are frozen.
