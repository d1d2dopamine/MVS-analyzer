#!/usr/bin/env bash
set -euo pipefail

# Run one bounded GitHub Actions segment of the frozen paper benchmark.
# A completed benchmark is passed through unchanged. An incomplete segment
# exports MVS_Backups.zip so the next job can resume at completed-unit boundaries.

chunk="${1:?usage: run_paper_benchmark_chunk.sh <chunk-number> [incoming-dir] [state-dir] [work-dir]}"
incoming="${2:-}"
state="${3:-paper-benchmark-state}"
work="${4:-paper-benchmark-work}"

profile="${MVS_BENCH_PROFILE:-full}"
seed="${MVS_BENCH_SEED:-20260904}"
threads="${MVS_BENCH_THREADS:-$(nproc)}"
chunk_seconds="${MVS_BENCH_CHUNK_SECONDS:-19000}"

rm -rf "$state" "$work"
mkdir -p "$state" "$work/results" "$work/backups"

# Preserve logs and provenance from earlier segments, and refuse to mix source revisions.
if [[ -n "$incoming" && -d "$incoming" ]]; then
  current_commit="$(git rev-parse HEAD)"
  while IFS= read -r provenance_file; do
    prior_commit="$(sed -n 's/^commit=//p' "$provenance_file" | head -n 1)"
    if [[ -n "$prior_commit" && "$prior_commit" != "$current_commit" ]]; then
      echo "Incoming checkpoint was produced by commit $prior_commit, current commit is $current_commit." >&2
      exit 1
    fi
  done < <(find "$incoming" -maxdepth 1 -type f -name 'chunk-*.txt' -print | sort)
  find "$incoming" -maxdepth 1 -type f \( -name 'chunk-*.log' -o -name 'chunk-*.txt' \) -exec cp -a {} "$state/" \;
fi

# If an earlier segment already finished, do not calculate anything again.
if [[ -n "$incoming" && -d "$incoming" ]]; then
  previous_manifest="$(find "$incoming" -type f -name benchmark_manifest.json -print -quit)"
  if [[ -n "$previous_manifest" ]]; then
    previous_result="$(dirname "$previous_manifest")"
    rm -rf "$state/result"
    cp -a "$previous_result" "$state/result"
    if [[ -f "$incoming/MVS_Backups.zip" ]]; then cp -a "$incoming/MVS_Backups.zip" "$state/"; fi
    printf 'complete\n' > "$state/status.txt"
    printf 'chunk=%s\naction=pass-through\ncommit=%s\n' "$chunk" "$(git rev-parse HEAD)" > "$state/chunk-${chunk}.txt"
    exit 0
  fi
fi

export MVS_BACKUP_DIR="$work/backups"
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_NOLOGO=1

log="$state/chunk-${chunk}.log"
provenance="$state/chunk-${chunk}.txt"

{
  printf 'chunk=%s\n' "$chunk"
  printf 'commit=%s\n' "$(git rev-parse HEAD)"
  printf 'describe=%s\n' "$(git describe --tags --always --dirty)"
  printf 'profile=%s\nseed=%s\nthreads=%s\nchunk_seconds=%s\n' "$profile" "$seed" "$threads" "$chunk_seconds"
  printf 'utc_started=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'cpu_count=%s\n' "$(nproc)"
} > "$provenance"

resume_archive=""
if [[ -n "$incoming" && -d "$incoming" ]]; then
  resume_archive="$(find "$incoming" -type f -name MVS_Backups.zip -print -quit)"
fi

if [[ -n "$resume_archive" ]]; then
  cp -a "$resume_archive" "$work/incoming-backups.zip"
  command=(dotnet publish/cli/mvs.dll resume --in "$work/incoming-backups.zip" --out "$work/results")
  printf 'action=resume\n' >> "$provenance"
else
  command=(dotnet publish/cli/mvs.dll benchmark --profile "$profile" --seed "$seed" --threads "$threads" --out "$work/results")
  printf 'action=start\n' >> "$provenance"
fi

set +e
timeout --signal=INT --kill-after=120 "${chunk_seconds}s" "${command[@]}" 2>&1 | tee "$log"
code=${PIPESTATUS[0]}
set -e

printf 'command_exit_code=%s\n' "$code" >> "$provenance"
printf 'utc_finished=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$provenance"

manifest="$(find "$work/results" -type f -name benchmark_manifest.json -print -quit)"
if [[ -n "$manifest" ]]; then
  result_dir="$(dirname "$manifest")"
  rm -rf "$state/result"
  cp -a "$result_dir" "$state/result"
  if [[ -f "$MVS_BACKUP_DIR/MVS_Backups.zip" ]]; then cp -a "$MVS_BACKUP_DIR/MVS_Backups.zip" "$state/"; fi
  printf 'complete\n' > "$state/status.txt"
  printf 'status=complete\n' >> "$provenance"
  # Exit code 2 is a scientific no-go verdict, not an execution failure.
  if [[ "$code" -ne 0 && "$code" -ne 2 ]]; then
    echo "A result manifest exists, but the benchmark command returned unexpected exit code $code." >&2
    exit 1
  fi
  exit 0
fi

# GNU timeout returns 124 when the time budget expired. That is an expected
# checkpoint boundary. Other early exits are treated as technical failures.
if [[ "$code" -ne 124 ]]; then
  echo "Benchmark stopped before producing a result (exit $code), and it was not the planned timeout." >&2
  exit 1
fi

if [[ ! -f "$MVS_BACKUP_DIR/MVS_Backups.zip" ]]; then
  echo "Timed segment produced no portable checkpoint archive." >&2
  exit 1
fi

cp -a "$MVS_BACKUP_DIR/MVS_Backups.zip" "$state/"
printf 'incomplete\n' > "$state/status.txt"
printf 'status=incomplete_checkpoint_saved\n' >> "$provenance"
