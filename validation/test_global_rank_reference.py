"""Pre-pilot arithmetic tests; these generate no scientific datasets."""
import copy
from collections import Counter
from fractions import Fraction
import json
import math
import unittest

import global_rank_reference as ref


class GlobalRankReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures=json.loads(ref.FIXTURES.read_text())['matrixFixtures']

    def test_independent_tie_variance_formula(self):
        for f in self.fixtures:
            rows=f['rows']; n=len(rows); k=f['nCase']
            self.assertTrue(ref.verify_independent_algebra(rows,k)['passed'])
            for assignment in ref.enumerate_orbit(rows,k):
                for j,score in enumerate(assignment['scores']):
                    col=[r[j] for r in rows]
                    # Independently rank by counts strictly below/equal each value.
                    ranks=[Fraction(2*sum(y<x for y in col)+sum(y==x for y in col)+1,2) for x in col]
                    a=sum(ranks[i] for i in assignment['selected'])-Fraction(k*(n+1),2)
                    correction=sum(t**3-t for t in Counter(col).values())
                    variance=Fraction(k*(n-k),12)*(n+1-Fraction(correction,n*(n-1)))
                    self.assertEqual(score,a*a/variance if variance else 0)

    def test_every_observed_exact_tails_and_plus_one_identity(self):
        for f in self.fixtures:
            orbit=ref.enumerate_orbit(f['rows'],f['nCase'])
            rejected=0
            for observed in orbit:
                tail=ref.exhaustive_tails(orbit,observed['scores'])
                self.assertEqual(tail['globalP'],min(tail['maxTP']))
                self.assertGreaterEqual(tail['globalCount'],1)
                self.assertEqual(tail['globalP'],Fraction(tail['globalCount'],len(orbit)))
                # All OTHER assignments once: 1+c divided by B+1 = exact.
                others=[x for x in orbit if x['selected']!=observed['selected']]
                for j in range(12):
                    c=sum(x['maxScore']>=observed['scores'][j] for x in others)
                    self.assertEqual(Fraction(c+1,len(others)+1),tail['maxTP'][j])
                rejected+=tail['globalP']<ref.ALPHA
            self.assertLessEqual(Fraction(rejected,len(orbit)),ref.ALPHA)

    def test_literal_duplicates_identity_and_constant(self):
        for f in self.fixtures:
            self.assertGreaterEqual(f['draws'].count(f['observed']),2)
            mc=ref.monte_carlo(f['rows'],f['observed'],f['draws'])
            self.assertGreaterEqual(mc['globalCount'],2)
            self.assertEqual(mc['globalP'],min(mc['maxTP']))
        f=self.fixtures[-1]
        mc=ref.monte_carlo(f['rows'],f['observed'],f['draws'])
        self.assertEqual(mc['globalP'],1)
        self.assertEqual(mc['marginalP'],[1]*12)
        self.assertEqual(mc['observedScores'],[0]*12)

    def test_nontrivial_rational_cross_column_ties(self):
        expected={8:Fraction(7,4),9:Fraction(9,5),10:Fraction(9,10)}
        for f in self.fixtures:
            if f['id'].startswith('rational_tie'):
                a=ref.rank_matrix(f['rows'])
                q=[sum(r[j]**2 for r in a) for j in range(2)]
                self.assertNotEqual(q[0],q[1])
                s=ref.scores(f['rows'],f['observed'])
                self.assertEqual(s[0],s[1]); self.assertEqual(s[0],expected[len(a)])
                self.assertEqual(max(s),s[0])

    def test_row_column_and_label_reversal(self):
        for f in self.fixtures:
            rows=f['rows']; n=len(rows)
            for x in ref.enumerate_orbit(rows,f['nCase']):
                chosen=x['selected']; s=x['scores']
                self.assertEqual(ref.scores(rows,[i for i in range(n) if i not in chosen]),s)
                self.assertEqual(ref.scores(rows[::-1],[n-1-i for i in chosen]),s)
                self.assertEqual(ref.scores([r[::-1] for r in rows],chosen),s[::-1])

    def test_strict_b999_thresholds(self):
        self.assertTrue(ref.rejects(48,999)); self.assertFalse(ref.rejects(49,999))
        self.assertTrue(ref.rejects(3,999,True)); self.assertFalse(ref.rejects(4,999,True))

    def test_invalid_slot_invalidates_whole_case(self):
        good=[[1]*12,[2]*12,[3]*12,[4]*12]
        for bad in (None, [], [[]], [[1]*11]*4, [[1]*13]*4):
            with self.assertRaises((TypeError,ValueError)):
                ref.scores(bad,[0,1])
        for value in (float('nan'),float('inf'),float('-inf'),None,'1',True):
            rows=copy.deepcopy(good); rows[2][7]=value
            with self.assertRaises(ValueError): ref.scores(rows,[0,1])
        for selection in ([0,0],[0,4],[],[0,1,2,3],[True,2]):
            with self.assertRaises(ValueError): ref.scores(good,selection)
        with self.assertRaises(ValueError): ref.monte_carlo(good,[0,1],[[0]])

    def test_native_comparison_protocol_and_corruption(self):
        f=self.fixtures[0]
        orbit=ref.enumerate_orbit(f['rows'],f['nCase'])
        def floats(x):
            if isinstance(x,Fraction): return float(x)
            if isinstance(x,list): return [floats(v) for v in x]
            if isinstance(x,dict): return {k:floats(v) for k,v in x.items()}
            return x
        native=floats(ref.monte_carlo(f['rows'],f['observed'],f['draws']))
        native['allAssignments']=[]
        for x in orbit:
            t=ref.exhaustive_tails(orbit,x['scores'])
            native['allAssignments'].append(floats(dict(x,globalTailCount=t['globalCount'],
                marginalTailCounts=t['marginalCounts'],maxTailCounts=t['maxTCounts'],
                otherAssignmentMaxTP=t['maxTP'])))
        self.assertTrue(ref.compare_native(f,native)['passed'])
        bad=copy.deepcopy(native); bad['globalCount']-=1
        with self.assertRaises(AssertionError): ref.compare_native(f,bad)
        bad=copy.deepcopy(native); bad['allAssignments'][0]['scores'][0]+=1e-14
        with self.assertRaises(AssertionError): ref.compare_native(f,bad)

    def test_reporting(self):
        self.assertEqual(ref.mcnemar_one_sided(0,0),1)
        self.assertEqual(ref.mcnemar_one_sided(5,0),Fraction(1,32))
        self.assertEqual(ref.mcnemar_one_sided(2,2),Fraction(11,16))
        lo,hi=ref.wilson95(10,200)
        self.assertLess(lo,.05); self.assertGreater(hi,.05)
        try: import scipy
        except ImportError: self.skipTest('optional scipy beta quantiles unavailable')
        x=ref.paired_delta_bounds(0,0,200)
        self.assertAlmostEqual(x['bounds'][0],-x['bounds'][1])
        y=ref.paired_delta_bounds(20,5,250)
        z=ref.paired_delta_bounds(5,20,250)
        self.assertEqual(y['delta'],.06)
        self.assertAlmostEqual(y['bounds'][0],-z['bounds'][1])
        self.assertEqual(y['implementation']['version'],scipy.__version__)

if __name__=='__main__': unittest.main()
