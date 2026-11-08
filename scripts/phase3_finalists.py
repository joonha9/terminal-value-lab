"""Freeze the Phase 3 finalists (docs/phase3_design.md section 6.1). Exploration only.

    python3 -P scripts/phase3_finalists.py

- Agent finalists: per run a1..a5, agents.select (3 best graded, distinct fingerprints, ties
  earlier id) -> 15.
- Random finalists: the 15 stored in results/phase3/baselines_explore.json (same rule).
- Unconditional finalists: the top 3 distinct of the grid, stored in the same file.

Writes results/phase3/finalists.json (refuses to overwrite) and prints its SHA-256, which is
recorded in a commit before validation is opened. Requires every run to be complete.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tvlab import agents as A  # noqa: E402
from tvlab import recipes as R  # noqa: E402

OUT = ROOT / "results" / "phase3" / "finalists.json"
RUNS = ["a1", "a2", "a3", "a4", "a5"]

if OUT.exists():
    sys.exit(f"REFUSE: {OUT} exists (finalists are frozen once)")

agent = []
for name in RUNS:
    run = A.Run(name)
    st = run.state
    if st.get("stage") != "complete":
        sys.exit(f"{name} is not complete: {st}")
    for rank, r in enumerate(A.select(run.archive()), 1):
        agent.append({"run": name, "rank": rank, "id": f"{name}/{r['id']}", "name": r["name"],
                      "hash": R.recipe_hash(r["recipe"]), "depth": R.depth(r["recipe"]),
                      "compact": r["compact"], "recipe": r["recipe"],
                      "explore_median_abs": r["explore"]["median_abs"],
                      "fingerprint": r["explore"]["fingerprint"]})

base = json.loads((ROOT / "results" / "phase3" / "baselines_explore.json").read_text())
random = [{"run": int(k), "rank": i, "id": f["id"], "hash": R.recipe_hash(f["recipe"]),
           "compact": f["compact"], "recipe": f["recipe"], "explore_median_abs": f["median_abs"]}
          for k, fs in sorted(base["random"]["runs"].items(), key=lambda kv: int(kv[0]))
          for i, f in enumerate(fs, 1)]
uncond = [{"rank": i, "id": f"unc-{i}", "hash": R.recipe_hash(f["recipe"]), "compact": f["compact"],
           "recipe": f["recipe"], "explore_median_abs": f["explore"]["median_abs"],
           "fingerprint": f["explore"]["fingerprint"]}
          for i, f in enumerate(base["unconditional"]["top3"], 1)]

res = {"rule": "docs/phase3_design.md section 6.1", "code_hash": A.code_hash(),
       "funnels": {n: A.funnel(A.Run(n).archive()) for n in RUNS},
       "agent": agent, "random": random, "unconditional": uncond}
text = json.dumps(res, indent=1, sort_keys=True) + "\n"
OUT.write_text(text)
print(f"agent {len(agent)}, random {len(random)}, unconditional {len(uncond)}")
for f in agent:
    print(f"  {f['id']:10s} d{f['depth']} {f['explore_median_abs']:.4f} {f['hash']} {f['name']}")
for f in random:
    print(f"  rnd run{f['run']} #{f['rank']} {f['id']} {f['explore_median_abs']:.4f}")
for f in uncond:
    print(f"  {f['id']} {f['explore_median_abs']:.4f} {f['compact']}")
print("sha256", hashlib.sha256(text.encode()).hexdigest())
