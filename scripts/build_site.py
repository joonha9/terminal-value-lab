"""Build the Terminal Value Lab site (index.html at the repository root) from the results.

    python3 -P scripts/build_site.py

Every number on the site comes from results/ (git-ignored, FactSet-derived); only aggregates
(medians, test statistics, counts) are exported, never firm-level data. The data are written to
site/site_data.json and injected into site/template.html. GitHub Pages serves the root index.html.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tvlab import phase4 as Q  # noqa: E402

RES = ROOT / "results"
RUNS = ["a1", "a2", "a3", "a4", "a5"]


def load(p):
    return json.loads((RES / p).read_text())


def r(x, n=4):
    return None if x is None or not np.isfinite(float(x)) else round(float(x), n)


def test_row(t):
    return {"stat": r(t["stat"]), "lo": r(t["ci95"][0]), "hi": r(t["ci95"][1]), "p": r(t["p_one_sided"], 4),
            "n": t["n"], "dir": t["direction"]}


def main() -> None:
    EX = load("phase4_dryrun/validation.json")["replication"]   # exploration replication (no selection)
    V, T = load("phase4/validation.json"), load("phase4/test.json")
    PH, F, B, QR = load("phase4/posthoc.json"), load("phase3/finalists.json"), load("phase3/baselines_explore.json"), load("q4/results.json")
    D = {}

    # ---- sample sizes
    D["sample"] = {"M": {"exploration": EX["describe"]["M"]["n_graded"], "validation": V["replication"]["describe"]["M"]["n_graded"],
                         "test": T["describe"]["M"]["n_graded"]},
                   "M_common": {"exploration": EX["describe"]["M"]["n_common"], "validation": V["replication"]["describe"]["M"]["n_common"],
                                "test": T["describe"]["M"]["n_common"]},
                   "D": {"exploration": EX["describe"]["D"]["n_graded"], "validation": V["replication"]["describe"]["D"]["n_graded"],
                         "test": T["describe"]["D"]["n_graded"]},
                   "eval": {"exploration": PH["splits"]["exploration"]["n"], "validation": PH["splits"]["validation"]["n"],
                            "test": PH["splits"]["test"]["n"]},
                   "windows_quality_ok": {"exploration": EX["describe"]["window_counts"]["quality_ok_at_t"],
                                          "validation": V["replication"]["describe"]["window_counts"]["quality_ok_at_t"],
                                          "test": T["describe"]["window_counts"]["quality_ok_at_t"]}}

    # ---- core methods on the common sample, truth M, each split; and truth D on test
    D["methods"] = {}
    for k in Q.CORE_M:
        D["methods"][k] = {s: {"abs": r(src["methods"][k]["median_abs"]), "bias": r(src["methods"][k]["bias"])}
                           for s, src in (("exploration", EX["describe"]["M"]), ("validation", V["replication"]["describe"]["M"]),
                                          ("test", T["describe"]["M"]))}
        dm = T["describe"]["D"]["methods"].get(k)
        D["methods"][k]["test_D"] = {"abs": r(dm["median_abs"]), "bias": r(dm["bias"])} if dm else None

    # ---- pre-registered tests by split
    D["tests"] = {}
    for k in Q.HOLM_FAMILY:
        row = {}
        if k in EX["tests"]:
            row["exploration"] = test_row(EX["tests"][k])
        if k in V["replication"]["tests"]:
            row["validation"] = test_row(V["replication"]["tests"][k])
        row["test"] = {**test_row(T["tests"][k]), "p_holm": r(T["holm"][k]["p_holm"], 4), "reject": T["holm"][k]["reject"]}
        D["tests"][k] = row
    D["decisions"] = T["decisions"]
    D["h3"] = {s: {k: test_row(v) for k, v in src.items()} for s, src in
               (("validation", V["replication"]["robustness_h3"]), ("test", T["robustness_h3"]))}
    D["robust"] = {}
    for k in T["robustness"]:
        if k.startswith("D:excl"):
            D["robust"][k] = {s: {"dropped": src[k]["n_windows_dropped"], "kept": src[k]["n_windows_kept"],
                                  "T1D": r(src[k]["tests"]["T1D"]["stat"]) if "T1D" in src[k]["tests"] else None}
                              for s, src in (("validation", V["robustness"]), ("test", T["robustness"]))}
            continue
        D["robust"][k] = {s: {kk: test_row(vv) for kk, vv in src[k].items()} for s, src in
                          (("validation", V["robustness"]), ("test", T["robustness"]))}

    # ---- agent search
    arch = {n: [json.loads(x) for x in (RES / "phase3" / "agent_runs" / n / "archive.jsonl").read_text().splitlines()]
            for n in RUNS}
    conv = {}
    for n, rows in arch.items():
        graded = [x for x in rows if x["status"] == "graded"]
        best, seq = 9.0, []
        for g in range(1, 6):
            sc = [x["explore"]["median_abs"] for x in graded if x["generation"] == g]
            best = min([best] + sc)
            seq.append(r(best))
        conv[n] = seq
    D["agent"] = {
        "funnels": F["funnels"], "convergence": conv,
        "bench_explore": {"unconditional": r(B["unconditional"]["top3"][0]["explore"]["median_abs"]),
                          "own": r(B["single"]["E_own"]["median_abs"]), "ff12": r(B["single"]["E_ff12_med"]["median_abs"]),
                          "gordon": r(B["single"]["G_fcf_g2.5"]["median_abs"]),
                          "random_best30_mean": r(B["random"]["best_of_30"]["mean"]),
                          "random_best_pool": r(B["random"]["best_of_pool"]), "random_median": r(B["random"]["median_score"]),
                          "gbm_traits": r(B["gbm"]["traits"]["median_abs"]), "gbm_traits_methods": r(B["gbm"]["traits+methods"]["median_abs"])},
        "chosen": {g: V["chosen"][g]["id"] for g in ("agent", "random", "unconditional")},
        "chosen_compact": {g: load("phase4/chosen.json")[g]["compact"] for g in ("agent", "random", "unconditional")},
    }
    # trajectories of the chosen rules and two single methods (recipe evaluation set)
    keys = {"agent": f"agent:{V['chosen']['agent']['id']}", "random": f"random:{V['chosen']['random']['id']}",
            "unconditional": f"unconditional:{V['chosen']['unconditional']['id']}", "own": "single:E_own", "ff12": "single:E_ff12_med"}
    D["agent"]["trajectory"] = {g: {s: {"abs": r(PH["splits"][s]["rules"][k]["median_abs"]), "bias": r(PH["splits"][s]["rules"][k]["bias"]),
                                        "lr": r(PH["splits"][s]["rules"][k]["level_removed_year"])}
                                    for s in ("exploration", "validation", "test")} for g, k in keys.items()}
    # every finalist on every split (median abs e, bias)
    fin = {}
    for g in ("agent", "random", "unconditional"):
        for f in F[g]:
            fid = f["id"]
            fin[f"{g}:{fid}"] = {"group": g,
                                 "exploration": [r(T["finalists_on_exploration"][g][fid]["median_abs"]), r(T["finalists_on_exploration"][g][fid]["bias"])],
                                 "validation": [r(V["finalist_scores"][g][fid]["median_abs"]), r(V["finalist_scores"][g][fid]["bias"])],
                                 "test": [r(T["finalists_on_test"][g][fid]["median_abs"]), r(T["finalists_on_test"][g][fid]["bias"])]}
    D["agent"]["finalists"] = fin
    D["agent"]["posthoc"] = {s: {c: {"diff": r(v["diff"]), "lo": r(v["ci95"][0]), "hi": r(v["ci95"][1])}
                                 for c, v in PH["splits"][s]["contrasts"].items() if c.endswith(":year")}
                             for s in ("exploration", "validation", "test")}
    D["agent"]["gbm_test"] = {k: r(v["median_abs"]) for k, v in T["gbm"].items()}
    D["agent"]["gbm_val"] = {k: r(v["median_abs"]) for k, v in V["gbm"].items()}

    # ---- Q4
    def cf(c):
        return {"mean": r(c["mean"], 5), "se": r(c["se_nw"], 5), "t": r(c["t"], 3)}
    D["q4"] = {"months": QR["months"], "firm_months": QR["fm"]["H9_S1"]["n_firm_months"],
               "tests": {k: {"p": r(v["p"], 4), "p_holm": r(v["p_holm"], 4), "reject": v["reject"]} for k, v in QR["tests"]["holm"].items()},
               "coef": {"H9": cf(QR["fm"]["H9_S1"]["coef"]["S1"]), "H10a": cf(QR["fm"]["H10_S1a_S1b"]["coef"]["S1a"]),
                        "H10b": cf(QR["fm"]["H10_S1a_S1b"]["coef"]["S1b"]),
                        "nb_S1a": cf(QR["fm"]["H10_without_beta_companion"]["coef"]["S1a"]),
                        "nb_S1b": cf(QR["fm"]["H10_without_beta_companion"]["coef"]["S1b"]),
                        "S1_nocontrols": cf(QR["fm"]["H9_no_controls"]["coef"]["S1"]),
                        "S2": cf(QR["fm"]["S2_report"]["coef"]["S2"])},
               "controls": {k: cf(v) for k, v in QR["fm"]["H10_S1a_S1b"]["coef"].items() if not k.startswith("S")},
               "sorts": {s: {sch: {"q": [r(d[sch]["q_means"][str(i)], 5) for i in range(1, 6)], "spread": r(d[sch]["spread_mean"], 5),
                                   "t": r(d[sch]["spread_t"], 3), "alpha": r(d[sch]["ff6_alpha"], 5), "alpha_t": r(d[sch]["ff6_t"], 3)}
                             for sch in ("EW", "VW")} for s, d in QR["sorts"].items()},
               "robust": {k: {"H9": cf(v["H9"]), "S1a": cf(v["H10"]["S1a"]), "S1b": cf(v["H10"]["S1b"])} for k, v in QR["robustness"].items()},
               "coverage": QR["coverage"], "delisting": QR["delisting"], "equiv_band": QR["tests"]["S1b_equivalence_band"]}

    out = ROOT / "site" / "site_data.json"
    out.write_text(json.dumps(D, indent=1, ensure_ascii=False) + "\n")
    tpl = (ROOT / "site" / "template.html").read_text()
    assert "/*__DATA__*/" in tpl
    (ROOT / "index.html").write_text(tpl.replace("/*__DATA__*/", "const DATA = " + json.dumps(D, ensure_ascii=False) + ";"))
    print(f"wrote site/site_data.json ({out.stat().st_size // 1024} KB) and index.html")


if __name__ == "__main__":
    main()
