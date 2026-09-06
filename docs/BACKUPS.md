# Backups and offline continuation

MVS automatically creates portable checkpoints during benchmark, calibration, summary analysis, variance-component analysis, known-truth estimation and MELSM calculations.

## One folder, one complete archive

- Windows: `%LOCALAPPDATA%\MVS_Analyzer\MVS_Backups`.
- Colab: `/content/MVS_Backups`.
- Each operation has a `.mvsbackup` file and a previous snapshot in that same folder. There are no per-operation backup subfolders.
- `MVS_Backups.zip` contains all those files. Temporary files are replaced atomically and are not included in the ZIP.
- Use **Data → Open backups folder** or **Save all backups as ZIP** in MVS. In Colab the complete ZIP is also available from the Files pane.

Backups contain the data used by the calculation, settings, seeds and completed computational units. They are not anonymous reports. Keep them private and do not commit them to a repository. They contain no connection codes and cannot execute arbitrary commands. Checksums detect corruption, not forgery: import backups only from a trusted source.

## Protecting work from a Colab shutdown

Keep the updated MVS application and its Colab browser tab connected. The controller automatically sends changed checkpoints to the desktop. **“Backup copied to MVS / Бэкап сохранён на компьютере”** is printed only after the desktop acknowledges a successful save. The desktop retains that copy even if Google subsequently deletes the runtime.

A backup stored only under `/content` will disappear with the runtime. If the connection is broken, the desktop retains its last received checkpoint; newer work is not protected until a transfer succeeds. An older desktop without backup support receives no backup payload and the notebook prints a warning. Manual/offline notebook mode has no automatic external mirror: download the backup separately before losing the runtime. MVS does not mount Google Drive or obtain extra credentials automatically.

## Continue offline

1. Stop the original calculation, if it is still alive.
2. Open **Data → Load backup and continue / Загрузить бэкап и продолжить**.
3. Choose one `.mvsbackup` or the complete `MVS_Backups.zip`.
4. If the archive contains several checkpoints, choose the operation and snapshot. Newest snapshots are listed first.
5. Confirm **“Continue from the last saved checkpoint? / Продолжить с места, на котором остановились?”** and choose a result destination.

Results go into a new folder; existing result files are not overwritten. Restored calibration/summary results are also loaded into the usual MVS workflow. Other methods produce their ordinary reports and tables. Input observations are already imported and filtered, so an external CSV parsing plugin is not required for continuation. Original processing information remains in the backup/provenance record.

CLI alternative:

```sh
mvs resume --in MVS_Backups.zip --out results
# If several operations are present:
mvs resume --in MVS_Backups.zip --out results --id <backup-id>
```

## Checkpoint boundaries and limits

Checkpoint writes are throttled to approximately 15 seconds and occur at safe completed-unit boundaries, not by copying the entire process memory. The initial request is saved before expensive work. Completion and cooperative cancellation also flush the latest safe state.

- Benchmark: completed outer replications, pilots and stability comparisons. Its two determinism passes use separate checkpoint keys, so replay is not certified by simply reading the same cached answer twice.
- Calibration: simulation repetitions and per-metric diagnostic rows.
- Summary analysis: completed metric rows; candidate labels are recomputed from the restored rows.
- Variance components: fitted models, interval/reference/evaluation bootstrap units.
- Estimation study: outer replications, each including its entity bootstrap.
- MELSM: fitted stages and the full Nelder–Mead simplex at iteration boundaries. An interrupted likelihood evaluation may be repeated; final information-matrix/prediction assembly may also be repeated.

A slow indivisible unit can take longer than 15 seconds. Abrupt termination loses work after the last durable snapshot, and a delayed transfer can make the desktop copy older still. A running unit is repeated; completed saved units are reused. This is not an operating-system memory dump or a guarantee of zero lost seconds.

Individual expanded snapshots are limited to 64 MiB; collections to 512 entries and 512 MiB on import/export (including a separate expanded-JSON import limit). Move older backups elsewhere when the collection is full. A save error is visible rather than silently claiming protection. The previous snapshot is retained.

The backup schema, implementation identifier, engine, formula and benchmark protocol must match. Changing settings is a new analysis, not continuation. Portability does not guarantee bit-identical arithmetic across operating systems/CPU runtimes; resume provenance records environments and the retained-unit count. Resumed benchmark duration describes the final execution segment, not all previous work. Scientific assumptions and experimental-model limitations remain unchanged.

These backups protect calculations started with this implementation. They cannot reconstruct an old interrupted run that never wrote checkpoints.

## Validation

`python tools/test_backups.py` checks offline Python transport, acknowledgements, job separation and UI/source contracts. `MvsAnalyzer.Core.Tests/BackupChecks.cs` exercises native interruption/resumption and archive validation in the Windows/Linux CI harness. Passing transport/static checks is not a substitute for compiling and running the native tests or testing a live Colab session.
