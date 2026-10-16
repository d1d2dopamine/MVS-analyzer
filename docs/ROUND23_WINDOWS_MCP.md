# Round 23: experimental Windows MCP backend

## Status and scope

Windows 10+ x64 / Windows 11 source support is implemented. **No Windows runtime
has been available in this cloud execution.** The manual Windows CI below is the
remaining acceptance gate, not a test already passed. Windows Server CI also does
not establish a real Windows 11 agent-host installation. Linux remains the locally
executed reference platform. Scientific NO-GO, summary-analysis-only scope and
existing calibration requirements are unchanged.

Round22 is the rollback source checkpoint. Round23 was developed in a separate
copy. No repository push, CI dispatch, release or external registrar was performed.

## Windows installation and agent configuration

Use official Python 3.12 x64 and .NET 8 SDK in PowerShell. From this source root:

```powershell
dotnet publish MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj -c Release -r win-x64 --self-contained true -o C:\mvs\cli
py -3.12 -m venv C:\mvs\venv
C:\mvs\venv\Scripts\python.exe -m pip install ".\python[mcp]"
```

Use a short local fixed NTFS path. Put only the intended CSV and its matching
`calibration_state.json` in `C:\mvs\inputs`. The work path `C:\mvs\work` must be
**nonexistent** initially: the service creates it with a protected current-user
and SYSTEM ACL. Do not pre-create it with `mkdir` and do not grant broad permissions
to work around an error. Use a new path or inspect the configuration.

Configure the local AI agent's supported stdio MCP entry (the host-specific settings
screen/key is not assumed):

```json
{
  "command": "C:\\mvs\\venv\\Scripts\\python.exe",
  "args": ["-m", "mvs.mcp_server", "--engine", "C:\\mvs\\cli\\mvs.exe",
           "--read-root", "C:\\mvs\\inputs", "--work-root", "C:\\mvs\\work",
           "--timeout-seconds", "120"]
}
```

This is the executable/argument object to place in the host's documented MCP
configuration; it is not a universal full host config. No network listener or
credentials are needed. SDK is pinned to official `mcp==1.30.0`; Linux tests exercise
protocol 2025-11-25 and 2024-11-05 negotiation. Windows negotiation still needs its
actual test. Test `mvs://capabilities`, then `get_protocol`/`run_analysis` with small
synthetic data before any study. Requests keep forward-slash relative input paths.

Example exploratory tool arguments:

```json
{"run_id":"smoke-001","data":"demo.csv","calibration":"calibration_state.json"}
```

Frozen mode remains a local immutable record, **not proof of prospective
registration**, unseen data, campaign completeness or statistical validity.

## Isolation and compatibility

- New child-only `MVS_APPDATA_ROOT` selects the root before `MVS_Analyzer` for
  journal, plugins, settings, benchmark preferences and related application-data
  paths. Unset retains each caller's exact former folder-resolution option.
  Explicit invalid roots fail rather than fall back. Existing `MVS_BACKUP_DIR`
  precedence is preserved. Workflow backups stay disabled.
- Native `version --json` adds `localAppDataOverride: "MVS_APPDATA_ROOT/v1"`.
  Windows workflow requires this capability before state-check or analysis, so an
  old engine that ignores the override cannot silently access normal appdata.
- Workspaces use a persistent non-inherited exclusive file handle for locking.
  Snapshot files use CREATE_NEW; immutable records publish flushed same-directory
  temporaries without replacement or copy-delete fallback. Uncertain writes must
  be reconciled using get_protocol/get_run. Power-loss-proof durability is not claimed.
- Win32 checks reject UNC/device/drive-relative/alternate-stream paths, reserved
  names, trailing-dot/space aliases, reparse points (including junctions), hard-linked
  input files, redirected drives and non-NTFS/removable/network volumes. Full paths
  must stay below 248 characters. Host/owner is trusted; this is not a race-proof
  namespace sandbox or protection from an administrator rewriting evidence.
- Windows worker launches inside an owned kill-on-close Job Object atomically via
  JOB_LIST, with an explicit inherited stdin/stdout/stderr handle list. The job
  and workspace lock are not inherited. No breakaway or uncontained fallback exists.
- Windows cancellation forcibly terminates that tree. Partial evidence remains;
  interrupted reserved IDs never automatically rerun. Job cleanup is bounded and
  cleanup timeouts become errors, never native/scientific success. Controller death
  cannot write a terminal receipt; reconciliation reports incomplete/unknown.
- Limits are sampled storage/output bounds and two-processor runtime hints, not
  an OS memory sandbox. Windows locks/ACLs/API layouts must pass actual runtime
  gates; Linux mocks are insufficient evidence.

## Round26 correction

The supplied Windows CI logs failed the original 18-check gate. Round26 fixes
a cleanup-completion race and replaces the PowerShell ACL test probe with a
read-only .NET helper. See [repair and owner rerun](ROUND26_WINDOWS_GATE_REPAIR.md).
The new 21-check gate includes three additional portable ordering/deadline tests;
all fourteen Windows-only checks still must execute, without skips.

## Owner-run acceptance gate

1. Inspect and commit this source to your repository using your own normal workflow.
2. GitHub Actions: choose **Manual Windows workflow acceptance**, Run workflow, select that
   commit/branch. The dispatch-only matrix targets windows-2022 and windows-2025,
   uses read-only repository permission, no secrets and no release/publish step.
   The Win32 gate requires exactly 21 tests and zero skips, so an all-skipped suite
   cannot produce a green runtime gate. Action versions are exact release tags
   verified against official release pages (checkout/setup-python 7.0.0,
   setup-dotnet/upload-artifact 6.0.0); tags are not full commit-SHA pins.
3. Download both acceptance artifacts. Check native counts, real Windows tests,
   parity results and logs; failure or skip must not be interpreted as support.
4. Keep Windows runtime status pending until both gates are reviewed. Then do a
   synthetic stdio smoke from the actual Windows 11 agent host. Supply error logs
   without private study data if it fails.

The local commands and exact current results are in the accompanying Russian report
and `validation/round23-results.json`. Manual CI provides an execution route; it
has not been dispatched by this work.

Official API references:
- [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [Process attributes / JOB_LIST and HANDLE_LIST](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute)
- [CreateFile flags](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilea)
- [GitHub-hosted Windows runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

Verified action release references (2026-10-15):
- https://github.com/actions/checkout/releases/tag/v7.0.0
- https://github.com/actions/setup-python/releases/tag/v7.0.0
- https://github.com/actions/setup-dotnet/releases/tag/v6.0.0
- https://github.com/actions/upload-artifact/releases/tag/v6.0.0
