#!/usr/bin/env python3
"""Opt-in bounded actual CLI/workflow/MCP parity on synthetic calibration inputs."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'python/src'), str(ROOT / 'tools')]
from test_python_cli import compare_analysis


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cli', type=Path, required=True)
    p.add_argument('--baseline-cli', type=Path, required=True)
    p.add_argument('--calibration', type=Path, required=True)
    p.add_argument('--artifacts', type=Path, required=True)
    a = p.parse_args(); root = a.artifacts.resolve(); root.mkdir(parents=True, exist_ok=False)
    os.sched_setaffinity(0, set(sorted(os.sched_getaffinity(0))[:2]))
    inputs = root/'inputs'; inputs.mkdir(); work = root/'workflow'
    shutil.copyfile(ROOT/'examples/demo_three_groups.csv', inputs/'input.csv')
    shutil.copyfile(a.calibration.resolve(), inputs/'state.json')
    original = {p.name: sha(p) for p in inputs.iterdir()}
    env = dict(os.environ, PYTHONPATH=str(ROOT/'python/src'), DOTNET_PROCESSOR_COUNT='2',
               DOTNET_EnableDiagnostics='0', MVS_DISABLE_BACKUPS='1',
               XDG_DATA_HOME=str(root/'native-data'), MVS_BACKUP_DIR=str(root/'backups'))
    Path(env['XDG_DATA_HOME']).mkdir()
    calls = []
    def invoke(label, argv, request=None, expected=0):
        proc = subprocess.run(argv, input=None if request is None else json.dumps(request), text=True, encoding='utf-8',
                              env=env, cwd=root, capture_output=True, timeout=180)
        (root/(label+'.stdout.json')).write_text(proc.stdout)
        (root/(label+'.stderr.txt')).write_text(proc.stderr)
        calls.append(dict(label=label, argv=argv, exit=proc.returncode, stdoutSha256=sha(root/(label+'.stdout.json'))))
        assert proc.returncode == expected, (label, proc.returncode, proc.stderr, proc.stdout)
        return json.loads(proc.stdout)
    common=['analyze','--in',str(inputs/'input.csv'),'--calibration',str(inputs/'state.json')]
    baseline=invoke('baseline-analysis',[str(a.baseline_cli.resolve()),*common,'--out',str(root/'baseline'),'--json','--quiet'])
    current=invoke('current-analysis',[str(a.cli.resolve()),*common,'--out',str(root/'current'),'--json','--quiet'])
    compare_analysis(Path(baseline['outputDirectory']),Path(current['outputDirectory']),1e-12,1e-10)
    assert current['scientificReadiness']['status']=='no_go' and current['execution']['completed'] is True
    # Existing fields remain exact for deterministic identity/error cases; only explicitly additive readiness/isolation fields differ.
    for command,expected in [('version',0),('unknown-command',1)]:
        old=invoke('baseline-'+command,[str(a.baseline_cli.resolve()),command,'--json','--quiet'],expected=expected)
        new=invoke('current-'+command,[str(a.cli.resolve()),command,'--json','--quiet'],expected=expected)
        assert {k:v for k,v in new.items() if k not in {'execution','scientificReadiness','localAppDataOverride'}}==old
        assert new['execution']['completed']==(expected==0) and new['scientificReadiness']['status']=='no_go'
    # Actual exit-2 fixture, not a full benchmark.
    constant=inputs/'constant.csv'
    constant.write_text('entity,group,value,sequence,variable,unit\n'+''.join(f'{g}{e},{g},1,{s},constant,u\n' for g in 'AB' for e in range(4) for s in range(1,4)))
    diagnostic=invoke('current-diagnostic',[str(a.cli.resolve()),'variance','--in',str(constant),'--out',str(root/'constant'),
        '--repetitions','100','--bootstrap','99','--seed','20260719','--min-measurements','3','--json','--quiet'],expected=2)
    assert diagnostic['status']=='diagnostic' and diagnostic['execution']['outcome']=='completed_with_diagnostic'
    cli=[sys.executable,'-m','mvs.workflow_cli','--engine',str(a.cli.resolve()),'--read-root',str(inputs),'--work-root',str(work),'--timeout-seconds','120']
    source={'data':'input.csv','calibration':'state.json'}
    registered=invoke('register',cli+['register_protocol'],source|{'protocol_id':'protocol1','prior_exposure':'previously_inspected','question':'Fixed synthetic interface parity fixture'})
    assert registered['execution']['status']=='completed'
    exploratory=invoke('exploratory',cli+['run_analysis'],source|{'run_id':'exploratory'})
    frozen=invoke('frozen',cli+['run_analysis'],source|{'run_id':'frozen','mode':'frozen','protocol_id':'protocol1'})
    for result in [exploratory,frozen]:
        assert result['scientificReadiness']['status']=='no_go' and not result['data']['confirmatoryCertified']
        compare_analysis(Path(current['outputDirectory']),work/result['data']['native']['outputDirectory'],1e-12,1e-10)
    repeated=invoke('replay',cli+['run_analysis'],source|{'run_id':'frozen','mode':'frozen','protocol_id':'protocol1'})
    assert repeated==frozen
    conflict=invoke('registration-conflict',cli+['register_protocol'],source|{'protocol_id':'protocol1','prior_exposure':'unknown','question':'Do not replace'},expected=1)
    assert conflict['error']['code']=='protocol_conflict'
    original_state=(inputs/'state.json').read_bytes(); (inputs/'state.json').write_bytes(original_state+b'\n')
    changed=invoke('frozen-deviation',cli+['run_analysis'],source|{'run_id':'deviation','mode':'frozen','protocol_id':'protocol1'},expected=1)
    assert changed['error']['code']=='protocol_deviation'
    (inputs/'state.json').write_bytes(original_state)
    async def wire():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        config=StdioServerParameters(command=sys.executable,args=['-m','mvs.mcp_server','--engine',str(a.cli.resolve()),'--read-root',str(inputs),'--work-root',str(work),'--timeout-seconds','120'],env=env)
        with (root/'mcp.stderr.txt').open('w') as err:
            async with stdio_client(config,errlog=err) as (read,write):
                async with ClientSession(read,write) as session:
                    init=await session.initialize()
                    response=await session.call_tool('get_run',{'run_id':'frozen'})
                    assert not response.isError and response.structuredContent==frozen
                    fresh=await session.call_tool('run_analysis',source|{'run_id':'mcp-frozen','mode':'frozen','protocol_id':'protocol1'})
                    assert not fresh.isError, fresh
                    value=fresh.structuredContent
                    compare_analysis(Path(current['outputDirectory']),work/value['data']['native']['outputDirectory'],1e-12,1e-10)
                    (root/'mcp-frozen.json').write_text(json.dumps(value,indent=2))
                    return {'protocolVersion':init.protocolVersion,'getRunMatchesCli':True,'freshNativeScientificParity':True}
    mcp=asyncio.run(wire())
    assert all(sha(inputs/name)==v for name,v in original.items())
    result={'status':'passed','legacyScientificParity':True,'legacyIdentityAndErrorFieldsPreserved':True,'nativeDiagnosticExit2':True,
            'exploratoryFrozenAndMcpScientificParity':True,'frozenDeviationRejected':True,'idempotentReplay':True,
            'mcp':mcp,'calls':calls,'scientificReadiness':'NO-GO retained','limits':['Synthetic same-engine consistency, not independent scientific validity.','Linux only; no full benchmark or Windows run.']}
    (root/'integration-results.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps({k:v for k,v in result.items() if k!='calls'}))


if __name__=='__main__': main()
