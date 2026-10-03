"""Compare with explicitly supplied immutable prior validator; never vendor another authority."""
import argparse
import importlib.util
import json
import pathlib
import subprocess
import sys
import validate_bundle
import validation_diagnostics
ROOT=pathlib.Path(__file__).parent


def compare(baseline):
    spec=importlib.util.spec_from_file_location('prior_validator',baseline)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    schema=validate_bundle.loads((ROOT/'disco-metadata-bundle.schema.json').read_bytes())
    files=list((ROOT/'examples').glob('*.json'))
    files += [p for p in (ROOT/'invalid').glob('*.json') if p.name!='expected-errors.json']
    files += list((ROOT/'worked-examples').glob('expected*/bundle.json'))
    files += [p for p in (ROOT/'worked-examples/bad').glob('*.json') if p.name!='cases.json' and not p.name.endswith('.expected.json')]
    rows=[]
    for path in sorted(files):
        raw=path.read_bytes();data=old.loads(raw);expected=old.validate(data,schema)
        default=validate_bundle.validate(data,schema)
        detailed=validation_diagnostics.validate_bytes(raw,schema)
        before=subprocess.run([sys.executable,'-B',str(baseline),str(path)],capture_output=True)
        after=subprocess.run([sys.executable,'-B',str(ROOT/'validate_bundle.py'),str(path)],capture_output=True)
        rows.append({'fixture':str(path.relative_to(ROOT)),'api_equal':expected==default==detailed['legacy_report'],
                     'cli_equal':(before.returncode,before.stdout,before.stderr)==(after.returncode,after.stdout,after.stderr)})
    return {'valid':all(r['api_equal'] and r['cli_equal'] for r in rows),'cases':rows}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--baseline',required=True,type=pathlib.Path);args=parser.parse_args()
    result=compare(args.baseline);print(json.dumps(result,indent=2));raise SystemExit(0 if result['valid'] else 1)
