#!/usr/bin/env python3
"""CI-only native preflight of peer-host synthetic fixtures. Requires a built CLI."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixtures', type=Path)
    parser.add_argument('dll', type=Path)
    args = parser.parse_args()
    host = shutil.which('dotnet')
    if not host or not args.dll.is_file():
        parser.error('A .NET host and built CLI are required; this is not an offline Python test.')
    folders = [args.fixtures / name for name in ('builtin', 'custom')]
    for folder in folders:
        expected = (folder / 'expected-settings.sha256').read_text(encoding="utf-8-sig").strip()
        for name in ('portable.json', 'legacy-lf.json', 'legacy-crlf.json'):
            with tempfile.TemporaryDirectory() as temporary:
                state = Path(temporary) / 'calibration_state.json'
                shutil.copyfile(folder / name, state)
                command = [host, str(args.dll.resolve()), 'state-check', '--calibration', str(state),
                           '--in', str((folder / 'data.csv').resolve()), '--job', str((folder / 'job.json').resolve()),
                           '--normalize', '--settings-hash', expected, '--repetitions', '150']
                subprocess.run(command, check=True)
                assert b'\r\n' not in state.read_bytes(), 'Normalized file still has CRLF formatting'
                assert json.loads(state.read_text(encoding="utf-8-sig"))['SettingsHash'] == expected
                text = state.read_text(encoding="utf-8-sig")
                assert '"Dataset": "data.csv"' in text
                state.write_text(text.replace('"Dataset": "data.csv"', '"Dataset": "tampered.csv"'))
                before = state.read_bytes()
                failed = subprocess.run(command, check=False)
                assert failed.returncode != 0, 'Tampered state passed native verification'
                assert state.read_bytes() == before, 'Failed checksum was silently re-signed'
    print('Native cross-platform state/job preflight and tamper rejection passed.')


if __name__ == '__main__':
    main()
