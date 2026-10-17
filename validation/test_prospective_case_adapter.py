"""Zero-compute native contract checks; opt in with MVS_PROSPECTIVE_CASE_NATIVE.

No native calculation is ever invoked, including in negative tests. Literal rows
are engineering transport fixtures, not generated prospective study datasets.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

PROTOCOL = 'MVS-STAT-COMPONENTS-PROSPECTIVE-1.0.0'
PIN = '75d594af6fd2f249ca044340013ea02d16e8cdbae71aef8c4e16ff6853a324ed'


def fixture(cell=10, rep=0):
    n, m = (16, 40) if cell < 10 else (8, 5)
    values = [20.0 + g + i * .125 + j * .0625 for g in range(2) for i in range(n) for j in range(m)]
    raw = b''.join(struct.pack('<d', v) for v in values)
    return dict(schema='mvs-prospective-case/v1', protocol_id=PROTOCOL, protocol_sha256=PIN,
                purpose='engineering_literal', case_id=f'engineering_literal/C{cell:02d}/R{rep:04d}',
                cell_index=cell, replication_zero_based=rep, native_seed=1540000000 + 1000 * cell + rep,
                entities_per_group=n, repeats_per_entity=m, value_order='group_entity_repeat',
                values_bits=[struct.pack('>d', v).hex() for v in values],
                ordered_binary64_sha256=hashlib.sha256(raw).hexdigest())


@unittest.skipUnless(os.environ.get('MVS_PROSPECTIVE_CASE_NATIVE'), 'native DLL not selected')
class NativeCaseContract(unittest.TestCase):
    def invoke(self, value=None, raw=None, expected=None, mode='validate-only'):
        with tempfile.TemporaryDirectory(prefix='mvs-case-contract-') as tmp:
            path = Path(tmp) / 'case.json'
            if raw is None:
                raw = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()
            path.write_bytes(raw)
            command = [os.environ.get('DOTNET', 'dotnet'), os.environ['MVS_PROSPECTIVE_CASE_NATIVE']]
            command += ['identity'] if mode == 'identity' else [mode, str(path), expected or hashlib.sha256(raw).hexdigest()]
            result = subprocess.run(command, capture_output=True, timeout=20, env=dict(os.environ, DOTNET_PROCESSOR_COUNT='1', MVS_DISABLE_BACKUPS='1'))
            rows = [json.loads(s) for s in result.stdout.splitlines() + result.stderr.splitlines()]
            self.assertEqual(len(rows), 1, (result.stdout, result.stderr))
            row = rows[0]
            self.assertEqual(row['schema'], 'mvs-prospective-case-result/v1')
            self.assertTrue(all(v == 0 for v in row['operationCounts'].values()), row)
            return result.returncode, row

    def test_identity_has_zero_work_and_pinned_sources(self):
        code, row = self.invoke({}, mode='identity')
        self.assertEqual(code, 0)
        self.assertEqual(row['configSha256'], PIN)
        self.assertEqual(len(row['identity']['sourceSha256']), 14)
        self.assertEqual(len(row['adapterSourceSha256']), 2)

    def test_all_dimensions_coordinates_and_purposes(self):
        for cell, rep in ((0, 0), (9, 999), (10, 0), (11, 999)):
            for purpose in ('engineering_literal', 'planned_case'):
                value = fixture(cell, rep)
                value['purpose'] = purpose
                value['case_id'] = f'{PROTOCOL if purpose == "planned_case" else purpose}/C{cell:02d}/R{rep:04d}'
                code, row = self.invoke(value)
                self.assertEqual(code, 0, row)
                self.assertFalse(row['computationInvoked'])

    def test_schema_coordinate_shape_type_and_digest_negatives(self):
        patches = [dict(unknown=1), dict(schema='wrong'), dict(protocol_id='wrong'), dict(protocol_sha256='0'*64),
                   dict(purpose='study_results'), dict(case_id='wrong'), dict(cell_index=-1), dict(cell_index=12),
                   dict(cell_index=True), dict(replication_zero_based=-1), dict(replication_zero_based=1000),
                   dict(replication_zero_based=0.5), dict(native_seed=1540010001), dict(entities_per_group=16),
                   dict(repeats_per_entity=40), dict(value_order='repeat_entity_group'), dict(values_bits=[]),
                   dict(ordered_binary64_sha256='0'*64)]
        for patch in patches:
            with self.subTest(patch=patch):
                value = fixture(); value.update(patch)
                code, row = self.invoke(value)
                self.assertEqual(code, 2, row)
                self.assertEqual(row['kind'], 'adapter_error')
        value = fixture(); del value['purpose']; self.assertEqual(self.invoke(value)[0], 2)

    def test_value_encoding_nonfinite_and_order_negatives(self):
        for token in ('7ff0000000000000', 'fff0000000000000', '7ff8000000000001', 'ABCDEF0123456789', '1', 20.0, None, {'bits':'4034000000000000'}):
            value = fixture(); value['values_bits'][0] = token
            self.assertEqual(self.invoke(value)[0], 2)
        value = fixture(); value['values_bits'][0], value['values_bits'][1] = value['values_bits'][1], value['values_bits'][0]
        self.assertEqual(self.invoke(value)[0], 2)

    def test_duplicates_hash_and_bounded_bytes(self):
        raw = json.dumps(fixture()).encode()
        self.assertEqual(self.invoke(raw=raw[:-1] + b',"cell_index":10}')[0], 2)
        self.assertEqual(self.invoke(raw=raw, expected='0'*64)[0], 2)
        self.assertEqual(self.invoke(raw=b' ' * 65537)[0], 2)
        self.assertEqual(self.invoke(raw=b'\xff')[0], 2)
        self.assertEqual(self.invoke(raw=b'[]')[0], 2)

    def test_finite_out_of_bounds_and_negative_zero_preserved_in_validation(self):
        value = fixture(); value['values_bits'][0] = '8000000000000000'; value['values_bits'][1] = struct.pack('>d', 1000001.0).hex()
        value['ordered_binary64_sha256'] = hashlib.sha256(b''.join(bytes.fromhex(x)[::-1] for x in value['values_bits'])).hexdigest()
        self.assertEqual(self.invoke(value)[0], 0)


if __name__ == '__main__':
    unittest.main()
