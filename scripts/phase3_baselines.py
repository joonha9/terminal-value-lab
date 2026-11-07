"""Phase 3 benchmarks on EXPLORATION windows only (t = 2015-16, truth M).

    python3 -P scripts/phase3_baselines.py

Writes results/phase3/baselines_explore.json and results/phase3/random_pool.jsonl:
  single     every protocol section 4 candidate as a one-leaf recipe (FF12-exit fallback)
  random     a pool of 1,000 random recipes (seed 2026). Random run k (k = 1..5) = pool rules
             30(k-1)+1 .. 30k: the same budget as one agent run. Also the distribution of the
             best of 30 over 10,000 resampled searches.
  uncond     [addition, design review 2026-11-07] best recipe WITHOUT a split: exhaustive grid of
             single leaves and 2-part blends (0.05 weight steps, log and level); top 3 distinct
             kept for Phase 4 (chosen on validation like the finalists)
  gbm        GBM ceiling, 5-fold out-of-fold (folds grouped by firm): predicts ln(truth / FF12
             exit) from the recipe traits (protocol), and a second version that also sees the
             methods' log ratios to the FF12 exit (reported, not in the protocol).
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tvlab import phase3 as P3  # noqa: E402
from tvlab import recipes as R  # noqa: E402

OUT = ROOT / "results" / "phase3"
POOL, RUN_SIZE, N_RUNS, SEED = 1000, 30, 5, 2026


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    T = P3.build_table("exploration")
    res = {"split": "exploration", "n_eval": int(T["in_eval"].sum()), "n_graded": len(T)}

    res["single"] = {k: P3.grade(R.validate(v), T) for k, v in P3.SINGLE_METHODS.items()}
    best = min(res["single"], key=lambda k: res["single"][k]["median_abs"])
    res["best_single"] = best
    print(f"best single method: {best} {res['single'][best]['median_abs']:.3f}")

    rng = random.Random(SEED)
    q = P3.raw_quantiles("exploration")
    pool = []
    with open(OUT / "random_pool.jsonl", "w") as f:
        for i in range(POOL):
            tree = R.random_recipe(rng, q)
            s = P3.grade(tree, T, detail=False)
            rec = {"id": f"rnd-{i + 1:04d}", "run": i // RUN_SIZE + 1 if i < RUN_SIZE * N_RUNS else None,
                   "hash": R.recipe_hash(tree), "depth": R.depth(tree), "compact": R.compact(tree),
                   "recipe": tree, "explore": s}
            pool.append(rec)
            f.write(json.dumps(rec) + "\n")
    sc = np.array([r["explore"]["median_abs"] for r in pool])
    draws = np.random.default_rng(SEED).integers(0, POOL, size=(10000, RUN_SIZE))
    best30 = sc[draws].min(axis=1)
    # finalists: top 3 per random run with distinct behaviour (same rule as agent runs)
    runs = {k: P3.top_distinct([r for r in pool if r["run"] == k]) for k in range(1, N_RUNS + 1)}
    res["random"] = {
        "pool": POOL, "seed": SEED, "median_score": float(np.median(sc)),
        "best_of_30": {"mean": float(best30.mean()), "p5": float(np.percentile(best30, 5)),
                       "p50": float(np.median(best30)), "p95": float(np.percentile(best30, 95))},
        "best_of_pool": float(sc.min()),
        "runs": {k: [{"id": r["id"], "median_abs": r["explore"]["median_abs"], "compact": r["compact"],
                      "recipe": r["recipe"]} for r in rs] for k, rs in runs.items()},
        "distinct_fingerprints_in_runs": len({r["explore"]["fingerprint"] for r in pool if r["run"]}),
        "pool_sha1": hashlib.sha1((OUT / "random_pool.jsonl").read_bytes()).hexdigest(),
        "share_beating_best_single": float(np.mean(sc < res["single"][best]["median_abs"])),
    }
    uc = P3.unconditional_grid(T)
    top, seen = [], set()
    for m, tree in uc:
        s = P3.grade(R.validate(tree), T)
        if s["fingerprint"] in seen:
            continue
        seen.add(s["fingerprint"])
        top.append({"compact": R.compact(R.validate(tree)), "recipe": R.validate(tree), "explore": s})
        if len(top) == 3:
            break
    res["unconditional"] = {"n_recipes": len(uc), "top3": top,
                            "best_2part_blend_of_exits_only": None}
    for m, tree in uc:
        lv = [pt["leaf"] for pt in tree.get("parts", [tree])]
        if all(l["method"] == "exit" for l in lv):
            res["unconditional"]["best_2part_blend_of_exits_only"] = {"median_abs": m, "compact": R.compact(R.validate(tree))}
            break
    print(f"unconditional best: {top[0]['explore']['median_abs']:.3f} {top[0]['compact']}")
    print(f"random: median {np.median(sc):.3f}; best of 30 mean {best30.mean():.3f}; best of pool {sc.min():.3f}")

    res["gbm"] = {}
    for name, wm in (("traits", False), ("traits+methods", True)):
        pred = P3.gbm_crossfit(T, wm)
        s = P3.score_pred(pred, np.zeros(len(T), bool), T)
        res["gbm"][name] = s
        print(f"GBM {name}: {s['median_abs']:.3f} (bias {s['bias']:+.3f})")
    res["gbm_params"] = P3.GBM_PARAMS
    res["diagnostics"] = P3.diagnostics(T)
    (OUT / "baselines_explore.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
