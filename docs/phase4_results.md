# Phase 4 results: validation and test (2026-11-07)

Validation (t = 2017–18) and test (t = 2019–20) were each opened **once**, by
`scripts/phase4.py`, from a clean tree:
- validation at commit `9b7757b` (tag `phase4-freeze`);
- test at `ead4fa7`, after validation's output hashes were committed and pushed.

There were no reruns and no deviations from `docs/phase4_procedure.md`. The unseal log has 10
entries per split, all from that single invocation. Output hashes are pinned in
`docs/phase4_pins.json`. Every number below is rendered by `scripts/phase4_report.py` from
`results/phase4/*.json`; none is retyped.

## Summary

1. **Exit multiples beat Gordon, and Gordon fails where r − g is small.** This holds in every
   split and under both truths:
   - T1: +0.237 on test;
   - T1D: +0.245;
   - T3: +0.566;
   - T3D: +0.481.

   All four reject after Holm, and the result holds in every protocol §8 robustness variant.
   It is the project's main, robust finding.
2. **Gordon's bias is not stable across periods.** It overvalued on exploration (+0.20), was
   about unbiased on validation (−0.01, so T2 did not replicate there), and overvalued strongly
   on test (+0.46). T2 and T2D reject on test, but the sign of the bias depends on the period.
   Every method overvalues on test (own multiple +0.13, FF12 +0.15), which suggests a
   market-wide fall in multiples between the valuation dates (2020–21) and the outcome dates
   (2025–26).
3. **H5 is not supported: the agent's recipe lost out of sample.** The chosen agent recipe
   (`a1/g04-02`, a 3-level tree) did worse on test than:
   - the own multiple (T8a +0.034);
   - the chosen random recipe (T8b +0.048);
   - the best recipe without a split (T8c +0.038).

   All three CIs exclude 0 in the wrong direction. It was also worse than the plain FF12 exit,
   so its share of GBM gain is negative.
4. **Why it lost: level, not ranking (to be checked; see `docs/phase4_posthoc.md`).** All 15
   agent finalists carry the largest upward bias on test (+0.26 to +0.33), against +0.02 to
   +0.33 for random finalists. Agent recipes mostly add a Gordon component at g = 4% to the
   own multiple. That raises the predicted level. It helped on exploration, where most methods
   undervalued, and hurt on test, where all of them overvalued. The design had flagged this
   risk (`docs/phase3_design.md` §3.3, "level levers").
5. **Tests that stay null:**
   - T4: Damodaran 5-year average in cyclicals;
   - T5/T5D: 50/50 blends, as expected after exploration;
   - T7: the own multiple ranks better against D′ than D; right sign in both splits, but not
     significant.

   T4D was significant on validation (−0.134) but not on test (+0.056).

## Caveats

- **Test is one period,** with outcome years after the 2022–23 rate rise. FY2024–25 outcomes had
  been seen in earlier labs (disclosed in the protocol).
- **Truth D reuses deals across splits:**
  - 423 of 738 validation windows and 421 of 805 test windows were graded in an earlier split.
  - Without those windows, T1D stays large on both splits.
- **Exploration values of the chosen recipes are in-sample after selection.**

### Pre-registered tests

| Test | Statistic | H | Validation (n) | Test: value, 95% CI | n (firms) | p one-sided | p Holm | Reject |
|---|---|---|---|---|---|---|---|---|
| T1 | Gordon g2.5 − FF12 exit (M) | > 0 | +0.152 [+0.121, +0.182] (2256) | +0.237 [+0.201, +0.272] | 2226 (1307) | 0.0005 | 0.0070 | **yes** |
| T2 | median e of Gordon g2.5 (M) | > 0 | -0.012 [-0.059, +0.049] (2256) | +0.463 [+0.399, +0.514] | 2226 (1307) | 0.0005 | 0.0070 | **yes** |
| T3 | Gordon − FF12, low- minus high-spread tercile (M) | > 0 | +0.144 [+0.078, +0.220] (2256) | +0.566 [+0.475, +0.645] | 2226 (1307) | 0.0005 | 0.0070 | **yes** |
| T4 | Damodaran 5-yr − at t, cyclicals (M) | < 0 | +0.004 [-0.034, +0.033] (674) | +0.020 [-0.024, +0.051] | 601 (353) | 0.7605 | 1.0000 | no |
| T5 | 50/50 log blend − better pure method (M) | < 0 | +0.028 [+0.008, +0.051] (2256) | +0.061 [+0.040, +0.086] | 2226 (1307) | 1.0000 | 1.0000 | no |
| T1D | Gordon g2.5 − FF12 exit (D) | > 0 | +0.233 [+0.127, +0.337] (387) | +0.245 [+0.138, +0.366] | 367 (250) | 0.0005 | 0.0070 | **yes** |
| T2D | median e of Gordon g2.5 (D) | > 0 | -0.199 [-0.329, -0.041] (387) | +0.337 [+0.154, +0.477] | 367 (250) | 0.0005 | 0.0070 | **yes** |
| T3D | Gordon − FF12, low- minus high-spread tercile (D) | > 0 | -0.003 [-0.223, +0.322] (387) | +0.481 [+0.196, +0.770] | 367 (250) | 0.0005 | 0.0070 | **yes** |
| T4D | Damodaran 5-yr − at t, cyclicals (D) | < 0 | -0.134 [-0.268, -0.038] (79) | +0.056 [-0.129, +0.261] | 89 (59) | 0.6570 | 1.0000 | no |
| T5D | 50/50 log blend − better pure method (D) | < 0 | +0.044 [-0.034, +0.130] (387) | +0.063 [+0.003, +0.148] | 367 (250) | 0.9795 | 1.0000 | no |
| T7 | own − Damodaran-industry: D′ minus D | < 0 | -0.054 [-0.160, +0.043] (219) | -0.058 [-0.143, +0.082] | 211 (144) | 0.2725 | 1.0000 | no |
| T8a | agent − best single method | < 0 | — | +0.034 [+0.013, +0.056] | 3392 (1891) | 0.9995 | 1.0000 | no |
| T8b | agent − chosen random | < 0 | — | +0.048 [+0.032, +0.066] | 3392 (1891) | 1.0000 | 1.0000 | no |
| T8c | agent − chosen unconditional | < 0 | — | +0.038 [+0.019, +0.053] | 3392 (1891) | 0.9995 | 1.0000 | no |

Decisions: {"H5_supported": false, "agent_depth": 3, "conditional_gain": false, "note": ""}

### Chosen recipes and benchmarks (median abs e / bias, recipe evaluation set)

| Rule | Exploration | Validation | Test |
|---|---|---|---|
| agent `a1/g04-02` | 0.355 / +0.003 | 0.338 / +0.096 | 0.460 / +0.262 |
| random `rnd-0090` | 0.379 / -0.053 | 0.336 / +0.049 | 0.411 / +0.161 |
| unconditional `unc-3` | 0.369 / -0.024 | 0.342 / +0.071 | 0.422 / +0.202 |
| best single `E_own` | — | 0.349 / +0.039 | 0.426 (agent − T8a) |
| FF12 exit | — | 0.427 | 0.453 |
| GBM traits_only | — | 0.397 / +0.178 | 0.452 / +0.194 |
| GBM traits_methods | — | 0.306 / +0.099 | 0.391 / +0.187 |

### All finalists on test (median abs e, bias): range per group

- agent: median abs e 0.459–0.495; bias +0.262 to +0.330 (15 recipes)
- random: median abs e 0.395–0.544; bias +0.022 to +0.326 (15 recipes)
- unconditional: median abs e 0.422–0.493; bias +0.202 to +0.326 (3 recipes)

### Share of GBM gain (test)

- agent: traits_methods -0.11; traits_only -8.42
- random: traits_methods 0.68; traits_only 52.67 (exceeds the ceiling (ceiling uninformative))
- unconditional: traits_methods 0.51; traits_only 39.19 (exceeds the ceiling (ceiling uninformative))

### Chosen recipes against truth D (test) and protocol section 3 metrics

- agent: vs D 0.466 / +0.285 (n 525); common sample with best single (n 3040): recipe 0.436 vs single 0.399; ITT hit 0.211 vs 0.215; Damodaran-leaf share 0.073
- random: vs D 0.459 / +0.213 (n 525); common sample with best single (n 3040): recipe 0.388 vs single 0.399; ITT hit 0.236 vs 0.215; Damodaran-leaf share 0.000
- unconditional: vs D 0.476 / +0.252 (n 525); common sample with best single (n 3040): recipe 0.393 vs single 0.399; ITT hit 0.226 vs 0.215; Damodaran-leaf share 0.000

### Robustness (protocol section 8; T1 / T2 or T1D / T2D, value and n)

| Variant | Validation | Test |
|---|---|---|
| D:cash_deals | T1D +0.230 [+0.098, +0.400] (265); T2D -0.160 [-0.337, +0.043] (265) | T1D +0.186 [+0.063, +0.328] (254); T2D +0.278 [+0.113, +0.421] (254) |
| D:excluding_deals_graded_in_earlier_splits | dropped 423, kept 315: T1D +0.384, T2D -0.230, T3D +0.016, T4D -0.098, T5D +0.131; T7 -0.083 | dropped 421, kept 384: T1D +0.372, T2D +0.648, T3D +0.922, T4D +0.061, T5D +0.156; T7 +0.070 |
| D:low_leverage | T1D +0.185 [-0.017, +0.332] (150); T2D -0.576 [-0.761, -0.410] (150) | T1D +0.063 [-0.077, +0.320] (125); T2D +0.061 [-0.155, +0.282] (125) |
| D:old_double_count_definition | T1D +0.242 [+0.154, +0.328] (387); T2D -0.433 [-0.522, -0.296] (387) | T1D +0.161 [+0.086, +0.326] (367); T2D +0.042 [-0.077, +0.250] (367) |
| D:pe_buyers | T1D +0.184 [-0.008, +0.339] (127); T2D -0.287 [-0.459, -0.007] (127) | T1D +0.126 [-0.055, +0.338] (124); T2D +0.152 [+0.061, +0.342] (124) |
| M:annual_erp | T1 +0.153 [+0.122, +0.181] (2256); T2 -0.017 [-0.063, +0.045] (2256) | T1 +0.196 [+0.159, +0.229] (2231); T2 +0.420 [+0.373, +0.460] (2231) |
| M:excl_mcap_jump | T1 +0.152 [+0.118, +0.181] (2248); T2 -0.016 [-0.064, +0.043] (2248) | T1 +0.237 [+0.200, +0.269] (2219); T2 +0.461 [+0.399, +0.509] (2219) |
| M:fcf_ex_sbc | T1 +0.183 [+0.155, +0.213] (2223); T2 -0.109 [-0.170, -0.054] (2223) | T1 +0.199 [+0.168, +0.237] (2198); T2 +0.345 [+0.293, +0.388] (2198) |
| M:no_outcome_quality_filter | T1 +0.152 [+0.121, +0.182] (2256); T2 -0.012 [-0.059, +0.049] (2256) | T1 +0.237 [+0.201, +0.272] (2226); T2 +0.463 [+0.399, +0.514] (2226) |
| M:no_quality_screen | T1 +0.152 [+0.119, +0.182] (2262); T2 -0.012 [-0.062, +0.049] (2262) | T1 +0.237 [+0.202, +0.270] (2227); T2 +0.463 [+0.402, +0.515] (2227) |
| M:statements_90d | T1 +0.154 [+0.119, +0.181] (2200); T2 -0.018 [-0.064, +0.040] (2200) | T1 +0.234 [+0.196, +0.269] (2168); T2 +0.453 [+0.397, +0.507] (2168) |
| M:survivors_only | T1 +0.153 [+0.119, +0.181] (2229); T2 -0.014 [-0.063, +0.040] (2229) | T1 +0.237 [+0.201, +0.270] (2195); T2 +0.461 [+0.399, +0.512] (2195) |
| M:treasury_plus_5 | T1 +0.136 [+0.105, +0.174] (2256); T2 +0.046 [-0.006, +0.091] (2256) | T1 +0.145 [+0.114, +0.176] (2226); T2 +0.404 [+0.369, +0.436] (2226) |

Horizon 3 (T1–T5, M): validation T1_h3 +0.124, T2_h3 +0.024, T3_h3 +0.145, T4_h3 +0.015, T5_h3 +0.016; test T1_h3 +0.231, T2_h3 +0.446, T3_h3 +0.503, T4_h3 +0.051, T5_h3 +0.076

### Core methods on the common sample (median abs e / bias)

| Method | Validation (M) | Test (M) | Test (D) |
|---|---|---|---|
| B50_G2.5_Eff12 | 0.429 / +0.099 | 0.511 / +0.368 | 0.601 / +0.351 |
| B50geo_G2.5_Eff12 | 0.434 / +0.046 | 0.487 / +0.311 | 0.576 / +0.300 |
| E_dam_5yavg | 0.396 / +0.102 | 0.409 / +0.152 | 0.483 / +0.241 |
| E_dam_t | 0.421 / +0.213 | 0.456 / +0.240 | 0.524 / +0.247 |
| E_damind_med | 0.380 / +0.085 | 0.428 / +0.147 | 0.473 / +0.243 |
| E_ff12_med | 0.406 / +0.105 | 0.426 / +0.153 | 0.513 / +0.241 |
| E_own | 0.302 / +0.085 | 0.382 / +0.127 | 0.406 / +0.158 |
| G_fcf3avg_g2.5 | 0.502 / -0.080 | 0.662 / +0.399 | 0.645 / +0.214 |
| G_fcf_g2.5 | 0.558 / -0.012 | 0.663 / +0.463 | 0.758 / +0.337 |
| G_vd_roic_g2.5 | 0.605 / -0.298 | 0.551 / +0.050 | — |
| G_vd_ronic=r | 0.574 / -0.414 | 0.428 / -0.235 | — |

Common-sample n: validation M 2256, test M 2226, test D 367. Window counts (test): {"acquired_graded": 805, "exited": 1529, "exited_by_type": {"acquired": 1101, "acquired_late": 10, "inactive": 266, "listed": 152}, "gap": 4, "quality_ok_at_t": 6053, "shrank": 511, "survived": 4009}
