"""Explicit source-contract revisions; never silently skip a protected file."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def expected_source_hash(name, historical_hash):
    revisions = json.loads((ROOT / 'validation/checkpoint-source-baseline.json').read_text())['sha256']
    if name not in revisions:
        return historical_hash
    revision = revisions[name]
    assert revision['originalSha256'] == historical_hash, name
    assert len(revision['sha256']) == 64, name
    return revision['sha256']
