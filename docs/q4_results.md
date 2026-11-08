# Q4 results: the Gordon-vs-market gap and future returns (2026-11-07)

Run once, from a clean tree at the frozen commit (tag `q4-freeze`), with the design in
`docs/q4_design.md`. Output hash is pinned in `docs/q4_pins.json`. Tables are rendered by
`scripts/q4_report.py` from `results/q4/results.json`; no number is retyped.

## Summary

1. **H9 is not supported: the Gordon gap does not predict returns.** The slope is +0.06% a
   month (t 0.19) with controls, and +0.18% (t 0.45) without them. Both are far from
   significant, under every robustness variant.
2. **H10a is not supported.** The cash-flow-yield part has the expected sign (+0.13% a month)
   but is not significant (t 0.47). Over 2016–2026, even this standard value signal adds
   nothing detectable after the controls.
3. **H10b is not rejected, and equivalence to zero is not shown either.**
   - The discount-rate part's slope is −0.38% a month (t −1.02), given beta.
   - Its 95% CI [−1.11%, +0.35%] is too wide to call the effect economically small, as
     anticipated in the design.
   - The point estimate is **negative**: firms whose low WACC inflates their Gordon value
     earned, if anything, lower returns. That is the opposite of the market-mispricing reading.
4. **Reported only, not tests:**
   - Without the beta control (the pre-declared companion), the discount-rate part is −0.50%
     (t −1.85).
   - The value-weighted S1b quintile spread is −1.17% a month (t −2.74; FF5 + UMD alpha −0.65%,
     t −1.75).
   - These are consistent with high-WACC (high-beta) stocks outperforming in this decade, not
     with low-WACC firms being underpriced. They are among many reported statistics and outside
     the test family, so they are not claims.

**Reading against the design (§1).** Nothing supports reading 2, that the market misprices
low-WACC firms and the Gordon gap later closes through returns. The large Gordon misses where
r − g is small (v1 T3) are better read as **formula error**: the 1/(r − g) convexity. The data
cannot rule out a small effect either way: the power stated in advance was about 0.55% a month
for a reliable detection.

**Next, as pre-registered:** the frozen specification is tested live on the June 2027 formation
and later formations.

Run: commit `b0c911c`, clean tree = True; months 2016-07 to 2026-09 (123).

### Pre-registered tests (Fama-MacBeth, monthly slope on rank-scaled signal = long-short spread per month)

| Test | Slope (NW t) | p | p Holm | Reject |
|---|---|---|---|---|
| H9: S1 GAP > 0 | +0.056% (t +0.19) | 0.426 | 0.919 | no |
| H10a: S1a yield part > 0 | +0.128% (t +0.47) | 0.320 | 0.919 | no |
| H10b: S1b discount-rate part ≠ 0 (given beta) | -0.380% (t -1.02) | 0.306 | 0.919 | no |

S1b 95% CI [-1.107%, +0.348%] a month; within the ±0.25% equivalence band: False. Firm-months: 217,787.

### Reported only (outside Holm)

| Specification | Slopes (NW t) |
|---|---|
| H10 without the beta control (pre-declared companion) | S1a +0.150% (t +0.53); S1b -0.499% (t -1.85) |
| S1 without controls | S1 +0.180% (t +0.45) |
| S2 TV disagreement, with controls | S2 -0.089% (t -0.48) |
| Controls in the H10 model | ag +0.169% (t +0.76); beta +0.243% (t +0.59); bm +0.321% (t +1.02); gp +0.103% (t +0.28); mom +0.022% (t +0.06); size +0.439% (t +1.26) |

### Quintile sorts (Q5 − Q1 a month; FF5 + UMD alpha; NW t)

| Signal | EW spread | EW alpha | VW spread | VW alpha |
|---|---|---|---|---|
| S1 | +0.145% (+0.45) | +0.276% (+1.21) | -0.480% (-1.00) | +0.018% (+0.06) |
| S1a | +0.240% (+0.66) | +0.350% (+1.63) | -0.007% (-0.01) | +0.495% (+1.68) |
| S1b | -0.264% (-1.12) | -0.116% (-0.42) | -1.174% (-2.74) | -0.647% (-1.75) |
| S2 | -0.110% (-0.67) | +0.076% (+0.44) | -0.191% (-0.66) | +0.166% (+0.72) |

### Robustness (H9 slope; H10 slopes)

| Variant | H9 S1 | H10 S1a | H10 S1b |
|---|---|---|---|
| perf_delist_0 | +0.052% (t +0.17) | +0.124% (t +0.45) | -0.382% (t -1.03) |
| perf_delist_minus100 | +0.068% (t +0.23) | +0.136% (t +0.50) | -0.374% (t -1.01) |
| returns_raw | +0.104% (t +0.19) | +0.300% (t +0.47) | -0.677% (t -1.58) |
| returns_winsor_1_99 | +0.088% (t +0.29) | +0.153% (t +0.58) | -0.350% (t -0.95) |
| statements_90d | +0.079% (t +0.26) | +0.152% (t +0.56) | -0.368% (t -0.99) |

Delisting months in the window: 2179 ({"-0.3": 360, "0.0": 1819}). Coverage per formation (firms / with S1): 2016-06: 2666/1831, 2017-06: 2659/1874, 2018-06: 2750/1807, 2019-06: 2676/1765, 2020-06: 2641/1663, 2021-06: 3401/1956, 2022-06: 3579/1842, 2023-06: 3071/1662, 2024-06: 2805/1818, 2025-06: 2744/1864, 2026-06: 2848/1823
