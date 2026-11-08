"""Load FactSet monthly total returns (Q4) and check every file.

    python3 -P scripts/build_returns.py            # check all files present, write the long table
    python3 -P scripts/build_returns.py --check    # checks only

Input: data/raw/factset_returns_YYYY.xlsx (docs/q4_returns_export.md). FactSet labels every
return column "Compound Tot Ret (USD)", so months are assigned by column order. Checks:
1. same 32,808 rows and the same entity order as the probe file;
2. the file holds the year's months as its LAST return columns (extra leading columns are
   leftovers from earlier screens and are dropped; check 3 confirms the kept columns' months);
3. month level: the value-weighted return of clean panel firms (weights = market cap in the
   prior fiscal year, returns clipped to [-90%, +300%] so a mis-scaled firm cannot dominate)
   must match the CRSP market return (Kenneth French Mkt-RF + RF): median monthly gap <= 2pp.
   This catches a wrong year or a large reorder.
4. month labels, column by column: an acquired firm's returns must stop at its completion
   month (FactSet leaves the month of a mid-month delisting empty). The expected last month is
   the month before completion; for completions on day 25 or later, it may also be the
   completion month; if that month falls in the previous year's file, the firm must have no
   return in this file. Required: >= 75% of in-file completions match, and >= 50% within every
   month with >= 5 completions (catches two swapped columns). On the 2016-26 files, a one-month
   shift drops the match rate from 0.81-0.99 to <= 0.23. The 2015 file has no in-file
   completions and relies on check 3.
   History: a median of large firms, then an adjacent-swap test on the market gap, were tried
   first. Both were too noisy to rank similar months and are not used.
This is a data check only: no return is related to any signal here.
Output: data/processed/returns_monthly.pkl (entity_id, symbol, fds_ticker, month, ret as a decimal).
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, PROC = ROOT / "data" / "raw", ROOT / "data" / "processed"
YEARS = range(2015, 2027)


def months_of(y: int) -> list[pd.Period]:
    lo, hi = (7, 12) if y == 2015 else (1, 10) if y == 2026 else (1, 12)
    return [pd.Period(f"{y}-{m:02d}", "M") for m in range(lo, hi + 1)]


def read(path: Path) -> pd.DataFrame:
    head = pd.read_excel(path, header=None, nrows=6)
    assert head.iloc[4, 0] == "Symbol", f"{path.name}: unexpected header row"
    return pd.read_excel(path, header=4).dropna(how="all").reset_index(drop=True)


def market() -> pd.Series:
    f = RAW / "french" / "F-F_Research_Data_5_Factors_2x3.csv"
    d = pd.read_csv(f, skiprows=4, index_col=0)
    d = d[d.index.astype(str).str.strip().str.fullmatch(r"\d{6}")]
    d.index = pd.PeriodIndex([f"{s.strip()[:4]}-{s.strip()[4:]}" for s in d.index.astype(str)], freq="M")
    d = d.astype(float)
    return (d["Mkt-RF"] + d["RF"]).rename("mkt")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    probe = read(RAW / "factset_returns_probe.xlsx")
    fy = pd.read_pickle(PROC / "firm_years.pkl")
    mkt = market()
    ex = pd.read_csv(PROC / "exits.csv", parse_dates=["complete_date"])
    acq = ex[ex.exit_type.eq("acquired") & ex.complete_date.notna()].drop_duplicates("id").set_index("id")["complete_date"]
    frames, ok_all = [], True
    for y in YEARS:
        p = RAW / f"factset_returns_{y}.xlsx"
        if not p.exists():
            print(f"{y}: missing")
            continue
        df = read(p)
        rc = [c for c in df.columns if str(c).startswith("Compound")]
        ms = months_of(y)
        msg = []
        same_rows = len(df) == len(probe) and (df["Entity ID"].values == probe["Entity ID"].values).all()
        if not same_rows:
            msg.append("ROWS DIFFER FROM PROBE")
        if len(rc) < len(ms):
            print(f"{y}: FAIL only {len(rc)} return columns, need {len(ms)}")
            ok_all = False
            continue
        if len(rc) > len(ms):
            msg.append(f"{len(rc) - len(ms)} extra leading columns dropped")
        R = df[rc[-len(ms):]].astype(float)
        R.columns = ms
        cl = fy[(fy.fiscal_year == max(y - 1, 2015)) & fy.in_universe & fy.quality_ok
                & ~fy.mcap_jump_suspect.eq(True)].drop_duplicates("id").set_index("id")["mkt_cap"]
        m = df["Entity ID"].isin(cl.index).to_numpy()
        sub = R[m].clip(-90, 300)
        sub.index = df.loc[m, "Entity ID"]
        sub = sub[~sub.index.duplicated()]
        w = cl.reindex(sub.index)
        vw = sub.mul(w, axis=0).sum() / sub.notna().mul(w, axis=0).sum()
        ref = mkt.reindex(ms)
        h = ref.notna().to_numpy()
        gap = float(np.median(np.abs(vw.to_numpy()[h] - ref.to_numpy()[h])))
        Rid = R.copy()
        Rid.index = df["Entity ID"]
        Rid = Rid[~Rid.index.duplicated()]
        cd = acq.reindex(Rid.index).dropna()
        cd = cd[(cd.dt.to_period("M") >= ms[0]) & (cd.dt.to_period("M") <= ms[-1])]
        last = Rid.loc[cd.index].apply(lambda row: row.last_valid_index(), axis=1)
        def expected(l, c, d):
            want = {c - 1} if d < 25 else {c - 1, c}
            inside = {m for m in want if m >= ms[0]}
            if not inside:  # last return month lies in the previous year's file
                return pd.isna(l)
            return (not pd.isna(l)) and l in inside
        hit = pd.Series([expected(l, c, d) for l, c, d in zip(last, cd.dt.to_period("M"), cd.dt.day)],
                        index=cd.index, dtype=bool)
        per_month = hit.groupby(cd.dt.to_period("M")).agg(["mean", "size"])
        worst = per_month[per_month["size"] >= 5]["mean"].min() if (per_month["size"] >= 5).any() else float("nan")
        match = float(hit.mean()) if len(hit) else float("nan")
        label_ok = len(hit) == 0 or (match >= 0.75 and (np.isnan(worst) or worst >= 0.5))
        good = same_rows and gap <= 2.0 and label_ok
        ok_all &= good
        print(f"{y}: {'ok ' if good else 'FAIL'} months {ms[0]}..{ms[-1]} median gap to market {gap:.2f}pp "
              f"| completions {len(hit)} matched {match:.2f} (worst month {worst:.2f}) | non-missing {R.notna().mean().mean():.2f}"
              + (f" | {'; '.join(msg)}" if msg else ""))
        long = R.assign(entity_id=df["Entity ID"], symbol=df["Symbol"], fds_ticker=df["FDS Ticker Symbol"]) \
            .melt(id_vars=["entity_id", "symbol", "fds_ticker"], var_name="month", value_name="ret_pct")
        frames.append(long.dropna(subset=["ret_pct"]))
    if a.check or not frames:
        sys.exit(0 if ok_all else 1)
    if not ok_all:
        sys.exit("checks failed: nothing written")
    out = pd.concat(frames, ignore_index=True)
    out["ret"] = out.pop("ret_pct") / 100.0
    out.to_pickle(PROC / "returns_monthly.pkl")
    print(f"wrote {len(out):,} security-months, {out.month.nunique()} months -> data/processed/returns_monthly.pkl")


if __name__ == "__main__":
    main()
