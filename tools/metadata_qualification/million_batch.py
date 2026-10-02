"""Exclusive serial coordinator: preserves capped/incomplete pairs and retries after-only safely."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--baseline-root',type=Path,required=True);p.add_argument('--implementation-root',type=Path,required=True)
    p.add_argument('--target-commit',required=True);p.add_argument('--plan',type=Path,required=True);args=p.parse_args()
    plan=json.loads(args.plan.read_bytes());out=args.root/'receipts';out.mkdir(exist_ok=True)
    common=[sys.executable,'-B',str(Path(__file__).with_name('million_worker.py')),
        '--baseline-root',str(args.baseline_root),'--implementation-root',str(args.implementation_root),
        '--target-commit',args.target_commit,'--source','/private/tmp/disco-real-million-20261001/base.sqlite',
        '--real','/private/tmp/disco-real-data-evals-20261001/engines/real.sqlite',
        '--candidate',str(args.root/'candidate.sqlite'),'--verified-corpus','/tmp/typed-qualification-corpus-verified.json',
        '--build-receipt','/tmp/typed-qualification-million-build.json','--plan',str(args.plan)]
    jobs=[(n,'page') for n in range(len(plan['cases']))]+[(n,'facets') for n in (0,1,10,11)]
    progress=dict(status='running',target_commit=args.target_commit,serial=True,jobs=[],started=time.time())
    manifest=args.root/'batch.json'
    def save():manifest.write_text(json.dumps(progress,indent=2)+'\n')
    save()
    for n,mode in jobs:
        label=plan['cases'][n]['label'];receipt=out/(label+'-'+mode+'.json');log=receipt.with_suffix('.log')
        if receipt.exists():
            prior=json.loads(receipt.read_bytes())
            if prior.get('status')=='passed' and prior.get('target_commit')==args.target_commit:
                progress['jobs'].append(dict(label=label,mode=mode,status='retained_completed_pair',receipt=str(receipt)));save();continue
        print(json.dumps(dict(event='job_start',case=label,mode=mode)),flush=True)
        cmd=common+['--case',str(n),'--mode',mode,'--receipt',str(receipt)]
        with log.open('w') as stream:
            try:result=subprocess.run(cmd,stdout=stream,stderr=subprocess.STDOUT,timeout=400)
            except subprocess.TimeoutExpired:result=None
        observed=json.loads(receipt.read_bytes()) if receipt.exists() else {'status':'missing'}
        progress['jobs'].append(dict(label=label,mode=mode,status=observed['status'],returncode=result.returncode if result else None,receipt=str(receipt)))
        save();print(json.dumps(progress['jobs'][-1]),flush=True)
        arms=observed.get('arms',{})
        if observed.get('status')!='passed' and arms.get('candidate',{}).get('status')!='passed':
            # No equivalence/speedup pass follows a capped baseline. Candidate-only
            # keeps independent source truth, but is explicitly an unpaired observation.
            fallback=out/(label+'-'+mode+'-candidate-only.json')
            with fallback.with_suffix('.log').open('w') as stream:
                try:after=subprocess.run(common+['--case',str(n),'--mode',mode,'--arms','candidate','--receipt',str(fallback)],stdout=stream,stderr=subprocess.STDOUT,timeout=180)
                except subprocess.TimeoutExpired:after=None
            value=json.loads(fallback.read_bytes()) if fallback.exists() else {'status':'missing'}
            progress['jobs'].append(dict(label=label,mode=mode,unpaired=True,status=value['status'],returncode=after.returncode if after else None,receipt=str(fallback)));save()
            print(json.dumps(progress['jobs'][-1]),flush=True)
    progress.update(status='complete_ledger_including_incomplete_arms',finished=time.time());save()


if __name__=='__main__':main()
