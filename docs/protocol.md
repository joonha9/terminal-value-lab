# Terminal Value Lab: pre-registration protocol (v1.1, 2026-11-07)

Status: **v1.1, frozen 2026-11-07, before any agent run and before any validation or test
window was graded.**
- v1 (tag `protocol-v1`, pushed 2026-11-07) stays as the reference.
- v1.1 is tagged `protocol-v1.1`.
- Any later change is a new version with a dated changelog entry explaining why.
- Text added or changed in v1.1 is marked **[v1.1]**.

## Changelog

**v1.1 (2026-11-07).** Amendment made after independent code and design reviews of the
Phase 3 setup (`docs/errors_and_fixes.md` §I). It was made before any agent run and before
validation or test was opened. Approved by the author on 2026-11-07.

1. **New benchmark and test T8c.**
   - **Why:** on exploration, one recipe without any split scores 0.368 in median |e|:
     0.8 × own-multiple exit + 0.2 × Gordon (3-yr FCF, g 4%, Treasury + 5%). That beats the best
     single method (0.415), the best of 1,000 random recipes (0.379) and the traits-only GBM
     (0.406). Under v1, T8 could therefore be passed by tuning blend weights alone, with no
     conditional rule.
   - **Change:** the "best recipe without a split" becomes a benchmark (§7), and agent − it is
     a new test, T8c, inside the Holm family (§6).
2. **Grading convention for recipes** (§3, §7).
   - v1's "common sample" is not defined for recipes that mix methods by firm.
   - **Change:** recipes and their benchmarks are scored on one fixed evaluation set, the
     windows where the FF12 exit is defined. Any undefined leaf falls back to the FF12 exit.
3. **Inference details** (§6), which v1 did not specify:
   - one-sided bootstrap p-values;
   - the family, now m = 14;
   - Holm decisions on test, with validation as replication;
   - the H5 decision rule.
4. **Agent isolation** (§7): proposers and critics run without tools.
5. **Erratum:** H8 quoted Gordon's pre-fix error against truth D (0.716). The revised
   exploration value is 0.646.

Implementation details are in `docs/phase3_design.md`, frozen with this version.
Everything in "Exploration findings" was seen before writing this. Hypotheses that come from
exploration are labelled as such and are tested only on validation and test data.

## 1. Questions

- **Q1.** Which terminal-value formula best matches the **market** enterprise value five years
  later, overall and by firm type?
- **Q2.** Which formula best matches **acquisition** prices, the price at which control changes
  hands? Do the answers to Q1 and Q2 differ?
- **Q3.** Can AI agents write interpretable conditional TV rules that beat the best single
  formula and random search with the same budget? What share of a GBM's gain do they capture?
- **Q4 (not in v1; decided 2026-11-07).** Does the gap between Gordon value and market value
  predict future stock returns beyond known factors? It needs monthly returns. It will be a
  separate pre-registration after the v1 results.

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

**M and D are co-primary** (decided 2026-11-07). D′ is used only for the paired D-versus-D′
comparison (T7).

Windows per split (counts only, before method-definedness):

| Split | M | D | D′ |
|---|---|---|---|
| Exploration | 3,948 | 815 | 498 |
| Validation | 4,063 | 742 | 453 |
| Test | 4,345 | 810 | 483 |

In exploration about 42% of D′ windows had every core method defined. T7 therefore
rest on about 200 firms per split.

| Truth | Windows | Fundamentals | Value compared |
|---|---|---|---|
| **M** (co-primary) | survived or shrank by t+5, `quality_ok` at t+5, EV > 0 | year t+5, realized | market EV, June 30 of t+6 |
| **D** (co-primary) | acquired, completion after t's valuation date and by t+5's; last pre-deal year L with t < L < t+5 | year L, realized | deal EV = deal equity + net claims at L |
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
- References only (look-ahead, never candidates): actual industry multiple at t+H; Gordon with
  WACC at t+H, which separates formula error from the change in rates; EV_t (no change).
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
  - **[v1.1] Decision rule:** H5 is supported if T8a and T8b both reject after Holm.
  - **[v1.1]** A *conditional* gain is claimed only if T8c also rejects.
  - **[v1.1]** If the chosen agent recipe has no split, it is reported as "no conditional gain"
    whatever T8a and T8b show.
- ~~H6~~ dropped (2026-11-07). "Gordon's bias is smaller against D than D′" is mechanical:
  for every method, bias against D = bias against D′ − deal premium.
- **H7 [expl, weak]** The firm's own multiple ranks higher against D′ than against D. After the
  deal-EV correction, exploration support is weak (1st vs 2nd, 0.366 vs 0.362).
- **H8 [expl]** Against truth D, the FF12 exit beats Gordon (T1D). Exploration: 0.436 vs 0.646
  **[v1.1 erratum:** v1 said 0.716, the value before the rating-table fix**]**.

## 6. Pre-registered tests (validation, then test)

| Test | Statistic | Truth |
|---|---|---|
| T1 | median abs e: Gordon g2.5 − FF12 exit | M |
| T2 | median e of Gordon g2.5 > 0 | M |
| T3 | low- minus high-spread tercile of (abs e_G − abs e_E) | M |
| T4 | Damodaran 5-yr − Damodaran at t, cyclical FF12 | M |
| T5 | 50/50 log blend − best of {Gordon g2.5, FF12 exit} | M |
| ~~T6~~ | dropped (mechanical, see H6) | |
| T7 | median abs e: own multiple − Damodaran-industry median, D′ minus D (rank change) | D, D′ |
| T8a | chosen agent rule − best single method | M |
| T8b | chosen agent rule − chosen random rule | M |
| **T8c [v1.1]** | chosen agent rule − chosen best recipe without a split | M |

Inference: firm-clustered bootstrap (2,000 reps) for differences in medians, with 95% CIs.
Holm correction at 5%. T1–T5 are also run on truth D (labelled T1D–T5D) and enter the same
Holm family. Report every test whatever the result.

**[v1.1] Details:**
- **p-values:** every hypothesis is directional, so p is one-sided: the share of the 2,000
  bootstrap statistics on the wrong side of 0, floored at 1/2,000. Bootstrap seed 0.
- **Family:** T1–T5, T1D–T5D, T7, T8a, T8b, T8c, so **m = 14**.
- **Split:** Holm decisions are made on **test**. T8 exists only on test, because finalists are
  chosen on validation. Validation results for T1–T7 are reported in full as a replication
  step, without Holm.
- **Recipe metric:** T8a–c use median |e| on the test evaluation set under the recipe grading
  convention (§7).

## 7. Agents (Q3)

- Recipe DSL: JSON. Conditions (≤ 3 levels) on firm traits at t that exist in every split:
  FF12, size (log sales, log assets), margins (EBITDA, EBIT), ROIC, leverage (net debt / EBITDA,
  debt / assets), R&D and capex intensity, FCF and EBITDA sign, WACC − g. **Sales growth is
  excluded:** the panel starts in FY2015, so 1-yr growth is missing for every t = 2015 window
  and 3-yr growth for t = 2015–17. Each leaf is a method + parameters or a blend weight.
  Deterministic validator.
- Loop: proposer (mechanism + falsifiable prediction) → blind critic → deterministic grader on
  exploration windows → archive. Claude Code subagents only. 5 runs × 30 proposals.
  - **[v1.1]** Proposers and critics are subagents **without tools**. The orchestrator passes
    the brief and saves the reply, and every raw reply is logged.
- **[v1.1] Grading convention for recipes:**
  - Every recipe and benchmark is scored on the same evaluation set: graded windows where the
    FF12 exit is defined.
  - A leaf that is undefined for a window uses the FF12 exit. For a blend, any undefined part
    triggers the fallback.
  - The chosen rules are also reported on the §3 common-sample and ITT metrics.
- Benchmarks: best single method, random search (same budget), and a GBM ceiling. The GBM
  predicts ln(truth / FF12 exit) from the same traits; we report the share of its gain captured.
  - **[v1.1]** Added: the **best recipe without a split**, from an exhaustive grid of single
    leaves and 2-part blends.
    - It is shown to proposers as the bar to beat.
    - Its top 3 on exploration are chosen on validation like the finalists.
  - **[v1.1]** Added, reported only: a GBM that also sees each method's log ratio to the FF12
    exit.
- Finalists: the top 3 per run on exploration, chosen once on validation. The single chosen rule
  is evaluated on test.
  - **[v1.1]** The 3 finalists must have distinct predictions (behaviour fingerprint).
  - **[v1.1]** Random finalists are chosen the same way per random run of 30.
- Leakage control: recipes see traits only, never names or dates.

## 8. Robustness (reported, not hypothesis tests)

- **Truth M with and without the outcome-quality filter** (`quality_ok` at t+5 selects on the
  outcome; T1 and T2 are reported both ways).
- **Statements at least 90 days old** at the valuation date (2% of start rows are younger).

Horizon 3; Treasury + 5% discount rate; excluding windows whose t or t+5 row has a > 10x market-cap jump with calm assets
(`mcap_jump_suspect`, 1–2% of windows); truth D restricted to low-leverage targets
(|net claims| < 20% of market cap); truth D with the old (double-count) definition, for the record; annual ERP instead of monthly; without the quality
screen; survivors only versus survivors + shrank; FCF ex-SBC; truth D restricted to cash deals
and to PE buyers.

## 9. Exploration findings already known (disclosure)

See `docs/phase1_exploration.md`, revised after the code review. On t = 2015–16:
- FF12 exit beats Gordon by 0.126 in median |e| (CI 0.098–0.155; truth M).
- Gordon bias: +0.20 against M (common sample), +0.13 against D, +0.20 against D′.
- Exit beats Gordon against M, D and D′.
- The own multiple is best against M and D′ and nearly tied for best against D.
- Energy supports H3. The blends do not beat the FF12 exit (CIs include 0).
- Withdrawn earlier findings:
  - "Gordon unbiased against deals": debt was counted twice in deal EV.
  - The first-pass Gordon bias of +0.25: wrong small-firm rating table.

## 10. Limitations (stated in advance)

- The sample is post-2015 and mostly low-rate. Pre-2015 history was not collected (decided
  2026-11-07).
- Perfect foresight on outcome-year fundamentals isolates formula error, not forecasting error.
- Market truth is partly circular: markets themselves use multiples. Truth D and Q4 address this.
- Targets may be selected for undervaluation (truth D).
- Industry classifications are snapshots: the Damodaran industry is the 2026 list, and SIC (hence
  FF12) does not vary over time in the FactSet exports.
- Damodaran multiples change definition: releases through Jan 2017 have one block; from Jan 2018
  "all firms" is used. The break falls between the exploration and validation years (H3/T4).
- Preferred stock is missing in the panel, so it enters neither panel EV nor deal EV.
- About 2% of start rows have fiscal year-ends less than 90 days before the valuation date
  (robustness).
- The deal-EV definition was selected on deals from all years. It was re-checked on
  exploration deals only and the same reading wins (`scripts/check_deal_ev_definition.py`).
- About 5% of FactSet market caps are unreliable (screened).
- FY2024–25 outcomes were seen before (earlier labs).
- LLM agents may know 2020–25 market history.

## 11. Before freezing

- [x] Q4 deferred to a later pre-registration; truth D co-primary with M (2026-11-07).
- [x] Literature check (2026-11-07): `docs/literature.md`. Courteau, Kao & Richardson (2001) and
  Kaplan & Ruback (1995) verified; positioning written. Others are listed as "to read".
- [x] Independent code review (2026-11-07). Fixes and their effect are in
  `docs/phase1_exploration.md` §5. High severity: wrong small-firm rating table, fixed.
- [x] User approval (2026-11-07) → tag `protocol-v1` → push.

**[v1.1] Before freezing v1.1**

- [x] Independent code review and design review of the Phase 3 setup (2026-11-07). Findings
  and fixes are in `docs/errors_and_fixes.md` §I; 32 tests pass.
- [x] Author decisions (2026-11-07):
  1. issue v1.1;
  2. T8c inside the Holm family;
  3. show the best recipe without a split to proposers;
  4. inference details as in §6.
- [x] Commit → tag `protocol-v1.1`.
- [ ] Push (with author approval) before the first agent run.
