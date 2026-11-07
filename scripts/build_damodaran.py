"""Build tidy discount-rate reference tables from Damodaran + FRED raw files.

Inputs  (data/raw/damodaran/, data/raw/fred_dgs10.csv; see docs/damodaran_data.md)
Outputs (data/processed/):
  betas_by_vintage.csv   one row per (vintage_t, industry); vintage_t = fiscal year t whose
                         valuation date (June 30 of t+1) first sees this January release
  erp_monthly.csv        Damodaran start-of-month implied ERP (2008-09 onward)
  erp_annual.csv         Damodaran start-of-year implied ERP (histimpl), keyed the same way
  spreads_by_year.csv    default spread by rating, keyed by Damodaran label year (= January release)
  coverage_rating.csv    interest-coverage -> rating thresholds (large / small firms)
  rf_dgs10.csv           daily 10-year Treasury yield (decimal)
  firm_industry.csv      panel firm id -> Damodaran industry, with mapping source

Point-in-time rule: for fiscal year t the valuation date is June 30 of t+1, so use the
Damodaran release of January t+1 (file betas{t}.xls, ERP row "t" / month June t+1,
spread label t+1). No release dated after the valuation date is ever used.

Run from anywhere:  python3 -P terminal-value-lab/scripts/build_damodaran.py
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "damodaran"
OUT = ROOT / "data" / "processed"
PANEL = ROOT.parent / "valuation-lab" / "data" / "cache" / "panel_with_holdout.pkl"

NAME_FIX = {"Publshing & Newspapers": "Publishing & Newspapers"}


def norm(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


def industry_table(path: Path) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Return the industry table and its 'Date updated' from a Damodaran industry file."""
    for _, d in pd.read_excel(path, sheet_name=None, header=None).items():
        col0 = d[0].map(norm)
        hdr = d.index[col0.str.lower().eq("industry name")]
        if not len(hdr):
            continue
        date = pd.Timestamp(d.loc[col0.eq("Date updated:"), 1].iloc[0])
        t = d.iloc[hdr[0] + 1:].copy()
        t.columns = [norm(c) for c in d.iloc[hdr[0]]]
        t["Industry Name"] = t["Industry Name"].map(norm).replace(NAME_FIX)
        return t[t["Industry Name"].ne("nan")].reset_index(drop=True), date
    raise ValueError(f"no industry table in {path.name}")


def build_betas() -> pd.DataFrame:
    rows = []
    files = {t: RAW / f"betas{t % 100:02d}.xls" for t in range(2015, 2025)}
    files[2025] = RAW / "betas.xls"  # current release (January 2026)
    for t, f in files.items():
        tab, date = industry_table(f)
        assert date.year == t + 1 and date.month == 1, (f.name, date)
        tax = "Effective Tax rate" if "Effective Tax rate" in tab else "Tax rate"
        rows.append(pd.DataFrame({
            "vintage_t": t,
            "release_date": date.date(),
            "industry": tab["Industry Name"],
            "n_firms": pd.to_numeric(tab["Number of firms"], errors="coerce"),
            "beta": pd.to_numeric(tab["Beta"], errors="coerce"),
            "de_ratio": pd.to_numeric(tab["D/E Ratio"], errors="coerce"),
            "tax_rate": pd.to_numeric(tab[tax], errors="coerce"),
            "unlevered_beta": pd.to_numeric(tab["Unlevered beta"], errors="coerce"),
            "unlevered_beta_cash_adj": pd.to_numeric(tab["Unlevered beta corrected for cash"], errors="coerce"),
            "cash_firm_value": pd.to_numeric(tab["Cash/Firm value"], errors="coerce"),
        }))
    return pd.concat(rows, ignore_index=True)


def build_multiples() -> pd.DataFrame:
    """US industry EV/EBITDA (aggregate: sum EV / sum EBITDA) by release. Files vebitda13..24
    + current; the industry taxonomy is the current one from the Jan-2014 release on.
    Releases from Jan 2018 have two blocks: 'Only positive EBITDA firms' then 'All firms'."""
    rows = []
    files = {t: RAW / f"vebitda{t % 100:02d}.xls" for t in range(2013, 2025)}
    files[2025] = RAW / "vebitda.xls"
    for t, f in files.items():
        for _, d in pd.read_excel(f, sheet_name=None, header=None).items():
            col0 = d[0].map(norm)
            hdr = d.index[col0.str.lower().isin(["industry name", "industry"])]
            if not len(hdr):
                continue
            h = hdr[0]
            heads = [norm(c) for c in d.iloc[h]]
            idx = [i for i, c in enumerate(heads) if c == "EV/EBITDA" or c.startswith("EV/EBITDA") and c[-1].isdigit() and "R&D" not in c]
            block_row = [norm(c) for c in d.iloc[h - 1]] if h > 0 else []
            t_ = d.iloc[h + 1:]
            names = t_[0].map(norm).replace(NAME_FIX)
            out = pd.DataFrame({"vintage_t": t, "industry": names,
                                "n_firms": pd.to_numeric(t_[1], errors="coerce"),
                                "ev_ebitda_a": pd.to_numeric(t_[idx[0]], errors="coerce")})
            out["ev_ebitda_b"] = pd.to_numeric(t_[idx[1]], errors="coerce") if len(idx) > 1 else np.nan
            out["block_a"] = "positive_only" if any("positive" in b.lower() for b in block_row) else "single"
            rows.append(out[out.industry.ne("nan")])
            break
    m = pd.concat(rows, ignore_index=True)
    # 'all firms' multiple: second block when two blocks exist, else the single block
    m["ev_ebitda_all"] = np.where(m["ev_ebitda_b"].notna(), m["ev_ebitda_b"], m["ev_ebitda_a"])
    m["ev_ebitda_pos"] = np.where(m["block_a"].eq("positive_only"), m["ev_ebitda_a"], np.nan)
    return m[["vintage_t", "industry", "n_firms", "ev_ebitda_all", "ev_ebitda_pos", "block_a"]]


def build_erp() -> tuple[pd.DataFrame, pd.DataFrame]:
    m = pd.read_excel(RAW / "ERPbymonth.xlsx", sheet_name=0)
    m = m.rename(columns=lambda c: norm(c))

    def pct(s: pd.Series) -> pd.Series:  # a few cells are text like "4.06%"
        txt = s.astype(str).str.strip()
        is_pct = txt.str.endswith("%")
        out = pd.to_numeric(s, errors="coerce")
        out[is_pct] = pd.to_numeric(txt[is_pct].str.rstrip("%"), errors="coerce") / 100
        return out

    for c in ["T.Bond Rate", "ERP (T12m)", "ERP (T12 m with sustainable payout)", "ERP (Normalized)"]:
        m[c] = pct(m[c])
    monthly = pd.DataFrame({
        "month_start": pd.to_datetime(m["Start of month"], errors="coerce"),
        "tbond": m["T.Bond Rate"],
        "erp_t12m": m["ERP (T12m)"],
        "erp_t12m_sustainable": m["ERP (T12 m with sustainable payout)"],
        "erp_normalized": m["ERP (Normalized)"],
    }).dropna(subset=["month_start"])
    a = pd.read_excel(RAW / "histimpl.xls", sheet_name=0, header=None)
    hdr = a.index[a[0].map(norm).eq("Year")][0]
    a.columns = [norm(c) for c in a.iloc[hdr]]
    a = a.iloc[hdr + 1:]
    a = a[pd.to_numeric(a["Year"], errors="coerce").notna()]
    annual = pd.DataFrame({
        # row "Year = Y" is the premium at the end of Y, published January Y+1
        "year_end": a["Year"].astype(int),
        "tbond": pd.to_numeric(a["T.Bond Rate"], errors="coerce"),
        "erp_fcfe": pd.to_numeric(a["Implied ERP (FCFE)"], errors="coerce"),
        "erp_ddm": pd.to_numeric(a["Implied Premium (DDM)"], errors="coerce"),
    })
    return monthly, annual


def build_spreads() -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.read_excel(RAW / "bondspreads24.xlsx", sheet_name=0, header=None)
    hdr = d.index[d[0].map(norm).eq("Rating is")][0]
    t = d.iloc[hdr + 1:].copy()
    t.columns = [norm(c) for c in d.iloc[hdr]]
    t = t[t["Rating is"].notna() & t["Rating is"].astype(str).str.contains("/")]
    long = t.melt(id_vars="Rating is", var_name="label", value_name="spread")
    long["year"] = long["label"].str.extract(r"(\d{4})").astype(int)
    long = long.rename(columns={"Rating is": "rating"})[["year", "rating", "spread"]]

    # ratings.xls layout: "For large non-financial service firms" (cols 0-3 under the ">" header)
    # sits next to "For financial service firms" (cols 5-8; NOT used). The small/riskier
    # non-financial table is a separate block further down, introduced by "For smaller and
    # riskier ...". (A first version wrongly read cols 5-8 as the small-firm table; caught in
    # code review 2026-11-07.)
    r = pd.read_excel(RAW / "ratings.xls", sheet_name=0, header=None)
    col0 = r[0].astype(str).str.strip()
    hdr = r.index[col0.eq(">")][0]
    assert "large non-financial" in str(r.iloc[hdr - 2, 0]).lower(), r.iloc[hdr - 2, 0]
    assert "financial service" in str(r.iloc[hdr - 2, 5]).lower()
    blk = r.iloc[hdr + 1: hdr + 16]
    small_title = r.index[col0.str.lower().str.startswith("for smaller and riskier")][0]
    sblk = r.iloc[small_title + 3: small_title + 18]
    cov = pd.concat([
        pd.DataFrame({"firm_size": "large", "cov_gt": blk[0], "cov_le": blk[1], "rating": blk[2]}),
        pd.DataFrame({"firm_size": "small", "cov_gt": sblk[0], "cov_le": sblk[1], "rating": sblk[2]}),
    ]).dropna()
    cov["cov_gt"] = pd.to_numeric(cov["cov_gt"]); cov["cov_le"] = pd.to_numeric(cov["cov_le"])
    aaa = cov[cov.rating.eq("Aaa/AAA")].set_index("firm_size").cov_gt
    assert aaa["large"] == 8.5 and aaa["small"] == 12.5, aaa.to_dict()
    assert len(cov) == 30, len(cov)
    cur = pd.DataFrame({"year": 2026, "rating": blk[2].values, "spread": blk[3].values})
    long = pd.concat([long, cur], ignore_index=True)
    long["spread"] = pd.to_numeric(long["spread"])
    return long.sort_values(["year", "spread"]).reset_index(drop=True), cov


def build_rf() -> pd.DataFrame:
    rf = pd.read_csv(RAW.parent / "fred_dgs10.csv")
    rf.columns = ["date", "dgs10"]
    rf["date"] = pd.to_datetime(rf["date"])
    rf["dgs10"] = pd.to_numeric(rf["dgs10"], errors="coerce") / 100
    return rf.dropna()


def build_firm_industry(valid: set[str]) -> pd.DataFrame:
    """Direct ticker match (name-checked) first; else FactSet SIC4 -> SIC3 -> SIC2 majority
    industry among the directly matched firms (built in our own SIC space, because
    Capital IQ SIC codes in indname agree with FactSet SIC4 only ~35% of the time)."""
    import difflib

    ind = pd.read_excel(RAW / "indname.xls", sheet_name="By industry")
    us = ind[ind["Country"].eq("United States")
             & ind["Exchange:Ticker"].str.match(r"^(NYSE|Nasdaq|NYSEAM|BATS|ARCA)")].copy()
    us["tk"] = us["Exchange:Ticker"].str.split(":").str[-1]
    us = us.drop_duplicates("tk")

    p = pd.read_pickle(PANEL)
    firms = p.sort_values("fiscal_year").drop_duplicates("id", keep="last")[
        ["id", "ticker", "name", "sic4", "sic3", "sic2"]]
    m = firms.merge(us[["tk", "Company Name", "Industry Group"]], left_on="ticker", right_on="tk", how="left")

    def clean(s):
        s = re.sub(r"\(.*?\)", " ", str(s).lower())
        s = re.sub(r"\b(inc|corp|corporation|co|company|ltd|plc|holdings?|group|the|class [a-z])\b", " ", s)
        return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())

    m["name_sim"] = [difflib.SequenceMatcher(None, clean(a), clean(b)).ratio() if isinstance(b, str) else np.nan
                     for a, b in zip(m["name"], m["Company Name"])]
    ok = m["name_sim"] >= 0.6
    m["industry"] = np.where(ok, m["Industry Group"], None)
    m["source"] = np.where(ok, "ticker", None)

    train = m[ok].copy()
    for lev in ("sic4", "sic3", "sic2"):
        maj = train.groupby(lev)["industry"].agg(lambda s: s.value_counts().index[0])
        fill = m["industry"].isna() & m[lev].isin(maj.index)
        m.loc[fill, "industry"] = m.loc[fill, lev].map(maj)
        m.loc[fill, "source"] = lev
    rest = m["industry"].isna()
    m.loc[rest, "industry"] = "Total Market (without financials)"
    m.loc[rest, "source"] = "market"
    unknown = set(m["industry"]) - valid
    assert not unknown, unknown
    return m[["id", "ticker", "name", "sic4", "industry", "source", "name_sim"]]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    betas = build_betas()
    monthly, annual = build_erp()
    spreads, cov = build_spreads()
    rf = build_rf()
    # Industries valid in every vintage our firms can hit. "Retail (Online)" was folded into
    # other retail groups from the Jan-2024 release on; indname (current) never assigns it.
    valid = set(betas.loc[betas.vintage_t == 2025, "industry"])
    firm_ind = build_firm_industry(valid)

    mult = build_multiples()
    mult.to_csv(OUT / "multiples_by_vintage.csv", index=False)
    print("EV/EBITDA medians by vintage (all / positive-only):",
          mult.groupby("vintage_t")[["ev_ebitda_all", "ev_ebitda_pos"]].median().round(1).to_dict("index"))
    betas.to_csv(OUT / "betas_by_vintage.csv", index=False)
    monthly.to_csv(OUT / "erp_monthly.csv", index=False)
    annual.to_csv(OUT / "erp_annual.csv", index=False)
    spreads.to_csv(OUT / "spreads_by_year.csv", index=False)
    cov.to_csv(OUT / "coverage_rating.csv", index=False)
    rf.to_csv(OUT / "rf_dgs10.csv", index=False)
    firm_ind.to_csv(OUT / "firm_industry.csv", index=False)

    # ---- summary -------------------------------------------------------------------
    p = pd.read_pickle(PANEL)[["id", "fiscal_year"]].merge(firm_ind[["id", "source", "industry"]], on="id")
    print("betas:", betas.groupby("vintage_t").size().to_dict())
    print("vintages missing a firm industry:",
          {t: sorted(set(firm_ind.industry) - set(g.industry)) for t, g in betas.groupby("vintage_t")
           if set(firm_ind.industry) - set(g.industry)})
    print("industry source (panel rows):", p["source"].value_counts(normalize=True).round(3).to_dict())
    june = monthly[monthly.month_start.dt.month.eq(6)]
    june = june.set_index(june.month_start.dt.year)
    rf_j = rf[rf.date.dt.month.eq(6)].groupby(rf.date.dt.year).last()
    print("\nvaluation-date inputs by fiscal year t (June of t+1):")
    print(f"{'t':>5} {'DGS10':>7} {'ERP_m':>7} {'ERP_a':>7} {'BBB':>7} {'mkt_beta_u':>10}")
    for t in range(2015, 2026):
        y = t + 1
        bbb = spreads.query("year == @y and rating == 'Baa2/BBB'")["spread"]
        # Jan-2016 release has only "Total Market" (incl. financials); later ones have both
        mb = betas.query("vintage_t == @t and industry in ['Total Market (without financials)', 'Total Market']")
        mb = mb.sort_values("industry", ascending=False)
        mb = mb["unlevered_beta_cash_adj"].iloc[0] if len(mb) else np.nan
        print(f"{t:>5} {rf_j.dgs10.get(y, np.nan):7.4f} {june.erp_t12m.get(y, np.nan):7.4f} "
              f"{annual.set_index('year_end').erp_fcfe.get(t, np.nan):7.4f} "
              f"{bbb.iloc[0] if len(bbb) else np.nan:7.4f} {mb:10.3f}")


if __name__ == "__main__":
    main()
