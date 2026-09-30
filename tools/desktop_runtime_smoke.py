#!/usr/bin/env python3
"""Exercise a relocated runtime under a fresh HOME without development PATH.

This local-host test does not substitute for another user/clean macOS machine.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROBE = r'''
import json,os,sys
from pathlib import Path
runtime=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(runtime/'application/python'))
os.environ['RIEKE_DESKTOP_RUNTIME']=str(runtime)
from workspace_bootstrap import prepare_desktop_parser_config,probe_runtime,validate_desktop_runtime
from workspace_mysql_runtime import mysql_runtime
manifest=validate_desktop_runtime(runtime,verify_hashes=True)
prepare_desktop_parser_config(Path.home()/'state')
parser=probe_runtime(str(runtime/'python/bin/python3.11'),str(runtime/'parser'))
mysql=mysql_runtime(runtime/'application')
validate_desktop_runtime(runtime,verify_hashes=True)
print('RIEKE_SMOKE='+json.dumps({'parser':parser,'mysql_version':mysql['version'],
 'resource_hashes_before_and_after':'unchanged','application_version':manifest['application_version']}))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=ROOT/'desktop/build/runtime')
    parser.add_argument('--output', type=Path)
    args=parser.parse_args()
    runtime=args.runtime.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='Rieke relocated app ') as temp:
        base=Path(temp)
        # APFS clones preserve symlinks and permissions without duplicate storage.
        subprocess.run(['/bin/cp','-cR',str(runtime),str(base/'runtime')],check=True)
        home=base/'fresh user state';home.mkdir()
        env={'HOME':str(home),'PATH':'/usr/bin:/bin','TMPDIR':temp,'LANG':'en_US.UTF-8',
             'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1', 'MPLCONFIGDIR':str(home/'matplotlib')}
        result=subprocess.run([str(base/'runtime/python/bin/python3.11'),'-c',PROBE,str(base/'runtime')],
                              env=env,cwd=home,text=True,capture_output=True,check=True,timeout=180)
        value=json.loads(next(line.split('=',1)[1] for line in result.stdout.splitlines() if line.startswith('RIEKE_SMOKE=')))
    report={'format':'rieke-desktop-runtime-local-smoke','version':1,'status':'passed',
            'local_host_only':True,'production_ready':False,'isolated_home':True,
            'development_path_excluded':True,'relocated_path_with_spaces':True,**value,
            'not_validated':['different user or clean machine','native database/scientific workflows',
                             'Developer ID and notarization','signed old-to-new update']}
    text=json.dumps(report,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text)
    print(text,end='')

if __name__=='__main__':main()
