"""Hash small source/runner files; never duplicates or hashes large corpora here."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser()
    for key in ('root','baseline-root','implementation-root','plan'):p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args();git=lambda root,*a:subprocess.check_output(['git','-C',str(root),*a],text=True).strip()
    target=git(args.implementation_root,'rev-parse','HEAD')
    if git(args.implementation_root,'status','--porcelain'):p.error('Target must remain clean')
    baseline='f03577e650ce5f604e9585f5bee983ef01bccad3'
    def hashes(root):return {str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((root/'python').glob('workspace_*.py'))}
    before=hashes(args.baseline_root);after=hashes(args.implementation_root)
    for relative,sha in before.items():
        original=subprocess.check_output(['git','-C',str(args.baseline_root),'show',baseline+':'+relative])
        if hashlib.sha256(original).hexdigest()!=sha:raise AssertionError('Baseline application changed')
    runners={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))}
    result=dict(status='exact_committed_application_and_runner_hashes',baseline_commit=baseline,target_commit=target,
        baseline_python=before,target_python=after,harness_python=runners,
        truth_json_sha256=hashlib.sha256(Path(__file__).with_name('native-truth.json').read_bytes()).hexdigest(),
        plan_sha256=hashlib.sha256(args.plan.read_bytes()).hexdigest(),captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        baseline_root=str(args.baseline_root),target_root=str(args.implementation_root),
        hardware_model='Fresh sysctl hardware lookup restricted by sandbox; runtime platform strings in receipts',
        source_path_policy='Main timing imports baseline native modules first; typed modules resolve to clean target; predicates/tree/metadata decoder dependencies unchanged across commits')
    (args.root/'provenance.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],native_files=len(before),target_files=len(after),runner_files=len(runners))))


if __name__=='__main__':main()
