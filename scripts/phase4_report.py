"""Render the Phase 4 result tables (markdown) from results/phase4/validation.json and test.json.

    python3 -P scripts/phase4_report.py > /tmp/tables.md

Numbers in docs/phase4_results.md are pasted from this output, never retyped.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V = json.loads((ROOT / "results" / "phase4" / "validation.json").read_text())
T = json.loads((ROOT / "results" / "phase4" / "test.json").read_text())
NAMES = {
    "T1": "Gordon g2.5 − FF12 exit (M)", "T2": "median e of Gordon g2.5 (M)",
    "T3": "Gordon − FF12, low- minus high-spread tercile (M)", "T4": "Damodaran 5-yr − at t, cyclicals (M)",
    "T5": "50/50 log blend − better pure method (M)",
    "T1D": "Gordon g2.5 − FF12 exit (D)", "T2D": "median e of Gordon g2.5 (D)",
    "T3D": "Gordon − FF12, low- minus high-spread tercile (D)", "T4D": "Damodaran 5-yr − at t, cyclicals (D)",
    "T5D": "50/50 log blend − better pure method (D)",
    "T7": "own − Damodaran-industry: D′ minus D", "T8a": "agent − best single method",
    "T8b": "agent − chosen random", "T8c": "agent − chosen unconditional",
}


def f(x, d=3):
    return f"{x:+.{d}f}"


def ci(t):
    return f"[{f(t['ci95'][0])}, {f(t['ci95'][1])}]"


out = sys.stdout
out.write("### Pre-registered tests\n\n")
out.write("| Test | Statistic | H | Validation (n) | Test: value, 95% CI | n (firms) | p one-sided | p Holm | Reject |\n")
out.write("|---|---|---|---|---|---|---|---|---|\n")
vt = V["replication"]["tests"]
for k in ["T1", "T2", "T3", "T4", "T5", "T1D", "T2D", "T3D", "T4D", "T5D", "T7", "T8a", "T8b", "T8c"]:
    t, h = T["tests"][k], T["holm"][k]
    val = f"{f(vt[k]['stat'])} {ci(vt[k])} ({vt[k]['n']})" if k in vt else "—"
    out.write(f"| {k} | {NAMES[k]} | {'> 0' if t['direction'] == 'gt' else '< 0'} | {val} | {f(t['stat'])} {ci(t)} | "
              f"{t['n']} ({t['n_firms']}) | {t['p_one_sided']:.4f} | {h['p_holm']:.4f} | {'**yes**' if h['reject'] else 'no'} |\n")
out.write(f"\nDecisions: {json.dumps(T['decisions'])}\n\n")

out.write("### Chosen recipes and benchmarks (median abs e / bias, recipe evaluation set)\n\n")
out.write("| Rule | Exploration | Validation | Test |\n|---|---|---|---|\n")
fin = {g: {x["id"]: x for x in grp} for g, grp in json.loads((ROOT / "results" / "phase3" / "finalists.json").read_text()).items()
       if g in ("agent", "random", "unconditional")}
for g in ("agent", "random", "unconditional"):
    cid = V["chosen"][g]["id"]
    ve, vv, tt = T["finalists_on_exploration"][g][cid], V["finalist_scores"][g][cid], T["finalists_on_test"][g][cid]
    out.write(f"| {g} `{cid}` | {ve['median_abs']:.3f} / {f(ve['bias'])} | {vv['median_abs']:.3f} / {f(vv['bias'])} | "
              f"{tt['median_abs']:.3f} / {f(tt['bias'])} |\n")
b = V["best_single_pooled_exploration_validation"]["method"]
own_test = T["chosen_on_test"]["agent"]["median_abs"] - T["tests"]["T8a"]["stat"]  # same evaluation set as T8a
out.write(f"| best single `{b}` | — | {V['single_methods'][b]['median_abs']:.3f} / {f(V['single_methods'][b]['bias'])} | "
          f"{own_test:.3f} (agent − T8a) |\n")
out.write(f"| FF12 exit | — | {V['single_methods']['E_ff12_med']['median_abs']:.3f} | {T['ff12_median_abs']:.3f} |\n")
for k in ("traits_only", "traits_methods"):
    out.write(f"| GBM {k} | — | {V['gbm'][k]['median_abs']:.3f} / {f(V['gbm'][k]['bias'])} | "
              f"{T['gbm'][k]['median_abs']:.3f} / {f(T['gbm'][k]['bias'])} |\n")

out.write("\n### All finalists on test (median abs e, bias): range per group\n\n")
for g in ("agent", "random", "unconditional"):
    d = T["finalists_on_test"][g]
    m = sorted(v["median_abs"] for v in d.values())
    bb = sorted(v["bias"] for v in d.values())
    out.write(f"- {g}: median abs e {m[0]:.3f}–{m[-1]:.3f}; bias {f(bb[0])} to {f(bb[-1])} ({len(d)} recipes)\n")

out.write("\n### Share of GBM gain (test)\n\n")
for g, d in T["share_of_gbm_gain"].items():
    out.write(f"- {g}: " + "; ".join(f"{k} {v['share']:.2f}{' (' + v['note'] + ')' if v['note'] else ''}"
                                     if v["share"] is not None else f"{k} undefined" for k, v in d.items()) + "\n")

out.write("\n### Chosen recipes against truth D (test) and protocol section 3 metrics\n\n")
for g in ("agent", "random", "unconditional"):
    d, c = T["chosen_vs_truth_D"][g], T["chosen_common_and_itt"][g]
    out.write(f"- {g}: vs D {d['median_abs']:.3f} / {f(d['bias'])} (n {d['n']}); common sample with best single "
              f"(n {c['n_common']}): recipe {c['recipe_median_abs']:.3f} vs single {c['single_median_abs']:.3f}; "
              f"ITT hit {c['recipe_itt_hit']:.3f} vs {c['single_itt_hit']:.3f}; Damodaran-leaf share "
              f"{T['damodaran_leaf_share'][g]:.3f}\n")

out.write("\n### Robustness (protocol section 8; T1 / T2 or T1D / T2D, value and n)\n\n")
out.write("| Variant | Validation | Test |\n|---|---|---|\n")
for k in T["robustness"]:
    def cell(r):
        if "skipped" in r:
            return "skipped"
        if "tests" in r:
            tt = r["tests"]
            return (f"dropped {r['n_windows_dropped']}, kept {r['n_windows_kept']}: " +
                    ", ".join(f"{kk} {f(x['stat'])}" for kk, x in tt.items()) + f"; T7 {f(r['T7']['stat'])}"
                    if "skipped" not in tt else "skipped")
        return "; ".join(f"{kk} {f(x['stat'])} {ci(x)} ({x['n']})" for kk, x in r.items())
    out.write(f"| {k} | {cell(V['robustness'][k])} | {cell(T['robustness'][k])} |\n")
out.write("\nHorizon 3 (T1–T5, M): validation " +
          ", ".join(f"{k} {f(x['stat'])}" for k, x in V["replication"]["robustness_h3"].items()) + "; test " +
          ", ".join(f"{k} {f(x['stat'])}" for k, x in T["robustness_h3"].items()) + "\n")

out.write("\n### Core methods on the common sample (median abs e / bias)\n\n")
out.write("| Method | Validation (M) | Test (M) | Test (D) |\n|---|---|---|---|\n")
for k, v in T["describe"]["M"]["methods"].items():
    vv = V["replication"]["describe"]["M"]["methods"][k]
    d = T["describe"]["D"]["methods"].get(k)
    out.write(f"| {k} | {vv['median_abs']:.3f} / {f(vv['bias'])} | {v['median_abs']:.3f} / {f(v['bias'])} | "
              f"{(str(round(d['median_abs'], 3)) + ' / ' + f(d['bias'])) if d else '—'} |\n")
out.write(f"\nCommon-sample n: validation M {V['replication']['describe']['M']['n_common']}, test M "
          f"{T['describe']['M']['n_common']}, test D {T['describe']['D']['n_common']}. Window counts (test): "
          f"{json.dumps(T['describe']['window_counts'])}\n")
