import copy,json,unittest
from unittest.mock import patch
from pathlib import Path
import prospective_case_verification as v

class VerificationTests(unittest.TestCase):
    def test_literal_hashes_sizes_and_subset(self):
        a=v.literal_case('large');b=v.literal_case('small')
        self.assertEqual(len(a['values_bits']),1280);self.assertEqual(len(b['values_bits']),80)
        self.assertEqual(b['values_bits'],[x for i,x in enumerate(a['values_bits']) if i//40%16<8 and i%40<5])
        self.assertEqual(a['native_seed'],1540000000);self.assertEqual(b['native_seed'],1540010000)
        self.assertTrue(a['case_id'].startswith('engineering_literal/'))
        with self.assertRaises(ValueError):v.literal_case('other')
    def test_frozen_schedule_and_exclusions(self):
        p=json.loads((v.ROOT/v.PROTOCOL).read_text())
        self.assertEqual([x['route'] for x in p['schedule']],['reference','serialized']*2)
        self.assertEqual(p['limits']['max_calls'],4);self.assertEqual(p['limits']['retries'],0)
        self.assertEqual(p['comparison']['allowed_different_top_level_fields'],v.VOLATILE)
        self.assertFalse(p['study_execution_authorized'])
    def fixture(self):
        end={k:1 for k in v.VOLATILE};end.update(operationCounts={'fixtureMaterializationCount':1,'runCallCount':1},payload={'value':{'bits':'0000000000000000'}},serializedUtf8Bytes=20)
        return {'end':end,'trace':[{'kind':'cached','call':1,'observation':{'Key':'x'}}],'callbacks':1}
    def test_only_declared_differences_allowed(self):
        a=self.fixture();b=copy.deepcopy(a)
        for key in v.VOLATILE:b['end'][key]=2
        b['end']['operationCounts']['fixtureMaterializationCount']=0
        self.assertTrue(v.compare_pair(a,b)['matched'])
        for key in ('payload','serializedUtf8Bytes'):
            c=copy.deepcopy(b);c['end'][key]='corrupted'
            with self.assertRaises(ValueError):v.compare_pair(a,c)
        c=copy.deepcopy(b);c['end']['operationCounts']['runCallCount']=0
        with self.assertRaises(ValueError):v.compare_pair(a,c)
    def test_trace_mutations_rejected(self):
        a=self.fixture()
        for change in ('missing','duplicate','value'):
            b=copy.deepcopy(a)
            if change=='missing':b['trace']=[]
            elif change=='duplicate':b['trace']*=2
            else:b['trace'][0]['observation']['Key']='y'
            with self.assertRaises(ValueError):v.compare_pair(a,b)
    def test_explicit_execution_before_any_io(self):
        with patch.object(v,'verify',side_effect=AssertionError('must not read')):
            with self.assertRaises(ValueError):v.run('/unused','0'*64,False)
    def test_verify_normalizes_root_path(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);m={'schema':'mvs-case-verification-binding/v1','science_execution_authorized':False,'pins':{},'root':d,'sources':[],'native_dir':d,'native_files':[],'provenance':{}}
            (root/'bind.json').write_text(json.dumps(m))
            def source_paths(path):
                self.assertIsInstance(path,Path)
                return []
            with patch.object(v.host.replay,'source_paths',side_effect=source_paths), patch.object(v.host,'files_in',return_value=[]), patch.object(v.outcomes,'validate_provenance'):
                self.assertEqual(v.verify(root,v.sha(root/'bind.json')),m)
    def test_real_supervisor_supplies_output_file_not_directory(self):
        import tempfile,sys,os
        seen=[]
        with tempfile.TemporaryDirectory() as d:
            labels=[('large',True),('large',False)]
            def check(directory,m,size,reference):
                seen.append((Path(directory).name,size,reference))
                self.assertTrue((Path(directory)/'stdout.jsonl').is_file())
                return {'callbacks':1}
            with patch.object(v,'validate_call',side_effect=check):
                commands=[[sys.executable,'-c','import time;print("{}",flush=True);time.sleep(.15)']]*2
                result=v.host.execute_schedule(Path(d),commands,[[0],[1]],dict(os.environ),lambda p:v.validate_output(p,{},labels),wall_seconds=5)
            self.assertFalse(result['stop_reasons'])
            self.assertEqual(seen,[('case-00','large',True),('case-01','large',False)])
        with self.assertRaises(ValueError):v.validate_output('/tmp/case-00/not-stdout',{},[])
    def test_continuation_launches_only_three_unstarted_slots(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'out';out.mkdir();large=root/'large.json';small=root/'small.json';large.write_text('{}');small.write_text('{}')
            prior={'directory':str(root/'old'),'original_elapsed_seconds':1.5,'original_bytes':100}
            m={'continuation':prior,'root':d,'requests':{'large':str(large),'small':str(small)},'taskset':'taskset','cpu':0,'command':['/tmp/dotnet','/tmp/adapter.dll']}
            captured={}
            def execute(out,commands,batches,env,validator,**kwargs):
                captured.update(commands=commands,batches=batches,limits=kwargs)
                return {'attempts':[],'stop_reasons':[{'code':'synthetic_stop'}],'cleanup_complete':True}
            with patch.object(v,'verify',return_value=m),patch.object(v,'validate_prior',return_value=prior),patch.object(v.host,'execute_schedule',side_effect=execute):
                result=v.run(out,'0'*64,True)
            self.assertEqual(len(captured['commands']),3)
            self.assertEqual(captured['batches'],[[0],[1],[2]])
            self.assertIn('run-case',captured['commands'][0]);self.assertEqual(captured['commands'][1][-2:],['engineering-reference','small'])
            self.assertEqual(captured['limits']['wall_seconds'],298.5)
            self.assertEqual(captured['limits']['output_bytes'],18_999_900)
            self.assertEqual(result['original_status'],'technical_failure')
            self.assertEqual(result['retained_call_count'],1)
            self.assertEqual(result['new_call_count'],3)
    def test_binary64_tokens_not_rounded(self):
        a=self.fixture();b=copy.deepcopy(a);b['end']['payload']['value']['bits']='8000000000000000'
        with self.assertRaises(ValueError):v.compare_pair(a,b)
if __name__=='__main__':unittest.main()
