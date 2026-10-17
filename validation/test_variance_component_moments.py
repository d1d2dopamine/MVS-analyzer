import unittest
from fractions import Fraction as F
import variance_component_moment_oracle as oracle


class ExactMomentTests(unittest.TestCase):
    def test_all_finite_support_orbits_match(self):
        result = oracle.exact_diagnostic()
        self.assertEqual(len(result['finiteSupportChecks']), 8)
        self.assertEqual(sum(r['outcomes'] for r in result['finiteSupportChecks']), 720)
        self.assertEqual(result['randomDraws'], 0)
        self.assertEqual(result['nativeCalls'], 0)

    def test_two_values_hand_identity(self):
        self.assertEqual(oracle.sample_variance([1, 3]), 2)
        self.assertEqual(oracle.sample_variance([4, 4]), 0)

    def test_translation_and_scale_identity(self):
        a = [F(-2), F(1, 2), F(5)]
        self.assertEqual(oracle.sample_variance([3*x+7 for x in a]), 9*oracle.sample_variance(a))

    def test_student_fourth_boundaries(self):
        self.assertEqual(oracle.standardized_student_fourth(5), 9)
        self.assertEqual(oracle.standardized_student_fourth(6), 6)
        for df in (0, 2, 3, 4, 5.0, True):
            with self.assertRaises(ValueError): oracle.standardized_student_fourth(df)

    def test_direct_fourth_expansion_two_terms(self):
        v,q = oracle.independent_sum_fourth([1,2],[1,1],[3,9])
        self.assertEqual(v, 5)
        self.assertEqual(q, 3+16*9+24)

    def test_exact_stress_ratios(self):
        result = oracle.exact_diagnostic()
        self.assertEqual(result['within']['uncertaintyVarianceRatio'], F(157,40))
        self.assertEqual(result['center']['uncertaintyVarianceRatio'], F(19297,5248))
        self.assertEqual(result['center']['t5SampleVarianceUncertainty'], F(791177,1536000))

    def test_independent_group_difference_ratio(self):
        result = oracle.exact_diagnostic()
        a=result['within']['normalGroupAverage'];b=result['within']['t5GroupAverage']
        self.assertEqual((b+b)/(a+a), F(157,40))

    def test_invalid_moments_and_enumeration_fail(self):
        for args in [(1,1,3),(2,0,0),(2,2,3)]:
            with self.assertRaises(ValueError): oracle.sample_variance_uncertainty(*args)
        with self.assertRaises(ValueError): oracle.enumerate_sample_variance(6,[F(1,3)]*3)
        with self.assertRaises(ValueError): oracle.enumerate_sample_variance(2,[0,0,0])
        with self.assertRaises(ValueError): oracle.independent_sum_fourth([1],[1,2],[3])


if __name__ == '__main__': unittest.main()
