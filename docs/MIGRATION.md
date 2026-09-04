# Migration to public 1.4.0 / engine 1.6.0

The public release follows 1.3.2. The supplied 1.5.0 archive was a development snapshot, not the release numbering used here. Requested development scopes 1.6/1.7/1.8 are consolidated in this update. Existing badges/images were intentionally not edited; version constants and manifests are authoritative.

1. Keep old input files, exports and the old executable/source together. Do not overwrite historical scientific evidence.
2. Re-import original data and create a **new calibration**. Schema 2 is deliberately incompatible with incomplete earlier states. `--force` cannot bypass this.
3. Revisit the inference plan: twelve registered metrics with full-registry Bonferroni; corrected Cliff sign; approximate two-group equivalence; descriptive selected-pair intervals; a two-factor detection index; three sensitivity tracks.
4. Expect different p-based decisions, rankings, gates and MDE availability. The earlier score scale is not numerically comparable.
5. For genuine repeated conditions on the same IDs, use MELSM rather than independent-group analysis. Confirm model assumptions; the new implementation is experimental.
6. Do not interpret a changed formula/protocol checksum as tampering by itself. It reflects intentionally changed methods.
7. Re-export remote jobs from this release. Import plugins must match their saved fingerprint on the remote machine; an unavailable profile causes an explicit refusal rather than silent fallback.
8. Run CI and the manual Windows checklist before publishing binaries. The new Windows badge in release notes resolves only after the named release asset is actually published.
