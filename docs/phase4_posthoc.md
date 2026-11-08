# Post-hoc diagnosis: did the agents' rules fail on level or on ranking? (EXPLORATORY)

**Status:** plan written and committed on 2026-11-07, after test was opened and **before** this
analysis was run. Validation and test have already been seen, so nothing here is
confirmatory. The analysis informs the next study; it changes no pre-registered result.

## Question

On test, every agent finalist was more biased upward than the benchmarks (`docs/phase4_results.md`).
Median |e| mixes two things:
- **level:** a common shift of a rule's predictions relative to the market;
- **ranking / dispersion:** how well the rule orders and spaces firms around that level.

The question is whether the agents' conditional rules have any **cross-sectional** value once
each rule's level is removed. If they do, the failure came from the metric and the levers, and a
redesigned study is worth running. If they do not, the conditional rules added nothing.

## Method (fixed before running)

- **Rules compared:**
  - all 33 finalists (agent 15, random 15, unconditional 3);
  - the own-multiple exit and the FF12 exit.

  Each is scored on the recipe evaluation set of each split (exploration, validation, test),
  with the FF12-exit fallback.
- **Primary metric, "level-removed median |e|":**
  1. Compute e = ln(pred / truth).
  2. Subtract the rule's own median e within each start year t of the split.
  3. Take the median absolute value of the result.

  This is an oracle recalibration: it uses outcome information, so it is not achievable in
  practice. It is a diagnostic of ranking and dispersion only.
- **Secondary metric:** the same with one level per split instead of per start year.
- **Contrasts on each split:** the chosen agent recipe (`a1/g04-02`) against the chosen
  unconditional recipe (`unc-3`), the chosen random recipe (`rnd-0090`) and the own multiple.
  Inference uses the difference in level-removed median |e|, a firm-clustered bootstrap with
  2,000 reps and seed 0, and recomputes the year levels inside each resample.
- **Also reported:** each group's range of level-removed scores per split, and each finalist's
  bias per split.

## Decision rule (fixed before running)

| Result for agent − unconditional, level-removed | Reading | Next step |
|---|---|---|
| 95% CI below 0 on **both** validation and test | The conditional rules carry cross-sectional signal; the failure was level | Pre-register v2: a level-neutral metric or level-locked recipes, on a fresh holdout (e.g. FactSet panel for 2005–14) |
| CI below 0 on neither | No cross-sectional value beyond the simple blend | Close Phase 3 with the negative result; move to Q4 |
| Anything else | Weak or mixed | Report as such. v2 only if the user judges the signal worth new data |

## Logging

The analysis reads validation and test again. Each read is appended to
`results/unseal_log.jsonl` with `what: posthoc_level_vs_ranking`, so the record separates
these reads from the one-shot pre-registered openings.

## Results (run 2026-11-07, after the plan above was committed and pushed in `5091fa3`)

Script: `scripts/posthoc_level_vs_ranking.py`, output in `results/phase4/posthoc.json`. Each
re-read of validation and test is logged with `what: posthoc_level_vs_ranking`.

Each rule is shown as raw median abs e / bias, then level-removed median abs e (year level ·
split level). Rules are scored on the recipe evaluation set.

| Rule | Exploration | Validation | Test |
|---|---|---|---|
| agent `a1/g04-02` | 0.355 / +0.003 · 0.340 · 0.356 | 0.338 / +0.096 · 0.334 · 0.333 | 0.460 / +0.262 · 0.387 · 0.395 |
| unconditional `unc-3` | 0.369 / −0.024 · 0.352 · 0.369 | 0.342 / +0.071 · 0.338 · 0.341 | 0.422 / +0.202 · 0.394 · 0.393 |
| random `rnd-0090` | 0.379 / −0.053 · 0.353 · 0.373 | 0.336 / +0.049 · 0.339 · 0.340 | 0.411 / +0.161 · 0.390 · 0.389 |
| own multiple | 0.415 / −0.097 · 0.367 · 0.404 | 0.349 / +0.039 · 0.346 · 0.344 | 0.426 / +0.074 · 0.411 · 0.418 |
| FF12 exit | 0.459 / −0.113 · 0.429 · 0.449 | 0.427 / +0.044 · 0.419 · 0.422 | 0.453 / +0.088 · 0.426 · 0.438 |

**Contrasts** (level-removed by year; difference, firm-clustered 95% CI):

| Agent minus | Exploration | Validation | Test |
|---|---|---|---|
| unconditional | −0.012 [−0.025, +0.001] | −0.004 [−0.019, +0.003] | −0.007 [−0.017, +0.012] |
| random | −0.013 [−0.026, +0.001] | −0.006 [−0.019, +0.003] | −0.003 [−0.016, +0.014] |
| own multiple | −0.027 [−0.043, −0.011] | −0.013 [−0.029, +0.000] | −0.023 [−0.039, −0.006] |

Level-removed range per group (year level):

| Group | Exploration | Validation | Test |
|---|---|---|---|
| agent | 0.336–0.350 | 0.333–0.344 | 0.387–0.401 |
| random | 0.353–0.424 | 0.338–0.444 | 0.368–0.450 |
| unconditional | 0.352–0.358 | 0.338–0.346 | 0.394–0.400 |

### Reading against the decision rule

- **Agent − unconditional:** the CI includes 0 on validation and on test. This is the
  "neither" row, so there is **no cross-sectional value beyond the simple blend. Phase 3 closes
  with the negative result, and the next study is Q4.**
- **The test loss was mostly level.**
  - Raw, the agent recipe is 0.038 worse than the unconditional blend on test.
  - With each rule's year level removed, it is 0.007 better (not significant).
  - So the agents' rules ranked firms about as well as the blend. They lost because their
    Gordon g 4% components set the level too high for the test period.
- **Against the own multiple, the agent recipe ranks better on test once level is removed**
  (−0.023, CI excludes 0). The unconditional blend shares this gain, so it comes from
  blending a cash-flow value into the own multiple, not from the conditional splits.
- **Agent finalists are tightly clustered** on every split. They are near-variants of one
  blend, while random finalists spread widely.

These readings are exploratory and condition on data already seen.
