# Calibration recommendations - 1.5 development line

MVS 1.5 adds a recommendation layer between calibration and inferential testing. This layer is diagnostic: it helps identify which summary metrics are plausible choices for each scientific track, but it does not change the current 12-metric Bonferroni decision family yet.

The recommendation method is identified as `family-power-ci-overlap-v1`.

## Family restriction

Metrics compete only with summaries that answer the same kind of question.

- `location` and `decrease` tracks use the `location` metric family.
- `variability` uses the `variability` family.
- `heterogeneity` currently uses entity-level `location` summaries because the generator perturbs entity centres. The family-level inferential test for heterogeneity is still scheduled for the later automatic-inference milestone.
- `magnitude` metrics such as RMS remain visible for legacy output but do not enter the new family recommendation set.

This prevents a variability summary such as SD from being called a better location estimator than the median merely because the simulated effect happens to favour it.

## Uncertainty-aware candidate set

Within a track, MVS first keeps metrics whose calibration is applicable and whose null false-positive Wilson upper bound satisfies the current diagnostic limit. Among those eligible metrics, the metric with the highest estimated power defines the reference interval.

A metric remains in the candidate set when

```text
metric power upper bound >= best metric power lower bound
```

The rule deliberately avoids forcing a top-1 winner when Monte Carlo uncertainty cannot separate the leading summaries.

The old lower-power target of 0.70 is no longer used to delete the candidate set. It is now a recommendation-quality label:

- `qualified`: candidate and lower power bound >= 0.70;
- `uncertain_power`: candidate, but the lower power bound is below 0.70;
- `lower_sensitivity`: eligible and null-controlled, but its interval is separated below the best candidate;
- `null_control_uncertain`: the current null diagnostic is not satisfactory;
- `not_applicable`: the metric or requested track power is unavailable;
- `outside_family`: the metric belongs to a different summary family.

This means a weak calibration can still say which metrics are statistically competitive while being explicit that the recommendation itself is uncertain.

## What changes in this checkpoint

The CLI now writes `calibration_recommendations.csv` next to `calibration.csv` and `calibration_tracks.csv`. Analysis manifests also include `developmentRecommendations`, one summary per calibration track.

The existing `candidate` and `candidate_tracks` fields in `results.csv` are retained unchanged for 1.4 compatibility during this checkpoint. They are legacy labels and are not the new 1.5 family-aware recommendation set. The inferential decision still uses the full 12-metric Bonferroni correction.

The four new 1.5 metrics remain staged. They will join active family calibration only when the multiplicity and automatic-inference layers are switched together, so the effect of each development step remains measurable in the benchmark history.
