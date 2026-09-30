"""Build a checked native single/batch/cell tagging report from raw receipts."""
import argparse
import json
from pathlib import Path

SIZES=(500,5000,100000)
TARGETS={'epoch_1':'One epoch','epoch_5':'Five epochs','epoch_20':'Twenty epochs','cell_1':'One cell (100 child epochs)'}
METRICS={'durable_save':'Durable save','first_stable_page':'First fresh page after save','focused_metadata':'Focused metadata after page',
    'save_plus_first_page':'Save + first fresh page','save_page_focus':'Save + first page + focused metadata',
    'affected_filter':'Changed-tag filter, after index maintenance'}

def pair(operation):return f"{operation['p50_seconds']*1000:.1f} / {operation['p95_seconds']*1000:.1f}"
def compact(operation):return {key:operation[key]*1000 for key in ('p50_seconds','p95_seconds')}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--baseline-only',action='store_true')
    args=parser.parse_args();stages=('baseline',) if args.baseline_only else ('baseline','after');receipts={};paths={}
    for stage in stages:
        receipts[stage]={};paths[stage]={}
        for size in SIZES:
            path=args.directory/f'tag-actions-{stage}-{size}.json';value=json.loads(path.read_text())
            assert value['passed'] and value['samples']==20 and value['epochs']==size,path
            assert value['source_unchanged'] and value['harness_unchanged'] and value['owned_native_runtime_stopped'],path
            assert value['source_inventory_before']==value['source_inventory_after'],path
            assert value['target_specification']=='epoch:1,epoch:5,epoch:20,cell:1',path
            assert all(check['passed'] for check in value['checks']),path
            receipts[stage][size]=value;paths[stage][size]=path.name
        reference=receipts[stage][SIZES[0]]
        assert all(value['harness_sha256']==reference['harness_sha256'] and value['source_inventory_before']==reference['source_inventory_before'] for value in receipts[stage].values()),stage
    assert len({value['harness_sha256'] for values in receipts.values() for value in values.values()})==1
    result={'scope':'Disposable native MySQL, real durable save hooks, Flask requests; synthetic acquisition; no browser wall-time claim.',
        'samples_per_add_and_remove':20,'harness_sha256':receipts['baseline'][500]['harness_sha256'],'receipts':paths,
        'source_roots':{stage:receipts[stage][500]['source_root'] for stage in stages},'metrics_ms':{},'profiles':{}}
    lines=['# Single-epoch, small-batch and whole-cell tag actions','',
        'The benchmark runs 20 additions and 20 removals for each target size against disposable native MySQL at 500, 5,000 and 100,000 epochs. Every epoch and cell starts with five tags from each of three author profiles; two protocol curation scopes remain independent. A cell contains 100 child epochs. Small batches select the first 1, 5 or 20 contiguous epochs.','',
        'Each measured action is a durable save followed immediately by the existing multi-tag filtered page, then focused metadata. The active filter does not contain the edited marker. A separate changed-marker filter verifies exact membership after that first page has maintained the index. All displayed times are p50 / p95 milliseconds from raw 20-sample distributions, using nearest-rank p95. Instrumented CPU/SQL profiles are separate additional operations.','']
    order=['save_page_focus','durable_save','save_plus_first_page','first_stable_page','focused_metadata','affected_filter']
    for metric in order:
        lines+=['## '+METRICS[metric],'']
        for action in ('add','remove'):
            lines+=['### '+action.capitalize(),'', '| Epochs | Target | '+' | '.join(stage.capitalize() for stage in stages)+' |',
                '| ---: | :--- | '+' | '.join('---:' for _ in stages)+' |']
            for size in SIZES:
                for target,label in TARGETS.items():
                    key=f'{target}_{action}_{metric}';row={stage:receipts[stage][size]['operations'][key] for stage in stages}
                    lines.append(f'| {size:,} | {label} | '+' | '.join(pair(row[stage]) for stage in stages)+' |')
                    result['metrics_ms'].setdefault(key,{})[size]={stage:compact(value) for stage,value in row.items()}
            lines.append('')
    lines+=['## One-time first indexed read','','This first request follows seeding and the initial durable checkpoint. It includes cold derived shared-index work and is one sample, not a tail-latency estimate. Actual import scheduling and browser startup are outside this synthetic fixture.','',
        '| Epochs | '+' | '.join(stage.capitalize()+' ms' for stage in stages)+' |','| ---: | '+' | '.join('---:' for _ in stages)+' |']
    for size in SIZES:lines.append(f'| {size:,} | '+' | '.join(f"{receipts[stage][size]['operations']['cold_initial_shared_index']['p50_seconds']*1000:.1f}" for stage in stages)+' |')
    lines+=['','## Separate save profiles','',
        'These are individually instrumented add operations, not the uninstrumented timing distributions above. Native SQL dispatch time excludes later cursor consumption; the full CPU profile retains fetch costs. Python fsync instrumentation does not intercept SQLite internal fsync. SQLite commit time is shown separately. Nested cumulative function times must not be added together.','',
        '| Version | Epochs | Target | SQL calls | SQL dispatch ms | Snapshot save ms | Annotation update ms | Recovery-store write ms | SQLite commit ms | Python fsync ms |',
        '| :--- | ---: | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for stage in stages:
        result['profiles'][stage]={}
        for size in SIZES:
            result['profiles'][stage][size]={}
            for target,label in TARGETS.items():
                profile=receipts[stage][size].get('cpu_profiles',{}).get(target+'_add')
                if profile is None:continue
                rows=profile['top_functions']+profile['sql_and_durability_functions']
                unique={(row['file'],row['line'],row['function']):row for row in rows}
                def timing(file,function):return sum(row['cumulative_seconds'] for row in unique.values() if row['file'].endswith(file) and row['function']==function)*1000
                data={'sql_calls':len(profile['native_sql_calls']),'sql_dispatch_ms':sum(row['seconds'] for row in profile['native_sql_calls'])*1000,
                    'snapshot_save_ms':timing('workspace_state_snapshot.py','save'),'annotation_update_ms':timing('workspace_annotations.py','update'),
                    'recovery_store_write_ms':timing('workspace_recovery_store.py','write'),
                    'sqlite_commit_ms':sum(row['cumulative_seconds'] for row in unique.values() if 'commit' in row['function'] and 'sqlite3.Connection' in row['function'])*1000,
                    'python_fsync_ms':sum(profile['python_fsync_calls_seconds'])*1000}
                result['profiles'][stage][size][target]=data
                lines.append(f'| {stage} | {size:,} | {label} | {data["sql_calls"]} | '+' | '.join(f'{data[key]:.3f}' for key in ('sql_dispatch_ms','snapshot_save_ms','annotation_update_ms','recovery_store_write_ms','sqlite_commit_ms','python_fsync_ms'))+' |')
    lines+=['','## Correctness and measurement limits','',
        '- Every add/remove checks exact effective-filter UUID membership, first/last page order, filtered cell counts, full direct/inherited author chips, native target tags and optimistic revisions. Final recovery-mirror content and both untouched protocol curation scopes are independently checked.',
        '- Whole-cell tags are inherited from one cell annotation row. All 100 child epochs are checked through effective membership and page chips; the direct epoch-only predicate remains empty. Native SQL confirms all 300 child annotation rows, revisions, authors and timestamps stay unchanged and no direct epoch annotation rows are added.',
        '- Save timings begin with known optimistic revisions. A selected-record editor may fetch revisions before saving; that preflight, browser scheduling, transport and rendering are excluded. Sums of measured sequential requests are not browser interaction times.',
        '- The changed-marker filter occurs after the stable page. Its samples isolate predicate rematching after index maintenance; they do not establish save-to-first-page latency when the active predicate itself contains the changed literal.',
        '- Profiles add instrumentation overhead and include overlapping cumulative times. Their SQL counts identify repeated work; Python fsync alone is not a full operating-system I/O trace.',
        '- All receipts validate stable product-source inventories, an unchanged identical benchmark harness and cleanup of their owned native MySQL runtime. This benchmark is not an overall release-readiness claim.','']
    for stage in stages:lines.append(stage.capitalize()+': '+', '.join(f'[{size:,} epochs]({paths[stage][size]})' for size in SIZES)+'.')
    args.output.write_text('\n'.join(lines)+'\n');args.output.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
