"""Render Q4 result tables (markdown) from results/q4/results.json; never retype numbers.

    python3 -P scripts/q4_report.py > /tmp/q4_tables.md
"""
import json
import sys
from pathlib import Path

R = json.loads((Path(__file__).resolve().parents[1] / "results" / "q4" / "results.json").read_text())
o = sys.stdout


def pc(x):
    return f"{x * 100:+.3f}%"


def coef(c):
    return f"{pc(c['mean'])} (t {c['t']:+.2f})"


o.write(f"Run: commit `{R['git']['head'][:7]}`, clean tree = {not R['git']['dirty']}; months {R['months'][0]} to "
        f"{R['months'][1]} ({R['months'][2]}).\n\n")
o.write("### Pre-registered tests (Fama-MacBeth, monthly slope on rank-scaled signal = long-short spread per month)\n\n")
o.write("| Test | Slope (NW t) | p | p Holm | Reject |\n|---|---|---|---|---|\n")
h = R["tests"]["holm"]
rows = {"H9": ("S1 GAP > 0", R["fm"]["H9_S1"]["coef"]["S1"]),
        "H10a": ("S1a yield part > 0", R["fm"]["H10_S1a_S1b"]["coef"]["S1a"]),
        "H10b": ("S1b discount-rate part ≠ 0 (given beta)", R["fm"]["H10_S1a_S1b"]["coef"]["S1b"])}
for k, (name, c) in rows.items():
    o.write(f"| {k}: {name} | {coef(c)} | {h[k]['p']:.3f} | {h[k]['p_holm']:.3f} | {'yes' if h[k]['reject'] else 'no'} |\n")
ci = R["tests"]["S1b_ci95"]
o.write(f"\nS1b 95% CI [{pc(ci[0])}, {pc(ci[1])}] a month; within the ±{R['tests']['S1b_equivalence_band'] * 100:.2f}% "
        f"equivalence band: {R['tests']['S1b_within_band']}. Firm-months: {R['fm']['H9_S1']['n_firm_months']:,}.\n\n")

o.write("### Reported only (outside Holm)\n\n| Specification | Slopes (NW t) |\n|---|---|\n")
for k, lab in (("H10_without_beta_companion", "H10 without the beta control (pre-declared companion)"),
               ("H9_no_controls", "S1 without controls"), ("S2_report", "S2 TV disagreement, with controls")):
    o.write(f"| {lab} | " + "; ".join(f"{kk} {coef(v)}" for kk, v in R["fm"][k]["coef"].items() if kk.startswith("S")) + " |\n")
o.write("| Controls in the H10 model | " + "; ".join(f"{kk} {coef(v)}" for kk, v in R["fm"]["H10_S1a_S1b"]["coef"].items()
                                              if not kk.startswith("S")) + " |\n")

o.write("\n### Quintile sorts (Q5 − Q1 a month; FF5 + UMD alpha; NW t)\n\n| Signal | EW spread | EW alpha | VW spread | VW alpha |\n|---|---|---|---|---|\n")
for s, d in R["sorts"].items():
    e, v = d["EW"], d["VW"]
    o.write(f"| {s} | {pc(e['spread_mean'])} ({e['spread_t']:+.2f}) | {pc(e['ff6_alpha'])} ({e['ff6_t']:+.2f}) | "
            f"{pc(v['spread_mean'])} ({v['spread_t']:+.2f}) | {pc(v['ff6_alpha'])} ({v['ff6_t']:+.2f}) |\n")

o.write("\n### Robustness (H9 slope; H10 slopes)\n\n| Variant | H9 S1 | H10 S1a | H10 S1b |\n|---|---|---|---|\n")
for k, v in R["robustness"].items():
    o.write(f"| {k} | {coef(v['H9'])} | {coef(v['H10']['S1a'])} | {coef(v['H10']['S1b'])} |\n")

o.write(f"\nDelisting months in the window: {R['delisting']['n_events_in_window']} "
        f"({json.dumps(R['delisting']['by_return'])}). Coverage per formation (firms / with S1): " +
        ", ".join(f"{f}: {c['firms']}/{c['with_S1']}" for f, c in R["coverage"].items()) + "\n")
