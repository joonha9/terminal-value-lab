"""Phase 3 data, grading and benchmarks for TV recipes (protocol v1 section 7).

Truth is M (market EV at June 30 of t+6) on the same graded windows as Phase 1. The evaluation
set is every graded window where the FF12 exit is defined (it is the fallback for undefined
leaves), so every recipe is scored on the same rows. Design notes: docs/phase3_design.md.

Validation and test tables are sealed: build_table refuses them unless the caller passes
`unseal=True`, which only the Phase 4 script does (once, after finalists are frozen).
"""
from __future__ import annotations

import hashlib
import itertools
import json
from datetime import datetime
from functools import lru_cache

import numpy as np
import pandas as pd

from . import methods as M
from . import panel as P
from . import recipes as R

LN25 = np.log(1.25)
G_TRAIT = 0.025  # wacc_minus_g uses g = 2.5%

SINGLE_METHODS = {  # protocol section 4 candidates, written as one-leaf recipes
    "G_fcf_g2": {"method": "gordon", "cash_flow": "fcf", "g": 0.02, "r": "wacc"},
    "G_fcf_g2.5": {"method": "gordon", "cash_flow": "fcf", "g": 0.025, "r": "wacc"},
    "G_fcf_g3": {"method": "gordon", "cash_flow": "fcf", "g": 0.03, "r": "wacc"},
    "G_fcf3avg_g2.5": {"method": "gordon", "cash_flow": "fcf_3yavg", "g": 0.025, "r": "wacc"},
    "G_exsbc_g2.5": {"method": "gordon", "cash_flow": "fcf_ex_sbc", "g": 0.025, "r": "wacc"},
    "G_fcf_g2.5_rf+5": {"method": "gordon", "cash_flow": "fcf", "g": 0.025, "r": "rf_plus_5"},
    "G_vd_roic_g2.5": {"method": "value_driver", "ronic": "roic", "g": 0.025, "r": "wacc"},
    "G_vd_ronic=r": {"method": "value_driver", "ronic": "r", "g": 0.025, "r": "wacc"},
    "E_ff12_med": {"method": "exit", "multiple": "ff12"},
    "E_damind_med": {"method": "exit", "multiple": "damind"},
    "E_own": {"method": "exit", "multiple": "own"},
    "E_dam_t": {"method": "exit", "multiple": "dam_t"},
    "E_dam_5yavg": {"method": "exit", "multiple": "dam_5yavg"},
    "B50_G2.5_Eff12": {"method": "blend", "space": "level", "parts": [
        {"weight": 0.5, "leaf": {"method": "gordon", "cash_flow": "fcf", "g": 0.025, "r": "wacc"}},
        {"weight": 0.5, "leaf": {"method": "exit", "multiple": "ff12"}}]},
    "B50geo_G2.5_Eff12": {"method": "blend", "space": "log", "parts": [
        {"weight": 0.5, "leaf": {"method": "gordon", "cash_flow": "fcf", "g": 0.025, "r": "wacc"}},
        {"weight": 0.5, "leaf": {"method": "exit", "multiple": "ff12"}}]},
}


# ------------------------------------------------------------------ tables
def _traits(fy: pd.DataFrame) -> pd.DataFrame:
    """Traits at each fiscal year, with within-year percentile ranks computed over the
    clean universe at that year (point-in-time; independent of what happens later)."""
    t = fy[["id", "fiscal_year", "ff12", "in_universe", "quality_ok", "fcf", "ebitda", "wacc"]
           + [c for c in R.TRAITS if c in fy.columns]].copy()
    t["wacc_minus_g"] = t["wacc"] - G_TRAIT
    t["fcf_positive"] = np.where(t["fcf"].isna(), np.nan, (t["fcf"] > 0).astype(float))
    t["ebitda_positive"] = np.where(t["ebitda"].isna(), np.nan, (t["ebitda"] > 0).astype(float))
    u = t["in_universe"] & t["quality_ok"]
    for c in R.TRAITS:
        ref = t[c].where(u)
        out = pd.Series(np.nan, index=t.index)
        for y, idx in t.groupby("fiscal_year").groups.items():
            base = np.sort(ref.loc[idx].dropna().to_numpy())
            if len(base) == 0:
                continue
            x = t.loc[idx, c].to_numpy(dtype=float)
            # share of clean universe firms at or below x (ties: average rank)
            lo = np.searchsorted(base, x, side="left")
            hi = np.searchsorted(base, x, side="right")
            pct = (lo + hi) / 2 / len(base)
            out.loc[idx] = np.where(np.isnan(x), np.nan, pct)
        t[f"pct_{c}"] = out
    keep = ["id", "fiscal_year", *R.TRAITS, *[f"pct_{c}" for c in R.TRAITS], *R.FLAGS]
    return t[keep]


def _leaf_matrix(g: pd.DataFrame, fy: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    std = M.predict_all(g, fy)
    out = {c: std[c] for c in R.EXIT_MULTIPLES.values()}
    H = int(g["horizon"].iloc[0])
    cf = {"fcf": g["fcf_tH"], "fcf_ex_sbc": g["fcf_ex_sbc_tH"],
          "fcf_3yavg": g[[f"fcf_t{k}" for k in (H - 2, H - 1, H)]].mean(axis=1, skipna=False)}
    rate = {"wacc": g["wacc_t"], "rf_plus_5": g["wacc_simple_t"]}
    for gg in R.G_GRID:
        for rn, r in rate.items():
            for cn, c in cf.items():
                out[f"gordon|{cn}|{gg:.3f}|{rn}"] = M.gordon(c, r, gg)
            out[f"vd|roic|{gg:.3f}|{rn}"] = M.value_driver(g["nopat_tH"], r, gg, g["roic_tH"])
            out[f"vd|r|{gg:.3f}|{rn}"] = M.value_driver(g["nopat_tH"], r, gg, r)
    return pd.DataFrame(out, index=g.index), std


UNSEAL_LOG = P.ROOT / "results" / "unseal_log.jsonl"


def build_table(split: str = "exploration", horizon: int = 5, unseal: bool = False) -> pd.DataFrame:
    """One row per graded truth-M window of the split: id, t, ff12, truth, traits at t and
    every leaf's prediction. `in_eval` marks the evaluation set (FF12 exit defined).
    Returns a copy, so callers cannot alter the cached table. Every unsealed call is logged."""
    if split != "exploration":
        if not unseal:
            raise PermissionError(f"{split} is sealed until Phase 4 (protocol v1 section 2)")
        UNSEAL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(UNSEAL_LOG, "a") as f:
            f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"),
                                "split": split, "horizon": horizon}) + "\n")
    return _build_table(split, horizon).copy()


@lru_cache(maxsize=None)
def _build_table(split: str, horizon: int) -> pd.DataFrame:
    fy = pd.read_pickle(P.PROC / "firm_years.pkl")
    allw = pd.read_pickle(P.PROC / f"windows_h{horizon}.pkl")
    a, b = P.SPLIT[split]
    w = allw[allw.t.between(a, b) & allw.quality_ok_t]
    g = w[w.status.isin(["survived", "shrank"]) & w.quality_ok_tH.eq(True) & w.ev_tH.gt(0)].copy()
    assert set(g.t) <= set(range(a, b + 1))
    with np.errstate(invalid="ignore", divide="ignore"):
        leaves, _ = _leaf_matrix(g, fy)
    tr = _traits(fy).rename(columns={"fiscal_year": "t"})
    T = g[["id", "t", "ff12_t", "ev_tH"]].rename(columns={"ff12_t": "ff12", "ev_tH": "truth"})
    T = pd.concat([T, leaves], axis=1).merge(tr, on=["id", "t"], how="left")
    T["in_eval"] = T[R.FALLBACK].gt(0)
    assert len(T) == len(g)
    return T.reset_index(drop=True)


@lru_cache(maxsize=None)
def raw_quantiles(split: str = "exploration") -> dict[str, list[float]]:
    """Percentiles 5..95 of each trait over the clean universe in the split's start years (the
    same point-in-time population as the percentile ranks; not outcome-selected). Used by the
    random-search generator to draw raw thresholds where the data are."""
    if split != "exploration":
        raise PermissionError("raw quantiles are only needed for the exploration search")
    fy = pd.read_pickle(P.PROC / "firm_years.pkl")
    a, b = P.SPLIT[split]
    tr = _traits(fy)
    u = fy[["id", "fiscal_year", "in_universe", "quality_ok"]]
    tr = tr.merge(u, on=["id", "fiscal_year"])
    tr = tr[tr.fiscal_year.between(a, b) & tr.in_universe & tr.quality_ok]
    return {c: [float(tr[c].quantile(q / 100)) for q in range(R.PCT_RANGE[0], R.PCT_RANGE[1] + 1)]
            for c in R.TRAITS}


# ------------------------------------------------------------------ grading
def errors(pred: np.ndarray, T: pd.DataFrame) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.log(pred / T["truth"].to_numpy(dtype=float))


def fingerprint(pred: np.ndarray, T: pd.DataFrame) -> str:
    """Behaviour identity of a recipe: hash of its rounded log predictions on the evaluation
    set. Recipes that predict the same values everywhere share a fingerprint."""
    ev = T["in_eval"].to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        v = np.round(np.log(pred[ev]), 6) + 0.0
    return hashlib.sha1(v.tobytes()).hexdigest()[:12]


def score_pred(pred: np.ndarray, used_fb: np.ndarray, T: pd.DataFrame, detail: bool = True) -> dict:
    """Scores on the evaluation set. `hit_rate_eval` is the share with |e| < ln 1.25 on the
    evaluation set (fallback applied); it is NOT the protocol section 3 ITT hit rate."""
    ev = T["in_eval"].to_numpy()
    e = errors(pred, T)[ev]
    out = {"n": int(ev.sum()), "median_abs": float(np.median(np.abs(e))), "bias": float(np.median(e)),
           "hit_rate_eval": float(np.mean(np.abs(e) < LN25)), "fallback_share": float(used_fb[ev].mean()),
           "fingerprint": fingerprint(pred, T)}
    if detail:
        s = pd.DataFrame({"a": np.abs(e), "e": e, "ff12": T.loc[ev, "ff12"].to_numpy()})
        by = s.groupby("ff12").agg(n=("a", "size"), median_abs=("a", "median"), bias=("e", "median"))
        out["by_ff12"] = {k: {"n": int(v.n), "median_abs": round(float(v.median_abs), 3),
                              "bias": round(float(v.bias), 3)} for k, v in by.iterrows()}
    return out


def grade(tree: dict, T: pd.DataFrame | None = None, detail: bool = True) -> dict:
    T = build_table() if T is None else T
    pred, fb, leaf = R.predict(tree, T, return_leaf=True)
    out = score_pred(pred, fb, T, detail)
    ev = T["in_eval"].to_numpy()
    n_leaves = len(R.leaves(tree))
    out["leaf_share"] = [round(float(np.mean(leaf[ev] == k)), 3) for k in range(n_leaves)]
    return out


def boot_diff(pa: np.ndarray, pb: np.ndarray, T: pd.DataFrame, reps: int = 2000, seed: int = 0) -> tuple:
    """Firm-clustered bootstrap of median|e_a| - median|e_b| on the evaluation set."""
    ev = T["in_eval"].to_numpy()
    a, b = np.abs(errors(pa, T))[ev], np.abs(errors(pb, T))[ev]
    firms = T.loc[ev, "id"].to_numpy()
    codes, inv = np.unique(firms, return_inverse=True)
    rows = [np.flatnonzero(inv == k) for k in range(len(codes))]
    rng = np.random.default_rng(seed)
    st = []
    for _ in range(reps):
        idx = np.concatenate([rows[k] for k in rng.integers(0, len(codes), len(codes))])
        st.append(np.median(a[idx]) - np.median(b[idx]))
    lo, hi = np.percentile(st, [2.5, 97.5])
    return float(np.median(a) - np.median(b)), float(lo), float(hi)


# ------------------------------------------------------------------ GBM ceiling
GBM_PARAMS = dict(loss="absolute_error", max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                  min_samples_leaf=40, l2_regularization=1.0, random_state=0)
GBM_METHOD_FEATURES = ["E_own", "E_damind_med", "E_dam_t", "E_dam_5yavg",
                       "gordon|fcf|0.025|wacc", "gordon|fcf_3yavg|0.025|wacc", "vd|roic|0.025|wacc"]


def gbm_features(T: pd.DataFrame, with_methods: bool) -> pd.DataFrame:
    X = T[list(R.TRAITS) + list(R.FLAGS)].astype(float).copy()
    X["ff12"] = pd.Categorical(T["ff12"], categories=R.FF12).codes.astype(float)
    X.loc[X["ff12"] < 0, "ff12"] = np.nan
    if with_methods:
        for c in GBM_METHOD_FEATURES:
            X[f"lnratio_{c}"] = np.log(T[c].where(T[c] > 0) / T[R.FALLBACK])
    return X


def _gbm():
    from sklearn.ensemble import HistGradientBoostingRegressor
    return HistGradientBoostingRegressor(categorical_features=["ff12"], **GBM_PARAMS)


def gbm_fit(T_train: pd.DataFrame, with_methods: bool):
    E = T_train[T_train["in_eval"]]
    y = np.log(E["truth"] / E[R.FALLBACK])
    return _gbm().fit(gbm_features(E, with_methods), y)


def gbm_predict(model, T: pd.DataFrame, with_methods: bool) -> np.ndarray:
    adj = model.predict(gbm_features(T, with_methods))
    return T[R.FALLBACK].to_numpy(dtype=float) * np.exp(adj)


def gbm_crossfit(T: pd.DataFrame, with_methods: bool, folds: int = 5) -> np.ndarray:
    """Out-of-fold GBM predictions on one split, folds grouped by firm."""
    from sklearn.model_selection import GroupKFold
    pred = np.full(len(T), np.nan)
    ev = np.flatnonzero(T["in_eval"].to_numpy())
    E = T.iloc[ev]
    X = gbm_features(E, with_methods)
    y = np.log(E["truth"] / E[R.FALLBACK]).to_numpy()
    for tr, te in GroupKFold(n_splits=folds).split(X, y, groups=E["id"]):
        m = _gbm().fit(X.iloc[tr], y[tr])
        pred[ev[te]] = E[R.FALLBACK].to_numpy()[te] * np.exp(m.predict(X.iloc[te]))
    return pred


# ------------------------------------------------------------------ diagnostics shown to agents
DIAG_METHODS = ["G_fcf_g2.5", "G_fcf3avg_g2.5", "E_ff12_med", "E_own", "E_dam_5yavg"]


def diagnostics(T: pd.DataFrame | None = None) -> dict:
    """Median |e| and bias of key single methods by FF12 and by tercile of each trait
    (exploration evaluation set; terciles of the evaluation set)."""
    T = build_table() if T is None else T
    ev = T["in_eval"].to_numpy()
    E = T[ev]
    errs = {}
    for k in DIAG_METHODS:
        p, _ = R.predict(SINGLE_METHODS[k], T)
        errs[k] = errors(p, T)[ev]
    D = pd.DataFrame(errs, index=E.index)
    out = {"by_ff12": {}, "by_tercile": {}}
    for f, idx in E.groupby("ff12").groups.items():
        out["by_ff12"][f] = {"n": len(idx), **{k: (round(float(D.loc[idx, k].abs().median()), 3),
                                                     round(float(D.loc[idx, k].median()), 3)) for k in DIAG_METHODS}}
    for c in R.TRAITS:
        x = E[c]
        q = x.quantile([1 / 3, 2 / 3]).to_numpy()
        bins = {"low": x <= q[0], "mid": (x > q[0]) & (x <= q[1]), "high": x > q[1]}
        out["by_tercile"][c] = {
            "cuts": [round(float(v), 4) for v in q],
            **{b: {"n": int(m.sum()), **{k: round(float(D.loc[m, k].abs().median()), 3) for k in DIAG_METHODS}}
               for b, m in bins.items()}}
    return out


# ------------------------------------------------------------------ unconditional benchmark
def _leaf_of_column(c: str) -> dict:
    if c in R.EXIT_MULTIPLES.values():
        return {"method": "exit", "multiple": {v: k for k, v in R.EXIT_MULTIPLES.items()}[c]}
    kind, a, g, r = c.split("|")
    if kind == "gordon":
        return {"method": "gordon", "cash_flow": a, "g": float(g), "r": r}
    return {"method": "value_driver", "ronic": a, "g": float(g), "r": r}


def unconditional_grid(T: pd.DataFrame) -> list[tuple[float, dict]]:
    """[addition, design review 2026-11-07] Every recipe without a split that uses one leaf or a
    2-part blend (weights 0.05..0.95, log and level), scored exactly as recipes are. Returns
    (median |e|, recipe) sorted best first. About 170k recipes."""
    ev = T["in_eval"].to_numpy()
    truth = T["truth"].to_numpy(dtype=float)[ev]
    fb = T[R.FALLBACK].to_numpy(dtype=float)[ev]
    cols = R.all_leaf_columns()
    V = {c: np.where(T[c].to_numpy(dtype=float)[ev] > 0, T[c].to_numpy(dtype=float)[ev], np.nan) for c in cols}
    L = {c: np.log(v) for c, v in V.items()}
    out = []

    def med(p: np.ndarray) -> float:
        p = np.where(p > 0, p, fb)
        return float(np.median(np.abs(np.log(p / truth))))

    with np.errstate(invalid="ignore", divide="ignore"):
        for c in cols:
            out.append((med(V[c]), _leaf_of_column(c)))
        weights = [round(0.05 * k, 2) for k in range(1, 20)]
        for a, b in itertools.combinations(cols, 2):
            for w in weights:
                for space in ("log", "level"):
                    p = np.exp(w * L[a] + (1 - w) * L[b]) if space == "log" else w * V[a] + (1 - w) * V[b]
                    tree = {"method": "blend", "space": space, "parts": [
                        {"weight": w, "leaf": _leaf_of_column(a)},
                        {"weight": round(1 - w, 2), "leaf": _leaf_of_column(b)}]}
                    out.append((med(p), tree))
    out.sort(key=lambda x: x[0])
    return out


def top_distinct(records: list[dict], k: int = 3, key=lambda r: r["explore"]["median_abs"]) -> list[dict]:
    """The k best records with distinct behaviour fingerprints (ties: list order)."""
    seen, out = set(), []
    for r in sorted(records, key=key):
        fp = r["explore"]["fingerprint"]
        if fp in seen:
            continue
        seen.add(fp)
        out.append(r)
        if len(out) == k:
            break
    return out
