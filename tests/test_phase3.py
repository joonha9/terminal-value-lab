"""Phase 3 checks: recipe validator, evaluation, fallback, sealing.  python3 -P -m pytest tests -q"""
import json
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tvlab import agents as ag  # noqa: E402
from tvlab import methods as M  # noqa: E402
from tvlab import phase3 as P3  # noqa: E402
from tvlab import recipes as R  # noqa: E402

GOOD = {"if": [{"var": "ff12", "in": ["Enrgy", "Chems"]}],
        "then": {"method": "exit", "multiple": "dam_5yavg"},
        "else": {"if": [{"var": "wacc_minus_g", "below": 0.04}, {"var": "fcf_positive"}],
                 "then": {"method": "blend", "space": "log", "parts": [
                     {"weight": 0.7, "leaf": {"method": "exit", "multiple": "own"}},
                     {"weight": 0.3, "leaf": {"method": "gordon", "cash_flow": "fcf_3yavg", "g": 0.02, "r": "wacc"}}]},
                 "else": {"method": "exit", "multiple": "own"}}}


def test_valid_recipe_passes():
    assert R.depth(R.validate(GOOD)) == 2


@pytest.mark.parametrize("bad", [
    {"method": "exit", "multiple": "sector"},
    {"method": "gordon", "cash_flow": "fcf", "g": 0.027, "r": "wacc"},
    {"method": "gordon", "cash_flow": "fcf", "g": 0.05, "r": "wacc"},
    {"method": "blend", "space": "log", "parts": [
        {"weight": 0.6, "leaf": {"method": "exit", "multiple": "own"}},
        {"weight": 0.6, "leaf": {"method": "exit", "multiple": "ff12"}}]},
    {"method": "blend", "space": "log", "parts": [
        {"weight": 0.5, "leaf": {"method": "exit", "multiple": "own"}},
        {"weight": 0.5, "leaf": {"method": "exit", "multiple": "own"}}]},
    {"if": [{"var": "sales_growth_1y", "above_pct": 50}], "then": {"method": "exit", "multiple": "own"},
     "else": {"method": "exit", "multiple": "ff12"}},
    {"if": [{"var": "roic", "above_pct": 3}], "then": {"method": "exit", "multiple": "own"},
     "else": {"method": "exit", "multiple": "ff12"}},
    {"if": [{"var": "ff12", "in": R.FF12}], "then": {"method": "exit", "multiple": "own"},
     "else": {"method": "exit", "multiple": "ff12"}},
])
def test_invalid_recipes_rejected(bad):
    with pytest.raises(R.RecipeError):
        R.validate(bad)


def test_depth_limit():
    leaf = {"method": "exit", "multiple": "own"}
    node = leaf
    for _ in range(4):
        node = {"if": [{"var": "fcf_positive"}], "then": node, "else": leaf}
    with pytest.raises(R.RecipeError):
        R.validate(node)


def test_hash_ignores_blend_order():
    a = {"method": "blend", "space": "log", "parts": [
        {"weight": 0.3, "leaf": {"method": "exit", "multiple": "own"}},
        {"weight": 0.7, "leaf": {"method": "exit", "multiple": "ff12"}}]}
    b = {**a, "parts": a["parts"][::-1]}
    assert R.recipe_hash(R.validate(a)) == R.recipe_hash(R.validate(b))


def test_random_recipes_valid():
    rng = random.Random(0)
    for _ in range(200):
        R.validate(R.random_recipe(rng))


@pytest.fixture(scope="module")
def T():
    return P3.build_table("exploration")


def test_leaf_columns_match_phase1_methods(T):
    assert set(R.all_leaf_columns()) <= set(T.columns)
    w = pd.read_pickle(P3.P.PROC / "windows_h5.pkl")
    w = w[w.t.between(2015, 2016) & w.quality_ok_t]
    g = w[w.status.isin(["survived", "shrank"]) & w.quality_ok_tH.eq(True) & w.ev_tH.gt(0)]
    std = M.predict_all(g, pd.read_pickle(P3.P.PROC / "firm_years.pkl")).reset_index(drop=True)
    for col, std_col in [("gordon|fcf|0.025|wacc", "G_fcf_g2.5"), ("gordon|fcf_3yavg|0.025|wacc", "G_fcf3avg_g2.5"),
                         ("gordon|fcf|0.025|rf_plus_5", "G_fcf_g2.5_rf+5"), ("vd|roic|0.025|wacc", "G_vd_roic_g2.5"),
                         ("vd|r|0.025|wacc", "G_vd_ronic=r"), ("gordon|fcf_ex_sbc|0.025|wacc", "G_exsbc_g2.5")]:
        pd.testing.assert_series_equal(T[col], std[std_col], check_names=False)


def test_fallback_and_routing(T):
    tree = R.validate(GOOD)
    pred, fb = R.predict(tree, T)
    en = T["ff12"].isin(["Enrgy", "Chems"]).to_numpy()
    d5 = T["E_dam_5yavg"].to_numpy()
    ok = en & (d5 > 0)
    assert np.allclose(pred[ok], d5[ok])
    miss = en & ~(d5 > 0)
    assert np.allclose(pred[miss], T["E_ff12_med"].to_numpy()[miss], equal_nan=True) and fb[miss].all()


def test_sealed_splits():
    with pytest.raises(PermissionError):
        P3.build_table("validation")
    with pytest.raises(PermissionError):
        P3.build_table("test")


def test_percentiles_in_unit_interval(T):
    for c in R.TRAITS:
        x = T[f"pct_{c}"].dropna()
        assert x.between(0, 1).all()


# ---------------------------------------------------------------- code review 2026-11-07 regressions
OWN = {"method": "exit", "multiple": "own"}
FF = {"method": "exit", "multiple": "ff12"}


def test_canonical_hash_ignores_spelling():
    a = {"if": [{"var": "roic", "above": 0}, {"var": "ff12", "in": ["Utils", "Enrgy"]}], "then": OWN, "else": FF}
    b = {"if": [{"var": "ff12", "in": ["Enrgy", "Utils"]}, {"var": "roic", "above": 0.0}], "then": OWN, "else": FF}
    assert R.recipe_hash(R.validate(a)) == R.recipe_hash(R.validate(b))
    g1 = {"method": "gordon", "cash_flow": "fcf", "g": -0.0, "r": "wacc"}
    g2 = {"method": "gordon", "cash_flow": "fcf", "g": 0, "r": "wacc"}
    assert R.recipe_hash(R.validate(g1)) == R.recipe_hash(R.validate(g2))


@pytest.mark.parametrize("bad", [
    {"if": [{"var": "fcf_positive"}], "then": OWN, "else": OWN},
    {"if": [{"var": "fcf_positive"}, {"var": "fcf_positive"}], "then": OWN, "else": FF},
    {"method": "blend", "space": "log", "parts": [
        {"weight": 0.5, "leaf": {"method": "gordon", "cash_flow": "fcf", "g": 0.025, "r": "wacc"}},
        {"weight": 0.5, "leaf": {"method": "gordon", "cash_flow": "fcf", "g": 0.0250000004, "r": "wacc"}}]},
    {"if": [{"var": "ff12", "in": [["Enrgy"]]}], "then": OWN, "else": FF},
    {"if": [{"var": ["roic"], "above": 1}], "then": OWN, "else": FF},
    {"method": "exit", "multiple": ["own"]},
    {"method": "gordon", "cash_flow": "fcf", "g": 10 ** 400, "r": "wacc"},
    "not a recipe",
])
def test_semantic_and_type_errors_are_recipe_errors(bad):
    with pytest.raises(R.RecipeError):
        R.validate(bad)


def test_verdict_checks():
    ok = ag.check_verdicts({"verdicts": [{"index": 0, "verdict": "Approved ", "reason": None},
                                         {"index": "1", "verdict": "reject", "reason": "x"}]}, 2)
    assert ok[0]["verdict"] == "approve" and ok[0]["reason"] == "" and ok[1]["verdict"] == "reject"
    for bad in ({"verdicts": [{"index": 1, "verdict": "approve"}, {"index": 2, "verdict": "approve"}]},  # 1-based
                {"verdicts": [{"index": 0, "verdict": "maybe"}, {"index": 1, "verdict": "approve"}]},
                {"verdicts": [{"index": 0, "verdict": "approve"}, {"index": 0, "verdict": "reject"}]},
                {"verdicts": [{"verdict": "approve"}, {"index": 1, "verdict": "approve"}]},
                {"verdicts": "approve all"}):
        with pytest.raises(ag.ReplyError):
            ag.check_verdicts(bad, 2)


def test_blind_masks_scores_only():
    t = ag._blind("beats 0.415 and 0.3683; net debt above 3.5x, margin 0.15")
    assert "0.415" not in t and "0.3683" not in t and "3.5x" in t and "0.15" in t


def test_parse_reply_with_backticks_inside_string():
    txt = json.dumps({"proposals": [{"name": "a ``` b", "mechanism": "m", "prediction": "p", "recipe": OWN}]})
    assert ag.parse_json_reply(txt)["proposals"][0]["name"] == "a ``` b"
    assert ag.parse_json_reply("```json\n" + txt + "\n```")["proposals"][0]["recipe"] == OWN


def test_stage_commit_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(ag, "RUNS", tmp_path)
    run = ag.Run("t", {})
    reply = {"proposals": [OWN, {"name": "x", "mechanism": "m", "prediction": "p", "recipe": FF}] +
             [{"name": f"e{i}", "recipe": OWN} for i in range(6)]}
    arch, pending = ag.register_proposals(run, reply, 1)
    statuses = sorted(r["status"] for r in arch)
    assert statuses.count("invalid") == 1 and statuses.count("over_budget") == 2
    run.commit(arch, {"generation": 1, "stage": "awaiting_verdicts"})
    run.commit(arch, {"generation": 1, "stage": "awaiting_verdicts"})  # re-run after a crash
    assert len(run.archive()) == len(arch)


def test_select_distinct_behaviour():
    recs = [{"id": f"g01-0{i}", "status": "graded", "explore": {"median_abs": m, "fingerprint": fp}}
            for i, (m, fp) in enumerate([(0.40, "a"), (0.40, "a"), (0.41, "b"), (0.39, "c"), (0.42, "d")])]
    recs.append(dict(recs[3]))  # same id archived twice
    assert [r["id"] for r in ag.select(recs)] == ["g01-03", "g01-00", "g01-02"]


def test_build_table_returns_copy(T):
    T2 = P3.build_table("exploration")
    T2.loc[0, "truth"] = -1
    assert P3.build_table("exploration").loc[0, "truth"] != -1


def test_known_unconditional_blend_score(T):
    leaf = {"method": "blend", "space": "level", "parts": [
        {"weight": 0.8, "leaf": OWN},
        {"weight": 0.2, "leaf": {"method": "gordon", "cash_flow": "fcf_3yavg", "g": 0.04, "r": "rf_plus_5"}}]}
    assert abs(P3.grade(R.validate(leaf), T)["median_abs"] - 0.3683) < 1e-3


def test_agent_definition_copy_matches():
    active = ROOT.parent / ".claude" / "agents" / "tv-text-only.md"
    assert active.read_text() == (ROOT / "config" / "tv-text-only.md").read_text()
