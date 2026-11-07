# Terminal Value Lab: pre-registration protocol (DRAFT, 2026-11-07)

Status: **draft, not frozen.** It is frozen by a tagged commit pushed to
github.com/joonha9/terminal-value-lab before any validation or test window is graded.
Everything in "Exploration findings" was seen before writing this. Hypotheses that come from
exploration are labelled as such and are tested only on validation and test data.

## 1. Questions

- **Q1.** Which terminal-value formula best matches the **market** enterprise value five years
  later, overall and by firm type?
- **Q2.** Which formula best matches **acquisition** prices, the price at which control changes
  hands? Do the answers to Q1 and Q2 differ?
- **Q3.** Can AI agents write interpretable conditional TV rules that beat the best single
  formula and random search with the same budget? What share of a GBM's gain do they capture?
- **Q4 (proposed, separate pre-registration).** Does the gap between Gordon value and market
  value predict future stock returns beyond known factors? Needs monthly returns; decided
  before freezing whether it joins v1 or becomes a separate later pre-registration.

## 2. Data and sample (fixed)

- ValuationLab FactSet panel, FY2015–2025, US-listed non-financials. Universe at t: market
  cap ≥ $100M at June 30 of t+1, and `quality_ok` (total assets ≥ $10M and market cap / assets
  ≤ 100). See `docs/panel.md`.
- Cash-flow fields from FactSet (`docs/factset_export.md`); discount-rate inputs from Damodaran
  and FRED, point-in-time (`docs/damodaran_data.md`); exits and deal prices from FactSet M&A
  (`docs/exits.md`).
- Windows: horizon 5 (main), horizon 3 (robustness).

| Split | Start t | Use |
|---|---|---|
| Exploration | 2015–16 | already used (Phase 1) |
| Validation | 2017–18 | finalist selection; opened once |
| Test | 2019–20 | final; opened once. FY2024–25 outcomes were seen in earlier labs (disclosed) |

## 3. Truths and grading

| Truth | Windows | Fundamentals | Value compared |
|---|---|---|---|
| **M** (main) | survived or shrank by t+5, `quality_ok` at t+5, EV > 0 | year t+5, realized | market EV, June 30 of t+6 |
| **D** | acquired, completion after t's valuation date and by t+5's; last pre-deal year L with t < L < t+5 | year L, realized | deal EV = deal equity + net claims at L |
| **D′** | same firms as D, deal announced after June 30 of L+1 | year L | market EV, June 30 of L+1 (pre-announcement) |

Multiples, growth and discount rates always use information at t only.
Inactive exits (no price, ~15% of exits) are not graded. Their count and characteristics are
reported by method-definedness. Firms still listed but out of the panel are excluded and reported.

**Error:** e = ln(predicted / truth).
**Metrics:**
1. Median |e| on the common sample (all compared methods defined). Primary.
2. Median e (bias).
3. Intention-to-treat hit rate: share of all graded windows with |e| < ln 1.25, where an
   undefined method counts as a miss.

## 4. Methods (fixed before validation)

- **Gordon:** FCF_t+H (or 3-year average) × (1+g)/(r−g); g ∈ {2, 2.5, 3%}; r = Damodaran WACC_t
  (main) or 10-yr Treasury + 5% (robustness). Undefined if FCF ≤ 0 or r − g < 1 pp.
  Also FCF ex-SBC and value-driver variants.
- **Exit:** EV/EBITDA × EBITDA_t+H. Multiples: FF12 median at t, Damodaran-industry median
  (our panel) at t, the firm's own multiple at t, Damodaran aggregate at t, Damodaran 5-year
  average.
- **Blends:** 50/50 in levels and in logs (Gordon g 2.5% + FF12 exit).
- References only: actual industry multiple at t+H (look-ahead); EV_t (no change).
- Code: `tvlab/methods.py` at the frozen commit.

## 5. Hypotheses

Labels: **[pre]** stated before exploration; **[expl]** formed from exploration, tested here first.

- **H1 [expl]** (original H1 was "Gordon undervalues"; exploration showed the opposite). Against
  truth M, Gordon (g 2.5%, WACC) has positive median bias.
- **H2 [expl]** (replaces the original H2, which exploration reversed). Gordon's error relative to
  the FF12 exit rises as r − g falls. Test: |e_G| − |e_E| by tercile of (WACC_t − g); the
  low-spread tercile is worse than the high-spread one.
- **H3 [pre]** In cyclical industries (FF12 Enrgy, Chems, Manuf, Durbl; fixed list), the
  Damodaran 5-year average multiple beats the Damodaran multiple at t.
- **H4 [pre, expected null after exploration]** A fixed 50/50 blend beats the best pure method.
- **H5 [pre]** Agent rules beat (a) the best single method chosen on exploration + validation and
  (b) random search with the same budget.
- **H6 [expl]** Against truth D, Gordon's bias is smaller in absolute value than against D′, on the
  same firms.
- **H7 [expl]** The firm's own multiple ranks higher against D′ than against D.

## 6. Pre-registered tests (validation, then test)

| Test | Statistic | Truth |
|---|---|---|
| T1 | median abs e: Gordon g2.5 − FF12 exit | M |
| T2 | median e of Gordon g2.5 > 0 | M |
| T3 | low- minus high-spread tercile of (abs e_G − abs e_E) | M |
| T4 | Damodaran 5-yr − Damodaran at t, cyclical FF12 | M |
| T5 | 50/50 log blend − best of {Gordon g2.5, FF12 exit} | M |
| T6 | abs bias of Gordon: D minus D′ | D, D′ |
| T7 | rank of own multiple: D′ vs D | D, D′ |
| T8 | best agent rule − best single method; − best random rule | M |

Inference: firm-clustered bootstrap (2,000 reps) for differences in medians, with 95% CIs.
Holm correction across T1–T8 at 5%. Report every test whatever the result.

## 7. Agents (Q3)

- Recipe DSL: JSON. Conditions (≤ 3 levels) on firm traits at t: FF12, size, growth, margins,
  ROIC, leverage, FCF and EBITDA sign, WACC − g. Each leaf is a method + parameters or a blend weight.
  Deterministic validator.
- Loop: proposer (mechanism + falsifiable prediction) → blind critic → deterministic grader on
  exploration windows → archive. Claude Code subagents only. 5 runs × 30 proposals.
- Benchmarks: best single method, random search (same budget), and a GBM ceiling. The GBM
  predicts ln(truth / FF12 exit) from the same traits; we report the share of its gain captured.
- Finalists: the top 3 per run on exploration, chosen once on validation. The single chosen rule
  is evaluated on test.
- Leakage control: recipes see traits only, never names or dates.

## 8. Robustness (reported, not hypothesis tests)

Horizon 3; Treasury + 5% discount rate; annual ERP instead of monthly; without the quality
screen; survivors only versus survivors + shrank; FCF ex-SBC; truth D restricted to cash deals
and to PE buyers.

## 9. Exploration findings already known (disclosure)

See `docs/phase1_exploration.md`. On t = 2015–16:
- FF12 exit beats Gordon by 0.16 in median |e| (truth M).
- Gordon bias is +0.25 against M, about 0 against D, and +0.41 against D′.
- The own multiple is best against M and D′, not against D.
- Energy supports H3.
- A fixed blend does not help.

## 10. Limitations (stated in advance)

- The sample is post-2015 and mostly low-rate. Pre-2015 history was not collected (decided
  2026-11-07).
- Perfect foresight on outcome-year fundamentals isolates formula error, not forecasting error.
- Market truth is partly circular: markets themselves use multiples. Truth D and Q4 address this.
- Targets may be selected for undervaluation (truth D).
- Damodaran industry classification is a 2026 snapshot applied to all years.
- About 5% of FactSet market caps are unreliable (screened).
- FY2024–25 outcomes were seen before (earlier labs).
- LLM agents may know 2020–25 market history.

## 11. Before freezing

- [ ] Decide: Q4 in v1 or later; truth D co-primary with M or secondary.
- [ ] Literature check: Courteau, Kao & Richardson (2001); Kaplan & Ruback (1995); others.
  Make sure Q1/Q2 are positioned against them. Citations are unverified until read.
- [ ] User approval of this file → tag `protocol-v1` → push.
