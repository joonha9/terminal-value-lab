"""Unit tests for tvlab/q4.py (toy data only; no real returns)."""
import numpy as np
import pandas as pd

from tvlab import q4


def test_rank_scale_bounds_and_nan():
    s = pd.Series([3.0, 1.0, np.nan, 2.0])
    r = q4.rank_scale(s)
    assert r.min() == -0.5 and r.max() == 0.5 and np.isnan(r.iloc[2])


def test_nw_mean_matches_ols_nw_on_constant():
    x = np.random.default_rng(0).normal(0, 1, 200)
    m, se = q4.nw_mean(x)
    b, se2 = q4.ols_nw(x, np.ones((200, 1)))
    assert abs(m - b[0]) < 1e-12 and abs(se - se2[0]) < 1e-12


def test_nw_equals_plain_se_with_lag0():
    x = np.random.default_rng(1).normal(0, 1, 500)
    _, se = q4.nw_mean(x, lag=0)
    assert abs(se - x.std(ddof=0) / np.sqrt(len(x))) < 1e-12


def test_winsorize_monthly_clips_within_month():
    d = pd.DataFrame({"month": [pd.Period("2020-01", "M")] * 5 + [pd.Period("2020-02", "M")] * 5,
                      "r": [0, 1, 2, 3, 100, 0, 1, 2, 3, 4.0]})
    w = q4.winsorize_monthly(d, "r", 0.0, 0.75)
    assert w.iloc[4] == 3.0 and w.iloc[9] == 3.0 and w.iloc[0] == 0


def test_pick_security_prefers_ticker_match_then_coverage():
    m = [pd.Period("2020-01", "M") + k for k in range(3)]
    ret = pd.DataFrame({"entity_id": ["A"] * 5 + ["B"] * 5,
                        "fds_ticker": ["A1"] * 3 + ["A2"] * 2 + ["B1"] * 2 + ["B2"] * 3,
                        "symbol": ["AAA"] * 3 + ["AAX"] * 2 + ["BB1"] * 2 + ["BB2"] * 3,
                        "month": m + m[:2] + m[:2] + m, "ret": 0.01})
    fy = pd.DataFrame({"id": ["A", "B"], "ticker": ["AAX", "ZZZ"]})
    got = q4.pick_security(ret, fy).groupby("entity_id")["fds_ticker"].first().to_dict()
    assert got == {"A": "A2", "B": "B2"}


def test_delisting_rule():
    months = [pd.Period("2020-01", "M") + k for k in range(24)]
    rows = []
    for e, r in (("ACQ", 0.0), ("FAIL", -0.2), ("REORG", 0.01), ("LISTED", 0.0)):
        for k in range(12):
            rows.append({"entity_id": e, "month": months[k], "ret": r})
    ret = pd.DataFrame(rows)
    exits = pd.DataFrame({"id": ["ACQ", "FAIL", "REORG", "LISTED"],
                          "exit_type": ["acquired", "inactive", "inactive", "listed"],
                          "last_mkt_cap": [5000, 500, 5000, 5000]})
    d = q4.delisting_returns(ret, exits, months).set_index("entity_id")
    assert d.loc["ACQ", "ret"] == 0.0 and d.loc["FAIL", "ret"] == -0.30 and d.loc["REORG", "ret"] == 0.0
    assert "LISTED" not in d.index and (d["month"] == months[12]).all()


def test_signal_decomposition_identity():
    fy = pd.DataFrame({"id": ["X"], "fiscal_year": [2015], "ff12": ["Manuf"], "in_universe": [True],
                       "quality_ok": [True], "value_date": [pd.Timestamp("2016-06-30")], "mkt_cap": [1000.0],
                       "ev": [1200.0], "fcf": [60.0], "wacc": [0.08], "ebitda": [150.0], "ebit": [100.0],
                       "book_equity": [500.0], "gross_profit": [300.0], "total_assets": [2000.0], "beta_l": [1.1]})
    s = q4.signals(fy).iloc[0]
    assert abs(s["S1"] - (s["S1a"] + s["S1b"])) < 1e-12
    assert s["formation"] == pd.Period("2016-06", "M")
