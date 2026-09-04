# Running MVS Analyzer somewhere else

The window cannot follow the work. A calibration is thousands of simulations, and the honest
benchmark profiles take hours; on one laptop that means choosing between the analysis and using
the computer. This document describes the second route added in 1.5.0: the same engine, without a
window, on hardware you borrow.

Nothing here replaces the local run. The desktop application still performs the entire analysis
offline and always will. For measurements that must not leave a building, that remains the only
correct way to use this program.

## The short version

In the application, open **Settings** and find **Remote run**.

| Button | What happens |
| --- | --- |
| Colab: calibration and analysis | Opens a notebook with three cells: calibrate, analyse, download a zip of the results |
| Colab: benchmark | Opens a notebook that runs the pre-registered protocol; it invents its own data |
| Build a job archive | Packs a dataset together with every current setting, for uploading in the first cell |
| Kaggle | Opens Kaggle, where the notebook has to be imported by hand |

## What one click can and cannot do

A button cannot create a filled-in notebook in your account. There is no address that carries code
into Colab, and any service that could write into your Drive would need an access token that this
project has no business holding.

What does work, and what the button actually does, is the notebook deep link Colab provides for
public repositories:

```
https://colab.research.google.com/github/d1d2dopamine/MVS-Analyzer/blob/main/notebooks/MVS_Colab.ipynb
```

If you are already signed in, that opens a ready notebook in your own session, one click, no
setup. The notebook is an unsaved copy: nothing this project controls can touch your account, and
you can save it to your Drive yourself if you want to keep it.

The difference from "a notebook with all the files already in it" is where the files come from. The
source is not carried through the browser; the first cell fetches it with `git clone` and builds
the engine, which takes a minute or two on the first run of a session and is skipped afterwards.
Your data is not in the repository, so the first cell asks for it once, from your machine.

**This only works once `notebooks/` is pushed to the public repository.** Until then the button
opens a 404, because the address points at a file GitHub cannot serve yet. Nothing else in the
release depends on that push.

## The three cells

### 1. Calibration

A form: repetitions, seed, effect, scenario, alpha, split calibration. The cell fetches the source,
installs the .NET 8 build tools, compiles the headless engine, asks for your data, and calibrates.

Upload either a CSV or the job archive built by the application. The archive is worth preferring:
it carries the settings with it, so the remote run is *the same analysis* rather than a similar
one. A mistyped seed produces a number that looks like a result and is not one.

The calibration is written to disk as `calibration_state.json`. That matters in a hosted session,
which can be reclaimed at any time: losing one costs a cell, not the whole run.

### 2. Analysis

Applies the calibration and writes the tables, the report and the manifest. Settings are taken
from the calibration, not from the form, so the two phases cannot disagree.

The analysis refuses to run if the data no longer hashes to what the calibration was measured on.
A calibration is a statement about one dataset and is worthless attached to another. `--force`
exists for the case where you know why the bytes changed; both hashes go into the manifest.

### 3. Download

Packs everything into one zip and downloads it. The manifest inside records the formula hash, the
seed and the environment id, so a reviewer can check the remote run against a local one.

On Kaggle the archive appears under **Output** after **Save Version**, since browser downloads are
not available there.

## Be honest about the speed

A free Colab session gives out **two vCPUs**. A laptop with eight cores runs the benchmark on
seven of them. So for the quick profile a hosted session is likely to be **slower** than your own
machine, not faster.

What a session actually buys:

- **Twelve uninterrupted hours** on a machine you can walk away from.
- **Your computer stays yours** while the work runs.
- **Kaggle gives four vCPUs** and thirty hours a week, which is the better free option for the
  longer profiles.
- **No installation.** Somebody with a locked-down work computer can still reproduce a run.

If you need a genuine speed-up, the same `mvs` binary runs on any rented Linux machine, and
`--threads` will use every core it is given.

## The command line

```
mvs calibrate --in data.csv --out folder [--repetitions n] [--seed n] [--effect x]
                                         [--scenario location|decrease|variability]
                                         [--alpha x] [--split] [--job job.json]
mvs analyze   --in data.csv --calibration folder --out folder [--project name] [--force]
mvs benchmark --profile quick|standard|full --out folder [--seed n] [--threads n]
                                            [--real-data dir] [--lang en|ru] [--quiet]
mvs env
mvs version
```

Exit codes: `0` done, `2` a benchmark threshold was missed, `1` error. The middle one is a result,
not a crash, and continuous integration should treat it as such.

Get the binary from the release assets (`MVS_Analyzer_<version>_linux-x64-cli.zip`) or build it:

```
dotnet publish MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj -c Release -r linux-x64 -o out
```

## Figures are missing on Linux

`System.Drawing.Common` does not draw outside Windows, so `BenchmarkFigures.cs` and
`FigureGenerator.cs` are excluded from the headless project and the figure step becomes a no-op.
Every table, report and manifest is written as usual, and the images can be produced afterwards
from the same folder on a Windows machine.

The source files of the headless project are listed one by one rather than globbed, so the next
form somebody adds cannot quietly break the Linux build.

## Determinism has a scope now

The benchmark advertises bit-identical replay, and that claim is only true **inside one
environment**. Thread count cannot change a result: every replication owns its own random stream,
so the parallel loops give identical output however the work is scheduled. Floating point across
platforms is a different matter. `Math.Log`, `Math.Exp`, `Math.Pow` and `Math.Cos` are not required
to be correctly rounded, and .NET makes no promise that they agree across operating systems,
architectures or runtime versions. `Math.Sqrt` is the exception; it is exact by specification.

So every manifest now records three extra fields:

| Field | Meaning |
| --- | --- |
| `environment` | Operating system, architecture and runtime version, in words |
| `environmentHash` | A hash over the architecture, the runtime and a probe of those four functions |
| `determinismScope` | `withinEnvironment` |

When two determinism hashes disagree, compare the environment ids first. Same id and different
hash is a regression worth reporting. Different id is expected, and `mvs env` prints the exact
fingerprint so the difference can be diffed instead of guessed at.

The operating system build string is deliberately left out of the hash: a Windows patch changes it
without changing a single arithmetic result, and a hash that moves for cosmetic reasons teaches its
reader to ignore it.

## Privacy, plainly

The **benchmark** needs no data of yours. Every observation is generated from the seed, so running
it on borrowed hardware risks nothing. Without `--real-data` nothing of yours is read at all.

**Calibration and analysis** need your measurements, and uploading them to a hosted notebook means
they leave your computer and are processed on somebody else's. For identifiable or restricted
recordings that is usually not acceptable, whatever the terms of service say. In that case:

- run the analysis locally, which is what the window is for; or
- run `mvs` on a machine your institution controls, which is the same binary and the same numbers.

The application says this next to the buttons rather than in a document nobody opens.

## What is not here yet

- **Sharding across sessions.** `--threads` uses one machine. Splitting one benchmark across
  several sessions and merging the parts needs `--shard` and `merge`, which are planned for 1.6.0.
  It is not urgent: the quick profile fits inside a session with room to spare.
- **Resume.** A reclaimed session loses an unfinished benchmark. The calibration is checkpointed;
  the benchmark is not.
- **A Docker image and `mvs remote --ssh`.** Planned, and deliberately not an HTTP daemon: a
  network service that accepts medical measurements is a liability this project should not create.
