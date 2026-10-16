#!/usr/bin/env python3
"""Historical source integrity regressions; no numerical/native execution."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import source_pins as pins


def digest(data):
    return hashlib.sha256(data).hexdigest()


class SourcePinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'validation').mkdir()
        (self.root/'Core').mkdir()
        self.name = 'Core/Revised.cs'
        self.other = 'Core/Untouched.cs'
        self.v2_only = 'Core/V2Only.cs'
        self.original = {'note': 'Historical immutable anchors', 'sha256': {
            self.name: digest(b'original'), self.other: digest(b'untouched'),
            self.v2_only: digest(b'v2-only-original')}}
        self.previous = {'note': 'Older explicit review', 'sha256': {self.name: {
            'originalSha256': digest(b'original'), 'sha256': digest(b'previous')}}}
        self.reviewed = {'schema': 'mvs-source-pin-revisions/v2', 'stage': 35,
            'note': 'Synthetic review for contract tests, not scientific proof.',
            'historicalManifestSha256': '', 'previousRevisionManifestSha256': '',
            'revisions': {self.name: {'originalSha256': digest(b'original'),
                'previousSha256': digest(b'previous'), 'sha256': digest(b'current'),
                'review': {'completeness': 'complete-retained-chain', 'stages': [25, 35],
                    'reason': 'Synthetic reviewed source transition.',
                    'evidence': ['docs/synthetic-review.md'],
                    'limitation': 'Integrity only; local-owner edits are not prevented.'}}}}
        self.reviewed['revisions'][self.v2_only] = copy.deepcopy(self.reviewed['revisions'][self.name])
        self.reviewed['revisions'][self.v2_only].update({
            'originalSha256': digest(b'v2-only-original'),
            'previousSha256': digest(b'v2-only-original'), 'sha256': digest(b'v2-only-current')})
        self.successor = {'schema': 'mvs-source-pin-revisions/v3', 'stage': 36,
            'note': 'Synthetic explicit successor review, not scientific proof.',
            'previousReviewedManifestSha256': '',
            'revisions': {self.name: {'originalSha256': digest(b'original'),
                'previousSha256': digest(b'current'), 'sha256': digest(b'round36'),
                'review': {'completeness': 'complete-retained-chain',
                    'transitionCompleteness': 'complete-reviewed-transition', 'stages': [36],
                    'reason': 'Synthetic fully reviewed successor transition.',
                    'evidence': ['docs/synthetic-successor-review.md'],
                    'limitation': 'Earlier provenance is inherited without new claims.'}}}}
        (self.root/self.name).write_bytes(b'round36')
        (self.root/self.other).write_bytes(b'untouched')
        (self.root/self.v2_only).write_bytes(b'v2-only-current')
        self.write_all()
        self.patch = patch.object(pins, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def write(self, name, value):
        (self.root/'validation'/name).write_text(json.dumps(value, indent=2)+'\n')

    def write_all(self):
        self.write('ui-patch-baseline.json', self.original)
        self.write('checkpoint-source-baseline.json', self.previous)
        self.reviewed['historicalManifestSha256'] = digest((self.root/'validation/ui-patch-baseline.json').read_bytes())
        self.reviewed['previousRevisionManifestSha256'] = digest((self.root/'validation/checkpoint-source-baseline.json').read_bytes())
        self.write('source-pin-revisions-v2.json', self.reviewed)
        self.successor['previousReviewedManifestSha256'] = digest((self.root/'validation/source-pin-revisions-v2.json').read_bytes())
        self.write('source-pin-revisions-v3.json', self.successor)

    def resolve(self, name=None):
        name = name or self.name
        return pins.expected_source_hash(name, self.original['sha256'][name])

    def check_sources(self):
        for name, anchor in self.original['sha256'].items():
            self.assertEqual(digest((self.root/name).read_bytes()), pins.expected_source_hash(name, anchor))

    def test_valid_layers_and_unchanged_source(self):
        self.check_sources()
        self.assertEqual(self.resolve(), digest(b'round36'))
        self.assertEqual(self.resolve(self.other), digest(b'untouched'))
        self.assertEqual(self.resolve(self.v2_only), digest(b'v2-only-current'))

    def test_modified_revised_source_fails_consumer_contract(self):
        (self.root/self.name).write_bytes(b'unreviewed drift')
        with self.assertRaises(AssertionError): self.check_sources()

    def test_modified_untouched_source_fails_consumer_contract(self):
        (self.root/self.other).write_bytes(b'unreviewed drift')
        with self.assertRaises(AssertionError): self.check_sources()

    def test_modified_v2_only_source_fails_consumer_contract(self):
        (self.root/self.v2_only).write_bytes(b'unreviewed v2 drift')
        with self.assertRaises(AssertionError): self.check_sources()

    def test_expected_hash_is_not_derived_from_live_source(self):
        (self.root/self.name).unlink()
        self.assertEqual(self.resolve(), digest(b'round36'))
        with self.assertRaises(FileNotFoundError): self.check_sources()

    def test_missing_each_manifest_fails_closed(self):
        for name in ('ui-patch-baseline.json', 'checkpoint-source-baseline.json',
                     'source-pin-revisions-v2.json', 'source-pin-revisions-v3.json'):
            with self.subTest(name=name):
                p=self.root/'validation'/name; raw=p.read_bytes(); p.unlink()
                with self.assertRaises(pins.SourcePinError): self.resolve()
                p.write_bytes(raw)

    def test_duplicate_keys_in_each_manifest_are_rejected(self):
        for name in ('ui-patch-baseline.json', 'checkpoint-source-baseline.json',
                     'source-pin-revisions-v2.json', 'source-pin-revisions-v3.json'):
            with self.subTest(name=name):
                p=self.root/'validation'/name; raw=p.read_bytes()
                p.write_bytes(b'{"duplicate":1,"duplicate":2}')
                with self.assertRaisesRegex(pins.SourcePinError, 'Duplicate'): self.resolve()
                p.write_bytes(raw)

    def test_malformed_json_encoding_and_root_are_rejected(self):
        for name in ('source-pin-revisions-v2.json', 'source-pin-revisions-v3.json'):
            p=self.root/'validation'/name; original=p.read_bytes()
            for raw in (b'{', b'\xff', b'[]', b'{"x":NaN}', b'null'):
                with self.subTest(name=name, raw=raw):
                    p.write_bytes(raw)
                    with self.assertRaises(pins.SourcePinError): self.resolve()
            p.write_bytes(original)

    def test_wrong_caller_original_anchor_rejected(self):
        with self.assertRaises(pins.SourcePinError): pins.expected_source_hash(self.name, digest(b'current'))

    def test_unknown_requested_path_rejected(self):
        with self.assertRaises(pins.SourcePinError): pins.expected_source_hash('Core/New.cs', 'a'*64)

    def test_noncanonical_unknown_review_paths_rejected(self):
        for name in ('.', 'Core/\x00.cs', 'Core/\n.cs', 'Core/\x7f.cs', '../Core/Revised.cs', '/Core/Revised.cs', 'Core/./Revised.cs', 'Core//Revised.cs',
                     r'Core\Revised.cs', 'C:Revised.cs', 'Core/New.cs'):
            with self.subTest(name=name):
                value=copy.deepcopy(self.reviewed);value['revisions'][name]=value['revisions'].pop(self.name)
                self.write('source-pin-revisions-v2.json',value)
                with self.assertRaisesRegex(pins.SourcePinError, 'source path|reviewed source'): self.resolve(self.other)

    def test_all_entries_validated_before_resolving_untouched_source(self):
        self.reviewed['revisions'][self.name]['sha256']='not-a-digest'
        self.write_all()
        with self.assertRaisesRegex(pins.SourcePinError, 'Invalid SHA256'): self.resolve(self.other)

    def test_malformed_hashes_rejected(self):
        for value in ('A'*64, 'a'*63, 'a'*65, None, 123, True):
            for field in ('originalSha256','previousSha256','sha256'):
                with self.subTest(value=value,field=field):
                    item=copy.deepcopy(self.reviewed);item['revisions'][self.name][field]=value
                    self.write('source-pin-revisions-v2.json',item)
                    with self.assertRaisesRegex(pins.SourcePinError, 'Invalid SHA256'): self.resolve()

    def test_broken_previous_or_original_chain_rejected(self):
        for field in ('originalSha256','previousSha256'):
            item=copy.deepcopy(self.reviewed);item['revisions'][self.name][field]='f'*64
            self.write('source-pin-revisions-v2.json',item)
            with self.assertRaisesRegex(pins.SourcePinError, 'Reviewed original anchor mismatch|Broken prior revision chain'): self.resolve()

    def test_prior_layer_original_mismatch_rejected(self):
        self.previous['sha256'][self.name]['originalSha256']='f'*64
        self.write_all()
        with self.assertRaisesRegex(pins.SourcePinError, 'Prior original anchor mismatch'): self.resolve()

    def test_unknown_prior_revision_rejected(self):
        self.previous['sha256']['Core/New.cs']=self.previous['sha256'][self.name]
        self.write_all()
        with self.assertRaisesRegex(pins.SourcePinError, 'Unknown prior revision'): self.resolve()

    def test_historical_bytes_cannot_be_silently_rewritten(self):
        for name in ('ui-patch-baseline.json','checkpoint-source-baseline.json'):
            p=self.root/'validation'/name;raw=p.read_bytes();p.write_bytes(raw+b' ')
            with self.assertRaisesRegex(pins.SourcePinError,'Historical manifest bytes changed'):self.resolve()
            p.write_bytes(raw)

    def test_missing_or_unexpected_review_fields_rejected(self):
        errors={'missing':'Unexpected reviewed entry fields', 'extra':'Unexpected reviewed manifest fields',
                'empty':'Missing reviewed revisions', 'stage':'Unsupported reviewed manifest version',
                'schema':'Unsupported reviewed manifest version', 'redundant':'Redundant reviewed revision'}
        for mutation in ('missing','extra','empty','stage','schema','redundant'):
            value=copy.deepcopy(self.reviewed)
            if mutation=='missing':del value['revisions'][self.name]['review']
            if mutation=='extra':value['extra']='unknown'
            if mutation=='empty':value['revisions']={}
            if mutation=='stage':value['stage']=True
            if mutation=='schema':value['schema']='other/v2'
            if mutation=='redundant':value['revisions'][self.name]['sha256']=digest(b'previous')
            self.write('source-pin-revisions-v2.json',value)
            with self.subTest(mutation=mutation),self.assertRaisesRegex(pins.SourcePinError,errors[mutation]):self.resolve()

    def test_missing_malformed_review_evidence_rejected(self):
        changes={'completeness':'invented-proof','stages':[True],'reason':'','evidence':[],'limitation':''}
        errors={'completeness':'Unknown provenance completeness', 'stages':'Invalid review stages',
                'reason':'Missing review reason', 'evidence':'Missing review evidence',
                'limitation':'Missing review limitation'}
        for field,value in changes.items():
            item=copy.deepcopy(self.reviewed);item['revisions'][self.name]['review'][field]=value
            self.write('source-pin-revisions-v2.json',item)
            with self.subTest(field=field),self.assertRaisesRegex(pins.SourcePinError,errors[field]):self.resolve()

    def test_gap_label_is_explicitly_supported_without_claiming_full_history(self):
        self.reviewed['revisions'][self.name]['review']['completeness']='reviewed-current-with-historical-gap'
        self.reviewed['revisions'][self.name]['review']['limitation']='Exact earlier transition bytes are unavailable.'
        self.successor['revisions'][self.name]['review']['completeness']='reviewed-current-with-historical-gap'
        self.write_all();self.check_sources()

    def test_v3_hash_is_bound_to_exact_v2_bytes(self):
        p=self.root/'validation/source-pin-revisions-v2.json'
        p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaisesRegex(pins.SourcePinError, 'Reviewed v2 manifest bytes changed'):
            self.resolve(self.other)

    def test_v3_wrong_v2_manifest_hash_rejected(self):
        self.successor['previousReviewedManifestSha256']='f'*64
        self.write('source-pin-revisions-v3.json',self.successor)
        with self.assertRaisesRegex(pins.SourcePinError, 'Reviewed v2 manifest bytes changed'):
            self.resolve()

    def test_v3_previous_hash_must_be_effective_v2_hash(self):
        for value in (digest(b'original'), digest(b'previous'), 'f'*64):
            with self.subTest(value=value):
                item=copy.deepcopy(self.successor)
                item['revisions'][self.name]['previousSha256']=value
                self.write('source-pin-revisions-v3.json',item)
                with self.assertRaisesRegex(pins.SourcePinError, 'Broken successor revision chain'):
                    self.resolve()

    def test_v3_original_hash_must_preserve_original_anchor(self):
        self.successor['revisions'][self.name]['originalSha256']=digest(b'current')
        self.write('source-pin-revisions-v3.json',self.successor)
        with self.assertRaisesRegex(pins.SourcePinError, 'Successor original anchor mismatch'):
            self.resolve()

    def test_v3_redundant_revision_rejected(self):
        self.successor['revisions'][self.name]['sha256']=digest(b'current')
        self.write('source-pin-revisions-v3.json',self.successor)
        with self.assertRaisesRegex(pins.SourcePinError, 'Redundant successor revision'):
            self.resolve()

    def test_v3_cannot_silently_fall_back_to_v2_source(self):
        (self.root/self.name).write_bytes(b'current')
        self.assertEqual(self.resolve(),digest(b'round36'))
        with self.assertRaises(AssertionError): self.check_sources()

    def test_v3_all_entries_checked_when_resolving_untouched_source(self):
        self.successor['revisions'][self.name]['sha256']='invalid'
        self.write('source-pin-revisions-v3.json',self.successor)
        with self.assertRaisesRegex(pins.SourcePinError, 'Invalid SHA256'):
            self.resolve(self.other)

    def test_v3_malformed_hashes_rejected(self):
        for value in ('A'*64, 'a'*63, 'a'*65, '', None, 123, True, [], {}):
            for field in ('originalSha256','previousSha256','sha256','previousReviewedManifestSha256'):
                with self.subTest(value=value,field=field):
                    item=copy.deepcopy(self.successor)
                    target=item if field=='previousReviewedManifestSha256' else item['revisions'][self.name]
                    target[field]=value
                    self.write('source-pin-revisions-v3.json',item)
                    with self.assertRaisesRegex(pins.SourcePinError,'Invalid SHA256'): self.resolve()

    def test_v3_noncanonical_unknown_or_unreviewed_paths_rejected(self):
        for name in ('.', 'Core/\x00.cs', 'Core/\n.cs', 'Core/\x7f.cs', '../Core/Revised.cs',
                     '/Core/Revised.cs', 'Core/./Revised.cs', 'Core//Revised.cs',
                     r'Core\Revised.cs', 'C:Revised.cs', 'Core/New.cs', self.other):
            with self.subTest(name=name):
                item=copy.deepcopy(self.successor)
                item['revisions'][name]=item['revisions'].pop(self.name)
                self.write('source-pin-revisions-v3.json',item)
                with self.assertRaisesRegex(pins.SourcePinError,'source path|successor source'):
                    self.resolve(self.other)

    def test_v3_missing_and_extra_fields_rejected_at_every_level(self):
        for level in ('manifest','entry','review'):
            original=self.successor if level=='manifest' else self.successor['revisions'][self.name]
            if level=='review': original=original['review']
            for field in list(original)+['extra']:
                with self.subTest(level=level,field=field):
                    item=copy.deepcopy(self.successor)
                    target=item if level=='manifest' else item['revisions'][self.name]
                    if level=='review': target=target['review']
                    if field=='extra': target[field]='unrecognized'
                    else: del target[field]
                    self.write('source-pin-revisions-v3.json',item)
                    with self.assertRaisesRegex(pins.SourcePinError,'successor .*fields|structured successor review'):
                        self.resolve()

    def test_v3_malformed_manifest_schema_stage_scope_and_revisions_rejected(self):
        changes={'schema':['mvs-source-pin-revisions/v2',None], 'stage':[35,37,True,36.0,'36'],
                 'note':['',' ',None,[]], 'revisions':[{},[],None]}
        for field,values in changes.items():
            for value in values:
                with self.subTest(field=field,value=value):
                    item=copy.deepcopy(self.successor);item[field]=value
                    self.write('source-pin-revisions-v3.json',item)
                    with self.assertRaises(pins.SourcePinError): self.resolve()

    def test_v3_malformed_entry_and_review_objects_rejected(self):
        for value in (None,[],False,'reviewed'):
            for target in ('entry','review'):
                with self.subTest(value=value,target=target):
                    item=copy.deepcopy(self.successor)
                    if target=='entry': item['revisions'][self.name]=value
                    else: item['revisions'][self.name]['review']=value
                    self.write('source-pin-revisions-v3.json',item)
                    with self.assertRaises(pins.SourcePinError): self.resolve()

    def test_v3_missing_or_malformed_review_data_rejected(self):
        changes={'completeness':['invented-proof',None],
                 'transitionCompleteness':['reviewed-current-with-historical-gap','',None],
                 'stages':[[],[35],[37],[36,36],[True],[36.0],36,None],
                 'reason':['',' ',None,[]], 'limitation':['',' ',None,[]],
                 'evidence':[[],None,'docs/review.md',['docs/review.md','docs/review.md'],
                             ['../review.md'],['/review.md'],['docs/./review.md'],
                             ['docs//review.md'],['docs\\review.md'],['docs/\nreview.md'],[None],[{}]]}
        for field,values in changes.items():
            for value in values:
                with self.subTest(field=field,value=value):
                    item=copy.deepcopy(self.successor);item['revisions'][self.name]['review'][field]=value
                    self.write('source-pin-revisions-v3.json',item)
                    with self.assertRaises(pins.SourcePinError): self.resolve()

    def test_v3_cannot_erase_v2_historical_gap(self):
        self.reviewed['revisions'][self.name]['review']['completeness']='reviewed-current-with-historical-gap'
        self.write_all()
        with self.assertRaisesRegex(pins.SourcePinError,'Successor historical completeness changed'):
            self.resolve()

    def test_v3_nested_duplicate_keys_rejected(self):
        original=json.dumps(self.successor)
        for key,value in (('sha256',digest(b'round36')),('transitionCompleteness','complete-reviewed-transition')):
            field=json.dumps(key)+': '+json.dumps(value)
            raw=original.replace(field,field+', '+field,1)
            with self.subTest(key=key):
                (self.root/'validation/source-pin-revisions-v3.json').write_text(raw)
                with self.assertRaisesRegex(pins.SourcePinError,'Duplicate manifest key'):
                    self.resolve()

    def test_optimized_python_cannot_disable_contract(self):
        self.reviewed['revisions'][self.name]['previousSha256']='f'*64;self.write_all()
        code="import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); import source_pins as p; p.ROOT=Path(sys.argv[2]);\ntry: p.expected_source_hash(sys.argv[3],sys.argv[4])\nexcept p.SourcePinError: print('rejected')\nelse: raise SystemExit('invalid manifest accepted')"
        result=subprocess.run([sys.executable,'-O','-c',code,str(Path(pins.__file__).parent),str(self.root),self.name,self.original['sha256'][self.name]],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'rejected')

    def test_optimized_python_cannot_disable_v3_contract(self):
        self.successor['revisions'][self.name]['previousSha256']='f'*64;self.write_all()
        code="import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); import source_pins as p; p.ROOT=Path(sys.argv[2]);\ntry: p.expected_source_hash(sys.argv[3],sys.argv[4])\nexcept p.SourcePinError as e: print(e)\nelse: raise SystemExit('invalid v3 manifest accepted')"
        result=subprocess.run([sys.executable,'-O','-c',code,str(Path(pins.__file__).parent),str(self.root),self.name,self.original['sha256'][self.name]],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Broken successor revision chain',result.stdout)


class RepositoryPinTests(unittest.TestCase):
    def test_reviewed_repository_sources_match(self):
        anchors,_=pins._contract()
        for name,anchor in anchors.items():
            with self.subTest(source=name):
                self.assertEqual(digest((pins.ROOT/name).read_bytes()),pins.expected_source_hash(name,anchor))

    def test_historical_manifest_bytes_remain_original(self):
        expected = {
            'ui-patch-baseline.json': 'f616b9060f762d636bc7214f37894845237694cc64f010da91d471697282c22e',
            'checkpoint-source-baseline.json': '77e5002db1ddf0bd3deb3b623f137273067ff37a5d26950de7db60edc5feb53f',
            'source-pin-revisions-v2.json': '2ace7d73f042dff2b3f0bca5d206c7e0f22d70e54fce41588ccb622c94eb0923',
        }
        for name, sha in expected.items():
            with self.subTest(manifest=name):
                self.assertEqual(digest((pins.ROOT/'validation'/name).read_bytes()), sha)

    def test_round35_scope_and_historical_gap_labels_are_explicit(self):
        _, reviewed = pins._read('source-pin-revisions-v2.json')
        expected = {
            'Benchmark/BenchmarkDatasets.cs', 'Benchmark/BenchmarkOptions.cs', 'Benchmark/BenchmarkReport.cs',
            'Core/AnalysisEngine.cs', 'Core/EstimationStudy.cs', 'Core/MelsmAnalysis.cs', 'Core/Models.cs',
            'Core/NumericalMethods.cs', 'Core/VarianceAnalysis.cs', 'Infrastructure/CliArguments.cs',
            'Infrastructure/CsvImporter.cs', 'Infrastructure/OutputExporter.cs', 'Infrastructure/PluginManager.cs',
            'Infrastructure/RunAuditor.cs', 'MvsAnalyzer.Cli/HeadlessRun.cs',
            'MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj', 'MvsAnalyzer.Cli/ScientificCommands.cs',
        }
        gaps = {'Infrastructure/CliArguments.cs', 'MvsAnalyzer.Cli/HeadlessRun.cs',
                'MvsAnalyzer.Cli/MvsAnalyzer.Cli.csproj', 'MvsAnalyzer.Cli/ScientificCommands.cs'}
        self.assertEqual(set(reviewed['revisions']), expected)
        self.assertEqual({name for name, item in reviewed['revisions'].items()
                          if item['review']['completeness'] == 'reviewed-current-with-historical-gap'}, gaps)

    def test_all_review_evidence_paths_exist(self):
        for manifest in ('source-pin-revisions-v2.json','source-pin-revisions-v3.json'):
            _,reviewed=pins._read(manifest)
            for name,record in reviewed['revisions'].items():
                for evidence in record['review']['evidence']:
                    with self.subTest(manifest=manifest,source=name,evidence=evidence):
                        self.assertTrue((pins.ROOT/evidence).is_file())

    def test_round36_scope_and_preserved_historical_gap_are_explicit(self):
        v2_raw,v2=pins._read('source-pin-revisions-v2.json')
        _,v3=pins._read('source-pin-revisions-v3.json')
        name='MvsAnalyzer.Cli/ScientificCommands.cs'
        self.assertEqual(set(v3['revisions']),{name})
        self.assertEqual(v3['previousReviewedManifestSha256'],digest(v2_raw))
        record=v3['revisions'][name]
        self.assertEqual(record['originalSha256'],v2['revisions'][name]['originalSha256'])
        self.assertEqual(record['previousSha256'],v2['revisions'][name]['sha256'])
        self.assertEqual(record['sha256'],'e645752d8b009ea4d5428e856d8741c2ece40d73de0142256587c255462ba8a8')
        self.assertEqual(record['review']['completeness'],'reviewed-current-with-historical-gap')
        self.assertEqual(record['review']['transitionCompleteness'],'complete-reviewed-transition')
        self.assertEqual(record['review']['stages'],[36])

    def test_only_one_effective_round35_pin_changes_in_round36(self):
        anchors,effective=pins._contract()
        _,previous=pins._read('checkpoint-source-baseline.json')
        _,v2=pins._read('source-pin-revisions-v2.json')
        round35=dict(anchors)
        for name,record in previous['sha256'].items(): round35[name]=record['sha256']
        for name,record in v2['revisions'].items(): round35[name]=record['sha256']
        self.assertEqual({name for name in anchors if round35[name]!=effective[name]},
                         {'MvsAnalyzer.Cli/ScientificCommands.cs'})


if __name__=='__main__':
    unittest.main(verbosity=2)
