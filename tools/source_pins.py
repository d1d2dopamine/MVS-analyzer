"""Explicit reviewed source revisions; integrity checks, not scientific validation.

Historical manifests remain immutable anchors. Expected hashes are literal review
records: this module never derives an expected hash from a production source file.
A local owner can edit code and manifests together; this is not tamper-proof proof.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parents[1]
_HEX = re.compile(r"[0-9a-f]{64}\Z")


class SourcePinError(ValueError):
    """Missing, malformed, or inconsistent reviewed pin contract."""


def _require(condition, message):
    if not condition:
        raise SourcePinError(message)


def _pairs(items):
    result = {}
    for key, value in items:
        _require(key not in result, "Duplicate manifest key: " + key)
        result[key] = value
    return result


def _read(name):
    try:
        raw = (ROOT / 'validation' / name).read_bytes()
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(SourcePinError('Nonfinite manifest value')))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SourcePinError('Cannot read source pin manifest: ' + name) from error
    _require(type(value) is dict, 'Manifest must be an object: ' + name)
    return raw, value


def _hash(value, label):
    _require(type(value) is str and _HEX.fullmatch(value) is not None, 'Invalid SHA256: ' + label)


def _path(value):
    _require(type(value) is str and value and '\\' not in value and ':' not in value and all(ord(char) >= 32 and ord(char) != 127 for char in value),
             'Invalid source path')
    path = PurePosixPath(value)
    _require(bool(path.parts) and not path.is_absolute() and str(path) == value and
             all(part not in ('.', '..') for part in path.parts), 'Noncanonical source path: ' + value)


def _contract():
    original_raw, original = _read('ui-patch-baseline.json')
    previous_raw, previous = _read('checkpoint-source-baseline.json')
    reviewed_raw, reviewed = _read('source-pin-revisions-v2.json')
    anchors = original.get('sha256')
    old = previous.get('sha256')
    _require(type(anchors) is dict and bool(anchors), 'Missing historical source anchors')
    _require(type(old) is dict, 'Missing prior revision mapping')
    for name, digest in anchors.items():
        _path(name)
        _hash(digest, name)
    expected = dict(anchors)
    for name, revision in old.items():
        _path(name)
        _require(name in anchors and type(revision) is dict, 'Unknown prior revision: ' + name)
        _hash(revision.get('originalSha256'), name + ' original')
        _hash(revision.get('sha256'), name + ' previous')
        _require(revision['originalSha256'] == anchors[name], 'Prior original anchor mismatch: ' + name)
        expected[name] = revision['sha256']
    _require(set(reviewed) == {'schema', 'stage', 'note', 'historicalManifestSha256',
                              'previousRevisionManifestSha256', 'revisions'}, 'Unexpected reviewed manifest fields')
    _require(reviewed['schema'] == 'mvs-source-pin-revisions/v2' and
             type(reviewed['stage']) is int and reviewed['stage'] == 35, 'Unsupported reviewed manifest version')
    _require(type(reviewed['note']) is str and bool(reviewed['note'].strip()), 'Missing review scope')
    for key, raw in [('historicalManifestSha256', original_raw),
                     ('previousRevisionManifestSha256', previous_raw)]:
        _hash(reviewed[key], key)
        _require(reviewed[key] == hashlib.sha256(raw).hexdigest(), 'Historical manifest bytes changed: ' + key)
    revisions = reviewed['revisions']
    _require(type(revisions) is dict and bool(revisions), 'Missing reviewed revisions')
    for name, revision in revisions.items():
        _path(name)
        _require(name in anchors and type(revision) is dict, 'Unknown reviewed source: ' + name)
        _require(set(revision) == {'originalSha256', 'previousSha256', 'sha256', 'review'},
                 'Unexpected reviewed entry fields: ' + name)
        for field in ('originalSha256', 'previousSha256', 'sha256'):
            _hash(revision[field], name + ' ' + field)
        _require(revision['originalSha256'] == anchors[name], 'Reviewed original anchor mismatch: ' + name)
        _require(revision['previousSha256'] == expected[name], 'Broken prior revision chain: ' + name)
        _require(revision['sha256'] != expected[name], 'Redundant reviewed revision: ' + name)
        review = revision['review']
        _require(type(review) is dict and set(review) == {'completeness', 'stages', 'reason', 'evidence', 'limitation'},
                 'Missing structured review: ' + name)
        _require(review['completeness'] in ('complete-retained-chain', 'reviewed-current-with-historical-gap'),
                 'Unknown provenance completeness: ' + name)
        _require(type(review['stages']) is list and bool(review['stages']) and
                 all(type(stage) is int and 1 <= stage <= 35 for stage in review['stages']), 'Invalid review stages: ' + name)
        _require(type(review['evidence']) is list and bool(review['evidence']), 'Missing review evidence: ' + name)
        for path in review['evidence']:
            _path(path)
        for field in ('reason', 'limitation'):
            _require(type(review[field]) is str and bool(review[field].strip()), 'Missing review ' + field + ': ' + name)
        expected[name] = revision['sha256']
    # Round36 is a required successor, never a fallback to the current source.
    # Validate v2 completely before v3 so earlier review checks remain effective.
    successor_raw, successor = _read('source-pin-revisions-v3.json')
    _require(set(successor) == {'schema', 'stage', 'note',
                                'previousReviewedManifestSha256', 'revisions'},
             'Unexpected successor manifest fields')
    _require(successor['schema'] == 'mvs-source-pin-revisions/v3' and
             type(successor['stage']) is int and successor['stage'] == 36,
             'Unsupported successor manifest version')
    _require(type(successor['note']) is str and bool(successor['note'].strip()),
             'Missing successor review scope')
    _hash(successor['previousReviewedManifestSha256'], 'previousReviewedManifestSha256')
    _require(successor['previousReviewedManifestSha256'] == hashlib.sha256(reviewed_raw).hexdigest(),
             'Reviewed v2 manifest bytes changed')
    updates = successor['revisions']
    _require(type(updates) is dict and bool(updates), 'Missing successor revisions')
    for name, revision in updates.items():
        _path(name)
        _require(name in revisions and type(revision) is dict, 'Unknown successor source: ' + name)
        _require(set(revision) == {'originalSha256', 'previousSha256', 'sha256', 'review'},
                 'Unexpected successor entry fields: ' + name)
        for field in ('originalSha256', 'previousSha256', 'sha256'):
            _hash(revision[field], name + ' ' + field)
        _require(revision['originalSha256'] == anchors[name], 'Successor original anchor mismatch: ' + name)
        _require(revision['previousSha256'] == expected[name], 'Broken successor revision chain: ' + name)
        _require(revision['sha256'] != expected[name], 'Redundant successor revision: ' + name)
        review = revision['review']
        _require(type(review) is dict and set(review) == {'completeness', 'transitionCompleteness',
                                                         'stages', 'reason', 'evidence', 'limitation'},
                 'Missing structured successor review: ' + name)
        _require(review['completeness'] == revisions[name]['review']['completeness'],
                 'Successor historical completeness changed: ' + name)
        _require(review['transitionCompleteness'] == 'complete-reviewed-transition',
                 'Incomplete successor transition review: ' + name)
        _require(type(review['stages']) is list and review['stages'] == [36] and
                 type(review['stages'][0]) is int,
                 'Invalid successor review stages: ' + name)
        _require(type(review['evidence']) is list and bool(review['evidence']),
                 'Missing successor review evidence: ' + name)
        for path in review['evidence']:
            _path(path)
        _require(len(set(review['evidence'])) == len(review['evidence']),
                 'Duplicate successor review evidence: ' + name)
        for field in ('reason', 'limitation'):
            _require(type(review[field]) is str and bool(review[field].strip()),
                     'Missing successor review ' + field + ': ' + name)
        expected[name] = revision['sha256']
    # Round38 can revise any anchored source, including a source whose most
    # recent retained review is the original or checkpoint layer, not v2/v3.
    # Always compare against the effective map after validating every old layer.
    _, round38 = _read('source-pin-revisions-v4.json')
    _require(set(round38) == {'schema', 'stage', 'note',
                              'previousReviewedManifestSha256', 'revisions'},
             'Unexpected Round38 manifest fields')
    _require(round38['schema'] == 'mvs-source-pin-revisions/v4' and
             type(round38['stage']) is int and round38['stage'] == 38,
             'Unsupported Round38 manifest version')
    _require(type(round38['note']) is str and bool(round38['note'].strip()),
             'Missing Round38 review scope')
    _hash(round38['previousReviewedManifestSha256'], 'previousReviewedManifestSha256')
    _require(round38['previousReviewedManifestSha256'] == hashlib.sha256(successor_raw).hexdigest(),
             'Reviewed v3 manifest bytes changed')
    round38_updates = round38['revisions']
    _require(type(round38_updates) is dict and bool(round38_updates), 'Missing Round38 revisions')
    for name, revision in round38_updates.items():
        _path(name)
        _require(name in anchors and type(revision) is dict, 'Unknown Round38 source: ' + name)
        _require(set(revision) == {'originalSha256', 'previousSha256', 'sha256', 'review'},
                 'Unexpected Round38 entry fields: ' + name)
        for field in ('originalSha256', 'previousSha256', 'sha256'):
            _hash(revision[field], name + ' ' + field)
        _require(revision['originalSha256'] == anchors[name], 'Round38 original anchor mismatch: ' + name)
        _require(revision['previousSha256'] == expected[name], 'Broken Round38 revision chain: ' + name)
        _require(revision['sha256'] != expected[name], 'Redundant Round38 revision: ' + name)
        review = revision['review']
        _require(type(review) is dict and set(review) == {'completeness', 'transitionCompleteness',
                                                         'stages', 'reason', 'evidence', 'limitation'},
                 'Missing structured Round38 review: ' + name)
        # No older gap is erased. Direct original/checkpoint transitions have
        # no v2/v3 gap label; their retained applicable anchor is sufficient.
        previous_review = updates.get(name, revisions.get(name))
        completeness = (previous_review['review']['completeness'] if previous_review is not None
                        else 'complete-retained-chain')
        _require(review['completeness'] == completeness,
                 'Round38 historical completeness changed: ' + name)
        _require(review['transitionCompleteness'] == 'complete-reviewed-transition',
                 'Incomplete Round38 transition review: ' + name)
        _require(type(review['stages']) is list and review['stages'] == [38] and
                 type(review['stages'][0]) is int,
                 'Invalid Round38 review stages: ' + name)
        _require(type(review['evidence']) is list and bool(review['evidence']),
                 'Missing Round38 review evidence: ' + name)
        for path in review['evidence']:
            _path(path)
        _require(len(set(review['evidence'])) == len(review['evidence']),
                 'Duplicate Round38 review evidence: ' + name)
        for field in ('reason', 'limitation'):
            _require(type(review[field]) is str and bool(review[field].strip()),
                     'Missing Round38 review ' + field + ': ' + name)
        expected[name] = revision['sha256']
    return anchors, expected


def expected_source_hash(name, historical_hash):
    """Resolve one known source through fully validated historical/reviewed layers."""
    anchors, expected = _contract()
    _path(name)
    _hash(historical_hash, 'caller historical hash')
    _require(name in anchors, 'Unknown requested source: ' + name)
    _require(historical_hash == anchors[name], 'Caller original anchor mismatch: ' + name)
    return expected[name]
