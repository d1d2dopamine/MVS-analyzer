# Round26: Windows acceptance failure repair

## Evidence before the correction

Two owner-supplied CI text excerpts each report 18 tests and exit 1. Both contain
`test_native_timeout_and_termination` failing because `proc.poll()` remained None
after `terminate_tree()`. Two ACL checks fail through the PowerShell helper:
module loading/empty output in one excerpt and 15-second subprocess timeouts in
the other. These excerpts do not identify the exact commit/runner image and do
not prove later native calibration or MCP acceptance ran. The separate local
fake-engine wrapper result is not native Windows engine evidence.

## Process completion contract

The job's ActiveProcesses counter reaching zero is not sufficient evidence that
the owned leader process handle is already signaled. The old implementation
called poll once, ignored None and returned. Three portable deterministic probes
were added before changing production code: two failed against that implementation.

The corrected loop requires both empty job accounting and a signaled leader with
cached exit status. One shared five-second deadline covers both conditions; the
sleep is bounded by remaining time. There is no second five-second wait, permission
change, process-breakaway path or new handle inheritance. Existing workflow cleanup
maps TimeoutExpired to `process_cleanup_timeout`, retains incomplete evidence and
closes owned handles in finally. It cannot become an unqualified completed result.
The real Windows assertion is retained unchanged for the owner's rerun.

Microsoft documents that external [TerminateProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess)
is asynchronous and completion requires observing the process handle;
[TerminateJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject)
applies termination to job members. The reproduced contract failure, rather than
a timing guess or a weaker assertion, motivated this change.

## Independent ACL acceptance probe

The unreliable nested PowerShell/Get-Acl subprocess is replaced with a small
read-only .NET helper using the framework's directory ACL APIs. It does not import
the Python production ACL verifier. It reports owner/current-user SIDs, protection,
rules and SDDL. Missing helper, helper error, empty/malformed output or timeout
fails the check; it is not a skip or a reason to weaken security assertions.

The tests still require protected private directories, owner/SYSTEM-only allowed
entries, no inherited rules, and acceptance of an existing correctly private
folder. A normal inherited folder must be rejected and retain exactly the same
security descriptor. The production ACL creation/validation implementation is
unchanged. No claim is made that the old ACL failures proved an insecure ACL.

## Owner rerun

Apply the cumulative Round25+26 PATCH to your Round24 checkout after a backup and
manifest hash check. The root README is omitted; this is not a full-source archive.
Commit the intended changes through your own normal workflow, then select
**Manual Windows workflow acceptance** in GitHub Actions. Run the intended commit
on both configured Windows runners. No CI was dispatched by this work.

The workflow builds the read-only ACL helper before the Win32 gate. The gate now
requires exactly 21 tests with zero skips: seven portable contract tests and
fourteen actual Windows tests. Calibration/native workflow/official MCP checks
must also pass; a green partial step or fake engine is insufficient. Return both
artifacts, including the helper build, Win32 log/counts and native acceptance
outputs. Actual Windows 11 agent-host smoke remains a separate final check.

Linux tests establish regression behavior and buildability only. Windows runtime
acceptance remains pending until the new source actually runs there. The science
engine, thresholds and historical NO-GO are unchanged.

### Local Windows contract checks (source checkout, .NET8 and Python installed)

```powershell
dotnet build tools/windows_acl_probe/WindowsAclProbe.csproj -c Release
if ($LASTEXITCODE -ne 0) { throw 'ACL probe build failed' }
$env:MVS_ACL_TEST_PROBE = (Resolve-Path 'tools/windows_acl_probe/bin/Release/net8.0/WindowsAclProbe.exe').Path
$env:PYTHONPATH = (Resolve-Path 'python/src').Path
python -m unittest discover -s python/tests -p 'test_windows*.py' -v
```

These 21 checks are only the contract/Win32 subset. They do not replace the
manual workflow's actual native calibration and official-SDK MCP acceptance.
The helper is a test dependency, not a new runtime dependency of installed MCP.

## Executed checks

Linux: 515 Python/tool tests discovered, 501 passed, 14 actual-Windows tests
skipped. The actual Linux native MCP round-trip passed. Three new ordering
regressions pass; two failed against the old code before correction. Independent
review reran those three plus the structured cleanup-timeout/close check: 4/4 pass.
The read-only ACL helper builds on .NET8 with zero warnings/errors. Its Linux
negative runtime check exits2 with no stdout and an explicit Windows-required
message. The first helper build failed platform-analyzer checks inside a callback;
the retained log documents the repair using a guarded foreach, without warning
suppression. Native statistical code is byte-identical to Round25, whose native
158-test run and exact CLI comparison are retained; that full native suite was
not repeated for this Python/test-helper-only correction.
