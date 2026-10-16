"""Synthetic unit tests only; never reads or executes the 200-case diagnostic."""
import copy
import hashlib
import struct
import unittest
from unittest.mock import patch
import replay_primary_rank_draws as r


class ReplayTests(unittest.TestCase):
    def test_existing_native_golden_stream(self):
        # Pre-existing MvsAnalyzer.Core.Tests/Program.cs BenchmarkRandomStream,
        # not generated from this Python implementation.
        rng = r.Random(20260904)
        self.assertEqual([rng.next64() for _ in range(5)], [8419501177352733710,
            9045835510591893074, 9237519410920844811, 9973926479834897958,
            14688187863013897198])

    def test_hand_state_transition(self):
        rng = r.Random(0)
        rng.state = [1, 2, 3, 4]
        self.assertEqual(rng.next64(), 11520)  # rotl(2*5,7)*9
        self.assertEqual(rng.state, [7, 0, 262146, 6 << 45])
        self.assertEqual(rng.next64(), 0)

    def test_seed_splitmix_published_seed_zero(self):
        # SplitMix64 standard first state from seed zero; hexadecimal fixture.
        self.assertEqual(r.scramble(0), 0xe220a8397b1dcdaf)
        self.assertEqual(r.rotl(1 << 63, 1), 1)
        self.assertEqual(r.rotl(r.MASK, 7), r.MASK)

    def test_rejection_boundary(self):
        rng = r.Random(0)
        with patch.object(rng, 'next64', side_effect=[0, 1]) as mock:
            self.assertEqual(rng.next(3), 1)
            self.assertEqual(mock.call_count, 2)
        with patch.object(rng, 'next64', return_value=0):
            self.assertEqual(rng.next(4), 0)
        for invalid in [0, -1, True, 2**31]:
            with self.assertRaises(ValueError):
                rng.next(invalid)

    def test_fresh_shuffle_identity_duplicates(self):
        class Identity:
            def next(self, bound):
                return bound-1
        self.assertEqual(list(r.assignments(4, 2, 3, Identity())), [[0, 1]]*3)
        class Zero:
            def next(self, bound):
                return 0
        self.assertEqual(list(r.assignments(4, 2, 3, Zero())), [[1, 2]]*3)

    def test_scripted_shuffle_hand_fixture(self):
        class Script:
            def __init__(self):
                self.script = iter([(4, 0), (3, 1), (2, 0)]*2)
            def next(self, bound):
                expected, value = next(self.script)
                assert bound == expected
                return value
        self.assertEqual(list(r.assignments(4, 2, 2, Script())), [[2, 3], [2, 3]])

    def test_synthetic_saved_input_corruptions(self):
        rows = [[float(i)]*12 for i in range(32)]
        evidence = dict(conditionOrdinal=0, replication=0,
            condition='primary_gait_heavy_tail_null', plannedConditionCount=200,
            dataMaster=20260904, dataStage=1, dataStream=1, labelMaster=2026102601,
            labelStage=26, datasetSeed=r.derive(20260904, 1, 1, 0),
            labelSeed=r.derive(2026102601, 26, 0, 0), metricOrder=r.METRICS,
            groupNames=['control', 'case'], groupCounts=[16, 16], validRows=1280,
            observedCaseIndices=list(range(16,32)), summaryRows=rows,
            summarySha256=r.sha(b''.join(struct.pack('<d', x) for row in rows for x in row)),
            entities=[dict(entity=f'{g}_{i:02}', group=g, measurements=40)
                      for g in ['control', 'case'] for i in range(1, 17)],
            candidate=dict(drawCount=999))
        document = dict(schemaVersion='mvs-global-rank-native/v1', status='ok',
                        mode='--case', conditionOrdinal=0, replication=0, evidence=evidence,
                        provenance=dict(drawScheme=r.SCHEME, draws=999))
        self.assertIs(r.validate_input(document, 0), evidence)
        for key, value in [('labelSeed', 0), ('datasetSeed', 0), ('summarySha256', '0'*64),
                           ('observedCaseIndices', list(range(16))), ('groupCounts', [15,17]),
                           ('replication', 1), ('metricOrder', list(reversed(r.METRICS)))]:
            bad = copy.deepcopy(document)
            bad['evidence'][key] = value
            with self.assertRaises(ValueError):
                r.validate_input(bad, 0)
        bad = copy.deepcopy(document)
        bad['evidence']['summaryRows'][0][0] += 1
        with self.assertRaises(ValueError):
            r.validate_input(bad, 0)

    def test_literal_label_hash_format(self):
        rows = [[1]*12]*4
        got = r.evaluate(rows, [0, 1], [[0, 1], [3, 2], [1, 0]], 3)
        literal = bytes.fromhex('040000000200000003000000010100000000010101010000')
        self.assertEqual(got['sampledLabelHash'], hashlib.sha256(literal).hexdigest())
        self.assertEqual(got['identities'], 2)
        self.assertEqual(got['duplicateAssignments'], 1)
        self.assertEqual(got['marginalExceedanceCounts'], [3]*12)
        self.assertEqual(got['maxTExceedanceCounts'], [3]*12)
        self.assertEqual(got['globalExceedanceCount'], 3)
        self.assertEqual(got['exact'], [(0, 1)]*12)

    def test_ties_inclusive_tail_hand_example(self):
        rows = [[x]*12 for x in [1, 1, 3, 4]]
        self.assertEqual([a[0] for a in r.ranks(rows)], [-2, -2, 1, 3])
        result = r.evaluate(rows, [0, 1], [[2, 3], [0, 2], [1, 0]], 3)
        self.assertEqual(result['exact'], [(192, 72)]*12)
        self.assertEqual(result['globalExceedanceCount'], 2)
        self.assertEqual(result['marginalExceedanceCounts'], [2]*12)
        self.assertEqual(r.compare((2, 4), (1, 2)), 0)
        self.assertEqual(r.maximum([(1, 2)]*12), 0)

    def test_large_integer_crossproducts(self):
        self.assertEqual(r.compare((2**62+1, 2**62), (1, 1)), 1)
        with self.assertRaises(ValueError):
            r.checked_compare((2**62+1, 2**62), (1, 1))

    def test_corrupt_matrices_labels_draw_count(self):
        for rows in [[], [[0]*11]*4, [[float('nan')]*12]*4, [[True]*12]*4]:
            with self.assertRaises(ValueError):
                r.ranks(rows)
        for selected in [[0, 0], [-1, 1], [0, 4], [True, 2]]:
            with self.assertRaises(ValueError):
                r.label_bytes(selected, 4, 2)
        with self.assertRaises(ValueError):
            r.evaluate([[0]*12]*4, [0, 1], [[0, 1]], 2)

    def test_checkpoint_corruption(self):
        records = [dict(conditionOrdinal=o, replication=i, status='completed', exitCode=0,
                        result=f'{o}-{i:04}.json') for o in range(6)
                   for i in range(200 if o < 4 else 250)]
        checkpoint = dict(planned=1300, records=records)
        self.assertEqual(len(r.checkpoint_records(checkpoint)), 200)
        for mutation in ['missing', 'duplicate', 'path', 'status']:
            bad = copy.deepcopy(checkpoint)
            if mutation == 'missing': bad['records'].pop()
            elif mutation == 'duplicate': bad['records'][1] = bad['records'][0]
            elif mutation == 'path': bad['records'][0]['result'] = '../0-0000.json'
            else: bad['records'][0]['status'] = 'failed'
            with self.assertRaises(ValueError):
                r.checkpoint_records(bad)


if __name__ == '__main__':
    unittest.main()
