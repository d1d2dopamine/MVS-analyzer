import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from multiplicity_reference import reference, load_fixtures, compare


class MultiplicityReferenceTests(unittest.TestCase):
    def test_analytical_closed_intersections(self):
        self.assertEqual(reference([.04,.01,.03,.002],4),dict(bonferroni=[.16,.04,.12,.008],holm=[.06,.03,.06,.008]))

    def test_ties(self):
        self.assertEqual(reference([.01,.01,.02,.02],4)['holm'],[.04]*4)

    def test_complete_family_with_unavailable(self):
        self.assertEqual(reference([.01]+[None]*11,12)['holm'],[.12]+[None]*11)

    def test_all_unavailable(self):
        self.assertEqual(reference([None]*12,12)['holm'],[None]*12)

    def test_invalid_values(self):
        for p in [-.1,1.1,float('nan'),float('inf'),True,'0.1']:
            with self.subTest(p=p), self.assertRaises(ValueError): reference([p],1)

    def test_invalid_family(self):
        for n in [0,2,13,True,1.0]:
            with self.subTest(n=n), self.assertRaises(ValueError): reference([.1],n)

    def test_permutation_and_nonmutation(self):
        p=[None,.03,.001,.009]; original=copy.copy(p)
        self.assertEqual(reference(p,4)['holm'][::-1],reference(p[::-1],4)['holm'])
        self.assertEqual(p,original)

    def test_strict_adjacent_boundary(self):
        p=.05/12
        result=[reference([x]+[1]*11,12)['holm'][0] < .05 for x in [math.nextafter(p,0),p,math.nextafter(p,1)]]
        self.assertEqual(result,[True,False,False])

    def test_holm_adds_members_but_not_any_event(self):
        r=reference([.003,.0045,.0048]+[1]*9,12)
        self.assertEqual(sum(x < .05 for x in r['bonferroni']),1)
        self.assertEqual(sum(x < .05 for x in r['holm']),3)
        self.assertEqual(any(x < .05 for x in r['bonferroni']),any(x < .05 for x in r['holm']))

    def test_fixture_invariants(self):
        doc,_=load_fixtures(Path(__file__).with_name('multiplicity-fixtures-v1.json'))
        for c in doc['cases']:
            p=c['p_values']; r=reference(p,c['family_size'])
            self.assertEqual(any(x is not None and x<.05 for x in r['holm']),any(x is not None and x<.05 for x in r['bonferroni']))
            for raw,h,b in zip(p,r['holm'],r['bonferroni']):
                if raw is None: self.assertIsNone(h); self.assertIsNone(b)
                else: self.assertLessEqual(raw,h); self.assertLessEqual(h,b); self.assertLessEqual(b,1)

    def make_evidence(self, directory):
        fixture=Path(directory)/'fixture.json'; native=Path(directory)/'native.json'
        fixture.write_text(json.dumps(dict(schema='MVS-MULTIPLICITY-REFERENCE-1',alpha=.05,cases=[dict(id='test',family_size=3,p_values=[.001,None,.02])])))
        r=reference([.001,None,.02],3)
        row=dict(id='test',**r)
        for method in r: row[method+'_rejected']=[p is not None and p<.05 for p in r[method]]
        data=dict(schema='MVS-MULTIPLICITY-NATIVE-1',fixtureSha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),engineVersion='1.6.2',activeMetricCount=12,coreAssemblySha256='a'*64,nativeRuntime='test fixture only',results=[row])
        native.write_text(json.dumps(data))
        return fixture,native,data

    def test_checker_accepts_known_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            f,n,_=self.make_evidence(d)
            self.assertTrue(compare(f,n)['passed'])

    def test_checker_detects_wrong_value_and_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            f,n,data=self.make_evidence(d)
            data['results'][0]['holm'][0]=.1
            data['results'][0]['holm_rejected'][0]=False
            n.write_text(json.dumps(data))
            self.assertEqual(len(compare(f,n)['failures']),2)

    def test_checker_rejects_provenance_and_missing_cases(self):
        for key,value in [('fixtureSha256','b'*64),('engineVersion','1.6.1'),('activeMetricCount',11),('results',[])]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as d:
                f,n,data=self.make_evidence(d); data[key]=value; n.write_text(json.dumps(data))
                with self.assertRaises(ValueError): compare(f,n)

    def test_duplicate_fixture_ids(self):
        with tempfile.TemporaryDirectory() as d:
            f,n,_=self.make_evidence(d); data=json.loads(f.read_text()); data['cases']*=2; f.write_text(json.dumps(data))
            with self.assertRaises(ValueError): load_fixtures(f)


if __name__=='__main__': unittest.main()
