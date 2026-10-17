"""Engineering-only generator checks. Never instantiate a reserved study RNG."""
from copy import deepcopy
import hashlib
import json
import math
import struct
import unittest
from unittest.mock import patch

import prospective_cases as p


class ScriptedRng:
    def __init__(self):
        self.calls = []
        self.bit_generator = self
        self.state = {"scripted": True, "draws": 0}

    def draws(self, kind, count):
        self.calls.append((kind, count))
        self.state["draws"] += count
        # Includes negative values; no positivity conditioning allowed.
        return [(i - count / 2) / 8 for i in range(count)]

    def standard_normal(self, count):
        return self.draws("normal", count)

    def standard_t(self, df, count):
        if df != 5:
            raise AssertionError("t degrees of freedom changed")
        return self.draws("t5", count)


class CaseTests(unittest.TestCase):
    def fixture(self, cell=10, rep=0):
        n = 80 if cell >= 10 else 1280
        return p.make_case([float(i - n / 2) for i in range(n)], cell, rep)

    def test_schema_round_trip_binary64_signed_zero_subnormal(self):
        values = [0.0, -0.0, float.fromhex('0x0.0000000000001p-1022'),
                  float.fromhex('0x1.fffffffffffffp+1023')] + [1.0] * 76
        c = p.make_case(values, 10, 999)
        self.assertEqual(p.loads(json.dumps(c)), c)
        self.assertEqual(c['values_bits'][:3], ['0000000000000000', '8000000000000000', '0000000000000001'])
        self.assertEqual(c['ordered_binary64_sha256'], hashlib.sha256(struct.pack('<80d', *values)).hexdigest())
        self.assertTrue(c['case_id'].startswith('engineering_literal/'))
        self.assertEqual(c['native_seed'], 1540010999)

    def test_every_cell_shape_identity_and_unique_seed(self):
        seeds = set()
        for cell in range(12):
            for rep in range(1000):
                coords = p.coordinate(cell, rep)
                self.assertEqual(coords, [2026101754, 1, 0, cell, rep])
                seed = 1540000000 + 1000 * cell + rep
                self.assertNotIn(seed, seeds)
                seeds.add(seed)
            c = self.fixture(cell)
            self.assertEqual(len(p.validate_case(c)), 80 if cell >= 10 else 1280)
        self.assertEqual(len(seeds), 12000)
        self.assertEqual(max(seeds), 1540011999)

    def test_missing_unknown_fields_and_strict_types(self):
        c = self.fixture()
        for field in p.FIELDS:
            bad = deepcopy(c)
            del bad[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                p.validate_case(bad)
        for field, value in [('extra', None), ('schema', 1), ('purpose', 'study'),
                             ('cell_index', True), ('cell_index', 12),
                             ('replication_zero_based', -1), ('replication_zero_based', 1000),
                             ('replication_zero_based', 1.0), ('native_seed', True),
                             ('native_seed', c['native_seed'] + 1),
                             ('entities_per_group', 8.0), ('repeats_per_entity', 40),
                             ('value_order', 'repeat_entity_group'), ('case_id', 'C10'),
                             ('protocol_id', 'other'), ('protocol_sha256', '0' * 64),
                             ('ordered_binary64_sha256', '0' * 64)]:
            bad = deepcopy(c)
            bad[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                p.validate_case(bad)

    def test_duplicate_json_keys_nonfinite_and_wrong_root(self):
        raw = json.dumps(self.fixture())
        for bad in ('[]', 'null', '{"x": NaN}', '{"x": 1e999}',
                    raw[:-1] + ',"purpose":"engineering_literal"}',
                    '{"x":{"a":0,"a":1}}'):
            with self.subTest(bad=bad[:50]), self.assertRaises(ValueError):
                p.loads(bad)

    def test_malformed_nonfinite_and_order_hash_rejection(self):
        c = self.fixture()
        for bit in ('7ff0000000000000', 'fff0000000000000', '7ff8000000000000',
                    'BFF0000000000000', '0', '0x00000000000000', 1, None):
            bad = deepcopy(c)
            bad['values_bits'][0] = bit
            with self.subTest(bit=bit), self.assertRaises(ValueError):
                p.validate_case(bad)
        for values in (c['values_bits'][:-1], c['values_bits'] + ['0000000000000000'],
                       list(reversed(c['values_bits'])), tuple(c['values_bits'])):
            bad = deepcopy(c)
            bad['values_bits'] = values
            with self.assertRaises(ValueError):
                p.validate_case(bad)

    def test_finite_out_of_bounds_retained_no_redraw(self):
        values = [-1000001.0, 1000001.0, -0.0] + [2.0] * 77
        c = p.make_case(values, 11, 2)
        self.assertEqual(p.validate_case(c), values)
        for value in (float('nan'), float('inf'), True):
            with self.assertRaises(ValueError):
                p.make_case([value] * 80, 10, 0)

    def test_frozen_configuration_tamper(self):
        with patch.object(p.Path, 'read_bytes', return_value=b'{}'):
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                p.frozen_config()

    def test_scripted_all_cells_draw_order_parameters_and_state(self):
        config = p.frozen_config()
        for cell in config['cells']:
            rng = ScriptedRng()
            seen = []
            def factory(coords):
                seen.append(coords)
                return rng
            c, provenance = p.generate_case(cell['index'], 17, rng_factory=factory)
            n, m = cell['entities_per_group'], cell['repeats_per_entity']
            self.assertEqual(seen, [[2026101754, 1, 0, cell['index'], 17]])
            expected_calls = [('normal' if cell[k] == 'gaussian' else 't5', count)
                              for k, count in [('between_distribution', 2*n), ('within_distribution', 2*n*m)]]
            self.assertEqual(rng.calls, expected_calls)
            self.assertEqual(provenance['state_before'], {'scripted': True, 'draws': 0})
            self.assertEqual(provenance['state_after']['draws'], 2*n + 2*n*m)
            actual = p.validate_case(c)
            expected = []
            for g in range(2):
                parameters = cell[f'group{g}']
                for e in range(n):
                    b = ((g*n+e) - n)/8
                    if cell['between_distribution'] == 'standardized_t5':
                        b *= math.sqrt(3/5)
                    for r in range(m):
                        error = ((g*n+e)*m+r-n*m)/8
                        if cell['within_distribution'] == 'standardized_t5':
                            error *= math.sqrt(3/5)
                        expected.append(parameters['mean'] + parameters['between_sd']*b + parameters['within_sd']*error)
            self.assertEqual(actual, expected)
            self.assertEqual(c['purpose'], 'planned_case')
            self.assertEqual(provenance['native_seed_coordinates'], [2026101754, 1, 1, cell['index'], 17])
            rng.state['draws'] = -1
            self.assertNotEqual(provenance['state_after']['draws'], -1)

    def test_numpy_factory_refuses_reserved_before_numpy_rng(self):
        with self.assertRaisesRegex(ValueError, 'test-only'):
            p.generate_case(0, 0, rng_factory=p.numpy_test_rng_factory)
        for coords in ([p.TEST_MASTER, 1, 1, 0, 0], [p.TEST_MASTER, 1, 0, True, 0],
                       [p.TEST_MASTER, 1, 0, 12, 0]):
            with self.assertRaises(ValueError):
                p.numpy_test_rng_factory(coords)

    def test_bad_draws_fail_without_retry(self):
        rng = ScriptedRng()
        rng.standard_normal = lambda count: [float('nan')] * count
        with self.assertRaises(ValueError):
            p.generate_case(10, 0, rng_factory=lambda _: rng)
        rng.standard_normal = lambda count: [0.0] * (count - 1)
        with self.assertRaises(ValueError):
            p.generate_case(10, 0, rng_factory=lambda _: rng)

    def test_test_namespace_pcg64_goldens_and_repeatability(self):
        goldens = {
            0: 'fd935b1d5f3b9eca30351b7720fde0a4d404d3543ebd52df7c25a805bc1a12ee',
            5: '8e53a85e7ede677beb42c8ffa59f02b7b273d3e473224affadf0490e7d79e40d',
            8: '6ffe8b66b43782085d2ab59d87a3ac736652bde536f9c18fe8fe429a3b949dc7',
            9: '0841dda91f0e081ef7fe498039196ae3f1bafb8442a603a8c1e105644dd602a1',
            10: '9532d1f7c7cbf2603899f84d6143a8d6c6df13bdaf225a2aeec886c8b013822b',
            11: 'b51050547bcc3ad7ca6ea459d66ced8c6a740e14277ed8014df3ded06b3b039d',
        }
        for cell in reversed(goldens):
            first = p.generate_case(cell, 7, rng_factory=p.numpy_test_rng_factory, test_namespace=True)
            second = p.generate_case(cell, 7, rng_factory=p.numpy_test_rng_factory, test_namespace=True)
            self.assertEqual(first, second)
            c, provenance = first
            self.assertEqual(c['ordered_binary64_sha256'], goldens[cell])
            self.assertTrue(provenance['test_namespace'])
            self.assertEqual(provenance['data_coordinates'], [p.TEST_MASTER, 1, 0, cell, 7])
            self.assertEqual(c['purpose'], 'engineering_literal')
            self.assertNotEqual(provenance['state_before'], provenance['state_after'])
            # Independent bulk NumPy construction, with explicit test-only seed.
            import numpy as np
            cfg = p.frozen_config()['cells'][cell]
            n, m = cfg['entities_per_group'], cfg['repeats_per_entity']
            rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([p.TEST_MASTER, 1, 0, cell, 7])))
            def draws(kind, size):
                return rng.standard_normal(size) if kind == 'gaussian' else rng.standard_t(5, size) * np.sqrt(3/5)
            b = draws(cfg['between_distribution'], 2*n).reshape(2, n, 1)
            e = draws(cfg['within_distribution'], 2*n*m).reshape(2, n, m)
            expected = []
            for g in range(2):
                q = cfg[f'group{g}']
                expected.extend((q['mean'] + q['between_sd']*b[g] + q['within_sd']*e[g]).ravel().tolist())
            self.assertEqual(c['values_bits'], p.encode_values(expected))


if __name__ == '__main__':
    unittest.main()
