"""Phase 1b: TV methods against acquisition prices, EXPLORATION START YEARS ONLY (t = 2015-16).

    python3 -P terminal-value-lab/scripts/explore_acquisitions.py

Acquired firms have no t+5 statements, so they are graded at the acquisition point. The
formulas use the last pre-deal fiscal year L (t < L < t+5) as the "outcome year"; multiples,
growth and WACC still come from t. Two truths on the same firms and the same fundamentals:
  A  deal EV   = deal equity value + net claims from year L (docs/exits.md)
  B  market EV at June 30 of L+1, kept only when the deal was announced after that date
     (so the market price does not already contain the bid)
Survivors (Phase 1, truth = market EV at t+5) are shown for reference.
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
from tvlab import methods as M  # noqa: E402
from tvlab import panel as P    # noqa: E402

OUT = ROOT / "results" / "phase1"
EXPLORATION = P.SPLIT["exploration"]
LN25 = np.log(1.25)
CORE = ["G_fcf_g2.5", "G_fcf3avg_g2.5", "E_ff12_med", "E_damind_med", "E_own", "E_dam_5yavg",
        "B50_G2.5_Eff12"]
pd.set_option("display.width", 220)


def score(e: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"n": e.notna().sum(), "median_abs": e.abs().median(), "bias": e.median(),
                         "within_25pct": (e.abs() < LN25).sum() / e.notna().sum()}).round(3)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fy = pd.read_pickle(P.PROC / "firm_years.pkl")
    ex = pd.read_csv(P.PROC / "exits.csv", parse_dates=["complete_date", "announce_date", "last_value_date"])
    w = pd.read_pickle(P.PROC / "windows_h5.pkl")
    w = w[w.t.between(*EXPLORATION) & w.quality_ok_t & w.status.eq("exited")].copy()
    assert set(w.t) <= set(range(EXPLORATION[0], EXPLORATION[1] + 1))

    w = w.merge(ex[["id", "exit_type", "complete_date", "announce_date", "last_fy", "last_value_date",
                    "acq_ev", "pe_buyer", "going_private", "stock_pct"]], on="id", how="left")
    end = pd.to_datetime((w.t + 6).astype(str) + "-06-30")
    start = pd.to_datetime((w.t + 1).astype(str) + "-06-30")
    a = w[w.exit_type.eq("acquired") & (w.complete_date > start) & (w.complete_date <= end)
          & w.last_fy.between(w.t + 1, w.t + 4)].copy()  # L = t would make E_own equal truth B by construction
    print(f"exploration exited windows: {len(w):,}; acquired between t and t+5 with L in [t+1, t+4]: {len(a):,}")
    print("L - t:", (a.last_fy - a.t).value_counts().sort_index().to_dict())

    by = fy.set_index(["id", "fiscal_year"])
    keyL = list(zip(a.id, a.last_fy))
    for src, dst in [("fcf", "fcf_tH"), ("fcf_ex_sbc", "fcf_ex_sbc_tH"), ("ebitda", "ebitda_tH"),
                     ("nopat", "nopat_tH"), ("roic", "roic_tH"), ("ev", "ev_L"), ("quality_ok", "quality_ok_L")]:
        a[dst] = by[src].reindex(keyL).to_numpy()
    for k, col in ((1, "fcf_tH_m1"), (2, "fcf_tH_m2")):
        a[col] = by["fcf"].reindex(list(zip(a.id, a.last_fy - k))).to_numpy()
    a["tH_year"] = a["last_fy"]
    a = a[a.acq_ev.gt(0) & a.quality_ok_L.eq(True)]

    pred = M.predict_all(a, fy)
    eA = np.log(pred.div(a.acq_ev, axis=0).where(pred.gt(0)))
    clean_mkt = a.announce_date > a.last_value_date
    eB = np.log(pred.div(a.ev_L.where(clean_mkt & a.ev_L.gt(0)), axis=0).where(pred.gt(0)))
    print(f"graded acquired windows: {len(a):,}; market EV before announcement available: {clean_mkt.sum():,}")
    prem = np.log(a.acq_ev / a.ev_L).where(clean_mkt & a.ev_L.gt(0))
    print(f"deal EV vs pre-announcement market EV, ln: median {prem.median():.3f}, IQR "
          f"[{prem.quantile(.25):.3f}, {prem.quantile(.75):.3f}]")

    common = eA[CORE].notna().all(axis=1) & eB[CORE].notna().all(axis=1)
    tab = pd.concat({"A_deal_EV": score(eA.loc[common, CORE]), "B_market_EV_L": score(eB.loc[common, CORE])}, axis=1)
    print(f"\n=== Same firms, same fundamentals (n = {common.sum():,}): truth A = deal EV, truth B = market EV")
    print(tab.to_string())
    tab.to_csv(OUT / "I_acquired_two_truths.csv")

    # premium-neutral view: remove each truth's median bias of the FF12 exit (a level shift)
    rank = pd.DataFrame({
        "A_rank": score(eA.loc[common, CORE])["median_abs"].rank(),
        "B_rank": score(eB.loc[common, CORE])["median_abs"].rank(),
        "A_abs_debiased": (eA.loc[common, CORE] - eA.loc[common, CORE].median()).abs().median().round(3),
        "B_abs_debiased": (eB.loc[common, CORE] - eB.loc[common, CORE].median()).abs().median().round(3),
    })
    print("\n=== Ranking under each truth, and error after removing each method's own median bias")
    print(rank.to_string())
    rank.to_csv(OUT / "J_acquired_rankings.csv")

    gap = (eA["G_fcf_g2.5"].abs() - eA["E_ff12_med"].abs())[eA[["G_fcf_g2.5", "E_ff12_med"]].notna().all(axis=1)]
    sub = pd.DataFrame({
        "n": a.loc[gap.index].groupby(a.pe_buyer).size(),
        "G_minus_E_abs (deal truth)": gap.groupby(a.loc[gap.index, "pe_buyer"]).median().round(3),
        "G_bias": eA.loc[gap.index, "G_fcf_g2.5"].groupby(a.loc[gap.index, "pe_buyer"]).median().round(3),
        "E_bias": eA.loc[gap.index, "E_ff12_med"].groupby(a.loc[gap.index, "pe_buyer"]).median().round(3),
    })
    print("\n=== By buyer type (PE buyers price on cash flows and leverage; strategic buyers include synergies)")
    print(sub.to_string())
    sub.to_csv(OUT / "K_acquired_by_buyer.csv")


if __name__ == "__main__":
    main()
