"""Q4 run (docs/q4_design.md): Gordon-vs-market gap and future returns.

    python3 -P scripts/q4_run.py --dry-run    # PLACEBO: holding-period returns shuffled across the
                                              # analysis firms within each month (seed 0), so no real
                                              # signal-return relation can be seen; writes results/q4_dryrun/
    python3 -P scripts/q4_run.py              # the one real run; writes results/q4/results.json

The real run refuses to start unless the git tree is clean, the data files match
docs/q4_pins.json, and results/q4/results.json does not exist.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tvlab import panel as P   # noqa: E402
from tvlab import phase4 as Q4H  # noqa: E402  (Holm)
from tvlab import q4           # noqa: E402

PINS = ROOT / "docs" / "q4_pins.json"
DATA = {"returns_monthly.pkl": P.PROC / "returns_monthly.pkl", "firm_years.pkl": P.PROC / "firm_years.pkl",
        "exits.csv": P.PROC / "exits.csv",
        "F-F_Research_Data_5_Factors_2x3.csv": ROOT / "data" / "raw" / "french" / "F-F_Research_Data_5_Factors_2x3.csv",
        "F-F_Momentum_Factor.csv": ROOT / "data" / "raw" / "french" / "F-F_Momentum_Factor.csv"}
EQUIV_BAND = 0.0025  # +-0.25% a month for the rank-scaled S1b slope (design section 3)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git_state() -> dict:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
    st = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True)
    return {"head": head.stdout.strip(), "dirty": bool(st.stdout.strip())}


def norm_sf(t: float) -> float:
    return 0.5 * math.erfc(t / math.sqrt(2))


def fm_block(d: pd.DataFrame, regs: list[str]) -> dict:
    r = q4.fama_macbeth(d, regs)
    r.pop("slopes")
    return r


def sorts_block(d: pd.DataFrame, fac: pd.DataFrame, sig: str) -> dict:
    pr = q4.sort_portfolios(d, sig)
    out = {}
    for sch in ("EW", "VW"):
        s = pr[(sch, "Q5-Q1")]
        m, se = q4.nw_mean(s.dropna().to_numpy())
        out[sch] = {"q_means": {str(k): float(pr[(sch, k)].mean()) for k in range(1, 6)},
                    "spread_mean": m, "spread_t": m / se, **{"ff6_" + k: v for k, v in q4.alpha(s, fac).items()}}
    return out


def run(returns: pd.DataFrame, out_dir: Path, label: str, placebo_seed: int | None = None) -> dict:
    fy = pd.read_pickle(P.PROC / "firm_years.pkl")
    exits = pd.read_csv(P.PROC / "exits.csv")
    fac = q4.french()
    rf = fac["RF"]
    ret = q4.pick_security(returns, fy)[["entity_id", "month", "ret"]]
    months = sorted(set(rf.index))
    dl = q4.delisting_returns(ret, exits, months)
    sig = q4.signals(fy)
    res = {"label": label, "delisting": {}, "coverage": {}, "fm": {}, "sorts": {}, "robustness": {}}

    def build(dl_rule: dict | None = None) -> pd.DataFrame:
        add = dl.copy()
        if dl_rule is not None and "perf" in dl_rule:
            add.loc[add["ret"] == q4.PERF_DELIST_RET, "ret"] = dl_rule["perf"]
        r = pd.concat([ret.assign(delist=False), add], ignore_index=True)
        dd = q4.firm_months(sig, r, rf)
        if placebo_seed is not None:  # shuffle outcomes across the analysis firm-months of each month
            rng = np.random.default_rng(placebo_seed)
            dd["ret"] = dd.groupby("month")["ret"].transform(lambda s: rng.permutation(s.to_numpy()))
        dd["ret_raw"] = dd["ret"]
        lo, hi = (dl_rule or {}).get("winsor", q4.WINSOR)
        # winsorize FactSet returns only; delisting returns are added unclipped (review fix)
        dd["ret"] = (q4.winsorize_monthly(dd, "ret_raw", lo, hi, mask=~dd["delist"].astype(bool).to_numpy())
                     if lo > 0 else dd["ret_raw"])
        dd["exret"] = dd["ret"] - dd["month"].map(rf)
        return dd

    d = build()
    res["delisting"] = {"n_events_in_window": int(len(dl)),
                        "by_return": {str(k): int(v) for k, v in dl["ret"].value_counts().items()}}
    firm = d.drop_duplicates(["formation", "id"])
    res["coverage"] = {str(f): {"firms": int(len(g)), "with_S1": int(g["S1"].notna().sum()),
                                "with_S2": int(g["S2"].notna().sum())} for f, g in firm.groupby("formation")}
    res["months"] = [str(d.month.min()), str(d.month.max()), int(d.month.nunique())]
    # ---- pre-registered tests
    h9 = fm_block(d, ["S1"])
    h10 = fm_block(d, ["S1a", "S1b"])
    res["fm"]["H9_S1"] = h9
    res["fm"]["H10_S1a_S1b"] = h10
    c9, ca, cb = h9["coef"]["S1"], h10["coef"]["S1a"], h10["coef"]["S1b"]
    p = {"H9": norm_sf(c9["t"]), "H10a": norm_sf(ca["t"]), "H10b": 2 * norm_sf(abs(cb["t"]))}
    res["tests"] = {"p": p, "holm": Q4H.holm(p),
                    "S1b_ci95": [cb["mean"] - 1.96 * cb["se_nw"], cb["mean"] + 1.96 * cb["se_nw"]],
                    "S1b_equivalence_band": EQUIV_BAND,
                    "S1b_within_band": bool(abs(cb["mean"]) + 1.645 * cb["se_nw"] < EQUIV_BAND)}
    # ---- reported only
    res["fm"]["S2_report"] = fm_block(d, ["S2"])
    # pre-declared companion (outside Holm): S1b is mostly minus industry beta within a formation,
    # so with beta controlled H10b tests the leverage / credit-spread wedge of WACC; without beta it
    # tests the whole discount-rate part but is confounded with any low-beta return premium.
    nb = q4.fama_macbeth(d, ["S1a", "S1b"], controls=[c for c in q4.CONTROLS if c != "beta"])
    nb.pop("slopes")
    res["fm"]["H10_without_beta_companion"] = nb
    res["fm"]["H9_no_controls"] = q4.fama_macbeth(d, ["S1"], controls=[])
    res["fm"]["H9_no_controls"].pop("slopes")
    for s in ("S1", "S1a", "S1b", "S2"):
        res["sorts"][s] = sorts_block(d, fac, s)
    res["implied_g"] = {str(f): g["S3_implied_g"].describe()[["count", "25%", "50%", "75%"]].round(4).to_dict()
                        for f, g in firm.groupby("formation")}
    for name, rule in (("perf_delist_0", {"perf": 0.0}), ("perf_delist_minus100", {"perf": -1.0}),
                       ("returns_raw", {"winsor": (0.0, 1.0)}), ("returns_winsor_1_99", {"winsor": (0.01, 0.99)}),
                       ("statements_90d", {"min_stmt_age": 90})):
        dd = build(rule)
        if "min_stmt_age" in rule:
            dd = dd[dd["stmt_age"] >= rule["min_stmt_age"]]
        res["robustness"][name] = {"H9": fm_block(dd, ["S1"])["coef"]["S1"],
                                   "H10": fm_block(dd, ["S1a", "S1b"])["coef"]}
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    returns = pd.read_pickle(P.PROC / "returns_monthly.pkl")
    seed = None
    if a.dry_run:
        out = ROOT / "results" / "q4_dryrun"
        seed = 0
        label = "PLACEBO (outcome returns shuffled across analysis firms within each month): pipeline check only"
    else:
        out = ROOT / "results" / "q4"
        if git_state()["dirty"]:
            sys.exit("git working tree is not clean: commit first")
        pins = json.loads(PINS.read_text())
        for k, p in DATA.items():
            if sha(p) != pins["data_sha256"][k]:
                sys.exit(f"{k} does not match docs/q4_pins.json")
        if (out / "results.json").exists():
            sys.exit("REFUSE: the Q4 run was already done")
        label = "REAL"
    out.mkdir(parents=True, exist_ok=True)
    res = run(returns, out, label, placebo_seed=seed)
    res["git"] = git_state()
    res["data_sha256"] = {k: sha(p) for k, p in DATA.items()}
    text = json.dumps(res, indent=1, sort_keys=True, default=str) + "\n"
    (out / "results.json.tmp").write_text(text)
    (out / "results.json.tmp").replace(out / "results.json")
    print(label, "| months", res["months"], "| sha256", hashlib.sha256(text.encode()).hexdigest()[:16])
    for k, v in res["tests"]["holm"].items():
        print(f"  {k}: p {v['p']:.4f} holm {v['p_holm']:.4f} reject {v['reject']}")
    print("  coefficients:", {k: round(v["mean"], 5) for k, v in res["fm"]["H10_S1a_S1b"]["coef"].items()})
    print("  delisting:", res["delisting"])


if __name__ == "__main__":
    main()
