# Exits: who leaves the panel and why (2026-11-07)

Code: `scripts/build_exits.py` → `data/processed/exits.csv` (git-ignored).

## Data (FactSet, two exports)

1. **Transactions screen** (Screening → Transactions → M&A). Settings:
   - Transaction type: Acquisition / Merger or Majority Stake.
   - Company Type **At Deal** (Target) = Public. Do not use "Company Type Current": it drops
     acquired targets, which are no longer public, and gave only 341 deals.
   - Deal status Completed; announced ≥ 2014-01-01; completed 2014-01-01 … 2026-11-07.
   - No country filter, so US-listed foreign-incorporated firms are kept.
   - Result: 12,184 deals, downloaded in two parts because of the 10,000-row download limit:
     `factset_ma_deals_1.xlsx` (completed 2014–2019, 5,990) and `_2.xlsx` (2020–2026, 6,194).
   - Columns: Company Entity ID (Target/Issuer) **and** (Buyer/Investor), names, announce and
     completion dates, transaction value and EV at completion, EV (announcement), market cap
     at deal, going private, PE buyer, cash % / stock %, EV/EBITDA.
2. **Universal Screening probe** (`factset_exit_probe.xlsx`): US, inactive securities included,
   with Security Listing Status (1 = inactive, 0 = active). The MergerStat company fields
   (`FMG_CLOSE_DATE_CO` etc.) return the latest deal **in any role**, including deals as buyer
   (e.g. Red Hat → 2025, Twitter → 2025). They cannot identify takeovers, so they are not used.

Known cases verified: Twitter/Musk 2022-10-27, Red Hat/IBM 2019-07-09, Activision/Microsoft
2023-10-13, Celgene/BMS 2019-11-20, Xilinx/AMD 2022-02-14, Tiffany/LVMH 2021-01-07.

## Classification of the 2,589 firms that left the panel

| Type | Firms | Rule |
|---|---|---|
| acquired | 1,411 | completed deal as target, completion after the last FYE and ≤ 18 months after the last valuation date |
| inactive | 783 | listing inactive, no matching deal (bankruptcy, going dark, other) |
| listed | 343 | still listed; left the panel for data reasons (stale statements, filters) |
| acquired_late | 52 | deal outside the window (mostly earlier majority stakes); not an exit cause |

Completion typically comes 7–17 months after the last fiscal year-end (median 11.7). That is
the expected pattern: the last annual report, then the deal, then no further reports.
Among acquisitions, 98.9% are full acquisitions and 98.7% have a deal value. 26% have a PE
buyer and 37% are take-privates.

**In the 5-year windows**, 3,231 of the 4,097 exited windows (79%) are acquisitions, 618 are
inactive and 218 are still listed. Most attrition is M&A with an observed price, not failure.

## Acquisition EV (corrected 2026-11-07)

FactSet's transaction value includes **gross debt assumed**. Test on 809 deals with a
pre-announcement panel price. We take the implied **equity** premium (equity paid / market cap)
by leverage bin; the right definition should give a flat premium at a plausible level.

| Reading of transaction value | Premium by leverage (net cash > 20% … net debt > 100% of mcap) | Spread |
|---|---|---|
| equity only | 0.32, 0.32, 0.39, 0.50, 0.61, 1.12 | 0.80 |
| **equity + gross debt** | **0.29, 0.27, 0.24, 0.25, 0.10, 0.18** | **0.19** |
| equity + net debt | 0.58, 0.38, 0.33, 0.28, 0.21, 0.28 | 0.38 |

Examples: Sprint (market cap $27B, transaction value $64B) and Celgene include debt. Red Hat
and Activision are equity only. FactSet mixes the two by deal, but gross debt dominates.

Rule (balance sheet and deal value only; no market prices, so truth D is not tied to D′):
- `gross` (1,280 deals): deal EV = transaction value − cash + minority + preferred.
- `equity_only` (102 deals, transaction value ≤ debt): deal EV = transaction value + debt +
  minority + preferred − cash.

Re-check on exploration-window deals only (428 deals): the gross-debt reading is again the
flattest (spread 0.14 vs 0.88 and 0.29). Script: `scripts/check_deal_ev_definition.py`.
In 44 of 801 gross-rule deals, cash exceeds the transaction value, giving deal EV ≤ 0; they
drop out of truth D and are reported.

Robustness: firms with |net claims| < 20% of market cap, where both readings nearly coincide.
FactSet's "EV at completion" equals the transaction value in 85% of deals and is not used.

## Open protocol decision (Phase 2)

How acquired windows enter the main test. Proposed:
- Superseded: acquired firms have no t+5 statements, so they are graded at their last
  pre-deal year (truth D in `docs/protocol.md`), not rolled forward to t+5.
- **Robustness:** survivors only; and acquired firms graded at the completion date against TV
  discounted back from t+5.
- Inactive firms (no price): intention-to-treat with a pre-declared rule. One option is
  outcome EV = 0 (or ≈ debt recovery), reported separately; they are 15% of exits.
