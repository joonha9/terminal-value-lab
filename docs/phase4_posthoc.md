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
