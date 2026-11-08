"""Phase 4: validation and test (protocol v1.1 sections 6 and 8, docs/phase3_design.md section 6,
operational choices in docs/phase4_procedure.md).

Tables:
- truth M: `phase3.build_table` (graded windows, every leaf column, traits at t).
- truth M variants for protocol section 8 robustness: windows with other filters, scored with
  methods.predict_all.
- truth D / D': acquired windows graded at the last pre-deal year L, built exactly as in
  scripts/explore_acquisitions.py, with the same leaf columns so recipes can be evaluated.

Every loader refuses validation and test unless unseal=True. Every unsealed read is appended to
results/unseal_log.jsonl before the data are touched.

Tests (differences in median |e|, or a median e for T2):
  T1  Gordon g2.5 - FF12 exit                         H: > 0
  T2  median e of Gordon g2.5                         H: > 0
  T3  (Gordon - FF12) in low minus high tercile of WACC_t - 2.5%      H: > 0
  T4  Damodaran 5-yr - Damodaran at t, cyclical FF12  H: < 0
  T5  50/50 log blend - better of {Gordon g2.5, FF12 exit}            H: < 0
  T7  (own - Damodaran-industry) under D' minus the same under D      H: < 0
  T8a/b/c  chosen agent recipe - best single / chosen random / chosen unconditional   H: < 0
T1-T5 use the common sample of the core methods (as in Phase 1); T8 uses the recipe evaluation
set with the FF12-exit fallback. Inference: firm-clustered bootstrap, 2,000 reps, seed 0,
one-sided p floored at 1/2,000; Holm over 14 tests on test only.
"""
from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd

from . import methods as M
from . import panel as P
from . import phase3 as P3
from . import recipes as R

REPS, SEED = 2000, 0
LN25 = np.log(1.25)
CYCLICAL = ["Enrgy", "Chems", "Manuf", "Durbl"]  # protocol H3, fixed list
# Phase 1 core sets (scripts/explore_phase1.py, scripts/explore_acquisitions.py). For D, E_dam_t
# and the log blend are added because T4D and T5D need them.
CORE_M = ["G_fcf_g2.5", "G_fcf3avg_g2.5", "G_vd_roic_g2.5", "G_vd_ronic=r", "E_ff12_med", "E_damind_med",
          "E_own", "E_dam_t", "E_dam_5yavg", "B50_G2.5_Eff12", "B50geo_G2.5_Eff12"]
CORE_D = ["G_fcf_g2.5", "G_fcf3avg_g2.5", "E_ff12_med", "E_damind_med", "E_own", "E_dam_5yavg",
          "B50_G2.5_Eff12", "E_dam_t", "B50geo_G2.5_Eff12"]
HOLM_FAMILY = ["T1", "T2", "T3", "T4", "T5", "T1D", "T2D", "T3D", "T4D", "T5D", "T7", "T8a", "T8b", "T8c"]
DATA_FILES = ["firm_years.pkl", "windows_h5.pkl", "windows_h3.pkl", "multiples_by_vintage.csv", "exits.csv"]


# ------------------------------------------------------------------ sealing
def _guard(split: str, unseal: bool, what: str) -> None:
    if split == "exploration":
        return
    if not unseal:
        raise PermissionError(f"{split} is sealed until Phase 4 (protocol v1 section 2)")
    P3.UNSEAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(P3.UNSEAL_LOG, "a") as f:
        f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "split": split,
                            "what": what}) + "\n")


def prior_unseals(split: str) -> list[dict]:
    if not P3.UNSEAL_LOG.exists():
        return []
    return [r for r in map(json.loads, P3.UNSEAL_LOG.read_text().splitlines()) if r.get("split") == split]


def _check_years(T: pd.DataFrame, split: str) -> None:
    a, b = P.SPLIT[split]
    assert len(T) and set(T["t"].unique()) <= set(range(a, b + 1)), (split, sorted(T["t"].unique()))


# ------------------------------------------------------------------ loading
def m_table(split: str, horizon: int = 5, unseal: bool = False) -> pd.DataFrame:
    T = P3.build_table(split, horizon, unseal=unseal)  # logs its own unseal
    _check_years(T, split)
    return T


def m_variant(split: str, unseal: bool, variant: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Truth-M windows (h5) under a protocol section 8 robustness filter, scored with
    methods.predict_all. Returns (S with id, t, ff12, truth, wacc_minus_g; X raw methods)."""
    _guard(split, unseal, f"m_variant:{variant}")
    fy = pd.read_pickle(P.PROC / "firm_years.pkl")
    allw = pd.read_pickle(P.PROC / "windows_h5.pkl")
    a, b = P.SPLIT[split]
    w = allw[allw.t.between(a, b)]
    base_t = w.quality_ok_t
    status = w.status.isin(["survived", "shrank"])
    out_q = w.quality_ok_tH.eq(True)
    pos = w.ev_tH.gt(0)
    sel = {
        "baseline": base_t & status & out_q & pos,
        "no_outcome_quality_filter": base_t & status & pos,
        "statements_90d": base_t & status & out_q & pos & w.stmt_age_days_t.ge(90),
        "excl_mcap_jump": base_t & status & out_q & pos & ~w.mcap_jump_suspect_t.eq(True) & ~w.mcap_jump_suspect_tH.eq(True),
        "no_quality_screen": status & pos,
        "survivors_only": base_t & w.status.eq("survived") & out_q & pos,
        "annual_erp": base_t & status & out_q & pos,
    }[variant]
    g = w[sel].copy().reset_index(drop=True)
    if variant == "annual_erp":  # same WACC with the annual ERP in the cost of equity (panel.add_wacc)
        E = g["mkt_cap_t"]
        V = E + g["total_debt_t"].fillna(0).clip(lower=0)
        g["wacc_t"] = g["wacc_t"] + E / V * g["beta_l_t"] * (g["erp_annual_t"] - g["erp_t"])
    with np.errstate(invalid="ignore", divide="ignore"):
        X = M.predict_all(g, fy)
    S = g[["id", "t", "ff12_t", "ev_tH"]].rename(columns={"ff12_t": "ff12", "ev_tH": "truth"})
    S["wacc_minus_g"] = g["wacc_t"] - 0.025
    _check_years(S, split)
    return S, X


def d_table(split: str, unseal: bool = False) -> tuple[pd.DataFrame, dict]:
    """Acquired windows of the split graded at L (t < L < t+5), same rules as
    scripts/explore_acquisitions.py. Columns: every leaf column, traits at t, truth (deal EV),
    truth_dp (market EV at June 30 of L+1 if the deal was announced after it, else NaN),
    in_eval (FF12 exit defined), and deal fields for robustness. Also returns window counts by
    exit status (reported)."""
    _guard(split, unseal, "d_table")
    fy = pd.read_pickle(P.PROC / "firm_years.pkl")
    ex = pd.read_csv(P.PROC / "exits.csv", parse_dates=["complete_date", "announce_date", "last_value_date"])
    a0, b0 = P.SPLIT[split]
    allw = pd.read_pickle(P.PROC / "windows_h5.pkl")
    wq = allw[allw.t.between(a0, b0) & allw.quality_ok_t]
    counts = {"quality_ok_at_t": int(len(wq)), **{k: int(v) for k, v in wq.status.value_counts().items()}}
    w = wq[wq.status.eq("exited")].merge(
        ex[["id", "exit_type", "complete_date", "announce_date", "last_fy", "last_value_date", "acq_ev",
            "acq_ev_old_double_count", "net_claims_to_mcap", "cash_pct", "pe_buyer"]], on="id", how="left")
    counts["exited_by_type"] = {str(k): int(v) for k, v in w.exit_type.fillna("none").value_counts().items()}
    end = pd.to_datetime((w.t + 6).astype(str) + "-06-30")
    start = pd.to_datetime((w.t + 1).astype(str) + "-06-30")
    a = w[w.exit_type.eq("acquired") & (w.complete_date > start) & (w.complete_date <= end)
          & w.last_fy.between(w.t + 1, w.t + 4)].copy()
    by = fy.set_index(["id", "fiscal_year"])
    keyL = list(zip(a.id, a.last_fy))
    for src, dst in [("fcf", "fcf_tH"), ("fcf_ex_sbc", "fcf_ex_sbc_tH"), ("ebitda", "ebitda_tH"),
                     ("nopat", "nopat_tH"), ("roic", "roic_tH"), ("ev", "ev_L"), ("quality_ok", "quality_ok_L")]:
        a[dst] = by[src].reindex(keyL).to_numpy()
    for k, col in ((1, "fcf_tH_m1"), (2, "fcf_tH_m2")):
        a[col] = by["fcf"].reindex(list(zip(a.id, a.last_fy - k))).to_numpy()
    a["tH_year"] = a["last_fy"]
    a = a[a.acq_ev.gt(0) & a.quality_ok_L.eq(True)].reset_index(drop=True)
    counts["acquired_graded"] = int(len(a))
    with np.errstate(invalid="ignore", divide="ignore"):
        std = M.predict_all(a, fy)
        fcf3 = a[["fcf_tH_m2", "fcf_tH_m1", "fcf_tH"]].mean(axis=1, skipna=False)  # ends at L
        cols = {c: std[c] for c in R.EXIT_MULTIPLES.values()}
        cf = {"fcf": a["fcf_tH"], "fcf_ex_sbc": a["fcf_ex_sbc_tH"], "fcf_3yavg": fcf3}
        rate = {"wacc": a["wacc_t"], "rf_plus_5": a["wacc_simple_t"]}
        for gg in R.G_GRID:
            for rn, r in rate.items():
                for cn, c in cf.items():
                    cols[f"gordon|{cn}|{gg:.3f}|{rn}"] = M.gordon(c, r, gg)
                cols[f"vd|roic|{gg:.3f}|{rn}"] = M.value_driver(a["nopat_tH"], r, gg, a["roic_tH"])
                cols[f"vd|r|{gg:.3f}|{rn}"] = M.value_driver(a["nopat_tH"], r, gg, r)
    tr = P3._traits(fy).rename(columns={"fiscal_year": "t"})
    T = a[["id", "t", "ff12_t", "acq_ev"]].rename(columns={"ff12_t": "ff12", "acq_ev": "truth"})
    clean = (a.announce_date > a.last_value_date) & a.ev_L.gt(0)
    T["truth_dp"] = a["ev_L"].where(clean)
    T["truth_old_def"] = a["acq_ev_old_double_count"]
    T["low_leverage"] = a["net_claims_to_mcap"].abs().lt(0.2)
    T["cash_deal"] = a["cash_pct"].eq(100)
    T["pe_buyer"] = a["pe_buyer"].eq("Yes")
    T = pd.concat([T, pd.DataFrame(cols, index=a.index)], axis=1).merge(tr, on=["id", "t"], how="left")
    T["in_eval"] = T[R.FALLBACK].gt(0)
    assert len(T) == len(a)
    _check_years(T, split)
    return T, counts


# ------------------------------------------------------------------ predictions
def raw_methods(T: pd.DataFrame, names=None) -> pd.DataFrame:
    """The protocol section 4 single methods with NaN where undefined (no fallback), so they
    equal methods.predict_all on the same windows."""
    out = {}
    for k in names or P3.SINGLE_METHODS:
        p, fb = R.predict(P3.SINGLE_METHODS[k], T)
        out[k] = np.where(fb, np.nan, p)
    return pd.DataFrame(out, index=T.index)


def ln_err(pred, truth) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.log(np.asarray(pred, dtype=float) / np.asarray(truth, dtype=float))


# ------------------------------------------------------------------ inference
def cluster_boot(stat, firms: np.ndarray, reps: int = REPS, seed: int = SEED) -> tuple[float, np.ndarray]:
    """Firm-clustered bootstrap of stat(row_index). Same resampling stream as
    phase3.boot_diff (np.unique codes, rng.integers), so T8 matches it exactly."""
    if len(firms) == 0:
        raise ValueError("empty sample")
    codes, inv = np.unique(firms, return_inverse=True)
    rows = [np.flatnonzero(inv == k) for k in range(len(codes))]
    rng = np.random.default_rng(seed)
    point = float(stat(np.arange(len(firms))))
    st = np.empty(reps)
    for i in range(reps):
        st[i] = stat(np.concatenate([rows[k] for k in rng.integers(0, len(codes), len(codes))]))
    return point, st


def summarize(point: float, st: np.ndarray, direction: str, n: int, firms: np.ndarray, **extra) -> dict:
    """direction 'gt': hypothesis stat > 0; 'lt': stat < 0. One-sided p = share of bootstrap
    statistics on the wrong side of 0 (ties count against H), floored at 1/reps."""
    assert np.isfinite(point) and np.isfinite(st).all(), "non-finite bootstrap statistic"
    wrong = np.mean(st <= 0) if direction == "gt" else np.mean(st >= 0)
    lo, hi = np.percentile(st, [2.5, 97.5])
    return {"n": int(n), "n_firms": int(len(np.unique(firms))), "stat": point, "ci95": [float(lo), float(hi)],
            "direction": direction, "p_one_sided": float(max(wrong, 1 / len(st))), **extra}


def holm(pvals: dict[str, float], alpha: float = 0.05) -> dict[str, dict]:
    keys = sorted(pvals, key=lambda k: (pvals[k], HOLM_FAMILY.index(k) if k in HOLM_FAMILY else 99))
    m, out, run, stop = len(keys), {}, 0.0, False
    for i, k in enumerate(keys):
        run = max(run, min(1.0, (m - i) * pvals[k]))
        reject = (not stop) and pvals[k] <= alpha / (m - i)
        stop = stop or not reject
        out[k] = {"p": pvals[k], "p_holm": run, "reject": bool(reject)}
    return out


# ------------------------------------------------------------------ T1-T5, T7
def _med_abs(e: np.ndarray, idx: np.ndarray) -> float:
    return float(np.median(np.abs(e[idx])))


def tests_from(X: pd.DataFrame, S: pd.DataFrame, core: list[str], suffix: str = "",
               which=("T1", "T2", "T3", "T4", "T5"), gordon: str = "G_fcf_g2.5",
               truth_col: str = "truth") -> tuple[dict, dict]:
    """T1-T5 on the common sample of `core` (+ `gordon`). X: raw method predictions (NaN where
    undefined), S: id, ff12, wacc_minus_g and the truth column, same index as X."""
    cols = list(dict.fromkeys(core + [gordon]))
    common = (X[cols].notna().all(axis=1) & S[truth_col].gt(0)).to_numpy()
    Sc = S[common].reset_index(drop=True)
    E = {k: ln_err(X.loc[common, k].to_numpy(), Sc[truth_col]) for k in cols}
    firms = Sc["id"].to_numpy()
    n, full = len(Sc), np.arange(len(Sc))
    graded = S[truth_col].gt(0).to_numpy()
    desc = {"n_graded": int(graded.sum()), "n_common": n, "n_common_firms": int(len(np.unique(firms))),
            "methods": {k: {"median_abs": _med_abs(E[k], full), "bias": float(np.median(E[k])),
                            "hit_rate_itt_all_graded": float(np.mean(np.nan_to_num(
                                np.abs(ln_err(X[k], S[truth_col]))[graded], nan=np.inf) < LN25))}
                        for k in cols}}
    G, F = E[gordon], E["E_ff12_med"]
    out = {}
    if "T1" in which:
        out["T1" + suffix] = summarize(*cluster_boot(lambda i: _med_abs(G, i) - _med_abs(F, i), firms), "gt", n, firms)
    if "T2" in which:
        out["T2" + suffix] = summarize(*cluster_boot(lambda i: float(np.median(G[i])), firms), "gt", n, firms)
    if "T3" in which:
        x = Sc["wacc_minus_g"].to_numpy(dtype=float)  # WACC_t - 2.5%
        q1, q2 = np.nanquantile(x, [1 / 3, 2 / 3])
        low, high = x <= q1, x > q2

        def t3(i):
            lo_i, hi_i = i[low[i]], i[high[i]]
            return (_med_abs(G, lo_i) - _med_abs(F, lo_i)) - (_med_abs(G, hi_i) - _med_abs(F, hi_i))
        out["T3" + suffix] = summarize(*cluster_boot(t3, firms), "gt", n, firms, cuts=[float(q1), float(q2)],
                                       n_low=int(low.sum()), n_high=int(high.sum()))
    if "T4" in which:
        ci = np.flatnonzero(Sc["ff12"].isin(CYCLICAL).to_numpy())
        d5c, dtc = E["E_dam_5yavg"][ci], E["E_dam_t"][ci]
        out["T4" + suffix] = summarize(*cluster_boot(lambda i: _med_abs(d5c, i) - _med_abs(dtc, i), firms[ci]),
                                       "lt", len(ci), firms[ci])
    if "T5" in which:
        best = gordon if _med_abs(G, full) < _med_abs(F, full) else "E_ff12_med"
        B, Pb = E["B50geo_G2.5_Eff12"], E[best]
        out["T5" + suffix] = summarize(*cluster_boot(lambda i: _med_abs(B, i) - _med_abs(Pb, i), firms), "lt", n,
                                       firms, best_pure=best)
    return out, desc


def method_tests(T: pd.DataFrame, core: list[str], suffix: str = "", rows=None, **kw) -> tuple[dict, dict]:
    T = T if rows is None else T[rows]
    return tests_from(raw_methods(T, list(dict.fromkeys(core + [kw.get("gordon", "G_fcf_g2.5")]))),
                      T, core, suffix, **kw)


def t7(TD: pd.DataFrame, rows=None) -> dict:
    """Same firms, same fundamentals: CORE_D defined, deal EV and clean pre-announcement EV."""
    TD = TD if rows is None else TD[rows]
    X = raw_methods(TD, CORE_D)
    ok = X.notna().all(axis=1).to_numpy() & TD["truth"].gt(0).to_numpy() & TD["truth_dp"].gt(0).to_numpy()
    S = TD[ok].reset_index(drop=True)
    o, d = X.loc[ok, "E_own"].to_numpy(), X.loc[ok, "E_damind_med"].to_numpy()
    oD, dD = ln_err(o, S["truth"]), ln_err(d, S["truth"])
    oP, dP = ln_err(o, S["truth_dp"]), ln_err(d, S["truth_dp"])

    def stat(i):
        return (_med_abs(oP, i) - _med_abs(dP, i)) - (_med_abs(oD, i) - _med_abs(dD, i))
    full, firms = np.arange(len(S)), S["id"].to_numpy()
    return summarize(*cluster_boot(stat, firms), "lt", len(S), firms,
                     D={"own": _med_abs(oD, full), "damind": _med_abs(dD, full)},
                     Dprime={"own": _med_abs(oP, full), "damind": _med_abs(dP, full)})


def replication(TM: pd.DataFrame, TD: pd.DataFrame, T3h: pd.DataFrame, counts: dict) -> dict:
    """T1-T5 on M (h5), T1D-T5D, T7. Horizon 3 (T1-T5 on M) as robustness."""
    tm, dm = method_tests(TM, CORE_M)
    td, dd = method_tests(TD, CORE_D, suffix="D")
    th3, dh3 = method_tests(T3h, CORE_M, suffix="_h3")
    return {"tests": {**tm, **td, "T7": t7(TD)}, "robustness_h3": th3,
            "describe": {"M": dm, "D": dd, "M_h3": dh3, "window_counts": counts}}


M_VARIANTS = ["no_outcome_quality_filter", "statements_90d", "excl_mcap_jump", "annual_erp",
              "no_quality_screen", "survivors_only"]


def _safe(fn):
    """Reported-only robustness must not stop a one-shot run: an empty or degenerate subsample
    is recorded as skipped (with the reason) instead of raising."""
    try:
        return fn()
    except (ValueError, IndexError, AssertionError, ZeroDivisionError) as e:
        return {"skipped": f"{type(e).__name__}: {e}"}


def robustness(split: str, unseal: bool, TM: pd.DataFrame, TD: pd.DataFrame, earlier_d_ids: set) -> dict:
    """Protocol section 8, reported only: T1 and T2 under each truth-M variant and each extra
    discount rate / cash-flow choice; T1D and T2D under each truth-D variant; and T1D-T5D and
    T7 without deals already graded under truth D in an earlier split."""
    out = {}
    S0, X0 = m_variant(split, unseal, "baseline")
    base = tests_from(X0, S0, CORE_M, which=("T1", "T2"))[0]
    ref = method_tests(TM, CORE_M, which=("T1", "T2"))[0]
    for k in ("T1", "T2"):  # the predict_all path must reproduce the main table exactly
        assert abs(base[k]["stat"] - ref[k]["stat"]) < 1e-12 and base[k]["n"] == ref[k]["n"], (k, base[k], ref[k])
    for v in M_VARIANTS:
        S, X = m_variant(split, unseal, v)
        out[f"M:{v}"] = _safe(lambda: tests_from(X, S, CORE_M, which=("T1", "T2"))[0])
    out["M:treasury_plus_5"] = _safe(lambda: method_tests(TM, CORE_M, which=("T1", "T2"), gordon="G_fcf_g2.5_rf+5")[0])
    out["M:fcf_ex_sbc"] = _safe(lambda: method_tests(TM, CORE_M, which=("T1", "T2"), gordon="G_exsbc_g2.5")[0])
    for name, rows in (("low_leverage", TD["low_leverage"]), ("cash_deals", TD["cash_deal"]),
                       ("pe_buyers", TD["pe_buyer"])):
        r = rows.to_numpy(dtype=bool)
        out[f"D:{name}"] = _safe(lambda: method_tests(TD, CORE_D, "D", rows=r, which=("T1", "T2"))[0])
    out["D:old_double_count_definition"] = _safe(lambda: method_tests(TD, CORE_D, "D", which=("T1", "T2"),
                                                                      truth_col="truth_old_def")[0])
    new = ~TD["id"].astype(str).isin({str(x) for x in earlier_d_ids}).to_numpy()
    out["D:excluding_deals_graded_in_earlier_splits"] = {
        "n_windows_dropped": int((~new).sum()), "n_windows_kept": int(new.sum()),
        "tests": _safe(lambda: method_tests(TD, CORE_D, "D", rows=new)[0]),
        "T7": _safe(lambda: t7(TD, rows=new))}
    return out


# ------------------------------------------------------------------ recipes on a split
def score_recipe(tree: dict, T: pd.DataFrame) -> dict:
    s = P3.grade(tree, T, detail=True)
    s.pop("fingerprint", None)
    return s


def dam_leaf_share(tree: dict, T: pd.DataFrame) -> float:
    """Share of evaluation rows routed to a leaf that uses a Damodaran published multiple."""
    _, _, leaf = R.predict(tree, T, return_leaf=True)
    ev = T["in_eval"].to_numpy()
    uses = [("dam_t" in json.dumps(lf) or "dam_5yavg" in json.dumps(lf)) for lf in R.leaves(tree)]
    return float(np.mean([uses[k] for k in leaf[ev]])) if ev.any() else float("nan")


def pooled_best_single(tables: list[pd.DataFrame]) -> tuple[str, dict]:
    """Best protocol section 4 method on the pooled evaluation sets (ties: list order)."""
    scores = {}
    for k, tree in P3.SINGLE_METHODS.items():
        es = []
        for T in tables:
            p, _ = R.predict(tree, T)
            es.append(np.abs(P3.errors(p, T))[T["in_eval"].to_numpy()])
        scores[k] = float(np.median(np.concatenate(es)))
    best = min(P3.SINGLE_METHODS, key=lambda k: (scores[k], list(P3.SINGLE_METHODS).index(k)))
    return best, scores


def t8(tree_a: dict, tree_b: dict, T: pd.DataFrame, name: str) -> dict:
    pa, _ = R.predict(tree_a, T)
    pb, _ = R.predict(tree_b, T)
    ev = T["in_eval"].to_numpy()
    a, b = np.abs(P3.errors(pa, T))[ev], np.abs(P3.errors(pb, T))[ev]
    firms = T.loc[ev, "id"].to_numpy()
    point, st = cluster_boot(lambda i: float(np.median(a[i]) - np.median(b[i])), firms)
    ref = P3.boot_diff(pa, pb, T)  # cross-check with the frozen helper
    assert abs(ref[0] - point) < 1e-12 and abs(ref[1] - np.percentile(st, 2.5)) < 1e-12, (name, ref, point)
    return summarize(point, st, "lt", int(ev.sum()), firms, vs=name)


def common_and_itt(tree: dict, single: dict, T: pd.DataFrame) -> dict:
    """Protocol section 3 metrics for a chosen recipe against the best single method:
    - common sample: windows where the single method is defined without fallback (the recipe is
      scored there with its own convention);
    - ITT hit rate over all graded truth-M windows. The recipe misses only where the FF12 exit is
      also undefined (outside the evaluation set); the single method misses wherever it is
      undefined."""
    pr, _ = R.predict(tree, T)
    ps, fbs = R.predict(single, T)
    truth = T["truth"].to_numpy(dtype=float)
    er, es = ln_err(pr, truth), ln_err(np.where(fbs, np.nan, ps), truth)
    both = ~np.isnan(er) & ~np.isnan(es)
    return {"n_common": int(both.sum()), "recipe_median_abs": float(np.median(np.abs(er[both]))),
            "recipe_bias": float(np.median(er[both])), "single_median_abs": float(np.median(np.abs(es[both]))),
            "single_bias": float(np.median(es[both])),
            "recipe_itt_hit": float(np.mean(np.nan_to_num(np.abs(er), nan=np.inf) < LN25)),
            "single_itt_hit": float(np.mean(np.nan_to_num(np.abs(es), nan=np.inf) < LN25)),
            "n_graded": int(len(T))}


def gain_share(ff12: float, rule: float, gbm: float) -> dict:
    """(FF12 - rule) / (FF12 - GBM). Undefined when the GBM does not beat the FF12 exit."""
    den = ff12 - gbm
    if den <= 0:
        return {"share": None, "note": "undefined: the GBM does not beat the FF12 exit on this split"}
    s = (ff12 - rule) / den
    return {"share": s, "note": "exceeds the ceiling (ceiling uninformative)" if s > 1 else ""}
