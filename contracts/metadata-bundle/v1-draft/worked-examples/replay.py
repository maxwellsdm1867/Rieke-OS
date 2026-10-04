"""Check frozen worked expectations without overwriting them. No bless mode."""
import argparse
import contextlib
import hashlib
import io
import json
import pathlib
import tempfile
import subprocess
import sys
import build_examples
ROOT=pathlib.Path(__file__).parent
DIRECTORIES=('expected','expected-raw-claim','expected-revision-2','expected-blocked','bad','cli-reports')
SOURCES=('source-revision-2.json','source-blocked.json')


def outputs(root):
    return {str(p.relative_to(root)):p for name in DIRECTORIES for p in (root/name).rglob('*') if p.is_file()} | {name:root/name for name in SOURCES if (root/name).is_file()}


def check(root=ROOT):
    root=pathlib.Path(root)
    with tempfile.TemporaryDirectory(prefix='disco-replay-') as tmp:
        destination=pathlib.Path(tmp)
        (destination/'source.json').write_bytes((root/'source.json').read_bytes())
        previous=build_examples.ROOT
        try:
            build_examples.ROOT=destination
            with contextlib.redirect_stdout(io.StringIO()):build_examples.build()
        finally:build_examples.ROOT=previous
        reports=destination/'cli-reports';reports.mkdir()
        bundles=list(destination.glob('expected*/bundle.json'))+[p for p in (destination/'bad').glob('*.json') if p.name!='cases.json' and not p.name.endswith('.expected.json')]
        for bundle in sorted(bundles):
            result=subprocess.run([sys.executable,'-B',str(ROOT.parent/'validate_bundle.py'),str(bundle)],capture_output=True)
            if result.returncode not in (0,1) or result.stderr:raise RuntimeError('validator CLI failed during replay')
            name=str(bundle.relative_to(destination)).replace('/','--')+'.report.json'
            (reports/name).write_bytes(result.stdout)
        expected=outputs(root);actual=outputs(destination);rows=[]
        for name in sorted(set(expected)|set(actual)):
            e=hashlib.sha256(expected[name].read_bytes()).hexdigest() if name in expected else None
            a=hashlib.sha256(actual[name].read_bytes()).hexdigest() if name in actual else None
            rows.append({'path':name,'expected_sha256':e,'actual_sha256':a,'match':e==a})
        return {'format':'disco-worked-golden-replay','valid':all(r['match'] for r in rows),'expected_files_modified':False,'comparisons':rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true',required=True);parser.parse_args()
    result=check();print(json.dumps(result,indent=2,sort_keys=True));return 0 if result['valid'] else 1
if __name__=='__main__':raise SystemExit(main())
