#!/usr/bin/env bash
# Re-download the free discount-rate inputs (Damodaran + FRED) into data/raw/.
# Original download: 2026-11-07. Damodaran replaces the "current" files (betas.xls, wacc.xls,
# ratings.xls, indname.xls, ERPbymonth.xlsx, histimpl.xls) every January (ERP monthly), so a
# later download gives newer releases; build_damodaran.py asserts the vintages it relies on.
set -euo pipefail
cd "$(dirname "$0")/.."
D=data/raw/damodaran
B=https://pages.stern.nyu.edu/~adamodar/pc
mkdir -p "$D"

get() { curl -fsS -L -o "$1" "$2" && echo "ok  $1"; }

for f in histimpl.xls betas.xls ratings.xls indname.xls wacc.xls; do get "$D/$f" "$B/datasets/$f"; done
get "$D/ERPbymonth.xlsx" "$B/implprem/ERPbymonth.xlsx"
for y in 15 16 17 18 19 20 21 22 23 24; do
  get "$D/betas$y.xls" "$B/archives/betas$y.xls"   # betasYY = January YY+1 release
  get "$D/wacc$y.xls"  "$B/archives/wacc$y.xls"
done
get "$D/bondspreads24.xlsx" "$B/archives/bondspreads24.xlsx"  # spread labels 2015-2025
get "$D/ratings21.xls" "$B/archives/ratings21.xls"            # coverage-table check
get "$D/ratings24.xls" "$B/archives/ratings24.xls"
get data/raw/fred_dgs10.csv "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
