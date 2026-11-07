"""Phase 1 exploration: TV methods vs actual EV at t+5, EXPLORATION START YEARS ONLY (t = 2015-16).

    python3 -P terminal-value-lab/scripts/explore_phase1.py

Validation (t = 2017-18) and test (t = 2019-20) windows are never loaded for grading here.
Tables are printed and written to results/phase1/.
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
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)
pd.set_option("display.max_rows", 80)
EXPLORATION = P.SPLIT["exploration"]
LN25 = np.log(1.25)
CORE = ["G_fcf_g2.5", "G_fcf3avg_g2.5", "G_vd_roic_g2.5", "G_vd_ronic=r", "E_ff12_med", "E_damind_med",
        "E_own", "E_dam_t", "E_dam_5yavg", "B50_G2.5_Eff12", "B50geo_G2.5_Eff12"]


def show(name: str, df: pd.DataFrame, note: str = "") -> None:
    print(f"\n=== {name} " + "=" * max(0, 74 - len(name)))
    if note:
        print(note)
    print(df.to_string())
    df.to_csv(OUT / f"{name.split(' ')[0]}.csv")


def score(e: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "n": e.notna().sum(),
        "median_abs_ln_err": e.abs().median(),
        "bias_median_ln": e.median(),
        "within_25pct": (e.abs() < LN25).sum() / e.notna().sum(),
    }).round(3)


def boot_diff(e: pd.DataFrame, a: str, b: str, firms: pd.Series, reps: int = 1000, seed: int = 0):
    """Firm-clustered bootstrap of median|e_a| - median|e_b| (negative = a better)."""
    rng = np.random.default_rng(seed)
    d = pd.DataFrame({"a": e[a].abs(), "b": e[b].abs(), "f": firms}).dropna()
    groups = {f: g.index.to_numpy() for f, g in d.groupby("f")}
    keys = np.array(list(groups))
    stats = []
    for _ in range(reps):
        idx = np.concatenate([groups[k] for k in rng.choice(keys, len(keys))])
        s = d.loc[idx]
        stats.append(s.a.median() - s.b.median())
    point = d.a.median() - d.b.median()
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return round(point, 3), round(lo, 3), round(hi, 3)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fy = pd.read_pickle(P.PROC / "firm_years.pkl")
    allw = pd.read_pickle(P.PROC / "windows_h5.pkl")
    w = allw[allw.t.between(*EXPLORATION)].copy()
    assert set(w.t) <= set(range(EXPLORATION[0], EXPLORATION[1] + 1))

    # ---- attrition (reported, not graded) -------------------------------------------
    w = w[w.quality_ok_t]
    att = pd.crosstab(w.ff12_t, w.status, normalize="index").round(3)
    att["n"] = w.groupby("ff12_t").size()
    show("A_attrition_by_ff12", att, "Exploration windows passing the quality screen at t (t = 2015-16).")

    g = w[w.status.isin(["survived", "shrank"]) & w.quality_ok_tH.eq(True) & w.ev_tH.gt(0)].copy()
    print(f"\nGraded windows: {len(g):,} (of {len(w):,}; exited {w.status.eq('exited').sum():,}, "
          f"outcome EV <= 0 or suspect {len(w) - len(g) - w.status.eq('exited').sum():,})")

    pred = M.predict_all(g, fy)
    err = np.log(pred.div(g.ev_tH, axis=0).where(pred.gt(0)))

    show("B_all_methods_own_sample", score(err),
         "Each method on the windows where it is defined. Not comparable across rows (different samples).")

    common = err[CORE].notna().all(axis=1)
    show("C_common_sample", score(err.loc[common, CORE + [c for c in err if c.startswith("REF")]]),
         f"Windows where every core method is defined: {common.sum():,} "
         f"({common.mean():.1%} of graded). Needs FCF_t+5 > 0, EBITDA_t+5 > 0, EBITDA_t > 0, ROIC > g.")

    # ---- bootstrap of key contrasts ---------------------------------------------------
    ec = err[common]
    firms = g.loc[common, "id"]
    rows = []
    for a, b in [("G_fcf_g2.5", "E_ff12_med"), ("B50_G2.5_Eff12", "E_ff12_med"),
                 ("B50geo_G2.5_Eff12", "E_ff12_med"), ("E_own", "E_ff12_med"),
                 ("E_dam_5yavg", "E_dam_t"), ("G_fcf3avg_g2.5", "G_fcf_g2.5"),
                 ("G_vd_roic_g2.5", "G_fcf_g2.5"), ("E_damind_med", "E_ff12_med")]:
        rows.append((a, b, *boot_diff(ec, a, b, firms)))
    show("D_bootstrap_contrasts", pd.DataFrame(rows, columns=["a", "b", "diff_median_abs", "ci_lo", "ci_hi"]),
         "median|e_a| - median|e_b| on the common sample; 95% firm-clustered bootstrap CI; negative = a better.")

    # ---- by industry (H2) ---------------------------------------------------------------
    gi = g[common]
    by = pd.DataFrame({
        "n": gi.groupby("ff12_t").size(),
        "G2.5_abs": ec["G_fcf_g2.5"].abs().groupby(gi.ff12_t).median(),
        "G2.5_bias": ec["G_fcf_g2.5"].groupby(gi.ff12_t).median(),
        "Eff12_abs": ec["E_ff12_med"].abs().groupby(gi.ff12_t).median(),
        "Eff12_bias": ec["E_ff12_med"].groupby(gi.ff12_t).median(),
        "Eown_abs": ec["E_own"].abs().groupby(gi.ff12_t).median(),
        "B50_abs": ec["B50_G2.5_Eff12"].abs().groupby(gi.ff12_t).median(),
        "Edam5y_abs": ec["E_dam_5yavg"].abs().groupby(gi.ff12_t).median(),
        "Edam_t_abs": ec["E_dam_t"].abs().groupby(gi.ff12_t).median(),
    }).round(3)
    by["G_minus_E"] = (by["G2.5_abs"] - by["Eff12_abs"]).round(3)
    show("E_by_ff12_common", by.sort_values("G_minus_E"), "Median |ln error| and bias by FF12 (common sample).")

    # ---- implied multiples and growth --------------------------------------------------
    ok = g.fcf_tH.gt(0) & g.ebitda_tH.gt(0)
    gg = g[ok]
    imp = pd.DataFrame({
        "n": gg.groupby("ff12_t").size(),
        "gordon_implied_ev_ebitda": (pred.loc[ok, "G_fcf_g2.5"] / gg.ebitda_tH).groupby(gg.ff12_t).median(),
        "actual_ev_ebitda_tH": (gg.ev_tH / gg.ebitda_tH).groupby(gg.ff12_t).median(),
        "ff12_multiple_at_t": (pred.loc[ok, "E_ff12_med"] / gg.ebitda_tH).groupby(gg.ff12_t).median(),
        "wacc_t": gg.groupby("ff12_t").wacc_t.median(),
        "g_implied_by_exit_ff12": M.implied_growth(pred.loc[ok, "E_ff12_med"], gg.fcf_tH, gg.wacc_t).groupby(gg.ff12_t).median(),
        "g_implied_by_actual_ev": M.implied_growth(gg.ev_tH, gg.fcf_tH, gg.wacc_t).groupby(gg.ff12_t).median(),
    })
    tot = pd.DataFrame({
        "n": [len(gg)],
        "gordon_implied_ev_ebitda": [(pred.loc[ok, "G_fcf_g2.5"] / gg.ebitda_tH).median()],
        "actual_ev_ebitda_tH": [(gg.ev_tH / gg.ebitda_tH).median()],
        "ff12_multiple_at_t": [(pred.loc[ok, "E_ff12_med"] / gg.ebitda_tH).median()],
        "wacc_t": [gg.wacc_t.median()],
        "g_implied_by_exit_ff12": [M.implied_growth(pred.loc[ok, "E_ff12_med"], gg.fcf_tH, gg.wacc_t).median()],
        "g_implied_by_actual_ev": [M.implied_growth(gg.ev_tH, gg.fcf_tH, gg.wacc_t).median()],
    }, index=["ALL"])
    show("F_implied_multiples_growth", pd.concat([imp, tot]).round(3),
         "FCF_t+5 > 0 and EBITDA_t+5 > 0. Gordon g = 2.5%, r = WACC_t.")

    # ---- r and g sensitivity ------------------------------------------------------------
    grid = []
    for dr in (-0.02, -0.01, 0.0, 0.01):
        for gr in (0.0, 0.01, 0.02, 0.025, 0.03, 0.04):
            tv = M.gordon(g.fcf_tH, g.wacc_t + dr, gr)
            e = np.log(tv / g.ev_tH)
            grid.append({"r_shift_pp": dr * 100, "g_pct": gr * 100, "n": e.notna().sum(),
                         "median_abs": e.abs().median(), "bias": e.median()})
    grid = pd.DataFrame(grid)
    show("G_gordon_sensitivity", grid.pivot(index="r_shift_pp", columns="g_pct", values="bias").round(3),
         "Median signed ln error of Gordon (FCF_t+5) by r shift (rows) and g (columns). Sample shrinks as r-g < 1pp drops.")
    show("G2_gordon_sensitivity_abs", grid.pivot(index="r_shift_pp", columns="g_pct", values="median_abs").round(3))
    show("G3_gordon_sensitivity_n", grid.pivot(index="r_shift_pp", columns="g_pct", values="n"))

    # ---- defined-ness by method (intention-to-treat input) ---------------------------
    dfn = pd.DataFrame({
        "share_defined_all_graded": pred.notna().mean().round(3),
        "share_defined_fcf_pos": pred[g.fcf_tH.gt(0)].notna().mean().round(3),
    })
    show("H_definedness", dfn)
    print(f"\nFCF_t+5 <= 0: {(g.fcf_tH <= 0).mean():.3f}; EBITDA_t+5 <= 0: {(g.ebitda_tH <= 0).mean():.3f}; "
          f"both <= 0: {((g.fcf_tH <= 0) & (g.ebitda_tH <= 0)).mean():.3f}")


if __name__ == "__main__":
    main()
