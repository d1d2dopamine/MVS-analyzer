"""Data-generating mechanisms for the MVS Analyzer validation suite.

Single source of truth. Both `make_datasets.py` (which writes the shipped CSV
files) and `reference_simulation.py` (which computes the Monte-Carlo truth
table) import this module, so the datasets and the expected numbers can never
drift apart.

Every mechanism returns a dict {group_name: ndarray of shape (entities, reps)}.
The hierarchy is deliberate and mirrors what the engine assumes:

    value[i, j] = f(entity_effect[i], within_entity_noise[j])

Entities are the independent unit; repeated measurements inside an entity are
not. A mechanism therefore always has two variance components.

No dependency other than numpy.
"""

from __future__ import annotations

import numpy as np

BASE = 100.0  # nominal level of the reference group, arbitrary units


# --------------------------------------------------------------------------
# A. Additive normal, additive shift. The textbook case for the mean.
# --------------------------------------------------------------------------
def normal_additive(rng, entities=20, reps=20, shift=5.0,
                    entity_sd=3.0, within_sd=8.0):
    """Symmetric, light-tailed, homoscedastic; the treated group is shifted by
    a constant. A priori optimum: the arithmetic mean (the median pays the
    classic 2/pi efficiency penalty)."""
    out = {}
    for name, delta in (("Control", 0.0), ("Treated", shift)):
        mu = BASE + delta + rng.normal(0.0, entity_sd, size=(entities, 1))
        out[name] = mu + rng.normal(0.0, within_sd, size=(entities, reps))
    return out


# --------------------------------------------------------------------------
# B. Multiplicative lognormal, multiplicative shift.
# --------------------------------------------------------------------------
def lognormal_multiplicative(rng, entities=20, reps=20, factor=1.20,
                             entity_sd_log=0.10, within_sd_log=0.45):
    """The process is multiplicative, so it is additive on the log scale and
    strongly right-skewed on the raw scale. A priori optimum: the geometric
    mean, with the median as its rank-equivalent stand-in. The arithmetic mean
    estimates exp(mu + sigma^2/2) and carries far more sampling noise here."""
    out = {}
    for name, mult in (("Control", 1.0), ("Treated", factor)):
        mu = np.log(BASE * mult) + rng.normal(0.0, entity_sd_log, size=(entities, 1))
        out[name] = np.exp(mu + rng.normal(0.0, within_sd_log, size=(entities, reps)))
    return out


# --------------------------------------------------------------------------
# C. Contaminated normal, additive shift. The textbook case for robustness.
# --------------------------------------------------------------------------
def heavy_tails(rng, entities=20, reps=20, shift=4.0, contamination=0.12,
                entity_sd=3.0, within_sd=6.0, outlier_sd=60.0):
    """A clean normal core plus a fixed share of wide-variance contamination
    (a two-component mixture, i.e. the Tukey-Huber model). A priori optimum:
    the median and the MAD/IQR family. The mean, SD and range have unbounded
    influence functions and should degrade sharply."""
    out = {}
    for name, delta in (("Control", 0.0), ("Treated", shift)):
        mu = BASE + delta + rng.normal(0.0, entity_sd, size=(entities, 1))
        clean = rng.normal(0.0, within_sd, size=(entities, reps))
        wide = rng.normal(0.0, outlier_sd, size=(entities, reps))
        mask = rng.random(size=(entities, reps)) < contamination
        out[name] = mu + np.where(mask, wide, clean)
    return out


# --------------------------------------------------------------------------
# D. Scale change only. Nothing happens to the level.
# --------------------------------------------------------------------------
def scale_only(rng, entities=20, reps=20, sd_ratio=2.0,
               entity_sd=3.0, within_sd=6.0):
    """Identical central tendency, doubled within-entity dispersion. A priori
    optimum: the spread family (SD, IQR, MAD, CV). Level metrics must show
    approximately nominal false-alarm behaviour and no power -- if they do not,
    something leaks between the families."""
    out = {}
    for name, ratio in (("Control", 1.0), ("Treated", sd_ratio)):
        mu = BASE + rng.normal(0.0, entity_sd, size=(entities, 1))
        out[name] = mu + rng.normal(0.0, within_sd * ratio, size=(entities, reps))
    return out


# --------------------------------------------------------------------------
# E. The null. The two groups are the same world.
# --------------------------------------------------------------------------
def pure_null(rng, entities=16, reps=16, entity_sd=3.0, within_sd=8.0):
    """No effect of any kind. Used to measure what the whole select-then-test
    pipeline actually does to the false-positive rate."""
    out = {}
    for name in ("Control", "Treated"):
        mu = BASE + rng.normal(0.0, entity_sd, size=(entities, 1))
        out[name] = mu + rng.normal(0.0, within_sd, size=(entities, reps))
    return out


# --------------------------------------------------------------------------
# F. Too little data. A design question disguised as a dataset.
# --------------------------------------------------------------------------
def small_n(rng, entities=4, reps=6, shift=5.0, entity_sd=3.0, within_sd=8.0):
    """Mechanism A, but with four entities per group. The effect is real and
    undetectable at this sample size; the honest output is an empty candidate
    set and 'insufficient' verdicts, not a recommendation."""
    return normal_additive(rng, entities=entities, reps=reps, shift=shift,
                           entity_sd=entity_sd, within_sd=within_sd)


# --------------------------------------------------------------------------
# G. Degenerate values: coarse rounding, heavy ties, one flat entity.
# --------------------------------------------------------------------------
def ties_and_zero_spread(rng, entities=12, reps=12, shift=2.0):
    """Values rounded to whole units so that ties dominate, and the first
    entity of each group is perfectly constant (zero spread). Relative and
    spread metrics are undefined or degenerate for it. Nothing here should
    crash, and undefined metrics must be reported as not applicable rather
    than silently dropped or filled with a number."""
    out = {}
    for name, delta in (("Control", 0.0), ("Treated", shift)):
        mu = BASE + delta + rng.normal(0.0, 2.0, size=(entities, 1))
        vals = np.round(mu + rng.normal(0.0, 3.0, size=(entities, reps)))
        vals[0, :] = np.round(BASE + delta)  # a perfectly repeatable instrument
        out[name] = vals
    return out


MECHANISMS = {
    "A_normal_additive": normal_additive,
    "B_lognormal_multiplicative": lognormal_multiplicative,
    "C_heavy_tails": heavy_tails,
    "D_scale_only": scale_only,
    "E_null": pure_null,
    "F_small_n": small_n,
    "G_ties_zero_spread": ties_and_zero_spread,
}

# A priori expectation, written down before any of this was run.
A_PRIORI = {
    "A_normal_additive": "mean (median close behind); spread metrics ~ no power",
    "B_lognormal_multiplicative": "geometric mean, median; mean/rms clearly worse",
    "C_heavy_tails": "median, mad, iqr; mean/sd/range collapse",
    "D_scale_only": "standard_deviation, iqr, mad, cv; level metrics ~ no power",
    "E_null": "nothing is detectable; every metric sits at alpha",
    "F_small_n": "no metric qualifies; empty candidate set is the correct answer",
    "G_ties_zero_spread": "relative metrics not applicable on the flat entity",
}
