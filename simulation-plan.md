# Simulation Plan

Version: 0.1  
Date: 2026-07-18  
Status: Prespecified before the primary simulation run

## Research question

Which reaction-time variability metrics remain reliable under skewed
distributions, outliers, missing responses, and unequal trial counts?

## Purpose

This project evaluates statistical methods. It does not test an ADHD diagnosis,
biological mechanism, treatment effect, or the Allostatic Sprint hypothesis.

## Simulated data

Each simulation will contain:

- two groups;
- 100 participants per group;
- 160 trials per participant;
- positively skewed reaction-time distributions;
- median reaction time of approximately 500 ms;
- fixed random seed: `20260718`.

## Primary scenarios

1. Same median and same variability in both groups.
2. Same median but greater variability in Group B.
3. Greater variability with 1% extreme slow-response outliers.
4. Greater variability with 15% randomly missing responses.
5. Greater variability with 15% slow-response-dependent missingness.
6. Unequal trial counts between participants.

## Metrics

The following participant-level metrics will be compared:

- median RT;
- standard deviation;
- coefficient of variation;
- median absolute deviation;
- interquartile range.

## Evaluation

Each scenario will be repeated 1,000 times.

For each metric, the benchmark will estimate:

- false-positive rate;
- statistical power;
- effect-size stability;
- sensitivity to outliers;
- sensitivity to missing responses;
- sensitivity to unequal trial counts.

## Missing responses

Missing RT values will not be silently converted into reaction times.

They will be:

- excluded from RT calculations;
- counted and reported separately;
- generated using either random or slow-response-dependent mechanisms.

## Outputs

The benchmark will produce:

- a CSV table with simulation results;
- a JSON file containing the configuration;
- a reproducibility log;
- at least one comparison figure;
- a summary of metric performance.

## Reproducibility

The project will record:

- random seed;
- Python version;
- package versions;
- simulation configuration;
- number of completed repetitions.

## Changes to this plan

Changes made after inspecting primary results must be documented in a separate
amendment. The original plan will remain available in the Git history.

## Interpretation boundary

A metric performing well in simulations does not establish that an observed
ADHD group difference is biological, diagnostic, causal, or clinically useful.
