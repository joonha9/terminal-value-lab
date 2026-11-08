"""Q4: does the Gordon-vs-market gap predict stock returns? (docs/q4_design.md)

Formation each June 30 of t+1 (the panel's valuation date) for fiscal year t; holding July t+1 to
June t+2. Signals use only fiscal-year-t data and market values at the formation date.

    S1  = ln(Gordon_t / EV_t),  Gordon_t = FCF_t (1+g) / (WACC_t - g), g = 2.5%
    S1a = ln(FCF_t / EV_t)                 (cash-flow yield part)
    S1b = ln((1+g) / (WACC_t - g))         (discount-rate part);  S1 = S1a + S1b exactly
    S2  = ln(Gordon_t / FF12-exit_t)       (reported only)

Fama-MacBeth: monthly cross-sectional OLS of excess returns on rank-scaled signals and controls
(ranks within each formation, scaled to [-0.5, 0.5]; a missing control gets 0, the median rank);
Newey-West (lag 6) standard errors on the monthly slopes. Monthly returns are winsorized at the
0.5% / 99.5% cross-sectional quantiles within each month (data errors such as unadjusted splits;
decided before any return was related to a signal), with raw and 1% / 99% as robustness.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import methods as M
from . import panel as P

G = 0.025
MIN_SPREAD = 0.01
NW_LAG = 6
CONTROLS = ["size", "bm", "mom", "gp", "ag", "beta"]
PERF_DELIST_RET = -0.30          # Shumway (1997), performance delistings
PERF_MCAP_MAX = 100.0            # USD millions, last market cap
PERF_RET12_MAX = -0.50           # cumulative return over the last 12 valid months
WINSOR = (0.005, 0.995)


# ------------------------------------------------------------------ data
def french() -> pd.DataFrame:
    """Monthly FF5 + momentum + RF, decimals, PeriodIndex."""
    def read(name: str) -> pd.DataFrame:
        d = pd.read_csv(P.ROOT / "data" / "raw" / "french" / name, skiprows=3 if "Momentum" not in name else 13,
                        index_col=0)
        d = d[d.index.astype(str).str.strip().str.fullmatch(r"\d{6}")]
        d.index = pd.PeriodIndex([f"{s.strip()[:4]}-{s.strip()[4:]}" for s in d.index.astype(str)], freq="M")
        d.columns = [c.strip() for c in d.columns]
        return d.astype(float) / 100.0
    f5 = read("F-F_Research_Data_5_Factors_2x3.csv")
    mom = read("F-F_Momentum_Factor.csv").rename(columns={"Mom": "UMD"})
    return f5.join(mom[["UMD"]], how="inner")


def pick_security(ret: pd.DataFrame, fy: pd.DataFrame) -> pd.DataFrame:
    """Stitch an entity's securities month by month: in each month keep one return, preferring
    the security whose symbol matches a panel ticker of the entity, then the security with the
    most months overall (ties: FDS ticker order). Bankruptcy reorganisations (old "...Q" equity,
    then the post-emergence equity) are therefore kept in sequence, not dropped (review fix)."""
    tick = fy.groupby("id")["ticker"].apply(lambda s: set(s.dropna().astype(str)))
    g = ret.groupby(["entity_id", "fds_ticker"]).agg(n=("ret", "size"), symbol=("symbol", "first")).reset_index()
    g["match"] = [str(sym) in tick.get(e, set()) for e, sym in zip(g.entity_id, g.symbol)]
    g = g.sort_values(["entity_id", "match", "n", "fds_ticker"], ascending=[True, False, False, True])
    g["prio"] = g.groupby("entity_id").cumcount()
    r = ret.merge(g[["entity_id", "fds_ticker", "prio"]], on=["entity_id", "fds_ticker"])
    r = r.sort_values(["entity_id", "month", "prio"]).drop_duplicates(["entity_id", "month"])
    return r.drop(columns="prio").reset_index(drop=True)


def signals(fy: pd.DataFrame) -> pd.DataFrame:
    """One row per (id, t) in the clean universe: signals and raw controls at formation."""
    u = fy[fy.in_universe & fy.quality_ok].copy()
    spread = u["wacc"] - G
    ok = (u["fcf"] > 0) & (spread >= MIN_SPREAD) & (u["ev"] > 0)
    gordon = (u["fcf"] * (1 + G) / spread).where(ok)
    out = pd.DataFrame({"id": u["id"], "t": u["fiscal_year"], "ff12": u["ff12"],
                        "formation": pd.PeriodIndex(u["value_date"], freq="M"), "mkt_cap": u["mkt_cap"]})
    with np.errstate(invalid="ignore", divide="ignore"):
        out["S1"] = np.log(gordon / u["ev"])
        out["S1a"] = np.log(u["fcf"] / u["ev"]).where(ok)
        out["S1b"] = np.log((1 + G) / spread).where(ok)
        ff = M.industry_median_multiple(fy, "ff12")
        mult = pd.Series(ff.reindex(list(zip(u["fiscal_year"], u["ff12"]))).to_numpy(), index=u.index)
        exit_ff12 = (mult * u["ebitda"]).where(u["ebitda"] > 0)
        out["S2"] = np.log(gordon / exit_ff12)
        out["S3_implied_g"] = ((u["wacc"] * u["ev"] - u["fcf"]) / (u["ev"] + u["fcf"])).where(ok)
        out["size"] = np.log(u["mkt_cap"])
        out["bm"] = np.log(u["book_equity"] / u["mkt_cap"]).where(u["book_equity"] > 0)
        out["gp"] = u["gross_profit"] / u["total_assets"]
        prev = fy.set_index(["id", "fiscal_year"])["total_assets"]
        ta_prev = pd.Series(prev.reindex(list(zip(u["id"], u["fiscal_year"] - 1))).to_numpy(), index=u.index)
        out["ag"] = (u["total_assets"] / ta_prev - 1).where(ta_prev > 0)
        out["beta"] = u["beta_l"]
        out["stmt_age"] = u["stmt_age_days"]
    return out.reset_index(drop=True)


def momentum(ret: pd.DataFrame, formation: pd.Period, ids) -> pd.Series:
    """Cumulative return over months formation-11 .. formation-1 (12-1), >= 8 valid months."""
    win = [formation - k for k in range(11, 0, -1)]
    r = ret[ret.month.isin(win) & ret.entity_id.isin(ids)]
    g = r.groupby("entity_id")["ret"]
    cum = g.apply(lambda s: float(np.prod(1 + s) - 1))
    return cum[g.size() >= 8]


def delisting_returns(ret: pd.DataFrame, exits: pd.DataFrame, months: list[pd.Period]) -> pd.DataFrame:
    """Return for the first missing month after a security's last valid return, for exited firms:
    acquired -> 0; inactive with last market cap < $100M or a return <= -50% over the 12 calendar
    months ending at the last valid month -> -30%;
    other inactive (e.g. reorganisations) -> 0. Listed-but-dropped firms get nothing."""
    ex = exits.drop_duplicates("id").set_index("id")
    r = ret.sort_values(["entity_id", "month"])
    last = r.groupby("entity_id")["month"].max()
    last = last[last.index.isin(ex.index[ex.exit_type.isin(["acquired", "inactive"])])]
    nxt = last + 1
    last, nxt = last[nxt.isin(months)], nxt[nxt.isin(months)]
    tail = r[r.entity_id.isin(last.index)]
    tail = tail[tail.month > tail.entity_id.map(last) - 12]
    r12 = tail.groupby("entity_id")["ret"].apply(lambda s: float(np.prod(1 + s) - 1))
    typ = ex.loc[last.index, "exit_type"]
    perf = (ex.loc[last.index, "last_mkt_cap"] < PERF_MCAP_MAX) | (r12.reindex(last.index) <= PERF_RET12_MAX)
    val = np.where(typ.eq("acquired"), 0.0, np.where(perf, PERF_DELIST_RET, 0.0))
    return pd.DataFrame({"entity_id": last.index, "month": nxt.to_numpy(), "ret": val, "delist": True})


# ------------------------------------------------------------------ panel of firm-months
def firm_months(sig: pd.DataFrame, ret: pd.DataFrame, rf: pd.Series) -> pd.DataFrame:
    """Each formation's firms joined to their holding-period returns (July .. June)."""
    out = []
    for f, s in sig.groupby("formation"):
        s = s.copy()
        s["mom"] = s["id"].map(momentum(ret, f, set(s["id"])))
        hold = [f + k for k in range(1, 13)]
        r = ret[ret.month.isin(hold) & ret.entity_id.isin(set(s["id"]))]
        m = r.merge(s, left_on="entity_id", right_on="id")
        out.append(m)
    d = pd.concat(out, ignore_index=True)
    d = d[d.month.isin(rf.index)]
    d["exret"] = d["ret"] - d["month"].map(rf)
    return d


def winsorize_monthly(d: pd.DataFrame, col: str, lo: float, hi: float, mask=None) -> pd.Series:
    """Clip `col` to its [lo, hi] cross-sectional quantiles within each month. With `mask`, the
    quantiles are computed on, and clipping applied to, the masked rows only (FactSet returns);
    other rows (delisting returns) pass through unchanged (review fix)."""
    m = pd.Series(True, index=d.index) if mask is None else pd.Series(mask, index=d.index)
    q = d[m].groupby("month")[col].quantile([lo, hi]).unstack()
    clipped = d[col].clip(d["month"].map(q[lo]), d["month"].map(q[hi]))
    return clipped.where(m, d[col])


def rank_scale(x: pd.Series) -> pd.Series:
    """Cross-sectional rank scaled to [-0.5, 0.5]; NaN stays NaN."""
    r = x.rank(method="average")
    n = r.notna().sum()
    return (r - 1) / (n - 1) - 0.5 if n > 1 else r * 0


def fama_macbeth(d: pd.DataFrame, regressors: list[str], controls: list[str] = CONTROLS) -> dict:
    """Monthly OLS of exret on rank-scaled regressors (rows with all regressors defined) and
    controls (missing -> 0). Ranks are taken within each formation on the formation sample.
    Returns mean slopes, NW(6) t-stats and the monthly slope series."""
    d = d.dropna(subset=regressors + ["exret"]).copy()
    for f, idx in d.groupby("formation").groups.items():
        firm = d.loc[idx].drop_duplicates("id").set_index("id")
        for c in regressors + controls:
            scaled = rank_scale(firm[c])
            d.loc[idx, "r_" + c] = d.loc[idx, "id"].map(scaled).to_numpy()
    for c in controls:
        d["r_" + c] = d["r_" + c].fillna(0.0)
    cols = ["r_" + c for c in regressors + controls]
    slopes = {}
    for m, g in d.groupby("month"):
        X = np.column_stack([np.ones(len(g)), g[cols].to_numpy(dtype=float)])
        if len(g) <= X.shape[1] + 10:
            continue
        beta, *_ = np.linalg.lstsq(X, g["exret"].to_numpy(dtype=float), rcond=None)
        slopes[m] = beta[1:]
    S = pd.DataFrame(slopes, index=cols).T.sort_index()
    out = {"n_months": len(S), "n_firm_months": int(len(d)), "coef": {}, "slopes": S}
    for c in cols:
        mean, se = nw_mean(S[c].to_numpy())
        out["coef"][c[2:]] = {"mean": mean, "se_nw": se, "t": mean / se}
    return out


def nw_mean(x: np.ndarray, lag: int = NW_LAG) -> tuple[float, float]:
    """Mean of a time series and its Newey-West standard error (Bartlett kernel)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    e = x - x.mean()
    s = e @ e / n
    for k in range(1, lag + 1):
        s += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    return float(x.mean()), float(np.sqrt(s / n))


# ------------------------------------------------------------------ portfolio sorts
def sort_portfolios(d: pd.DataFrame, signal: str, q: int = 5) -> pd.DataFrame:
    """Quintiles of `signal` at each formation. EW: equal weights each month. VW: formation
    market cap, drifting with each firm's cumulative return within the holding year.
    Returns monthly returns per (scheme, quintile) plus the Q5-Q1 spread."""
    d = d.dropna(subset=[signal, "ret"]).copy()
    firm = d.drop_duplicates(["formation", "id"])[["formation", "id", signal]]
    firm["q"] = firm.groupby("formation")[signal].transform(
        lambda s: pd.qcut(s.rank(method="first"), q, labels=False) + 1)
    d = d.merge(firm[["formation", "id", "q"]], on=["formation", "id"])
    d = d.sort_values(["formation", "id", "month"])
    d["gross_prior"] = d.groupby(["formation", "id"])["ret"].transform(lambda s: (1 + s).cumprod().shift(1).fillna(1.0))
    d["w"] = d["mkt_cap"] * d["gross_prior"]
    ew = d.groupby(["month", "q"])["ret"].mean().unstack()
    vw = (d.assign(wr=d["w"] * d["ret"]).groupby(["month", "q"])[["wr", "w"]].sum()
          .pipe(lambda x: x["wr"] / x["w"]).unstack())
    out = pd.concat({"EW": ew, "VW": vw}, axis=1)
    for sch in ("EW", "VW"):
        out[(sch, "Q5-Q1")] = out[(sch, q)] - out[(sch, 1)]
    return out


def ols_nw(y: np.ndarray, X: np.ndarray, lag: int = NW_LAG) -> tuple[np.ndarray, np.ndarray]:
    """OLS coefficients and Newey-West (Bartlett, no small-sample correction) standard errors.
    (statsmodels is not importable with the installed scipy, so this is done in numpy.)"""
    n = len(y)
    XtX_inv = np.linalg.inv(X.T @ X)
    b = XtX_inv @ X.T @ y
    u = (y - X @ b)[:, None] * X
    S = u.T @ u
    for k in range(1, lag + 1):
        G_k = u[k:].T @ u[:-k]
        S += (1 - k / (lag + 1)) * (G_k + G_k.T)
    V = XtX_inv @ S @ XtX_inv
    return b, np.sqrt(np.diag(V))


def alpha(spread: pd.Series, fac: pd.DataFrame) -> dict:
    """OLS of a long-short return on FF5 + UMD, NW(6) standard errors."""
    y = spread.dropna()
    y = y[y.index.isin(fac.index)]
    X = np.column_stack([np.ones(len(y)), fac.loc[y.index, ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "UMD"]].to_numpy()])
    b, se = ols_nw(y.to_numpy(dtype=float), X)
    return {"alpha": float(b[0]), "t": float(b[0] / se[0]), "n": int(len(y))}
