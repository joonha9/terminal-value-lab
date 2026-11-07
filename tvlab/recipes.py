"""TV-recipe language (protocol v1 section 7): a short decision tree on firm traits at t whose
leaves are terminal-value methods.

A recipe is JSON. A node is either a LEAF (a method) or a SPLIT:

    {"if": [clause, clause?], "then": node, "else": node}

All clauses (1 or 2) must hold for "then"; otherwise "else". At most 3 levels of splits.

Clauses (traits are measured at the start year t; never names, tickers or dates):
    {"var": T, "below_pct": P} / {"var": T, "above_pct": P}   within-year percentile, P integer 5-95
    {"var": T, "below": x}     / {"var": T, "above": x}       raw value (units in TRAITS)
    {"var": "ff12", "in": ["Enrgy", ...]}                      Fama-French 12 industry
    {"var": "fcf_positive"} / {"var": "ebitda_positive"}       sign flags at t
A missing trait makes the clause false (the window goes to "else").

Leaves:
    {"method": "exit", "multiple": M}                      EV/EBITDA multiple at t x EBITDA_tH
        M: ff12 | damind | own | dam_t | dam_5yavg
    {"method": "gordon", "cash_flow": C, "g": g, "r": R}   C_tH (1+g) / (r-g)
        C: fcf | fcf_3yavg | fcf_ex_sbc;  g: 0.000-0.040 in 0.005 steps;  R: wacc | rf_plus_5
    {"method": "value_driver", "ronic": N, "g": g, "r": R} NOPAT_tH (1+g)(1-g/RONIC) / (r-g)
        N: roic | r
    {"method": "blend", "space": "log"|"level", "parts": [{"weight": w, "leaf": LEAF}, ...]}
        2-3 non-blend leaves, weights in 0.05 steps, summing to 1

Grading convention (fixed before the agent search, docs/phase3_design.md): a leaf that is
undefined for a window (e.g. Gordon with FCF_tH <= 0) falls back to the FF12 exit; windows
where the FF12 exit itself is undefined are outside the evaluation set for every recipe.
"""
from __future__ import annotations

import hashlib
import json
import random
from typing import Any

import numpy as np
import pandas as pd

TRAITS = {  # continuous traits at t: description (units of raw thresholds)
    "log_sales": "natural log of sales, USD millions (e.g. 6.9 = $1bn)",
    "log_assets": "natural log of total assets, USD millions",
    "ebitda_margin": "EBITDA / sales (0.15 = 15%)",
    "ebit_margin": "EBIT / sales",
    "roic": "EBIT x (1 - 25%) / (equity + debt - cash)",
    "net_debt_to_ebitda": "(debt - cash) / EBITDA; missing when EBITDA <= 0",
    "debt_to_assets": "total debt / total assets",
    "rnd_intensity": ("R&D / sales (0 when no R&D reported). About half of firms are exactly 0 and tied "
                      "firms share one percentile (~25), so below_pct under 25 selects nobody: use a raw threshold"),
    "capex_intensity": "capital expenditure / sales",
    "wacc_minus_g": "firm WACC at t minus 2.5% (0.04 = 4 percentage points)",
}
FLAGS = {"fcf_positive": "unlevered FCF at t > 0", "ebitda_positive": "EBITDA at t > 0"}
FF12 = ["NoDur", "Durbl", "Manuf", "Enrgy", "Chems", "BusEq", "Telcm", "Utils", "Shops", "Hlth", "Other"]

EXIT_MULTIPLES = {"ff12": "E_ff12_med", "damind": "E_damind_med", "own": "E_own",
                  "dam_t": "E_dam_t", "dam_5yavg": "E_dam_5yavg"}
CASH_FLOWS = ("fcf", "fcf_3yavg", "fcf_ex_sbc")
RATES = ("wacc", "rf_plus_5")
RONICS = ("roic", "r")
G_GRID = tuple(round(0.005 * k, 3) for k in range(9))      # 0.0% .. 4.0%
W_STEP = 0.05
MAX_DEPTH, MAX_CLAUSES, MAX_PARTS = 3, 2, 3
PCT_RANGE = (5, 95)
FALLBACK = "E_ff12_med"
TEXT_KEYS = {"name", "mechanism", "prediction"}


class RecipeError(ValueError):
    """Raised when a recipe violates the schema; the message lists every problem."""


# ------------------------------------------------------------------ leaf column names
def leaf_column(leaf: dict) -> str:
    """Name of the precomputed prediction column for a non-blend leaf."""
    m = leaf["method"]
    if m == "exit":
        return EXIT_MULTIPLES[leaf["multiple"]]
    if m == "gordon":
        return f"gordon|{leaf['cash_flow']}|{leaf['g']:.3f}|{leaf['r']}"
    if m == "value_driver":
        return f"vd|{leaf['ronic']}|{leaf['g']:.3f}|{leaf['r']}"
    raise KeyError(m)


def all_leaf_columns() -> list[str]:
    cols = list(EXIT_MULTIPLES.values())
    cols += [f"gordon|{c}|{g:.3f}|{r}" for c in CASH_FLOWS for g in G_GRID for r in RATES]
    cols += [f"vd|{n}|{g:.3f}|{r}" for n in RONICS for g in G_GRID for r in RATES]
    return cols


# ------------------------------------------------------------------ validation
def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and np.isfinite(x)


def _on_grid(x: float, step: float) -> bool:
    return abs(x / step - round(x / step)) < 1e-6


def _check_leaf(x: Any, tag: str, p: list[str], allow_blend: bool = True) -> None:
    if not isinstance(x, dict) or "method" not in x:
        p.append(f"{tag}: a leaf needs 'method'")
        return
    m = x["method"]
    keys = set(x)
    if m == "exit":
        if keys != {"method", "multiple"} or x.get("multiple") not in EXIT_MULTIPLES:
            p.append(f"{tag}: exit leaf is {{'method': 'exit', 'multiple': one of {list(EXIT_MULTIPLES)}}}")
    elif m in ("gordon", "value_driver"):
        k2 = "cash_flow" if m == "gordon" else "ronic"
        allowed = CASH_FLOWS if m == "gordon" else RONICS
        if keys != {"method", k2, "g", "r"}:
            p.append(f"{tag}: {m} leaf needs exactly method, {k2}, g, r")
            return
        if x[k2] not in allowed:
            p.append(f"{tag}.{k2}: one of {list(allowed)}")
        if not _num(x["g"]) or not (0 <= x["g"] <= 0.04 + 1e-9) or not _on_grid(x["g"], 0.005):
            p.append(f"{tag}.g: a number 0-0.04 in steps of 0.005 (0.025 = 2.5%)")
        if x["r"] not in RATES:
            p.append(f"{tag}.r: one of {list(RATES)}")
    elif m == "blend":
        if not allow_blend:
            p.append(f"{tag}: a blend part cannot itself be a blend")
            return
        if keys != {"method", "space", "parts"}:
            p.append(f"{tag}: blend leaf needs exactly method, space, parts")
            return
        if x["space"] not in ("log", "level"):
            p.append(f"{tag}.space: 'log' or 'level'")
        parts = x["parts"]
        if not isinstance(parts, list) or not 2 <= len(parts) <= MAX_PARTS:
            p.append(f"{tag}.parts: a list of 2-{MAX_PARTS} parts")
            return
        tot = 0.0
        for j, part in enumerate(parts):
            pt = f"{tag}.parts[{j}]"
            if not isinstance(part, dict) or set(part) != {"weight", "leaf"}:
                p.append(f"{pt}: needs exactly 'weight' and 'leaf'")
                continue
            w = part["weight"]
            if not _num(w) or not (W_STEP - 1e-9 <= w <= 1 - W_STEP + 1e-9) or not _on_grid(w, W_STEP):
                p.append(f"{pt}.weight: 0.05-0.95 in steps of 0.05")
            else:
                tot += w
            _check_leaf(part["leaf"], f"{pt}.leaf", p, allow_blend=False)
        if abs(tot - 1) > 1e-6:
            p.append(f"{tag}: blend weights must sum to 1 (got {tot:g})")
    else:
        p.append(f"{tag}.method: one of exit, gordon, value_driver, blend")


def _check_clause(x: Any, tag: str, p: list[str]) -> None:
    if not isinstance(x, dict) or "var" not in x:
        p.append(f"{tag}: a clause needs 'var'")
        return
    v, rest = x["var"], set(x) - {"var"}
    if v in FLAGS:
        if rest:
            p.append(f"{tag}: flag '{v}' takes no threshold (use the else branch for 'not')")
    elif v == "ff12":
        ind = x.get("in")
        if rest != {"in"} or not isinstance(ind, list) or not ind or not set(ind) <= set(FF12) \
                or len(set(ind)) != len(ind) or len(ind) >= len(FF12):
            p.append(f"{tag}: ff12 clause is {{'var': 'ff12', 'in': [non-empty proper subset of {FF12}]}}")
    elif v in TRAITS:
        if len(rest) != 1 or not rest <= {"below_pct", "above_pct", "below", "above"}:
            p.append(f"{tag}: give exactly one of below_pct, above_pct, below, above")
            return
        (k,) = rest
        val = x[k]
        if k.endswith("_pct"):
            if not isinstance(val, int) or isinstance(val, bool) or not PCT_RANGE[0] <= val <= PCT_RANGE[1]:
                p.append(f"{tag}.{k}: an integer {PCT_RANGE[0]}-{PCT_RANGE[1]}")
        elif not _num(val):
            p.append(f"{tag}.{k}: a finite number")
    else:
        p.append(f"{tag}: unknown trait '{v}'")


def _check_node(x: Any, tag: str, depth: int, p: list[str]) -> None:
    if isinstance(x, dict) and "if" in x:
        if depth >= MAX_DEPTH:
            p.append(f"{tag}: more than {MAX_DEPTH} levels of splits")
            return
        if set(x) != {"if", "then", "else"}:
            p.append(f"{tag}: a split needs exactly 'if', 'then', 'else'")
            return
        cl = x["if"]
        if not isinstance(cl, list) or not 1 <= len(cl) <= MAX_CLAUSES:
            p.append(f"{tag}.if: a list of 1-{MAX_CLAUSES} clauses")
        else:
            for j, c in enumerate(cl):
                _check_clause(c, f"{tag}.if[{j}]", p)
        _check_node(x["then"], f"{tag}.then", depth + 1, p)
        _check_node(x["else"], f"{tag}.else", depth + 1, p)
    else:
        _check_leaf(x, tag, p)


def _canon(x: Any) -> Any:
    """Canonical form: numbers normalised (g, weights, raw thresholds as floats, no -0.0);
    blend parts, AND-clauses and FF12 lists sorted. Functionally identical spellings then
    hash equally (code review 2026-11-07)."""
    if isinstance(x, dict):
        out = {k: _canon(v) for k, v in x.items()}
        if "g" in out and _num(out["g"]):
            out["g"] = round(float(out["g"]), 3) + 0.0
        if "weight" in out and _num(out["weight"]):
            out["weight"] = round(float(out["weight"]), 2) + 0.0
        for k in ("below", "above"):
            if k in out and _num(out[k]):
                out[k] = float(out[k]) + 0.0
        if out.get("var") == "ff12" and isinstance(out.get("in"), list):
            out["in"] = sorted(out["in"], key=str)
        if out.get("method") == "blend" and isinstance(out.get("parts"), list):
            out["parts"] = sorted(out["parts"], key=lambda q: json.dumps(q, sort_keys=True))
        if isinstance(out.get("if"), list):
            out["if"] = sorted(out["if"], key=lambda q: json.dumps(q, sort_keys=True))
        return out
    if isinstance(x, list):
        return [_canon(v) for v in x]
    return x


def _check_semantics(x: dict, tag: str, p: list[str]) -> None:
    """Checks on the canonical tree: no do-nothing splits, no repeated clauses or blend parts."""
    if "if" in x:
        keys = [json.dumps(c, sort_keys=True) for c in x["if"]]
        if len(set(keys)) < len(keys):
            p.append(f"{tag}.if: the same clause twice")
        if json.dumps(x["then"], sort_keys=True) == json.dumps(x["else"], sort_keys=True):
            p.append(f"{tag}: 'then' and 'else' are identical (the split does nothing)")
        _check_semantics(x["then"], f"{tag}.then", p)
        _check_semantics(x["else"], f"{tag}.else", p)
    elif x.get("method") == "blend":
        keys = [json.dumps(pt["leaf"], sort_keys=True) for pt in x["parts"]]
        if len(set(keys)) < len(keys):
            p.append(f"{tag}: blend parts must be different leaves")


def validate(recipe: Any) -> dict:
    """Return the canonical recipe tree, or raise RecipeError listing every violation."""
    p: list[str] = []
    try:
        _check_node(recipe, "recipe", 0, p)
        if p:
            raise RecipeError("; ".join(p))
        tree = _canon(recipe)
        _check_semantics(tree, "recipe", p)
    except RecipeError:
        raise
    except (TypeError, ValueError, OverflowError, AttributeError, KeyError) as e:  # malformed types
        raise RecipeError(f"malformed recipe ({type(e).__name__}: {e})") from None
    if p:
        raise RecipeError("; ".join(p))
    return tree


def recipe_hash(tree: dict) -> str:
    return hashlib.sha1(json.dumps(_canon(tree), sort_keys=True).encode()).hexdigest()[:10]


def depth(tree: dict) -> int:
    if "if" in tree:
        return 1 + max(depth(tree["then"]), depth(tree["else"]))
    return 0


def leaves(tree: dict) -> list[dict]:
    if "if" in tree:
        return leaves(tree["then"]) + leaves(tree["else"])
    return [tree]


# ------------------------------------------------------------------ evaluation
def _leaf_values(leaf: dict, T: pd.DataFrame) -> np.ndarray:
    if leaf["method"] != "blend":
        v = T[leaf_column(leaf)].to_numpy(dtype=float)
        return np.where(v > 0, v, np.nan)
    vals = [(pt["weight"], _leaf_values(pt["leaf"], T)) for pt in leaf["parts"]]
    if leaf["space"] == "log":
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.exp(sum(w * np.log(v) for w, v in vals))
    return sum(w * v for w, v in vals)


def _clause_mask(c: dict, T: pd.DataFrame) -> np.ndarray:
    v = c["var"]
    if v in FLAGS:
        return T[v].fillna(False).to_numpy(dtype=bool)
    if v == "ff12":
        return T["ff12"].isin(c["in"]).to_numpy()
    if "below_pct" in c or "above_pct" in c:
        x = T[f"pct_{v}"].to_numpy(dtype=float) * 100
    else:
        x = T[v].to_numpy(dtype=float)
    with np.errstate(invalid="ignore"):
        if "below_pct" in c:
            out = x <= c["below_pct"]
        elif "above_pct" in c:
            out = x >= c["above_pct"]
        elif "below" in c:
            out = x <= c["below"]
        else:
            out = x >= c["above"]
    return out & ~np.isnan(x)


def predict(tree: dict, T: pd.DataFrame, return_leaf: bool = False):
    """Predicted EV for every row of a phase-3 table, and a mask of rows that used the FF12-exit
    fallback (leaf undefined; for a blend, ANY undefined part sends the whole leaf to the
    fallback). With return_leaf, also the index of the leaf (left to right, as in `leaves`)
    each row was routed to."""
    raw = np.full(len(T), np.nan)
    leaf_id = np.full(len(T), -1)
    counter = [0]

    def walk(node: dict, rows: np.ndarray) -> None:
        if "if" in node:
            hold = rows.copy()
            for c in node["if"]:
                hold &= _clause_mask(c, T)
            walk(node["then"], hold)
            walk(node["else"], rows & ~hold)
        else:
            raw[rows] = _leaf_values(node, T)[rows]
            leaf_id[rows] = counter[0]
            counter[0] += 1

    with np.errstate(invalid="ignore", divide="ignore"):
        walk(tree, np.ones(len(T), dtype=bool))
    fb = T[FALLBACK].to_numpy(dtype=float)
    used_fb = ~(raw > 0)
    pred = np.where(used_fb, fb, raw)
    return (pred, used_fb, leaf_id) if return_leaf else (pred, used_fb)


# ------------------------------------------------------------------ text
def leaf_text(leaf: dict) -> str:
    m = leaf["method"]
    if m == "exit":
        return f"Exit[{leaf['multiple']}]"
    if m == "gordon":
        return f"Gordon[{leaf['cash_flow']}, g {leaf['g'] * 100:g}%, {leaf['r']}]"
    if m == "value_driver":
        return f"ValueDriver[ronic={leaf['ronic']}, g {leaf['g'] * 100:g}%, {leaf['r']}]"
    parts = " + ".join(f"{pt['weight']:g}*{leaf_text(pt['leaf'])}" for pt in leaf["parts"])
    return f"Blend-{leaf['space']}({parts})"


def clause_text(c: dict) -> str:
    v = c["var"]
    if v in FLAGS:
        return v
    if v == "ff12":
        return f"ff12 in {{{','.join(c['in'])}}}"
    for k, op in (("below_pct", "<= p"), ("above_pct", ">= p"), ("below", "<= "), ("above", ">= ")):
        if k in c:
            return f"{v} {op}{c[k]:g}"
    raise KeyError(c)


def compact(tree: dict) -> str:
    if "if" in tree:
        cond = " AND ".join(clause_text(c) for c in tree["if"])
        return f"IF {cond} THEN {compact(tree['then'])} ELSE {compact(tree['else'])}"
    return leaf_text(tree)


# ------------------------------------------------------------------ random recipes
def random_leaf(rng: random.Random, allow_blend: bool = True) -> dict:
    kind = rng.choices(["exit", "gordon", "value_driver", "blend"],
                       weights=[4, 3, 1, 2 if allow_blend else 0])[0]
    if kind == "exit":
        return {"method": "exit", "multiple": rng.choice(list(EXIT_MULTIPLES))}
    if kind == "gordon":
        return {"method": "gordon", "cash_flow": rng.choice(CASH_FLOWS), "g": rng.choice(G_GRID),
                "r": rng.choice(RATES)}
    if kind == "value_driver":
        return {"method": "value_driver", "ronic": rng.choice(RONICS), "g": rng.choice(G_GRID),
                "r": rng.choice(RATES)}
    k = rng.choice([2, 2, 3])
    while True:
        parts = [random_leaf(rng, allow_blend=False) for _ in range(k)]
        if len({json.dumps(q, sort_keys=True) for q in parts}) == k:
            break
    cuts = sorted(rng.sample(range(1, 20), k - 1))
    ws = [b - a for a, b in zip([0] + cuts, cuts + [20])]
    return {"method": "blend", "space": rng.choice(["log", "level"]),
            "parts": [{"weight": round(w * W_STEP, 2), "leaf": q} for w, q in zip(ws, parts)]}


def random_clause(rng: random.Random, raw_quantiles: dict[str, list[float]] | None) -> dict:
    """A clause drawn over the whole clause language: percentile thresholds 5-95, raw thresholds at
    a random percentile (5-95) of the trait's distribution, FF12 sets of 1-10 industries."""
    v = rng.choices(["trait", "ff12", "flag"], weights=[7, 2, 1])[0]
    if v == "flag":
        return {"var": rng.choice(list(FLAGS))}
    if v == "ff12":
        return {"var": "ff12", "in": rng.sample(FF12, rng.randint(1, len(FF12) - 1))}
    t = rng.choice(list(TRAITS))
    side = rng.choice(["below", "above"])
    pct = rng.randint(PCT_RANGE[0], PCT_RANGE[1])
    if raw_quantiles and rng.random() < 0.5:  # raw threshold at that percentile of the trait
        return {"var": t, side: round(raw_quantiles[t][pct - PCT_RANGE[0]], 4)}
    return {"var": t, f"{side}_pct": pct}


def random_recipe(rng: random.Random, raw_quantiles: dict[str, list[float]] | None = None) -> dict:
    """A recipe drawn from the language with no economic knowledge (seeded)."""
    target = rng.choices([0, 1, 2, 3], weights=[1, 3, 3.5, 2.5])[0]

    def node(d: int) -> dict:
        if d >= target or (d > 0 and rng.random() < 0.3):
            return random_leaf(rng)
        cl = [random_clause(rng, raw_quantiles) for _ in range(rng.choice([1, 1, 2]))]
        return {"if": cl, "then": node(d + 1), "else": node(d + 1)}

    while True:
        try:
            return validate(node(0))
        except RecipeError:
            continue
