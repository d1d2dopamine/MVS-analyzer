"""Convert PhysioNet gait recordings into the CSV shape MVS Analyzer reads.

The archive cannot ship the recordings themselves, so it ships the converter instead.
Only the Python standard library is used, matching the application's own rule of not
taking on dependencies that later need version babysitting.

Source:
    Gait in Neurodegenerative Disease Database (gaitndd), version 1.0.0
    https://physionet.org/content/gaitndd/1.0.0/
    Licence: Open Data Commons Attribution License v1.0

Each .ts file holds one walk, sampled twice per second, with these columns:
    1  elapsed time (s)
    2  left stride interval (s)   <- what this script keeps
    3  right stride interval (s)
    4  left swing interval (s)
    5  right swing interval (s)
    ... and further swing/stance columns that are not used here.

Usage:
    python prepare_physionet.py --out .
    python prepare_physionet.py --out . --cohort control
    python prepare_physionet.py --out . --local ./downloaded_ts_files

The result is one CSV per run with the columns the program expects:
    entity,group,value,sequence,variable,unit
"""

import argparse
import csv
import os
import sys
import urllib.request

BASE_URL = "https://physionet.org/files/gaitndd/1.0.0/"

COHORTS = {
    "control": 16,
    "park": 15,
    "hunt": 20,
    "als": 13,
}

STRIDE_COLUMN = 1  # zero-based: column 2 of the file, the left stride interval
MIN_STRIDE = 0.2   # seconds; anything outside this window is a detector artefact
MAX_STRIDE = 3.0


def file_names(cohort):
    return [cohort + str(index) + ".ts" for index in range(1, COHORTS[cohort] + 1)]


def read_local(folder, name):
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def download(name):
    url = BASE_URL + name + "?download"
    request = urllib.request.Request(url, headers={"User-Agent": "mvs-benchmark-prepare/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def parse(text):
    """Return the usable left stride intervals of one recording, in order."""
    values = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.replace(",", " ").split()
        if len(parts) <= STRIDE_COLUMN:
            continue
        try:
            value = float(parts[STRIDE_COLUMN])
        except ValueError:
            continue
        if MIN_STRIDE <= value <= MAX_STRIDE:
            values.append(value)
    return values


def collect(cohorts, local, verbose=True):
    rows = []
    kept = 0
    skipped = []
    for cohort in cohorts:
        for name in file_names(cohort):
            text = read_local(local, name) if local else None
            if text is None:
                if local:
                    skipped.append(name + " (not in the local folder)")
                    continue
                try:
                    text = download(name)
                except Exception as error:  # noqa: BLE001 - the reason is printed, not swallowed
                    skipped.append(name + " (" + str(error) + ")")
                    continue
            values = parse(text)
            if len(values) < 40:
                skipped.append(name + " (only " + str(len(values)) + " usable strides)")
                continue
            entity = os.path.splitext(name)[0]
            for sequence, value in enumerate(values, start=1):
                rows.append((entity, cohort, value, sequence, "stride_interval", "s"))
            kept += 1
            if verbose:
                print("  " + entity.ljust(12) + str(len(values)).rjust(5) + " strides")
    return rows, kept, skipped


def write(rows, path):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["entity", "group", "value", "sequence", "variable", "unit"])
        for entity, group, value, sequence, variable, unit in rows:
            writer.writerow([entity, group, format(value, ".4f"), sequence, variable, unit])


def main():
    parser = argparse.ArgumentParser(description="Prepare PhysioNet gaitndd recordings for the MVS benchmark.")
    parser.add_argument("--out", default=".", help="folder the CSV is written to")
    parser.add_argument("--cohort", choices=sorted(COHORTS) + ["all"], default="all",
                        help="which cohort to convert; 'all' writes every cohort into one file")
    parser.add_argument("--local", default="", help="folder of already downloaded .ts files, used instead of the network")
    parser.add_argument("--name", default="", help="output file name; a sensible default is used when omitted")
    arguments = parser.parse_args()

    cohorts = sorted(COHORTS) if arguments.cohort == "all" else [arguments.cohort]
    print("Preparing: " + ", ".join(cohorts))
    if not arguments.local:
        print("Downloading from " + BASE_URL)
        print("By using these recordings you accept the ODC-BY 1.0 attribution terms of the source database.")

    rows, kept, skipped = collect(cohorts, arguments.local)
    if not rows:
        print("Nothing was converted. Check the network, or pass --local with the downloaded .ts files.")
        return 1

    name = arguments.name or ("gaitndd_" + ("all" if arguments.cohort == "all" else arguments.cohort) + "_stride_left.csv")
    os.makedirs(arguments.out, exist_ok=True)
    path = os.path.join(arguments.out, name)
    write(rows, path)

    print()
    print("Recordings kept : " + str(kept))
    print("Measurements    : " + str(len(rows)))
    print("Written to      : " + path)
    if skipped:
        print("Skipped:")
        for item in skipped:
            print("  " + item)
    print()
    print("Point the benchmark at this folder: Settings -> Developer -> Folder with real recordings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
