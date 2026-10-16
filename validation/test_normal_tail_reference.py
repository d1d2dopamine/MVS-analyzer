"""Helper-only tests; do not generate grid, reference tables, or candidate outputs."""
from fractions import Fraction
import math
import unittest
import mpmath as mp
import normal_tail_reference as ref

class Helpers(unittest.TestCase):
    def test_bits_roundtrip(self):
        for b in ('0000000000000000','8000000000000000','0000000000000001',
                  '0010000000000000','3ff0000000000000','7fefffffffffffff',
                  '7ff0000000000000','fff0000000000000','7ff8000000000000'):
            self.assertEqual(ref.bits(ref.from_bits(b)),b)
    def test_nearest_even_at_subnormal_half(self):
        half=Fraction(1,2**1075)
        self.assertEqual(ref.bits(ref.round_fraction_binary64(half)),'0000000000000000')
        self.assertEqual(ref.bits(ref.round_fraction_binary64(half+Fraction(1,2**1200))),'0000000000000001')
        self.assertEqual(ref.bits(ref.round_fraction_binary64(half-Fraction(1,2**1200))),'0000000000000000')
        self.assertEqual(ref.bits(ref.round_fraction_binary64(3*half)),'0000000000000002')
        self.assertEqual(ref.bits(ref.round_fraction_binary64(5*half)),'0000000000000002')
    def test_nearest_even_at_one(self):
        self.assertEqual(ref.round_fraction_binary64(Fraction(1)+Fraction(1,2**53)),1.0)
        self.assertEqual(ref.round_fraction_binary64(Fraction(1)+Fraction(3,2**53)),math.nextafter(math.nextafter(1,math.inf),math.inf))
    def test_boundary_and_large(self):
        for x in (2**-1022,math.nextafter(2**-1022,0),math.nextafter(2**-1022,math.inf),
                  1.0,2.0,2**52,2**100,float.fromhex('0x1.fffffffffffffp+1023')):
            self.assertEqual(ref.bits(ref.round_fraction_binary64(Fraction(x))),ref.bits(x))
    def test_exact_float_and_mp_roundtrip(self):
        for x in (0.,1.,0.001,1e-12,2**-1074,2**-1022,float.fromhex('0x1.fffffffffffffp+1023')):
            with mp.workdps(200):
                self.assertEqual(ref.mp_fraction(ref.exact_float(x)),Fraction(x))
                self.assertEqual(ref.bits(ref.round_mp_binary64(ref.exact_float(x))),ref.bits(x))
    def test_exact_ranks_hand_case(self):
        r=ref.exact_rank_summary([0.,1.],[2.,3.])
        self.assertEqual(r['rankSumB'],{'numerator':'7','denominator':'1'})
        self.assertEqual(r['uB'],{'numerator':'4','denominator':'1'})
        self.assertEqual(r['mean'],{'numerator':'2','denominator':'1'})
        self.assertEqual(r['variance'],{'numerator':'5','denominator':'3'})
        self.assertEqual(r['continuityAdjustedDistance'],{'numerator':'3','denominator':'2'})
    def test_exact_ranks_ties_policy(self):
        r=ref.exact_rank_summary([1.,1.],[1.,1.])
        self.assertEqual(r['status'],'constant_policy')
        self.assertEqual(r['variance'],{'numerator':'0','denominator':'1'})
        self.assertEqual(ref.exact_rank_summary([],[1.])['status'],'empty_policy')
    def test_negative_rational(self):
        self.assertEqual(ref.round_fraction_binary64(Fraction(-3,2)),-1.5)

if __name__=='__main__':
    unittest.main()
