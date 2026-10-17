import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import nist_univariate_study as study

class StudyIntegrityTests(unittest.TestCase):
    def fixtures(self):
        config={'inputSha256':'a'*64,'nativeFile':'test.dll','binaryFiles':{'test.dll':'b'*64,'MvsAnalyzer.Core.dll':'c'*64},'runtimeVersion':'8.0.31','architecture':'x64'}
        envelope={'schema':'mvs-nist-native/v1','status':'completed','inputSha256':'a'*64,'harnessSha256':'b'*64,'coreSha256':'c'*64,'runtimeVersion':'8.0.31','architecture':'x64','cases':[{'id':n} for n in study.NAMES]}
        return config,envelope
    def test_complete_bound_envelope_dispatches_exactly_nine(self):
        config,envelope=self.fixtures()
        with patch.object(study.reference,'compare_native',return_value={'primary':{'passed':True}}) as compare:
            rows=study.validate_envelope(envelope,config,[{}]*9,[{}]*9)
        self.assertEqual(9,len(rows));self.assertEqual(9,compare.call_count)
    def test_each_identity_corruption_blocks_before_comparison(self):
        config,envelope=self.fixtures()
        for key in ('schema','status','inputSha256','harnessSha256','coreSha256','runtimeVersion','architecture'):
            with self.subTest(key=key),patch.object(study.reference,'compare_native') as compare:
                broken=copy.deepcopy(envelope);broken[key]='wrong'
                with self.assertRaises(ValueError):study.validate_envelope(broken,config,[{}]*9,[{}]*9)
                compare.assert_not_called()
    def test_wrong_case_shapes_order_duplicates_and_missing_fail(self):
        config,envelope=self.fixtures()
        for cases in (None,[],envelope['cases'][:-1],list(reversed(envelope['cases'])),[{}]*9,[None]*9):
            with self.subTest(cases=cases):
                broken=copy.deepcopy(envelope);broken['cases']=cases
                with self.assertRaises(ValueError):study.validate_envelope(broken,config,[{}]*9,[{}]*9)
    def test_missing_reference_rows_cannot_zip_truncate(self):
        config,envelope=self.fixtures()
        with self.assertRaises(ValueError):study.validate_envelope(envelope,config,[{}]*9,[{}]*8)
    def test_duplicate_and_nonfinite_json_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.json'
            for content in ('{"a":1,"a":2}','{"a":NaN}','{"a":Infinity}'):
                p.write_text(content)
                with self.assertRaises(ValueError):study.read_json(p)
    def test_write_once_preserves_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'result.json';study.write_once(p,{'original':True})
            with self.assertRaises(FileExistsError):study.write_once(p,{'replacement':True})
            self.assertEqual({'original':True},study.read_json(p))
    def test_path_escape_and_hash_drift_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'file';p.write_text('original');pins={'file':study.sha(p)}
            study.verify_files(root,pins)
            p.write_text('changed')
            with self.assertRaises(ValueError):study.verify_files(root,pins)
            with self.assertRaises(ValueError):study.inside(root,'../outside')
            with self.assertRaises(ValueError):study.inside(root,str(p))
    def test_fixture_timeout_preserves_partial_output(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'stdout',Path(tmp)/'stderr'
            with patch.object(study.subprocess,'run',side_effect=subprocess.TimeoutExpired(['fake'],1,output=b'partial-out',stderr=b'partial-err')):
                result=study.retained_fixture_process(['fake'],1,a,b)
            self.assertEqual('TimeoutExpired',result['error']['type'])
            self.assertIsNone(result['exitCode']);self.assertEqual(b'partial-out',a.read_bytes());self.assertEqual(b'partial-err',b.read_bytes())
    def test_source_pins_cover_actual_core_imports(self):
        root=Path(__file__).resolve().parents[1]
        pins=study.source_pins(root)
        self.assertIn('SharedSources.props',pins);self.assertIn('Benchmark/BenchmarkRunner.cs',pins)
        self.assertIn('MvsAnalyzer.Core/AssemblyInfo.cs',pins)
    def test_explicit_execution_opt_in_required(self):
        with patch.object(study,'run') as run:
            self.assertEqual(1,study.main(['run','--root','.','--out','.','--native','test.dll']))
        run.assert_not_called()



class NativeAdapterContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        cls.native=os.environ.get('MVS_NIST_NATIVE')
        cls.dotnet=os.environ.get('MVS_NIST_DOTNET')
        cls.evidence=os.environ.get('MVS_NIST_SMOKE_EVIDENCE')
        if not all((cls.native,cls.dotnet,cls.evidence)):
            raise unittest.SkipTest('Set MVS_NIST_NATIVE, MVS_NIST_DOTNET and new MVS_NIST_SMOKE_EVIDENCE for explicitly authorized native adapter checks')
        cls.out=Path(cls.evidence);cls.out.mkdir(parents=True,exist_ok=False)
    def test_bounded_native_contract_matrix(self):
        import subprocess,time,struct
        def case(name,values):return {'id':name,'sourceSha256':'a'*64,'values':values}
        def payload(cases):return json.dumps({'schema':'mvs-nist-input/v1','cases':cases}).encode()
        good=payload([case('known',['-1','0','1']),case('signed-zero',['-0','0']),case('offset',['1','2','3'])])
        one=case('a',['1','2'])
        bad=[
            ('escaped-duplicate',b'{"schema":"mvs-nist-input/v1","\\u0073chema":"mvs-nist-input/v1","cases":[]}'),
            ('unknown',b'{"schema":"mvs-nist-input/v1","cases":[],"extra":1}'),
            ('missing',b'{"schema":"mvs-nist-input/v1"}'),
            ('numeric-token',payload([case('a',[1,2])])),
            ('whitespace',payload([case('a',[' 1','2'])])),
            ('nan',payload([case('a',['NaN','2'])])),
            ('overflow-token',payload([case('a',['1e999','2'])])),
            ('duplicate-id',payload([one,one])),
            ('zero-cases',payload([])),
            ('thirteen-cases',payload([case(str(i),['1','2']) for i in range(13)])),
            ('one-value',payload([case('a',['1'])])),
            ('too-many-per-case',payload([case('a',['1']*10001)])),
            ('too-many-total',payload([case('a',['1']*8000),case('b',['1']*8000),case('c',['1']*4001)])),
            ('oversize',b' '*(16*1024*1024+1)),
            ('late-computation-failure',payload([one,case('later',['1e308','-1e308'])])),
            ('invalid-utf8',b'\xff'),
            ('malformed-json',b'{'),
            ('wrong-schema',b'{"schema":"wrong","cases":[]}'),
        ]
        began=time.monotonic();records=[];passed=False;identity=None
        try:
            for name,raw,success in [('known-vectors',good,True)]+[(n,r,False) for n,r in bad]:
                input_path=self.out/(name+'.input.json');input_path.write_bytes(raw)
                remaining=120-(time.monotonic()-began)
                self.assertGreater(remaining,0,'Cumulative adapter budget exhausted')
                captured=study.retained_fixture_process([self.dotnet,self.native,'--input',str(input_path)],remaining,self.out/(name+'.stdout.json'),self.out/(name+'.stderr.txt'))
                record={'case':name,'exitCode':captured['exitCode'],'status':None,'error':captured['error']};records.append(record)
                self.assertIsNone(captured['error'])
                envelope=json.loads(captured['stdout']);record['status']=envelope.get('status')
                record['files']={p.name:study.sha(p) for p in (input_path,self.out/(name+'.stdout.json'),self.out/(name+'.stderr.txt'))}
                if success:
                    identity={key:envelope[key] for key in ('harnessSha256','coreSha256','runtimeVersion','architecture')}
                    self.assertEqual(0,captured['exitCode']);self.assertEqual('completed',envelope['status'])
                    self.assertEqual([0,0,2],[c['mean'] for c in envelope['cases']])
                    self.assertEqual([1,0,1],[c['standardDeviation'] for c in envelope['cases']])
                    self.assertEqual('8000000000000000',envelope['cases'][1]['inputBits'][0])
                    self.assertEqual(study.sha(input_path),envelope['inputSha256'])
                else:
                    self.assertEqual(1,captured['exitCode']);self.assertEqual('failed',envelope['status'])
                    self.assertNotIn('cases',envelope);self.assertIn('type',envelope['error'])
            passed=True
        finally:
            study.write_once(self.out/'summary.json',{'status':'passed' if passed else 'failed','processes':len(records),'records':records,'wallSeconds':time.monotonic()-began,'nativeSha256':study.sha(self.native),'nativeIdentity':identity,'testSourceSha256':study.sha(__file__)})

if __name__=='__main__':unittest.main()
