"""Build the firm-year panel and 5-year windows, then print QA checks.

    python3 -P terminal-value-lab/scripts/build_panel.py

Writes data/processed/firm_years.pkl and windows_h5.pkl (and h3 for robustness).
QA only looks at inputs and coverage; no TV method is evaluated here.
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

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)


def section(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 70 - len(title)))


def main() -> None:
    fy = P.build_firm_years()
    uni = fy[fy.in_universe]

    section("1. Universe reproduces ValuationLab panel_with_holdout")
    vl = pd.read_pickle(P.VL / "data/cache/panel_with_holdout.pkl")
    a = set(zip(uni.id, uni.fiscal_year)); b = set(zip(vl.id, vl.fiscal_year))
    print(f"wide panel rows {len(fy):,}; universe rows {len(uni):,}; VL rows {len(vl):,}; "
          f"only-ours {len(a - b)}, only-VL {len(b - a)}")
    m = uni.merge(vl[["id", "fiscal_year", "ev", "ebitda"]], on=["id", "fiscal_year"], suffixes=("", "_vl"))
    print(f"EV identical: {np.isclose(m.ev, m.ev_vl, equal_nan=True).mean():.4f}; "
          f"EBITDA identical: {np.isclose(m.ebitda, m.ebitda_vl, equal_nan=True).mean():.4f}")

    section("2. Cash-flow field coverage (universe rows) and year-end agreement")
    cols = ["cfo", "interest", "income_tax", "pretax_income", "sbc", "fcf"]
    cov = uni.groupby("fiscal_year")[cols].apply(lambda d: d.notna().mean()).round(3)
    cov["fye_match"] = uni.groupby("fiscal_year").apply(
        lambda d: (d.fye_tv == d.fye_date)[d.fye_tv.notna()].mean()).round(4)
    print(cov.to_string())

    section("3. FCF definition checks (universe rows)")
    ok = uni[uni.fcf.notna() & uni.sales.gt(0)]
    print(f"FCF<=0: {(ok.fcf <= 0).mean():.3f}; EBITDA<=0: {(uni.ebitda <= 0).mean():.3f}; "
          f"FCF-ex-SBC<=0: {(ok.fcf_ex_sbc <= 0).mean():.3f}")
    print(f"corr(FCF/sales, simple FCF/sales) Spearman: "
          f"{(ok.fcf / ok.sales).corr(ok.fcf_simple / ok.sales, method='spearman'):.3f}")
    print(f"median FCF/sales {np.nanmedian(ok.fcf / ok.sales):.3f}; "
          f"median simple {np.nanmedian(ok.fcf_simple / ok.sales):.3f}")
    print(f"median tax rate {uni.tax_rate.median():.3f}; interest missing {uni.interest_missing.mean():.3f} "
          f"(of which debt > 0: {(uni.interest_missing & uni.total_debt.gt(0)).mean():.3f})")
    print("FCF/sales quantiles:", (ok.fcf / ok.sales).quantile([.01, .05, .25, .5, .75, .95, .99]).round(3).to_dict())

    section("4. Outliers")
    print("largest market caps (USD m):")
    print(fy.nlargest(5, "mkt_cap")[["id", "ticker", "name", "fiscal_year", "mkt_cap", "sales"]].to_string(index=False))
    print(f"EV <= 0 (universe): {(uni.ev <= 0).mean():.4f}")
    q = ~uni.quality_ok
    print(f"quality flag fails (assets < ${P.MIN_TOTAL_ASSETS:.0f}M or mcap/assets > {P.MAX_MCAP_TO_ASSETS:.0f}): "
          f"{q.sum():,} universe rows ({q.mean():.3f}); by year {uni[q].groupby('fiscal_year').size().to_dict()}")

    section("5. Discount rate (universe rows)")
    w = uni.groupby("fiscal_year").agg(rf=("rf", "first"), erp=("erp", "first"),
                                       beta_u=("beta_u", "median"), beta_l=("beta_l", "median"),
                                       ke=("cost_equity", "median"), wacc_p10=("wacc", lambda s: s.quantile(.1)),
                                       wacc=("wacc", "median"), wacc_p90=("wacc", lambda s: s.quantile(.9)),
                                       missing=("wacc", lambda s: s.isna().mean()))
    print(w.round(4).to_string())
    print("synthetic rating mix:", uni.synthetic_rating.value_counts(normalize=True).round(3).head(8).to_dict())
    print("rating source:", uni.rating_source.value_counts(normalize=True).round(3).to_dict())
    print("Damodaran industry source:", uni.dam_industry_source.value_counts(normalize=True).round(3).to_dict())
    print("WACC by FF12 (median):", uni.groupby("ff12").wacc.median().round(4).sort_values().to_dict())
    print(f"beta_l > 3: {(uni.beta_l > 3).mean():.4f}; WACC < rf: {(uni.wacc < uni.rf).mean():.4f}")

    for h in (5, 3):
        win = P.build_windows(fy, horizon=h)
        win.to_pickle(P.PROC / f"windows_h{h}.pkl")
        section(f"6. Windows, horizon {h}")
        tab = pd.crosstab(win.t, win.status, margins=True)
        tab["exit_share"] = (1 - tab["survived"] / tab["All"]).round(3)
        tab["fcf_path_complete"] = win.groupby("t").fcf_path_complete.sum()
        tab.loc["All", "fcf_path_complete"] = win.fcf_path_complete.sum()
        print(tab.to_string())
        okt = win.quality_ok_t
        okH = win.quality_ok_tH.eq(True) | win.status.eq("exited")
        print(f"quality ok at t: {okt.sum():,} of {len(win):,}; of those, outcome row suspect at t+{h}: "
              f"{(okt & ~okH).sum():,}; clean windows: {(okt & okH).sum():,}")
        if h == 5:
            win["split"] = P.split_of(win.t)
            print("by split:", win.groupby("split").size().to_dict(),
                  "| clean:", win[okt & okH].groupby("split").size().to_dict())
            c = win[okt & okH]
            print("clean, FCF_tH > 0 and EBITDA_tH > 0 (both methods defined):",
                  (c.fcf_tH.gt(0) & c.ebitda_tH.gt(0)).sum())
            print("FF12 counts (h5, all starts):", win.ff12_t.value_counts().to_dict())

    print("\nSaved:", ", ".join(p.name for p in sorted(P.PROC.glob("*.pkl"))))


if __name__ == "__main__":
    main()
