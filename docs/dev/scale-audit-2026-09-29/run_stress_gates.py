"""Run implemented exact-data stress gates; preserve failures and evidence.

Uses the current Python interpreter and installed Node. Always runs all stages,
even after a failed gate. No real lab projects or production databases accessed.
Exit 1 means an implemented gate failed. release_ready additionally requires
the separately listed browser/native crash/power-loss trials.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--epochs',type=int,default=100000)
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args()
    if not 100<=args.epochs<=1000000:parser.error('--epochs must be 100–1000000')
    output=(args.output_dir or Path(tempfile.mkdtemp(prefix='rieke-stress-results-'))).resolve()
    output.mkdir(parents=True,exist_ok=True)
    if (output/'summary.json').exists():parser.error('Output already contains a run; choose a new directory to preserve evidence')
    env=dict(os.environ)
    env['PYTHONPATH']=os.pathsep.join([str(REPO/'python'),str(REPO/'python/tests'),env.get('PYTHONPATH','')])
    code_files=set((REPO/'python').glob('*.py')) | set((REPO/'python/tests').glob('*.py'))
    code_files.update(path for path in (REPO/'workspace-app/src').rglob('*') if path.suffix in {'.js','.jsx'})
    code_files.update(HERE.glob('*.py'));code_files.update(HERE.glob('*.mjs'))
    parser_root=REPO/'.rieke-runtime/retinanalysis'
    code_files.update(parser_root.rglob('*.py'))
    source_paths=sorted(str(path.relative_to(REPO)) for path in code_files)
    hashes={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in source_paths}
    node=shutil.which('node') or 'node'
    npm=shutil.which('npm') or 'npm'
    stages=[
        ('large_index_contracts',[sys.executable,str(HERE/'stress_contracts.py'),'--epochs',str(args.epochs),'--output',str(output/'contracts.json')]),
        ('strict_acquisition_identity',[sys.executable,str(HERE/'safety_identity_probes.py'),'--strict','--output',str(output/'identity.json')]),
        ('strict_async_selection',[node,str(HERE/'frontend-selection-race.mjs'),'--strict','--output',str(output/'selection.json')]),
        ('trace_integrity',[sys.executable,str(HERE/'benchmark_trace_integrity.py'),'--output',str(output/'trace.json')]),
        ('derived_index_process_kill',[sys.executable,'-m','unittest','test_workspace_disk_index_crash']),
        ('safety_scale_regressions',[sys.executable,'-m','unittest',
            'test_workspace_source_identity','test_workspace_catalog_identity','test_workspace_catalog_collision',
            'test_workspace_backend_responsiveness','test_workspace_epoch_page_performance','test_workspace_protocol_state','test_workspace_state_generation',
            'test_workspace_shared_tag_index','test_workspace_shared_tag_cache_dependencies','test_workspace_shared_tag_threads','test_workspace_shared_vocabulary','test_workspace_annotation_density',
            'test_workspace_metadata_objects','test_workspace_metadata_object_contract','test_workspace_cache_lifecycle',
            'test_workspace_projection_cache','test_workspace_projection_objects','test_workspace_cache_publication',
            'test_workspace_disk_index','test_workspace_tree_pages','test_workspace_refresh_cache']),
        ('export_tag_restore_regressions',[sys.executable,'-m','unittest',
            'test_recording_workspace','test_workspace_import_identities','test_workspace_identity_conflicts',
            'test_workspace_export_reader','test_workspace_sqlite',
            'test_workspace_state_snapshot','test_workspace_recovery_store','test_workspace_generation_portability',
            'test_workspace_recovery_generation',
            'test_workspace_curation_batch',
            'test_workspace_tag_lifecycle','test_workspace_tag_exchange',
            'test_workspace_portability','test_workspace_native_crash',
            'test_workspace_import_progress_failures']),
        ('frontend_regressions',[npm,'--prefix',str(REPO/'workspace-app'),'test']),
        ('frontend_build',[npm,'--prefix',str(REPO/'workspace-app'),'run','build'])]
    report={'epochs':args.epochs,'output_directory':str(output),'python':platform.python_version(),
        'platform':platform.platform(),'source_sha256':hashes,'stages':[],
        'required_unexecuted_trials':['Real browser 100k interaction/revision races',
            'Physical large multi-source H5 parse/import/export against independent waveform oracle',
            'Native MySQL/API process-kill recovery matrix','Clean-machine complete portable restore drill',
            'Power-loss/filesystem fault and disk-full trials','Tens-of-GB lab NAS cold/warm throughput and soak']}
    for name,command in stages:
        started=time.perf_counter();log=output/(name+'.log')
        print('Running '+name,flush=True)
        error=None
        with log.open('w') as stream:
            try:finished=subprocess.run(command,cwd=REPO,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=1800);code=finished.returncode
            except (OSError,subprocess.TimeoutExpired) as failure:
                error=str(failure);stream.write(error+'\n');code=-1
        item={'name':name,'status':'PASS' if code==0 else 'FAIL','exit_code':code,
              'seconds':time.perf_counter()-started,'log':str(log)}
        if error:item['error']=error
        raw=log.read_text()
        if name=='export_tag_restore_regressions':
            count=re.search(r'Ran (\d+) tests?',raw);skipped=re.search(r'skipped=(\d+)',raw)
            item.update(tests_run=int(count.group(1)) if count else None,skipped=int(skipped.group(1)) if skipped else 0)
        report['stages'].append(item)
        print(name+': '+item['status'],flush=True)
    report['release_ready']=False
    report['source_changed_during_run']=[name for name,digest in hashes.items()
        if hashlib.sha256((REPO/name).read_bytes()).hexdigest()!=digest]
    report['implemented_gates_passed']=all(stage['status']=='PASS' for stage in report['stages']) and not report['source_changed_during_run']
    (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Evidence: '+str(output/'summary.json'),flush=True)
    return 0 if report['implemented_gates_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
