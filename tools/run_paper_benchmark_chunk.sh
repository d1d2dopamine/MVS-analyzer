#!/usr/bin/env bash
set -euo pipefail

# One bounded segment of the frozen historical benchmark. Inputs are read-only;
# output directories must be new or empty. Never reset or delete a destination.
if [[ $# -lt 1 || $# -gt 4 ]]; then
  echo 'usage: run_paper_benchmark_chunk.sh <chunk-number> [incoming-dir] [state-dir] [work-dir]' >&2
  exit 1
fi
chunk="$1"
incoming="${2-}"
state="${3-paper-benchmark-state}"
work="${4-paper-benchmark-work}"
profile="${MVS_BENCH_PROFILE-full}"
seed="${MVS_BENCH_SEED-20260904}"
threads="${MVS_BENCH_THREADS-$(nproc)}"
chunk_seconds="${MVS_BENCH_CHUNK_SECONDS-19000}"
source_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
paths="$source_root/tools/paper_benchmark_paths.py"
verifier="$source_root/tools/verify_paper_benchmark.py"

# No mkdir/copy/truncation occurs until all input and identity checks pass.
checked="$(python3 "$paths" preflight --chunk="$chunk" --incoming="$incoming" \
  --state="$state" --work="$work" --profile="$profile" --seed="$seed" \
  --threads="$threads" --seconds="$chunk_seconds")"
mapfile -t selected <<< "$checked"
incoming="${selected[0]}"; state="${selected[1]}"; work="${selected[2]}"
previous_result="${selected[3]-}"; resume_archive="${selected[4]-}"
if ! current_commit="$(git -C "$source_root" rev-parse HEAD)"; then
  echo 'Cannot read source Git identity; use a verified source checkout. No output was changed.' >&2
  exit 1
fi
python3 "$paths" provenance --incoming="$incoming" --commit="$current_commit"
if [[ -z "$previous_result" ]]; then
  python3 "$verifier" --check-source "$source_root"
fi

mkdir -p -- "$state" "$work/results" "$work/backups"
if [[ -n "$incoming" ]]; then
  find "$incoming" -maxdepth 1 -type f \( -name 'chunk-*.log' -o -name 'chunk-*.txt' \) -exec cp -a -- {} "$state/" \;
fi
# Retain the incoming checkpoint even if the CLI fails before writing a new one.
if [[ -n "$resume_archive" ]]; then
  cp -a -- "$resume_archive" "$state/MVS_Backups.zip"
fi
provenance="$state/chunk-${chunk}.txt"
if [[ -n "$previous_result" ]]; then
  cp -a -- "$previous_result" "$state/result"
  python3 "$verifier" "$state/result"
  printf 'chunk=%s\naction=pass-through\ncommit=%s\n' "$chunk" "$current_commit" > "$provenance"
  printf 'complete\n' > "$state/status.txt"
  exit 0
fi

export MVS_BACKUP_DIR="$work/backups"
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_NOLOGO=1
log="$state/chunk-${chunk}.log"
{
  printf 'chunk=%s\ncommit=%s\n' "$chunk" "$current_commit"
  printf 'describe=%s\n' "$(git -C "$source_root" describe --tags --always --dirty)"
  printf 'profile=%s\nseed=%s\nthreads=%s\nchunk_seconds=%s\n' "$profile" "$seed" "$threads" "$chunk_seconds"
  printf 'utc_started=%s\ncpu_count=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(nproc)"
} > "$provenance"
if [[ -n "$resume_archive" ]]; then
  cp -a -- "$resume_archive" "$work/incoming-backups.zip"
  command=(dotnet "$source_root/publish/cli/mvs.dll" resume --in "$work/incoming-backups.zip" --out "$work/results")
  printf 'action=resume\n' >> "$provenance"
else
  command=(dotnet "$source_root/publish/cli/mvs.dll" benchmark --profile "$profile" --seed "$seed" --threads "$threads" --out "$work/results")
  printf 'action=start\n' >> "$provenance"
fi

set +e
timeout --signal=INT --kill-after=120 "${chunk_seconds}s" "${command[@]}" 2>&1 | tee "$log"
statuses=("${PIPESTATUS[@]}")
set -e
code="${statuses[0]}"
printf 'command_exit_code=%s\nutc_finished=%s\n' "$code" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$provenance"
# Export a newly written checkpoint on every exit, including technical failure.
# The original incoming archive and the work directory are never removed.
if [[ -f "$MVS_BACKUP_DIR/MVS_Backups.zip" && ! -L "$MVS_BACKUP_DIR/MVS_Backups.zip" ]]; then
  if [[ -n "$resume_archive" ]]; then cp -a -- "$resume_archive" "$state/incoming-backups.zip"; fi
  cp -a -- "$MVS_BACKUP_DIR/MVS_Backups.zip" "$state/MVS_Backups.zip"
fi
if [[ "${statuses[1]}" -ne 0 ]]; then
  echo 'Benchmark log could not be saved; outputs/checkpoints retained, completion not certified.' >&2
  exit 1
fi
if [[ "$code" -ne 0 && "$code" -ne 2 && "$code" -ne 124 ]]; then
  echo "Benchmark command returned unexpected exit code $code; outputs/checkpoints retained." >&2
  exit 1
fi
result_dir="$(python3 "$paths" result "$work/results")"
if [[ -n "$result_dir" ]]; then
  # A planned timeout with a manifest is still incomplete execution.
  if [[ "$code" -eq 124 ]]; then
    echo 'A result exists but the command timed out; completion not certified. Checkpoints retained.' >&2
    exit 1
  fi
  cp -a -- "$result_dir" "$state/result"
  python3 "$verifier" "$state/result"
  printf 'status=complete\n' >> "$provenance"
  printf 'complete\n' > "$state/status.txt"
  # Exit 2 is a verified scientific NO-GO, not an execution failure.
  exit 0
fi
if [[ "$code" -ne 124 ]]; then
  echo "Benchmark stopped without a verified result (exit $code); checkpoints retained." >&2
  exit 1
fi
if [[ ! -f "$MVS_BACKUP_DIR/MVS_Backups.zip" || -L "$MVS_BACKUP_DIR/MVS_Backups.zip" ]]; then
  echo 'Timed segment produced no portable checkpoint archive; incoming checkpoint retained.' >&2
  exit 1
fi
printf 'status=incomplete_checkpoint_saved\n' >> "$provenance"
printf 'incomplete\n' > "$state/status.txt"
