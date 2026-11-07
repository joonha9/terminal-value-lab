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

## Acquisition EV

`acq_ev` = deal value (equity, full acquisitions only) + debt + minority interest + preferred
− cash, all from the firm's last panel row. This matches the panel's EV definition.

- ln(acq EV / last panel EV): median +0.31 (premium plus drift).
- Premium, ln(deal equity / market cap at deal): median +0.39.
- FactSet's "EV at completion" equals the transaction value in 78% of deals. It often omits
  net debt (Activision: EV = equity value despite > $13B cash), so it is not used. It is kept
  in the file for reference.

## Open protocol decision (Phase 2)

How acquired windows enter the main test. Proposed:
- **Primary:** survivors + shrunk firms (as now), plus acquired firms with
  outcome = acq EV rolled forward from completion to the t+5 valuation date at WACC_t
  (proceeds reinvested at the cost of capital).
- **Robustness:** survivors only; and acquired firms graded at the completion date against TV
  discounted back from t+5.
- Inactive firms (no price): intention-to-treat with a pre-declared rule. One option is
  outcome EV = 0 (or ≈ debt recovery), reported separately; they are 15% of exits.
