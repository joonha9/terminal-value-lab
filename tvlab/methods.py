"""Terminal-value methods: each maps a window row to a predicted EV at t+H.

Perfect-foresight convention (plan section 3): fundamentals of year t+H are the realized
ones; multiples, growth and discount rates use information available at t only.
A method returns NaN where it is undefined (e.g. FCF <= 0 for Gordon, r <= g).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .panel import PROC

MIN_SPREAD = 0.01  # r - g below 1 pp is treated as undefined (TV explodes)


def _pos(x: pd.Series) -> pd.Series:
    return x.where(x > 0)


def gordon(cash_flow: pd.Series, r: pd.Series, g: float) -> pd.Series:
    spread = r - g
    tv = cash_flow * (1 + g) / spread
    return tv.where((cash_flow > 0) & (spread >= MIN_SPREAD))


def value_driver(nopat: pd.Series, r: pd.Series, g: float, ronic: pd.Series) -> pd.Series:
    """McKinsey value driver: NOPAT_{t+H+1} (1 - g / RONIC) / (r - g)."""
    reinvest = g / ronic
    tv = nopat * (1 + g) * (1 - reinvest) / (r - g)
    ok = (nopat > 0) & (ronic > g) & ((r - g) >= MIN_SPREAD)
    return tv.where(ok)


# ---------------------------------------------------------------- multiples at t
def industry_median_multiple(fy: pd.DataFrame, group: str, min_n: int = 5) -> pd.Series:
    """Median EV/EBITDA by (fiscal_year, group) over clean universe firms with EV, EBITDA > 0.
    Returns a Series indexed by (fiscal_year, group)."""
    u = fy[fy.in_universe & fy.quality_ok & fy.ebitda.gt(0) & fy.ev.gt(0)]
    m = (u.ev / u.ebitda).groupby([u.fiscal_year, u[group]])
    med, n = m.median(), m.size()
    return med[n >= min_n]


def damodaran_multiples() -> pd.DataFrame:
    return pd.read_csv(PROC / "multiples_by_vintage.csv")


def damodaran_longrun(mult: pd.DataFrame, years: int = 5) -> pd.Series:
    """Mean of the last `years` releases available at t (vintage t-years+1 .. t),
    indexed by (vintage_t, industry). Releases start with vintage 2013, so early t
    average fewer years (t=2015: 3, t=2016: 4)."""
    p = mult.pivot(index="vintage_t", columns="industry", values="ev_ebitda_all")
    p = p.where(p > 0)
    lr = p.rolling(years, min_periods=2).mean()
    return lr.stack()


def predict_all(w: pd.DataFrame, fy: pd.DataFrame) -> pd.DataFrame:
    """All Phase-1 methods for windows w. Returns a DataFrame of predicted EV_{t+H}."""
    H = int(w["horizon"].iloc[0])
    # outcome year: t+H for windows; may vary by row (e.g. last pre-deal year for acquisitions)
    tH_year = w["tH_year"] if "tH_year" in w else w["t"] + H
    r, r_s = w["wacc_t"], w["wacc_simple_t"]
    fcf, eb = w["fcf_tH"], _pos(w["ebitda_tH"])
    if {"fcf_tH_m1", "fcf_tH_m2"} <= set(w.columns):
        fcf3 = w[["fcf_tH_m2", "fcf_tH_m1", "fcf_tH"]].mean(axis=1, skipna=False)
    else:
        fcf3 = w[[f"fcf_t{k}" for k in (H - 2, H - 1, H)]].mean(axis=1, skipna=False)
    out = {}

    for g in (0.02, 0.025, 0.03):
        out[f"G_fcf_g{g * 100:g}"] = gordon(fcf, r, g)
    out["G_fcf3avg_g2.5"] = gordon(fcf3, r, 0.025)
    out["G_exsbc_g2.5"] = gordon(w["fcf_ex_sbc_tH"], r, 0.025)
    out["G_vd_roic_g2.5"] = value_driver(w["nopat_tH"], r, 0.025, w["roic_tH"])
    out["G_vd_ronic=r"] = value_driver(w["nopat_tH"], r, 0.025, r)  # = NOPAT(1+g)/r
    out["G_fcf_g2.5_rf+5"] = gordon(fcf, r_s, 0.025)

    def lookup(series: pd.Series, years: pd.Series, keys: pd.Series) -> pd.Series:
        return pd.Series(series.reindex(list(zip(years, keys))).to_numpy(), index=w.index)

    ff = industry_median_multiple(fy, "ff12")
    dm = industry_median_multiple(fy, "dam_industry")
    m_ff = lookup(ff, w["t"], w["ff12_t"])
    m_dm = lookup(dm, w["t"], w["dam_industry_t"]).fillna(m_ff)
    out["E_ff12_med"] = m_ff * eb
    out["E_damind_med"] = m_dm * eb
    own = (w["ev_t"] / w["ebitda_t"]).where((w["ebitda_t"] > 0) & (w["ev_t"] > 0))
    out["E_own"] = own * eb

    mult = damodaran_multiples()
    cur = mult.set_index(["vintage_t", "industry"])["ev_ebitda_all"]
    cur = cur.where(cur > 0)
    out["E_dam_t"] = lookup(cur, w["t"], w["dam_industry_t"]) * eb
    out["E_dam_5yavg"] = lookup(damodaran_longrun(mult), w["t"], w["dam_industry_t"]) * eb

    out["B50_G2.5_Eff12"] = 0.5 * out["G_fcf_g2.5"] + 0.5 * out["E_ff12_med"]
    # geometric blend: same weights in log space
    out["B50geo_G2.5_Eff12"] = np.sqrt(out["G_fcf_g2.5"] * out["E_ff12_med"])

    # references (not candidates)
    out["REF_ff12_med_at_tH (look-ahead)"] = lookup(ff, tH_year, w["ff12_t"]) * eb
    out["REF_ev_t (no change)"] = w["ev_t"].where(w["ev_t"] > 0)
    return pd.DataFrame(out, index=w.index)


def implied_growth(tv: pd.Series, fcf: pd.Series, r: pd.Series) -> pd.Series:
    """g that makes Gordon equal tv: tv = fcf (1+g)/(r-g)  =>  g = (r tv - fcf)/(tv + fcf)."""
    return ((r * tv - fcf) / (tv + fcf)).where((fcf > 0) & (tv > 0))
