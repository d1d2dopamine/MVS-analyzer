"""Independent exact-count oracle fixtures; native comparison is recorded separately."""
import json
import math
from pathlib import Path
import unittest
from fractions import Fraction

class TauOracleFixtures(unittest.TestCase):
    def test_frozen_exact_pair_counts(self):
        fixtures = json.loads(Path(__file__).with_name('benchmark-tau-oracle-v1.json').read_text())
        self.assertEqual(len(fixtures), 25)
        for fixture in fixtures:
            with self.subTest(name=fixture['name']):
                a = [float.fromhex(x) for x in fixture['a_hex']]
                b = [float.fromhex(x) for x in fixture['b_hex']]
                expected = fixture['expected']
                if len(a) != len(b) or len(a) < 2 or not all(map(math.isfinite, a+b)):
                    self.assertEqual(expected['status'], 'undefined')
                    self.assertEqual(expected['reason'], 'invalid_input')
                    continue
                counts = dict(C=0, D=0, TA=0, TB=0, J=0)
                for i in range(len(a)):
                    for j in range(i):
                        x = (a[i] > a[j]) - (a[i] < a[j])
                        y = (b[i] > b[j]) - (b[i] < b[j])
                        key = 'J' if not x and not y else 'TA' if not x else 'TB' if not y else 'C' if x == y else 'D'
                        counts[key] += 1
                self.assertEqual(counts, expected['counts'])
                n = counts['C'] - counts['D']
                pairs = counts['C'] + counts['D']
                denominator = (pairs + counts['TA']) * (pairs + counts['TB'])
                self.assertEqual(denominator, expected['denominator_squared'])
                self.assertEqual(n, expected['numerator'])
                if not denominator:
                    self.assertEqual(expected['status'], 'undefined')
                else:
                    self.assertEqual(Fraction(expected['tau_squared']), Fraction(n*n, denominator))
                    self.assertEqual(expected['sign'], (n > 0) - (n < 0))
                    self.assertEqual(expected['tau'], n/math.sqrt(denominator))

if __name__ == '__main__': unittest.main()
