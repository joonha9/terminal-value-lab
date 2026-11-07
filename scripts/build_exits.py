"""Classify firms that leave the panel, and attach acquisition values.

    python3 -P terminal-value-lab/scripts/build_exits.py

Inputs (git-ignored):
  data/raw/factset_ma_deals_{1,2}.xlsx   FactSet Transactions screen: M&A, Acquisition/Merger or
                                         Majority Stake, target public at deal, completed,
                                         announced >= 2014, completion 2014-01-01..2026-11-07
                                         (split in two for the 10,000-row download limit)
  data/raw/factset_exit_probe.xlsx       Universal Screening, US, inactive included:
                                         Security Listing Status (1 = inactive)
Output: data/processed/exits.csv, one row per firm that ever left the panel.

Exit types
  acquired       completed deal as target, completion in (last FYE, last valuation date + 18 m]
  acquired_late  completed deal as target outside that window (reported, not used as outcome)
  inactive       listing inactive and no matching deal (bankruptcy, going dark, other)
  listed         security still active: firm left the panel for data reasons (stale
                 statements, filters), not a real exit
"""
from __future__ import annotations

import glob
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tvlab import panel as P  # noqa: E402

NA = ["-", "", "NA", "#N/A", "@NA"]
WINDOW_AFTER_VALUE_DATE = pd.DateOffset(months=18)


def load_deals() -> pd.DataFrame:
    files = sorted(glob.glob(str(P.RAW / "factset_ma_deals_*.xlsx")))
    d = pd.concat([pd.read_excel(f, header=3, na_values=NA) for f in files], ignore_index=True)
    assert not d["Deal ID"].duplicated().any()
    d = d.rename(columns={
        "Company Entity ID (Target/Issuer)": "id", "Company Name (Target/Issuer)": "target_name",
        "Company Name (Buyer/Investor)": "acquirer", "Company Entity ID (Buyer/Investor)": "acquirer_id",
        "Announcement Date": "announce_date", "Completion Date": "complete_date",
        "Transaction Type": "transaction_type", "Deal Type": "deal_type",
        "Transaction Value at Completion (MM)": "deal_value", "Enterprise Value at Completion (MM)": "deal_ev_fs",
        "Enterprise Value (EV)": "deal_ev_fs_announce",
        "Market Cap (at deal) (MM) (USD) (Target/Issuer)": "mktcap_at_deal",
        "Going Private (Target/Issuer)": "going_private", "Private Equity Buyer": "pe_buyer",
        "Cash (%) - Consideration": "cash_pct", "Stock (%) - Consideration": "stock_pct",
        "EV/EBITDA": "deal_ev_ebitda",
    })
    for c in ("announce_date", "complete_date"):
        d[c] = pd.to_datetime(d[c], errors="coerce")
    return d


def load_listing_status() -> pd.Series:
    f = P.RAW / "factset_exit_probe.xlsx"
    probe = pd.read_excel(f, header=None, nrows=30)
    h = next(i for i, v in enumerate(probe.iloc[:, 0].astype(str)) if v.strip() == "Symbol")
    s = pd.read_excel(f, header=h, na_values=NA).dropna(subset=["Entity ID"])
    # an entity may have several securities; inactive only if every one is inactive
    return s.groupby("Entity ID")["Listing Status"].min()


def main() -> None:
    fy = pd.read_pickle(P.PROC / "firm_years.pkl")
    ex = pd.read_csv(P.PROC / "exit_ids.csv")
    last = (fy.sort_values("fiscal_year").groupby("id")
              .agg(last_fy=("fiscal_year", "last"), last_fye=("fye_date", "last"),
                   last_value_date=("value_date", "last"), last_mkt_cap=("mkt_cap", "last"),
                   last_ev=("ev", "last"), last_debt=("total_debt", "last"), last_cash=("cash", "last"),
                   last_minority=("minority_interest", "last"), last_preferred=("preferred", "last"),
                   last_quality_ok=("quality_ok", "last")))
    ex = ex.merge(last, left_on="id", right_index=True, how="left")
    ex["listing_status"] = ex["id"].map(load_listing_status())

    deals = load_deals()
    d = deals[deals["id"].isin(ex["id"])].merge(ex[["id", "last_fye", "last_value_date"]], on="id")
    d["in_window"] = (d.complete_date > d.last_fye) & (d.complete_date <= d.last_value_date + WINDOW_AFTER_VALUE_DATE)
    # prefer an in-window deal, then the earliest completion after the last FYE
    d["after"] = d.complete_date > d.last_fye
    d = d.sort_values(["id", "in_window", "after", "complete_date"], ascending=[True, False, False, True])
    best = d.drop_duplicates("id")
    keep = ["id", "complete_date", "announce_date", "acquirer", "acquirer_id", "transaction_type", "deal_type",
            "deal_value", "deal_ev_fs", "deal_ev_fs_announce", "mktcap_at_deal", "going_private", "pe_buyer",
            "cash_pct", "stock_pct", "deal_ev_ebitda", "in_window"]
    ex = ex.merge(best[keep], on="id", how="left")

    ex["exit_type"] = np.select(
        [ex.in_window.eq(True), ex.complete_date.notna(), ex.listing_status.eq(0)],
        ["acquired", "acquired_late", "listed"], default="inactive")

    # acquisition EV on the panel's EV definition: equity paid + last balance-sheet net claims
    net_claims = (ex.last_debt.fillna(0) + ex.last_minority.fillna(0) + ex.last_preferred.fillna(0)
                  - ex.last_cash.fillna(0))
    full = ex.transaction_type.eq("Acquisition / Merger")
    ex["acq_equity"] = ex.deal_value.where(full)
    ex["acq_ev"] = ex.acq_equity + net_claims
    ex["acq_ev_source"] = np.where(ex.acq_ev.notna(), "deal_value+net_debt", None)
    ex.to_csv(P.PROC / "exits.csv", index=False)

    # ---- report -----------------------------------------------------------------------
    print(f"firms that left the panel: {len(ex):,}")
    print("exit type:", ex.exit_type.value_counts().to_dict())
    a = ex[ex.exit_type.eq("acquired")]
    gap = (a.complete_date - a.last_fye).dt.days / 30.4
    print(f"acquired: months from last FYE to completion, quantiles {gap.quantile([.1, .5, .9]).round(1).to_dict()}")
    print(f"acquired: full acquisitions {full[a.index].mean():.3f}; deal value present {a.deal_value.notna().mean():.3f}; "
          f"PE buyer {a.pe_buyer.eq('Yes').mean():.3f}; going private {a.going_private.eq('Yes').mean():.3f}")
    r1 = np.log(a.acq_ev / a.last_ev).where((a.acq_ev > 0) & (a.last_ev > 0))
    r2 = np.log(a.deal_ev_fs / a.last_ev).where((a.deal_ev_fs > 0) & (a.last_ev > 0))
    r3 = np.log(a.acq_equity / a.mktcap_at_deal)
    print("ln(acq EV ours / last panel EV):", r1.quantile([.05, .25, .5, .75, .95]).round(3).to_dict())
    print("ln(FactSet EV at completion / last panel EV):", r2.quantile([.05, .25, .5, .75, .95]).round(3).to_dict())
    print("ln(deal equity / market cap at deal) = premium:", r3.quantile([.05, .25, .5, .75, .95]).round(3).to_dict())
    print("acquired_late: months from last FYE:",
          ((ex[ex.exit_type.eq('acquired_late')].complete_date - ex[ex.exit_type.eq('acquired_late')].last_fye).dt.days / 30.4)
          .quantile([.1, .5, .9]).round(1).to_dict())

    # windows view (h5): what the 'exited' windows become
    w = pd.read_pickle(P.PROC / "windows_h5.pkl")
    w = w[w.quality_ok_t & w.status.eq("exited")].merge(ex[["id", "exit_type", "complete_date"]], on="id", how="left")
    w["complete_by_tH"] = w.complete_date <= pd.to_datetime((w.t + P_HORIZON + 1).astype(str) + "-06-30")
    print("\nexited h5 windows (quality ok at t) by exit type:")
    print(pd.crosstab(w.t, w.exit_type, margins=True).to_string())


P_HORIZON = 5

if __name__ == "__main__":
    main()
