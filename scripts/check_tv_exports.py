"""Check FactSet cash-flow exports (data/raw/factset_tv_YYYY.xlsx) before use.

    python3 scripts/check_tv_exports.py

For each file, against the matching ValuationLab export (same YYYY; raw or holdout folder):
  - Fiscal Period End Date, Net Sales and Capital Expend CF must match on Entity ID
    (proves the date / RP / USD settings reproduce the old pull)
  - year-ends should centre on YYYY-1
Across files: any value column identical between two files means a formula's date was not
changed (look-ahead), as happened in the first ValuationLab exports.
See docs/factset_export.md for the formulas.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VL = Path(os.environ.get("VALUATION_LAB", ROOT.parent / "valuation-lab"))
NA = ["#N/A", "@NA", "NA", "-", ""]
KEY = "Entity ID"
STATIC = {"Symbol", "Name", KEY, "SIC Code", "Fiscal Period End Date"}
MATCH = ["Fiscal Period End Date", "Net Sales", "Capital Expend CF"]
WATCH = ["AAPL", "MSFT", "KO", "WMT"]
EXPECTED = ["Symbol", "Entity ID", "Fiscal Period End Date", "Net Sales", "Capital Expend CF",
            "Net Cash Flow -Oper", "Int on Debt Expense", "Total Income Taxes", "Pretax Income",
            "Deprec Deplete & Amort Exp-CF", "Total Current Assets", "Total Current Liabs",
            "Stock Option Cash Flow"]


def load(path: Path) -> pd.DataFrame:
    probe = pd.read_excel(path, header=None, nrows=30)
    header = next(i for i, v in enumerate(probe.iloc[:, 0].astype(str)) if v.strip() == "Symbol")
    df = pd.read_excel(path, header=header, na_values=NA).dropna(how="all")
    # An entity can appear on several security rows, some empty: keep the fullest row.
    return (df.assign(_n=df.notna().sum(axis=1)).sort_values("_n", ascending=False)
              .drop_duplicates(KEY).drop(columns="_n"))


def old_file(year: int) -> Path | None:
    for d in ("data/raw", "data/holdout"):
        p = VL / d / f"factset_{year}.xlsx"
        if p.exists():
            return p
    return None


def main() -> int:
    files = sorted((ROOT / "data/raw").glob("factset_tv_*.xlsx"))
    files = [f for f in files if not f.name.startswith("~$")]
    problems, frames = [], {}
    for f in files:
        year = int(re.search(r"(\d{4})", f.stem).group(1))
        df = frames[year] = load(f)
        missing = [c for c in EXPECTED if c not in df.columns]
        if missing:
            problems.append(f"{f.name}: missing columns {missing}")
            print(f"\n{f.name}: MISSING COLUMNS {missing}; skipped")
            continue
        fye = pd.to_datetime(df["Fiscal Period End Date"], format="%m/%d/%Y", errors="coerce")
        mode = int(fye.dt.year.mode().iloc[0])
        print(f"\n{f.name}: expect FY{year - 1}; most common year-end {mode}; latest year-end {fye.max().date()}")
        if mode != year - 1:
            problems.append(f"{f.name}: year-ends centre on {mode}, expected {year - 1}")
        if fye.max() > pd.Timestamp(f"{year}-06-15"):
            problems.append(f"{f.name}: year-end after June 15 {year} (date not changed?)")
        for s in WATCH:
            r = df[df["Symbol"] == s]
            if len(r):
                r = r.iloc[0]
                print(f"  {s:5s} FYE {r['Fiscal Period End Date']}  sales {r['Net Sales']:>9,.0f}  "
                      f"CFO {r['Net Cash Flow -Oper']:>8,.0f}  capex {r['Capital Expend CF']:>7,.0f}")

        ref = old_file(year)
        if ref is None:
            print("  (no ValuationLab file to compare)")
            continue
        m = load(ref).merge(df, on=KEY, suffixes=("_o", "_n"))
        m = m[m["Net Sales_o"].notna()]
        for c in MATCH:
            a, b = m[c + "_o"], m[c + "_n"]
            ok = a.notna() & b.notna()
            eq = (a[ok] == b[ok]) if c.startswith("Fiscal") else pd.Series(
                np.isclose(a[ok].astype(float), b[ok].astype(float), rtol=0.005))
            lost = int((a.notna() & b.isna()).sum())
            print(f"  vs {ref.name}: {c:24s} {ok.sum():>6,} pairs  match {eq.mean():7.2%}  missing in new {lost}")
            if eq.mean() < 0.995 or lost > 0.01 * ok.sum():
                problems.append(f"{f.name}: '{c}' matches old file only {eq.mean():.2%} (missing {lost})")
        new_cols = [c for c in df.columns if c not in STATIC and c not in MATCH]
        cov = ", ".join(f"{c.split()[0]} {m[c].notna().mean():.0%}" for c in new_cols)
        print(f"  coverage on old-file firms: {cov}")
        for c in new_cols:
            if m[c].notna().mean() < 0.5:
                problems.append(f"{f.name}: '{c}' is mostly empty ({m[c].notna().mean():.0%}); "
                                "exported before FactSet finished calculating?")

    frames = {y: d for y, d in frames.items() if all(c in d.columns for c in EXPECTED)}
    years = sorted(frames)
    for i, a in enumerate(years):
        for b in years[i + 1:]:
            for c in frames[a].columns:
                if c in STATIC or c not in frames[b].columns:
                    continue
                m = frames[a][[KEY, c]].merge(frames[b][[KEY, c]], on=KEY).dropna()
                m = m[m[c + "_x"] != 0]
                if len(m) >= 50 and (m[c + "_x"] == m[c + "_y"]).mean() > 0.5:
                    problems.append(f"'{c}' identical in {a} and {b}: its date was not changed")

    print("\n" + ("\n".join("PROBLEM: " + p for p in problems) if problems
                  else f"All {len(files)} files OK."))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
