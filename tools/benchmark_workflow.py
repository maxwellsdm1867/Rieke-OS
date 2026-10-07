#!/usr/bin/env python3
"""End-to-end action receipts, module attribution and matched regression comparison.

Browser wall time is the headline. Profiled module evidence is a separate layer;
server elapsed time is nested inside transport, never added to browser wall time.
"""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import time

if __package__:
    from . import benchmark_everyday as query_bench
else:
    import benchmark_everyday as query_bench

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 'disco-workflow-v1'
BROWSER_FORMAT = 'disco-workflow-browser-v1'


def number(value, name, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or positive and value == 0:
        raise ValueError(f'Invalid {name}')
    return value


def union(intervals):
    result = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def length(intervals):
    return sum(end-start for start,end in union(intervals))


def subtract(interval, children):
    start,end = interval
    result = []
    cursor = start
    for left,right in union(children):
        if left > cursor:
            result.append((cursor,left))
        cursor = max(cursor,right)
    if cursor < end:
        result.append((cursor,end))
    return result


def summarize_spans(spans, total_ms, clock='browser'):
    """Union within an owner; report cross-owner overlap instead of inventing CPU shares."""
    number(total_ms, 'total_ms', positive=True)
    by_id = {}
    for span in spans:
        identity = span.get('id')
        if not isinstance(identity,str) or not identity or identity in by_id:
            raise ValueError('Missing/duplicate span identity')
        if span.get('clock') != clock:
            raise ValueError('Cross-clock spans require explicit nesting, not subtraction')
        if not isinstance(span.get('module'),str) or not span['module']:
            raise ValueError('Missing module owner')
        start,end = number(span.get('start_ms'),'span start'),number(span.get('end_ms'),'span end')
        if end < start or end > total_ms+1e-6:
            raise ValueError('Span outside action window')
        by_id[identity] = span
    children = {key:[] for key in by_id}
    for identity,span in by_id.items():
        parent = span.get('parent_id')
        if parent is not None:
            if parent not in by_id or parent == identity:
                raise ValueError('Invalid span parent')
            ancestor = by_id[parent]
            if ancestor['start_ms'] > span['start_ms'] or ancestor['end_ms'] < span['end_ms']:
                raise ValueError('Parent does not contain child')
            seen = {identity}
            cursor = parent
            while cursor is not None:
                if cursor in seen:
                    raise ValueError('Cyclic span nesting')
                seen.add(cursor)
                if cursor not in by_id:
                    raise ValueError('Missing span parent')
                cursor = by_id[cursor].get('parent_id')
            children[parent].append((span['start_ms'],span['end_ms']))
    groups = {}
    for identity,span in by_id.items():
        group = groups.setdefault(span['module'], {'inclusive':[],'self':[],'calls':0})
        interval = (span['start_ms'],span['end_ms'])
        group['inclusive'].append(interval)
        group['self'].extend(subtract(interval,children[identity]))
        group['calls'] += 1
    covered = length((s['start_ms'],s['end_ms']) for s in spans)
    exclusive = [interval for group in groups.values() for interval in group['self']]
    overlap = max(0, sum(length(g['self']) for g in groups.values())-length(exclusive))
    return {'clock':clock,'total_ms':total_ms,'covered_ms':covered,
            'unattributed_ms':max(0,total_ms-covered),'cross_owner_overlap_ms':overlap,
            'additive':overlap < 1e-6,
            'modules':{owner:{'inclusive_ms':length(g['inclusive']), 'self_ms':length(g['self']),
                              'calls':g['calls']} for owner,g in groups.items()}}


def validate_trace(trace, total_ms):
    if not isinstance(trace,dict):
        raise ValueError('Missing trace identity/window evidence')
    fields = ('epoch_uuid','stream_uuid','units','start','end')
    expected = trace.get('expected')
    if not isinstance(expected,dict) or any(key not in expected for key in fields):
        raise ValueError('Missing expected trace identity/window')
    for key in ('epoch_uuid','stream_uuid','units'):
        if not isinstance(expected[key],str) or not expected[key]:
            raise ValueError('Invalid trace identity/units')
    number(expected['start'],'trace window start')
    number(expected['end'],'trace window end',positive=True)
    if expected['end'] <= expected['start']:
        raise ValueError('Invalid trace window')
    for boundary in ('first','complete'):
        actual = trace.get(boundary)
        if not isinstance(actual,dict) or any(actual.get(key) != expected[key] for key in fields):
            raise ValueError(f'Wrong {boundary} trace identity/window')
    first = number(trace.get('first_visible_ms'),'first trace time')
    complete = number(trace.get('complete_ms'),'complete trace time')
    if not 0 <= first <= complete <= total_ms+1e-6:
        raise ValueError('Trace endpoints outside action or in wrong order')


def validate_action(action, cfgcase, samples):
    if action.get('id') != cfgcase['id'] or not isinstance(action.get('variant'),str) or not action['variant']:
        raise ValueError('Missing action identity/variant')
    values = action.get('samples')
    if not isinstance(values,list):
        raise ValueError('Missing action samples')
    ordinary = [s for s in values if s.get('phase') == 'ordinary']
    profile = [s for s in values if s.get('phase') == 'profile']
    if len(ordinary) != samples or not profile or len(ordinary)+len(profile) != len(values):
        raise ValueError('Missing ordinary/profile samples or invalid phase')
    identities = set()
    request_identities = set()
    for sample in values:
        identity = sample.get('action_id')
        if not isinstance(identity,str) or not identity or identity in identities:
            raise ValueError('Missing/duplicate action correlation ID')
        identities.add(identity)
        total = number(sample.get('total_ms'),'action total',positive=True)
        if not isinstance(sample.get('correctness'),dict) or sample['correctness'].get('passed') is not True:
            raise ValueError('Failed/missing action correctness oracle')
        if not isinstance(sample.get('requests'),list) or not isinstance(sample.get('frontend_spans'),list):
            raise ValueError('Missing request/stage evidence')
        for request in sample['requests']:
            if (request.get('action_id') != identity or not isinstance(request.get('request_id'),str)
                    or not request['request_id'] or request['request_id'] in request_identities):
                raise ValueError('Missing/duplicate request correlation')
            request_identities.add(request['request_id'])
            if type(request.get('status')) is not int or not 200 <= request['status'] < 300:
                raise ValueError('Failed action request')
        summarize_spans(sample['frontend_spans'],total)
        if cfgcase.get('trace'):
            validate_trace(sample.get('trace'),total)
    return {'total_ms':statistics.median(s['total_ms'] for s in ordinary),
            'ordinary_samples':len(ordinary),'profile_samples':len(profile)}


def validate_browser(result, cfg, epochs=1_000_000, samples=3):
    if result.get('format') != BROWSER_FORMAT or result.get('status') != 'passed':
        raise ValueError('Failed/incomplete browser result')
    if epochs != 1_000_000 or result.get('epochs') != epochs:
        raise ValueError('End-to-end qualification requires an actual million-epoch project')
    if result.get('failures') != [] or result.get('gaps') != []:
        raise ValueError('Unmeasured/failed required action coverage')
    cleanup = result.get('cleanup',{})
    if cleanup.get('browser_closed') is not True or cleanup.get('vite_closed') is not True:
        raise ValueError('Browser cleanup is incomplete or unknown')
    actions = result.get('actions')
    if not isinstance(actions,list):
        raise ValueError('Missing action results')
    required = {case['id']:case for case in cfg['cases']}
    found = set()
    variants = set()
    for action in actions:
        identity = action.get('id')
        key = (identity,action.get('variant'))
        if identity not in required or key in variants:
            raise ValueError('Unknown/duplicate action')
        if required[identity].get('variants') and action.get('variant') not in required[identity]['variants']:
            raise ValueError('Unknown action variant')
        variants.add(key)
        found.add(identity)
        validate_action(action,required[identity],samples)
    if found != set(required):
        raise ValueError('Missing required action')
    for identity,case in required.items():
        for variant in case.get('variants',[]):
            if (identity,variant) not in variants:
                raise ValueError(f'Missing required variant {identity}/{variant}')


def compare_metrics(baseline, candidate, policy):
    if set(baseline) != set(candidate):
        raise ValueError('Different action coverage')
    rows, findings = [], []
    for case,before in baseline.items():
        after = candidate[case]
        if set(before['modules']) != set(after['modules']):
            raise ValueError('Different module attribution coverage')
        metrics = [('total_ms',before['total_ms'],after['total_ms'])]
        metrics += [('module:'+m,v,after['modules'][m]) for m,v in before['modules'].items()]
        for metric,old,new in metrics:
            number(old,'baseline metric');number(new,'candidate metric')
            threshold = max(old*(1+policy['relative']),old+policy['absolute_ms'])
            review = new > threshold
            rows.append({'case':case,'metric':metric,'baseline_ms':old,'candidate_ms':new,
                         'threshold_ms':threshold,'review_required':review})
            if review:
                findings.append(case+'/'+metric)
    return {'status':'review_required' if findings else 'passed','review_required':findings,'metrics':rows}


def config():
    return json.loads((ROOT/'benchmarks/registry.json').read_text())['stress_tracks']['workflow-million']


def harness():
    names = ['tools/benchmark_workflow.py','tools/benchmark_everyday.py',
             'benchmarks/registry.json','benchmarks/requirements-py311.txt',
             'benchmarks/navigation-probe.mjs']
    names += [str(p.relative_to(ROOT)) for p in (ROOT/'benchmarks/workflow').rglob('*')
              if p.is_file() and p.suffix in {'.py','.mjs'}]
    return {name:query_bench.sha((ROOT/name).read_bytes()) for name in sorted(names)}


def load_requests(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    found = {}
    for row in rows:
        identity = row.get('request_id')
        if not isinstance(identity,str) or not identity or identity in found:
            raise ValueError('Duplicate/missing backend request identity')
        number(row.get('total_ms'),'server request total',positive=True)
        if row.get('clock') != 'server' or row.get('phase') not in ('ordinary','profile'):
            raise ValueError('Missing backend phase/clock')
        if not isinstance(row.get('spans'),list):
            raise ValueError('Missing backend profile evidence')
        if row['phase'] == 'ordinary' and row['spans']:
            raise ValueError('Ordinary latency run was profiled')
        for span in row['spans']:
            inclusive = number(span.get('inclusive_ms'),'profile inclusive')
            own = number(span.get('self_ms'),'profile self')
            if own > inclusive+1e-5 or not isinstance(span.get('module'),str):
                raise ValueError('Invalid backend module attribution')
        accesses = row.get('h5_accesses')
        if not isinstance(accesses,list) or row.get('h5_access_count') != len(accesses):
            raise ValueError('Missing H5 access evidence')
        if accesses and (not row['path'].endswith('/trace') or any(x.get('allowed') is not True for x in accesses)):
            raise ValueError('Unexpected H5 access in metadata workflow')
        found[identity] = row
    return found


def owner(module):
    # Existing physical package owners, with retained composition files named.
    return '.'.join(module.split('.')[:2]) if module.startswith('disco.') else module.split('.')[0]


def metrics(browser, requests, cfg):
    values = {}
    for action in browser['actions']:
        case = next(c for c in cfg['cases'] if c['id'] == action['id'])
        validate_action(action,case,cfg['samples'])
        profiles = []
        for sample in action['samples']:
            server = []
            for request in sample['requests']:
                remote = requests.get(request['request_id'])
                if (remote is None or remote['action_id'] != sample['action_id']
                        or remote['phase'] != sample['phase'] or remote['status'] != request['status']):
                    raise ValueError('Browser/server request correlation mismatch')
                server.append(remote)
            if sample['phase'] != 'profile':
                continue
            attribution = summarize_spans(sample['frontend_spans'],sample['total_ms'])
            sample['attribution_summary'] = attribution
            totals = {'browser:'+module:data['self_ms'] for module,data in attribution['modules'].items()}
            totals['browser:unattributed'] = attribution['unattributed_ms']
            totals['browser:cross_owner_overlap'] = attribution['cross_owner_overlap_ms']
            # Profiler self times across requests are work totals, not action wall fractions.
            for request in server:
                for span in request['spans']:
                    key = 'server:'+owner(span['module'])
                    totals[key] = totals.get(key,0)+span['self_ms']
            for render in sample.get('react_renders',[]):
                duration = number(render.get('actual_duration_ms'),'React render duration')
                key = 'react-render:'+render['module']
                totals[key] = totals.get(key,0)+duration
            profiles.append(totals)
        keys = set().union(*(p.keys() for p in profiles))
        ordinary = [s for s in action['samples'] if s['phase'] == 'ordinary']
        profile_samples = [s for s in action['samples'] if s['phase'] == 'profile']
        values[action['id']+'/'+action['variant']] = {
            'total_ms':statistics.median(s['total_ms'] for s in ordinary),
            'profile_total_ms':statistics.median(s['total_ms'] for s in profile_samples),
            'modules':{key:statistics.median(p.get(key,0) for p in profiles) for key in sorted(keys)},
            'request_counts':[len(s['requests']) for s in ordinary],
            'ordinary_samples_ms':[s['total_ms'] for s in ordinary],
            'profile_samples_ms':[s['total_ms'] for s in profile_samples]}
    return values


def report(receipt, output):
    import html
    esc = lambda value: html.escape(str(value))
    lines = ['# End-to-end benchmark workflow', '', 'Status: **'+receipt['status']+'**.', '',
             'Browser action wall time is measured without backend profiling. Module rows below come from separate instrumented samples. Server work is nested inside request latency; React render durations and overlapping spans are not additive wall-time components.', '',
             '| Action / variant | Ordinary median (ms) | Profile median (ms) | Requests |',
             '| --- | ---: | ---: | --- |']
    cards = []
    for case,value in receipt.get('metrics',{}).items():
        lines.append(f"| {case} | {value['total_ms']:.2f} | {value['profile_total_ms']:.2f} | {value['request_counts']} |")
        table = ''.join(f'<tr><td>{esc(module)}</td><td>{ms:.3f}</td></tr>' for module,ms in sorted(value['modules'].items(),key=lambda x:-x[1]))
        cards.append(f'<details><summary><strong>{esc(case)}</strong><span>{value["total_ms"]:.2f} ms ordinary · {value["profile_total_ms"]:.2f} ms instrumented</span></summary><table><thead><tr><th>Module / measurement layer</th><th>Profile evidence (ms)</th></tr></thead><tbody>{table}</tbody></table></details>')
    for case,value in receipt.get('metrics',{}).items():
        lines += ['', '## '+case, '', '| Layer / module | Profile evidence (ms) |','| --- | ---: |']
        lines += [f'| {module} | {ms:.3f} |' for module,ms in sorted(value['modules'].items(),key=lambda x:-x[1])]
    limitations = receipt.get('limitations',[])
    lines += ['', '## Scope and remaining coverage', ''] + ['- '+x for x in limitations]
    (output/'workflow.md').write_text('\n'.join(lines)+'\n')
    limits = ''.join('<li>'+esc(x)+'</li>' for x in limitations)
    title = 'End-to-end benchmark workflow'
    (output/'workflow.html').write_text(f'''<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><style>
body{{font:16px/1.55 system-ui;margin:40px auto;padding:0 24px;max-width:1080px;color:#183039;background:#f5f8f8}}h1{{font-size:30px}}.lead{{max-width:900px}}details{{background:white;border:1px solid #ccd9da;border-radius:8px;margin:12px 0;padding:14px}}summary{{cursor:pointer}}summary span{{display:block;margin-left:20px;color:#405b60}}table{{width:100%;border-collapse:collapse;margin-top:12px}}td,th{{text-align:left;border-bottom:1px solid #e1e8e8;padding:8px}}td:last-child,th:last-child{{text-align:right;font-variant-numeric:tabular-nums}}.badge{{font-weight:700}}li{{margin:6px 0}}</style></head><body><h1>{title}</h1><p class="badge">{esc(receipt['status'])}</p><p class="lead">Ordinary click-to-correct-result latency is the headline. Expand an action to inspect its module evidence from a separate instrumented run. Backend timings sit inside transport; React render durations and overlapping spans cannot be added to the headline.</p>{''.join(cards)}<h2>Scope and remaining coverage</h2><ul>{limits}</ul></body></html>''')


def execute_owned(command, log, deadline, rss_limit, identities):
    import psutil
    stream = log.open('wb')
    child = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                             env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}, start_new_session=True)
    identities[child.pid] = psutil.Process(child.pid).create_time()
    return child,stream,time.monotonic()+deadline


def poll_owned(child, deadline, rss_limit, identities):
    import psutil
    if child.poll() is not None:
        return child.returncode
    try:
        process = psutil.Process(child.pid)
        group = [process,*process.children(recursive=True)]
        rss = 0
        for item in group:
            try:
                identities[item.pid] = item.create_time()
                rss += item.memory_info().rss
            except psutil.NoSuchProcess:
                pass
        if rss > rss_limit:
            raise RuntimeError('Owned worker RSS budget exceeded')
    except psutil.NoSuchProcess:
        return child.poll()
    if time.monotonic() > deadline:
        raise TimeoutError('Owned workflow worker timed out')
    return None


def stop_owned(child, identities):
    import psutil
    if child is not None and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill();child.wait(timeout=5)
    alive = []
    for pid,created in identities.items():
        try:
            item = psutil.Process(pid)
            if item.create_time() == created and item.status() != psutil.STATUS_ZOMBIE:
                item.terminate();alive.append(item)
        except psutil.NoSuchProcess:
            pass
    _,remaining = psutil.wait_procs(alive,timeout=5)
    for item in remaining:
        if item.create_time() == identities[item.pid]:
            item.kill()
    _,remaining = psutil.wait_procs(remaining,timeout=5)
    return not remaining


def run(source_root, output, *, smoke=False, browser_executable=None):
    cfg = config()
    source_root,output = source_root.resolve(),output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    epochs,samples = (1000,1) if smoke else (cfg['epochs'],cfg['samples'])
    receipt = {'format':FORMAT,'status':'running','source_root':str(source_root),
               'source_start':query_bench.source(source_root),'harness_start':harness(),
               'environment':query_bench.environment(),'config':cfg,'epochs':epochs,
               'samples':samples,'smoke':smoke,'cleanup':{},'metrics':{},'limitations':[]}
    query_bench.write(output/'receipt.json',receipt)
    server=browser=None
    started = time.monotonic()
    streams=[]
    server_ids,browser_ids = {},{}
    try:
        server,stream,deadline = execute_owned([sys.executable,'-B',str(ROOT/'benchmarks/workflow/server.py'),
            '--source-root',str(source_root),'--output',str(output/'server'),'--epochs',str(epochs)],
            output/'server.log',cfg['max_startup_seconds'],cfg['max_rss_bytes'],server_ids)
        streams.append(stream)
        meta_path = output/'server/server.json'
        while not meta_path.is_file():
            code = poll_owned(server,deadline,cfg['max_rss_bytes'],server_ids)
            if code is not None:
                raise RuntimeError(f'Fixture server exited before readiness ({code})')
            time.sleep(.25)
        receipt['fixture_setup_seconds'] = time.monotonic()-started
        metadata = json.loads(meta_path.read_text())
        if metadata['epochs'] != epochs:
            raise ValueError('Fixture scale mismatch')
        receipt['fixture'] = metadata
        command = ['node',str(ROOT/'benchmarks/workflow/browser.mjs'),'--source-root',str(source_root),
                   '--server-json',str(meta_path),'--output',str(output/'browser'),'--samples',str(samples)]
        if browser_executable:
            command += ['--browser-executable',str(browser_executable)]
        browser,stream,deadline = execute_owned(command,output/'browser.log',cfg['max_browser_seconds'],cfg['max_rss_bytes'],browser_ids)
        streams.append(stream)
        while True:
            if server.poll() is not None:
                raise RuntimeError('Fixture server exited during actions')
            poll_owned(server,deadline,cfg['max_rss_bytes'],server_ids)
            code = poll_owned(browser,deadline,cfg['max_rss_bytes'],browser_ids)
            if code is not None:
                if code:
                    raise RuntimeError(f'Browser worker failed ({code})')
                break
            time.sleep(.25)
        browser_result = json.loads((output/'browser/browser.json').read_text())
        receipt['limitations'] = browser_result.get('limitations',[])+browser_result.get('unmeasured_variants',[])
        # Small fixture verifies composition only, never masquerades as million-scale evidence.
        if smoke:
            if browser_result.get('status') != 'passed' or browser_result.get('failures') or browser_result.get('gaps'):
                raise ValueError('Incomplete/failed smoke actions')
            check_cfg = {**cfg,'samples':samples}
        else:
            validate_browser(browser_result,cfg,epochs,samples)
            check_cfg = cfg
        requests = load_requests(output/'server/requests.jsonl')
        receipt['metrics'] = metrics(browser_result,requests,check_cfg)
        receipt['browser_environment'] = browser_result.get('environment',{})
        receipt['source_end'] = query_bench.source(source_root)
        receipt['harness_end'] = harness()
        if receipt['source_start'] != receipt['source_end'] or receipt['harness_start'] != receipt['harness_end']:
            raise ValueError('Source/harness changed during workflow measurement')
        receipt['status'] = 'diagnostic' if smoke else 'passed'
    except BaseException as error:
        receipt['status'] = 'failed'
        receipt['error'] = repr(error)
        raise
    finally:
        receipt['elapsed_seconds'] = time.monotonic()-started
        receipt['cleanup']['browser_processes_closed'] = stop_owned(browser,browser_ids)
        receipt['cleanup']['server_processes_closed'] = stop_owned(server,server_ids)
        for stream in streams:
            stream.close()
        backend_cleanup = output/'server/cleanup.json'
        receipt['cleanup']['backend'] = json.loads(backend_cleanup.read_text()) if backend_cleanup.is_file() else {}
        if (not all(receipt['cleanup'][key] for key in ('browser_processes_closed','server_processes_closed'))
                or not all(receipt['cleanup']['backend'].get(key) is True for key in ('server_closed','fixture_closed','instrumentation_restored'))):
            receipt['status'] = 'failed'
            receipt['cleanup_error'] = 'Owned cleanup incomplete or unverified'
        provenance_keys = ('source_start','source_end','harness_start','harness_end','environment','browser_environment','config','epochs','samples','fixture')
        provenance = {key:receipt[key] for key in provenance_keys if key in receipt}
        query_bench.write(output/'provenance.json',provenance)
        receipt['provenance_sha256'] = query_bench.sha((output/'provenance.json').read_bytes())
        files = {}
        for folder in (output/'server',output/'browser'):
            if folder.exists():
                for path in folder.rglob('*'):
                    if path.is_file() and path.suffix in {'.json','.jsonl','.log','.txt','.h5'}:
                        files[str(path.relative_to(output))] = query_bench.sha(path.read_bytes())
        receipt['evidence_sha256'] = files
        query_bench.write(output/'receipt.json',receipt)
        report(receipt,output)
    if receipt['status'] == 'failed':
        raise RuntimeError(receipt.get('cleanup_error','Workflow failed'))
    return output/'receipt.json'



def load_receipt(path):
    receipt = json.loads(path.read_text())
    if receipt.get('format') != FORMAT or receipt.get('status') != 'passed' or receipt.get('smoke') is not False:
        raise ValueError('Missing/failed/diagnostic workflow receipt')
    if receipt.get('config') != config() or receipt.get('harness_start') != harness():
        raise ValueError('Different workflow suite; rerun both sources with this harness')
    for boundary in ('source_start','source_end'):
        query_bench.validate_source(receipt.get(boundary))
    query_bench.validate_environment(receipt.get('environment'))
    if receipt['source_start'] != receipt['source_end'] or receipt['harness_start'] != receipt.get('harness_end'):
        raise ValueError('Source/harness changed during measurement')
    cleanup = receipt.get('cleanup',{})
    if (cleanup.get('server_processes_closed') is not True or cleanup.get('browser_processes_closed') is not True
            or any(cleanup.get('backend',{}).get(key) is not True for key in ('server_closed','fixture_closed','instrumentation_restored'))):
        raise ValueError('Unverified cleanup')
    for name,digest in receipt.get('evidence_sha256',{}).items():
        file = path.parent/name
        if (Path(name).is_absolute() or '..' in Path(name).parts or file.is_symlink()
                or not file.resolve().is_relative_to(path.parent.resolve())):
            raise ValueError('Invalid evidence path')
        if query_bench.sha(file.read_bytes()) != digest:
            raise ValueError('Workflow evidence changed')
    provenance = path.parent/'provenance.json'
    keys = ('source_start','source_end','harness_start','harness_end','environment','browser_environment','config','epochs','samples','fixture')
    if (query_bench.sha(provenance.read_bytes()) != receipt.get('provenance_sha256')
            or json.loads(provenance.read_text()) != {key:receipt[key] for key in keys}):
        raise ValueError('Provenance evidence changed')
    required = {'browser/browser.json','server/requests.jsonl','server/server.json','server/cleanup.json'}
    if not required.issubset(receipt.get('evidence_sha256',{})):
        raise ValueError('Missing workflow evidence')
    raw_cleanup = json.loads((path.parent/'server/cleanup.json').read_text())
    raw_fixture = json.loads((path.parent/'server/server.json').read_text())
    if raw_cleanup != receipt['cleanup']['backend']:
        raise ValueError('Raw cleanup disagrees with receipt')
    if raw_fixture != receipt.get('fixture') or raw_fixture.get('epochs') != receipt.get('epochs'):
        raise ValueError('Raw fixture identity/scale disagrees with receipt')
    if receipt['environment'].get('cpu_model','').strip().lower() in {'unknown','unavailable','none','missing','n/a'}:
        raise ValueError('Unknown CPU hardware cannot qualify')
    raw = json.loads((path.parent/'browser/browser.json').read_text())
    validate_browser(raw,receipt['config'],receipt['epochs'],receipt['samples'])
    computed = metrics(raw,load_requests(path.parent/'server/requests.jsonl'),receipt['config'])
    if computed != receipt.get('metrics'):
        raise ValueError('Summary differs from raw correlated evidence')
    environment = raw.get('environment',{})
    if environment != receipt.get('browser_environment') or any(not environment.get(k) for k in ('browser','node','viewport')):
        raise ValueError('Missing/different browser runtime identity')
    return receipt


def compare(baseline_path, candidate_path, output):
    baseline,candidate = load_receipt(baseline_path),load_receipt(candidate_path)
    for key in ('config','harness_start','environment','browser_environment'):
        if baseline[key] != candidate[key]:
            raise ValueError(f'Incomparable workflow {key}')
    if baseline['source_start']['status']:
        raise ValueError('Retained baseline must be clean')
    result = compare_metrics(baseline['metrics'],candidate['metrics'],candidate['config']['comparison'])
    result.update(format=FORMAT+'-comparison',
                  baseline_commit=baseline['source_start']['commit'],candidate_commit=candidate['source_start']['commit'],
                  baseline_receipt_sha256=query_bench.sha(baseline_path.read_bytes()),
                  candidate_receipt_sha256=query_bench.sha(candidate_path.read_bytes()),
                  attribution='Ordinary browser total; instrumented per-module evidence compared separately. No additive cross-clock claim.')
    with output.open('x') as stream:
        json.dump(result,stream,indent=2)
        stream.write('\n')
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    command = commands.add_parser('run')
    command.add_argument('--source-root',type=Path,default=ROOT)
    command.add_argument('--output',type=Path,required=True)
    command.add_argument('--smoke',action='store_true')
    command.add_argument('--browser-executable',type=Path)
    comparison = commands.add_parser('compare')
    comparison.add_argument('baseline',type=Path)
    comparison.add_argument('candidate',type=Path)
    comparison.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    try:
        if args.command == 'run':
            import fcntl
            import tempfile
            with (Path(tempfile.gettempdir())/'disco-everyday-million.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                print(run(args.source_root,args.output,smoke=args.smoke,browser_executable=args.browser_executable))
        elif args.command == 'compare':
            result = compare(args.baseline,args.candidate,args.output)
            print(json.dumps({'status':result['status'],'review_required':result['review_required']}))
            return 2 if result['review_required'] else 0
        return 0
    except Exception as error:
        print(str(error),file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
