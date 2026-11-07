"""Which reading of FactSet's transaction value is right? (docs/exits.md)

    python3 -P terminal-value-lab/scripts/check_deal_ev_definition.py [--exploration-only]

For deals announced after the target's last panel valuation date, compute the implied EQUITY
premium ln(equity paid / panel market cap) by leverage bin under three readings. The right
reading gives a flat premium at a plausible level. Uses no TV method and no grading.
--exploration-only keeps targets acquired inside exploration windows (t = 2015-16).
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tvlab import panel as P  # noqa: E402


def main(exploration_only: bool) -> None:
    ex = pd.read_csv(P.PROC / "exits.csv", parse_dates=["complete_date", "announce_date", "last_value_date"])
    a = ex[ex.exit_type.eq("acquired") & ex.transaction_type.eq("Acquisition / Merger") & ex.deal_value.gt(0)
           & ex.last_mkt_cap.gt(0) & ex.last_quality_ok.eq(True) & (ex.announce_date > ex.last_value_date)].copy()
    if exploration_only:
        w = pd.read_pickle(P.PROC / "windows_h5.pkl")
        w = w[w.t.between(*P.SPLIT["exploration"]) & w.status.eq("exited")]
        end = pd.to_datetime((w.t + 6).astype(str) + "-06-30")
        ids = set(w.id)
        a = a[a.id.isin(ids) & (a.complete_date <= end.max())]
    D, C = a.last_debt.fillna(0), a.last_cash.fillna(0)
    MI, PF = a.last_minority.fillna(0), a.last_preferred.fillna(0)
    lev = (D + MI + PF - C) / a.last_mkt_cap
    bins = pd.cut(lev, [-10, -0.2, 0, 0.2, 0.5, 1, 100],
                  labels=["cash>20%", "cash0-20", "debt0-20", "20-50", "50-100", ">100"])
    readings = {"equity only": a.deal_value, "equity + gross debt": a.deal_value - D,
                "equity + net debt": a.deal_value - (D - C)}
    rows = {}
    for k, e in readings.items():
        r = np.log(e.where(e > 0) / a.last_mkt_cap)
        med = r.groupby(bins).median()
        rows[k] = {**med.round(3).to_dict(), "spread": round(med.max() - med.min(), 3),
                   "share<=0": round((e <= 0).mean(), 3)}
    print(f"deals: {len(a)}  ({'exploration windows only' if exploration_only else 'all years'})")
    print("bin counts:", bins.value_counts().sort_index().to_dict())
    print(pd.DataFrame(rows).T.to_string())
    g = a.acq_ev_rule.eq("gross")
    print(f"gross-rule deals with deal EV <= 0 (cash > transaction value; dropped from truth D): "
          f"{(g & a.acq_ev.le(0)).sum()} of {g.sum()}")


if __name__ == "__main__":
    main("--exploration-only" in sys.argv)
