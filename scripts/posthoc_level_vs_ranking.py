"""EXPLORATORY post-hoc diagnosis (docs/phase4_posthoc.md): level-removed median |e| of every
finalist and two single methods on exploration, validation and test.

    python3 -P scripts/posthoc_level_vs_ranking.py

Validation and test were already opened by scripts/phase4.py; each re-read here is logged to
results/unseal_log.jsonl with what = posthoc_level_vs_ranking. Writes results/phase4/posthoc.json.
"""
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tvlab import phase3 as P3  # noqa: E402
from tvlab import phase4 as Q   # noqa: E402
from tvlab import recipes as R  # noqa: E402

OUT = ROOT / "results" / "phase4" / "posthoc.json"
fin = json.loads((ROOT / "results" / "phase3" / "finalists.json").read_text())
ch = json.loads((ROOT / "results" / "phase4" / "chosen.json").read_text())
RULES = {f"{g}:{f['id']}": f["recipe"] for g in ("agent", "random", "unconditional") for f in fin[g]}
RULES["single:E_own"] = P3.SINGLE_METHODS["E_own"]
RULES["single:E_ff12_med"] = P3.SINGLE_METHODS["E_ff12_med"]
CHOSEN = {"agent": f"agent:{ch['agent']['id']}", "unconditional": f"unconditional:{ch['unconditional']['id']}",
          "random": f"random:{ch['random']['id']}", "own": "single:E_own"}


def load(split):
    if split != "exploration":
        with open(P3.UNSEAL_LOG, "a") as f:
            f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "split": split,
                                "what": "posthoc_level_vs_ranking"}) + "\n")
        return Q.m_table(split, 5, unseal=True)
    return Q.m_table(split)


def resid(e, years, idx, per_year=True):
    """e[idx] minus the median of e over idx within each start year (or over all of idx)."""
    x, y = e[idx], years[idx]
    if not per_year:
        return x - np.median(x)
    out = np.empty_like(x)
    for v in np.unique(y):
        m = y == v
        out[m] = x[m] - np.median(x[m])
    return out


res = {"note": "EXPLORATORY; see docs/phase4_posthoc.md", "splits": {}}
for split in ("exploration", "validation", "test"):
    T = load(split)
    ev = T["in_eval"].to_numpy()
    years = T.loc[ev, "t"].to_numpy()
    firms = T.loc[ev, "id"].to_numpy()
    E = {}
    for k, tree in RULES.items():
        p, _ = R.predict(tree, T)
        E[k] = P3.errors(p, T)[ev]
    full = np.arange(ev.sum())
    rules = {k: {"median_abs": float(np.median(np.abs(e))), "bias": float(np.median(e)),
                 "level_removed_year": float(np.median(np.abs(resid(e, years, full)))),
                 "level_removed_split": float(np.median(np.abs(resid(e, years, full, False))))}
             for k, e in E.items()}
    contrasts = {}
    for other in ("unconditional", "random", "own"):
        a, b = E[CHOSEN["agent"]], E[CHOSEN[other]]
        for per_year, tag in ((True, "year"), (False, "split")):
            def stat(i, a=a, b=b, per_year=per_year):
                return float(np.median(np.abs(resid(a, years, i, per_year))) -
                             np.median(np.abs(resid(b, years, i, per_year))))
            point, st = Q.cluster_boot(stat, firms)
            lo, hi = np.percentile(st, [2.5, 97.5])
            contrasts[f"agent-{other}:{tag}"] = {"diff": point, "ci95": [float(lo), float(hi)]}
    groups = {}
    for g in ("agent", "random", "unconditional"):
        v = sorted(r["level_removed_year"] for k, r in rules.items() if k.startswith(g + ":"))
        groups[g] = {"min": v[0], "median": float(np.median(v)), "max": v[-1]}
    res["splits"][split] = {"n": int(ev.sum()), "rules": rules, "contrasts": contrasts, "groups": groups}

OUT.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
for split, s in res["splits"].items():
    print(f"\n== {split} (n {s['n']})")
    for k in CHOSEN.values():
        r = s["rules"][k]
        print(f"  {k:24s} raw {r['median_abs']:.3f} bias {r['bias']:+.3f} | level-removed year {r['level_removed_year']:.3f} split {r['level_removed_split']:.3f}")
    r = s["rules"]["single:E_ff12_med"]
    print(f"  {'single:E_ff12_med':24s} raw {r['median_abs']:.3f} bias {r['bias']:+.3f} | level-removed year {r['level_removed_year']:.3f} split {r['level_removed_split']:.3f}")
    for k, c in s["contrasts"].items():
        print(f"  {k:28s} {c['diff']:+.4f} [{c['ci95'][0]:+.4f}, {c['ci95'][1]:+.4f}]")
    print("  groups (level-removed, year):", {g: {kk: round(v, 3) for kk, v in d.items()} for g, d in s["groups"].items()})
