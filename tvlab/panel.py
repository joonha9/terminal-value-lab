"""Firm-year panel and 5-year windows for the Terminal Value Lab.

Pipeline (all cached in data/processed/, rebuilt when an input file changes):

1. wide panel   ValuationLab FactSet exports (FY2015-2025) read with ValuationLab's own reader
                and filters EXCEPT the $100M market-cap floor, so firms that shrink below
                $100M by t+5 keep their outcome row (plan section 6). `in_universe` marks
                the ValuationLab universe (mkt_cap >= $100M); it reproduces
                panel_with_holdout.pkl row for row (checked in qa.py).
2. cash flows   merge data/raw/factset_tv_YYYY.xlsx (FY YYYY-1) on Entity ID.
3. definitions  tax rate, unlevered FCF, NOPAT, FF12, Damodaran industry, WACC.
4. windows      one row per (firm, start year t) for firms in the universe at t, with
                realized FCF t+1..t+H, fundamentals at t+H, EV at t+H and exit status.

Nothing here grades a TV method; outcome columns are only attached.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VL = ROOT.parent / "valuation-lab"
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"

UNIVERSE_MIN_MKT_CAP = 100.0      # USD millions, ValuationLab protocol
LARGE_FIRM_MKT_CAP = 5000.0       # Damodaran synthetic-rating table split
FCF_TAX_CLIP = (0.0, 0.40)
NA = ["#N/A", "@NA", "NA", "-", ""]

TV_COLUMNS = {
    "Net Cash Flow -Oper": "cfo",
    "Int on Debt Expense": "interest",
    "Total Income Taxes": "income_tax",
    "Pretax Income": "pretax_income",
    "Deprec Deplete & Amort Exp-CF": "da_cf",
    "Total Current Assets": "current_assets",
    "Total Current Liabs": "current_liabs",
    "Stock Option Cash Flow": "sbc",
    "Fiscal Period End Date": "fye_tv",
    "Net Sales": "sales_tv",
    "Capital Expend CF": "capex_tv",
}


# ----------------------------------------------------------------------------- utils
def _signature(files: list[Path]) -> str:
    return json.dumps([[f.name, f.stat().st_mtime, f.stat().st_size] for f in files])


def _cached(name: str, files: list[Path], build) -> pd.DataFrame:
    PROC.mkdir(parents=True, exist_ok=True)
    pkl, sig = PROC / f"{name}.pkl", PROC / f"{name}.sig"
    s = _signature(files)
    if pkl.exists() and sig.exists() and sig.read_text() == s:
        return pd.read_pickle(pkl)
    df = build()
    df.to_pickle(pkl)
    sig.write_text(s)
    return df


def _vl_exports() -> list[Path]:
    out = []
    for d in ("data/raw", "data/holdout"):
        out += [f for f in sorted((VL / d).glob("factset_20*.xlsx")) if not f.name.startswith("~$")]
    return out


def _tv_exports() -> list[Path]:
    return [f for f in sorted(RAW.glob("factset_tv_*.xlsx")) if not f.name.startswith("~$")]


# ------------------------------------------------------------------- 1. wide panel
def load_wide_panel() -> pd.DataFrame:
    def build():
        sys.path.insert(0, str(VL))
        from valuationlab import factset
        from valuationlab.panel import build_panel
        factset.MIN_MKT_CAP = 0.0  # keep shrunken firms; universe flag added below
        raw, logs = factset.read_exports(_vl_exports(), VL / "config/factset_columns.json")
        df = build_panel(raw)
        df["in_universe"] = df["mkt_cap"].ge(UNIVERSE_MIN_MKT_CAP)
        return df

    return _cached("panel_wide", _vl_exports(), build)


# ------------------------------------------------------------------ 2. cash flows
def _read_tv(path: Path) -> pd.DataFrame:
    probe = pd.read_excel(path, header=None, nrows=30)
    header = next(i for i, v in enumerate(probe.iloc[:, 0].astype(str)) if v.strip() == "Symbol")
    df = pd.read_excel(path, header=header, na_values=NA).dropna(how="all")
    # an entity can appear on several security rows, some empty: keep the fullest row
    df = (df.assign(_n=df.notna().sum(axis=1)).sort_values("_n", ascending=False)
            .drop_duplicates("Entity ID").drop(columns="_n"))
    df = df.rename(columns=TV_COLUMNS | {"Entity ID": "id"})
    df["fiscal_year"] = int(re.search(r"(\d{4})", path.stem).group(1)) - 1
    df["fye_tv"] = pd.to_datetime(df["fye_tv"], format="%m/%d/%Y", errors="coerce")
    return df[["id", "fiscal_year", *TV_COLUMNS.values()]]


def load_tv_fields() -> pd.DataFrame:
    return _cached("tv_fields", _tv_exports(),
                   lambda: pd.concat([_read_tv(f) for f in _tv_exports()], ignore_index=True))


# ----------------------------------------------------------------- 3. definitions
FF12 = [  # Ken French Siccodes12; anything else (incl. 6000-6999 Money) -> "Other"/"Money"
    ("NoDur", [(100, 999), (2000, 2399), (2700, 2749), (2770, 2799), (3100, 3199), (3940, 3989)]),
    ("Durbl", [(2500, 2519), (2590, 2599), (3630, 3659), (3710, 3711), (3714, 3714), (3716, 3716),
               (3750, 3751), (3792, 3792), (3900, 3939), (3990, 3999)]),
    ("Manuf", [(2520, 2589), (2600, 2699), (2750, 2769), (3000, 3099), (3200, 3569), (3580, 3629),
               (3700, 3709), (3712, 3713), (3715, 3715), (3717, 3749), (3752, 3791), (3793, 3799),
               (3830, 3839), (3860, 3899)]),
    ("Enrgy", [(1200, 1399), (2900, 2999)]),
    ("Chems", [(2800, 2829), (2840, 2899)]),
    ("BusEq", [(3570, 3579), (3660, 3692), (3694, 3699), (3810, 3829), (7370, 7379)]),
    ("Telcm", [(4800, 4899)]),
    ("Utils", [(4900, 4949)]),
    ("Shops", [(5000, 5999), (7200, 7299), (7600, 7699)]),
    ("Hlth", [(2830, 2839), (3693, 3693), (3840, 3859), (8000, 8099)]),
    ("Money", [(6000, 6999)]),
]


def ff12(sic: pd.Series) -> pd.Series:
    code = pd.to_numeric(sic, errors="coerce")
    out = pd.Series("Other", index=sic.index, dtype=object)
    for name, ranges in FF12:
        for lo, hi in ranges:
            out[code.between(lo, hi)] = name
    out[code.isna()] = np.nan
    return out


def statutory_rate(fiscal_year: pd.Series) -> pd.Series:
    """US federal statutory rate for the fiscal year (TCJA: 21% from FY2018)."""
    return np.where(fiscal_year <= 2017, 0.35, 0.21)


def marginal_rate_at_valuation(t: pd.Series) -> pd.Series:
    """Damodaran's US marginal rate known at June 30 of t+1: 40% before TCJA, 25% after."""
    return np.where(t <= 2016, 0.40, 0.25)


def add_cash_flows(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    eff = df["income_tax"] / df["pretax_income"]
    df["tax_rate"] = np.where(df["pretax_income"] > 0, eff.clip(*FCF_TAX_CLIP),
                              statutory_rate(df["fiscal_year"]))
    df["tax_rate"] = pd.Series(df["tax_rate"], index=df.index).where(df["pretax_income"].notna())
    df["interest_missing"] = df["interest"].isna()
    interest = df["interest"].fillna(0)
    tax = df["tax_rate"].fillna(pd.Series(statutory_rate(df["fiscal_year"]), index=df.index))
    # CFO (US GAAP) is after interest paid and after the cash-flow-statement change in NWC
    df["fcf"] = df["cfo"] + interest * (1 - tax) - df["capex"].fillna(0)
    df["fcf_ex_sbc"] = df["fcf"] - df["sbc"].fillna(0)
    df["nopat"] = df["ebit"] * (1 - tax)
    # diagnostic only: EBITDA - taxes on EBIT - capex (no NWC); compare with fcf in QA
    df["fcf_simple"] = df["ebitda"] - df["ebit"].clip(lower=0) * tax - df["capex"].fillna(0)
    return df


def add_industries(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ff12"] = ff12(df["sic"])
    fi = pd.read_csv(PROC / "firm_industry.csv", usecols=["id", "industry", "source"])
    fi = fi.rename(columns={"industry": "dam_industry", "source": "dam_industry_source"})
    return df.merge(fi, on="id", how="left")


def add_wacc(df: pd.DataFrame) -> pd.DataFrame:
    """Damodaran-style WACC known at the valuation date (June 30 of t+1) for fiscal year t."""
    df = df.copy()
    t = df["fiscal_year"]

    rf = pd.read_csv(PROC / "rf_dgs10.csv", parse_dates=["date"])
    rf_june = rf[rf.date.dt.month.eq(6)].groupby(rf.date.dt.year)["dgs10"].last()
    df["rf"] = (t + 1).map(rf_june)

    erp = pd.read_csv(PROC / "erp_monthly.csv", parse_dates=["month_start"])
    erp_june = erp[erp.month_start.dt.month.eq(6)]
    erp_june = erp_june.set_index(erp_june.month_start.dt.year)["erp_t12m"]
    df["erp"] = (t + 1).map(erp_june)
    erp_a = pd.read_csv(PROC / "erp_annual.csv").set_index("year_end")["erp_fcfe"]
    df["erp_annual"] = t.map(erp_a)

    betas = pd.read_csv(PROC / "betas_by_vintage.csv")
    bu = betas.set_index(["vintage_t", "industry"])["unlevered_beta_cash_adj"]
    key = list(zip(t, df["dam_industry"]))
    df["beta_u"] = pd.Series(bu.reindex(key).to_numpy(), index=df.index)
    mkt = betas[betas.industry.isin(["Total Market (without financials)", "Total Market"])]
    mkt = mkt.sort_values("industry", ascending=False).drop_duplicates("vintage_t")
    df["beta_u"] = df["beta_u"].fillna(t.map(mkt.set_index("vintage_t")["unlevered_beta_cash_adj"]))

    tau = pd.Series(marginal_rate_at_valuation(t), index=df.index)
    debt = df["total_debt"].fillna(0).clip(lower=0)
    E = df["mkt_cap"]
    df["de_market"] = debt / E
    df["beta_l"] = df["beta_u"] * (1 + (1 - tau) * df["de_market"])
    df["cost_equity"] = df["rf"] + df["beta_l"] * df["erp"]

    # synthetic rating from interest coverage (EBIT / interest on debt)
    cov_tab = pd.read_csv(PROC / "coverage_rating.csv")
    spreads = pd.read_csv(PROC / "spreads_by_year.csv").set_index(["year", "rating"])["spread"]
    interest = df["interest"]
    coverage = np.where(interest > 0, df["ebit"] / interest, np.inf)
    # no debt -> infinite coverage (top rating). Debt but interest missing OR zero -> unknown
    # coverage -> median rating below (zero interest with debt was rated AAA in a first
    # version; caught in code review 2026-11-07).
    coverage = pd.Series(coverage, index=df.index).where(~((interest.isna() | interest.le(0)) & (debt > 0)))
    size = np.where(E > LARGE_FIRM_MKT_CAP, "large", "small")
    rating = pd.Series(np.nan, index=df.index, dtype=object)
    for s in ("large", "small"):
        tab = cov_tab[cov_tab.firm_size.eq(s)]
        for _, r in tab.iterrows():
            hit = (size == s) & (coverage > r.cov_gt) & (coverage <= r.cov_le)
            rating[hit] = r.rating
        top = tab.loc[tab.cov_le.idxmax(), "rating"]
        rating[(size == s) & np.isinf(coverage)] = top
    df["rating_source"] = np.where(rating.notna(), "coverage", "missing_or_zero_interest")
    rating = rating.fillna("Baa2/BBB")  # debt but no interest field: assume the median rating
    df["synthetic_rating"] = rating
    df["spread"] = pd.Series(spreads.reindex(list(zip(t + 1, rating))).to_numpy(), index=df.index)
    df["cost_debt_after_tax"] = (df["rf"] + df["spread"]) * (1 - tau)

    V = E + debt
    df["wacc"] = E / V * df["cost_equity"] + debt / V * df["cost_debt_after_tax"]
    df["wacc_simple"] = df["rf"] + 0.05  # robustness: Treasury + 5%, beta = 1
    return df


MIN_TOTAL_ASSETS = 10.0     # USD millions
MAX_MCAP_TO_ASSETS = 100.0


def add_quality(df: pd.DataFrame) -> pd.DataFrame:
    """Flag firm-years whose market value cannot be trusted (found in QA, 2026-11-07):
    MktVal Co mis-scaled after large reverse splits (e.g. JAGX FY2017 = $710 quadrillion),
    OTC shells with < $1M of assets priced above $100M, and de-SPAC years pairing the
    pre-merger statements with the post-merger market cap. Uses only data at that date."""
    df = df.copy()
    ratio = df["mkt_cap"] / df["total_assets"].where(df["total_assets"] > 0)
    df["mcap_to_assets"] = ratio
    df["quality_ok"] = df["total_assets"].fillna(0).ge(MIN_TOTAL_ASSETS) & ratio.le(MAX_MCAP_TO_ASSETS)

    # Robustness flag only (not the main screen): market cap more than 10x away from the
    # adjacent year's while total assets moved < 50%. Catches smaller reverse-split
    # mis-scalings, but also genuine collapses and spikes. It looks at the NEXT year, so it is
    # look-ahead and is never used to pick the main sample.
    df = df.sort_values(["id", "fiscal_year"])
    g = df.groupby("id")
    lmc = np.log(df["mkt_cap"].where(df["mkt_cap"] > 0))
    las = np.log(df["total_assets"].where(df["total_assets"] > 0))
    flag = pd.Series(False, index=df.index)
    for k in (1, -1):
        adjacent = g["fiscal_year"].shift(k).eq(df["fiscal_year"] - k)
        jump = (lmc - lmc.groupby(df["id"]).shift(k)).abs() > np.log(10)
        calm = (las - las.groupby(df["id"]).shift(k)).abs() < np.log(1.5)
        flag |= adjacent & jump & calm
    df["mcap_jump_suspect"] = flag
    # days between fiscal year-end and the valuation date; < 90 means the annual report may
    # not have been public yet on June 30 (robustness: require >= 90)
    df["stmt_age_days"] = (df["value_date"] - df["fye_date"]).dt.days
    return df


def build_firm_years() -> pd.DataFrame:
    def build():
        wide = load_wide_panel()
        tv = load_tv_fields()
        df = wide.merge(tv, on=["id", "fiscal_year"], how="left")
        df = add_cash_flows(df)
        df = add_industries(df)
        df = add_quality(df)
        return add_wacc(df)

    inputs = _vl_exports() + _tv_exports() + sorted(PROC.glob("*.csv")) + [Path(__file__)]
    return _cached("firm_years", inputs, build)


# ------------------------------------------------------------------- 4. windows
OUTCOME_COLS = ["ev", "mkt_cap", "fcf", "fcf_ex_sbc", "ebitda", "ebit", "nopat", "sales",
                "sbc", "roic", "in_universe", "quality_ok", "mcap_jump_suspect", "wacc"]
START_COLS = ["ticker", "name", "sic", "ff12", "dam_industry", "quality_ok", "mcap_jump_suspect", "mcap_to_assets",
              "total_assets", "ev", "mkt_cap", "total_debt",
              "cash", "fcf", "fcf_ex_sbc", "fcf_simple", "ebitda", "ebit", "nopat", "sales",
              "sbc", "roic", "sales_growth_1y", "sales_growth_3y", "rnd_intensity",
              "ebitda_margin", "tax_rate", "interest_missing", "rf", "erp", "erp_annual",
              "beta_u", "beta_l", "cost_equity", "synthetic_rating", "spread", "wacc",
              "wacc_simple", "stmt_age_days"]


def build_windows(fy: pd.DataFrame, horizon: int = 5) -> pd.DataFrame:
    """One row per (firm, start year t) with the firm in the universe at t and t+horizon
    inside the data. Outcome status:
      survived        row at t+H with mkt_cap >= $100M
      shrank          row at t+H below $100M (kept: no survivorship filter at t+H)
      exited          no row at t+H and none later (acquired, delisted, or stopped reporting)
      gap             no row at t+H but the firm reappears later (data gap; not an exit)
    """
    last = fy["fiscal_year"].max()
    start = fy[fy["in_universe"] & fy["fiscal_year"].le(last - horizon)][["id", "fiscal_year", *START_COLS]]
    w = start.rename(columns={c: f"{c}_t" for c in START_COLS}).rename(columns={"fiscal_year": "t"})
    by = fy.set_index(["id", "fiscal_year"])
    for k in range(1, horizon + 1):
        key = list(zip(w["id"], w["t"] + k))
        w[f"fcf_t{k}"] = by["fcf"].reindex(key).to_numpy()
    key = list(zip(w["id"], w["t"] + horizon))
    for c in OUTCOME_COLS:
        w[f"{c}_tH"] = by[c].reindex(key).to_numpy()
    present = w["ev_tH"].notna()
    last_fy = fy.groupby("id")["fiscal_year"].max()
    later = w["id"].map(last_fy) > w["t"] + horizon
    w["status"] = np.select([present & w["in_universe_tH"].eq(True), present, later],
                            ["survived", "shrank", "gap"], default="exited")
    w["fcf_path_complete"] = w[[f"fcf_t{k}" for k in range(1, horizon + 1)]].notna().all(axis=1)
    w["horizon"] = horizon
    return w.reset_index(drop=True)


SPLIT = {"exploration": (2015, 2016), "validation": (2017, 2018), "test": (2019, 2020)}


def split_of(t: pd.Series) -> pd.Series:
    out = pd.Series("other", index=t.index, dtype=object)
    for name, (a, b) in SPLIT.items():
        out[t.between(a, b)] = name
    return out
