# Round 16: release documentation and verification consistency

## Defect and scope

The readiness audit found that the release workflow copied a manually enumerated
subset of documentation. That list omitted linked ROUND reports,
METRIC_REGISTRY.md, CALIBRATION_RECOMMENDATIONS.md and supporting documentation
assets. The binary bundle could therefore contain a plan/method summary whose
local evidence links were missing.

The release workflow also lacked several current normal-CI checks: independent
Huber/Holm/maxT oracles, benchmark diagnostic reconciliation and real CLI
input-preservation regressions. A native suite and one canonical smoke test alone
were not the complete maintained verification contract.

This stage repairs local packaging and future workflow definitions. It does not
create a release, tag, commit, deployment or remote workflow run; publication
permissions/triggers/tag/version/draft behavior remain unchanged. Round 15 is the
source rollback point. Statistical code, active methods and saved-state identity
are unchanged. Scientific NO-GO and activation gates remain in force.

## Bundle boundary

A dependency-free local helper replaces the brittle document filename list. It
copies the complete documentation tree and existing public examples/notebooks,
plus the documentation's selected local support/evidence so included Markdown
links and images can resolve. It preserves source bytes and checks local
references against the resulting bundle boundary. It does not silently follow
source references outside the repository or select arbitrary unrelated files.

The output must be new; an existing folder is not reset or deleted. Source/path
preflight occurs before copying, and ordinary symlink/overlap cases are checked.
Unexpected I/O failure can still leave a partial new bundle; it is not a transaction
or a claim of race-proof filesystem security.

The Python wheel and complete source archive remain separate release assets.
A documentation code block that invokes build/validation tools may require the
companion source archive; checking local links is not a promise that every source
command runs from a binary-only folder.

## Verification boundary

Local bundle layout tests use a clearly synthetic, nonexecuted executable marker.
They establish documentation/evidence inclusion, byte preservation, path safety
and links, not single-file executable portability. No synthetic marker is a
compiled release. The actual publication, self-contained runtime packaging and
GitHub release action remain unexecuted for this stage.

The source archive and previously recorded Linux native/CLI evidence remain
available. Only checks actually run for this stage are recorded below; editing a
workflow does not mean that remote CI or its future gates have passed.

## Workflow changes and actual checks

Release now independently carries the same 19 maintained CI command gates, including
static/source/backup/evidence/runner tests, independent numerical references,
native oracle exports, diagnostic reconciliation, actual CLI safety and canonical
scientific parity. Release retains its own tag/version guard, publish directory,
packaging/checksums and draft action; CI retains separate jobs/artifact upload.
No trigger, checkout ref, permission or draft default is expanded.

- **34/34 new offline bundle regressions PASS.** They cover byte preservation,
  newly added checkpoint docs/assets, local references, existing output protection,
  traversal, source/output aliases, unsupported entries and malformed text.
- Actual-source layout using a nonexecuted synthetic marker: **116 files**,
  **47 Markdown documents**, **97 local links** verified before the final index
  additions below. All selected source/evidence bytes were preserved. These
  counts describe that recorded layout invocation, not a compiled release.
- Workflow YAML parsed; **40 shell snippets** pass `bash -n` and five embedded
  Python heredocs pass AST parsing. All 19 CI run blocks match release after
  normalizing the intentional publish-path difference. Release security/ref/draft
  settings are unchanged.
- The score-reproduction gate was also run on both retained synthetic analyses
  produced by the actual round-13 CLI safety suite. Both pass the existing 0.01
  score-unit criterion; no score/formula tolerance or reported result changed.

The link checker covers inline Markdown links/images (including supported angle,
escape and balanced-parenthesis destinations), reference definitions, and HTML
image/link attributes. It ignores code examples and URL fragments. It checks local
target existence, not CommonMark conformance, anchor IDs, external URL availability
or runtime behavior.

No new native build, full benchmark, self-contained publish or remote release was
needed or run for this tooling/workflow-only repair. Prior native scientific
checks remain separately identified; future workflow wiring is not reported as
an executed release.

Final current-source test run: **375/375 Python tests PASS** (341 prior tests plus
34 release-bundle tests), with 53 frozen SciPy rank-reference cases also passing.
This includes the actual-source bundle test after the final documentation index
changes. Source/CLI/notebook/payload checks pass; native sources and historical
scientific evidence remain byte-identical. Final scope guard and full source-ZIP
integrity/preservation checks pass. The ZIP is source, not a compiled release.
