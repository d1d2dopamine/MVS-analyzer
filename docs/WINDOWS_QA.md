# Windows UI acceptance checklist

The native harness was written for CI, **not executed during source preparation**. Run `MvsAnalyzer.Ui.Tests` and review its PNG artifacts. It covers Guided/Expert, English/Russian, light/dark, three window sizes and populated/empty calibration/run/results screens.

- Results have a real verdict card and full-height Overview / All metrics / Sensitivity / Files tabs. Expert mode adds diagnostics.
- There is no separate Scientific models sidebar item. Optional models and the benchmark are under Run → Additional methods, with a way back.
- Resize the window and test 100/125/150/200% display scaling, including real monitor changes; text, icons and controls must not clip or overlap.
- Exercise every results tab, scrolling, keyboard focus, cancellation, stale settings and newly imported data. The file list must not show stale previous-dataset output.
- Confirm crisp supplied Colab artwork in both themes and that ordinary local controls remain available.
- Pair a new notebook, reuse the same one for at least three successive jobs, and test returning to a completed job.
- A verified matching calibration disables only duplicate calibration. Changed data/settings/depth make a different job. Failed/cancelled runs must not report completion.
- Test browser local-network permission allowed and blocked, desktop restart, disconnected kernel and manual saved-notebook URL entry.
- Test custom import profiles, manual job/result ZIP exchange, nested analysis output and a benchmark diagnostic exit 2.

Screenshot/geometry checks are not statistical validation. Follow docs/VALIDATION.md before scientific use.
