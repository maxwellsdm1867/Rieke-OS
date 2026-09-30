"""Summarize matched native workflow receipts without hiding raw evidence."""
import argparse
import json
import math
from pathlib import Path
import statistics

SIZES=(500,1000,5000,100000)
COMMON={
    'cold_filter_A':'First multi-tag filter page, cold shared index (one sample)',
    'suggestions_cold':'First autocomplete request after index initialization (one sample)',
    'suggestions_warm':'Warm autocomplete (baseline may reuse its two-second TTL)',
    'A_B_A_sequential_server_bundle':'A → B → A, summary + page each',
    'return_A_page':'Return to A page (after summary)',
    'shared_add_durable_save':'Add shared tag to 10 epochs, durable save',
    'first_after_shared_add_server_bundle':'First summary + page after shared add',
    'suggestions_after_shared_add':'Autocomplete after shared add',
    'shared_remove_durable_save':'Remove shared tag from 10 epochs, durable save',
    'suggestions_after_shared_remove':'Autocomplete after shared removal',
    'added_tag_filter':'Affected marker predicate after add (index already maintained)',
    'removed_tag_filter':'Affected marker predicate after remove (index already maintained)',
    'dataset_add_durable_save':'Add protocol tag to 10 epochs, durable save',
    'first_after_dataset_add_server_bundle':'First summary + page after protocol add',
}
PAGE_FIRST={
    'measured_page_first_A_B_A':'A → B → A, page first with filtered cell counts',
    'page_first_return_A':'Return to A page, no preceding summary',
    'measured_shared_add_save_plus_first_page':'Shared add + first page',
    'measured_shared_remove_save_plus_first_page':'Shared remove + first page',
    'measured_shared_add_save_page_focus':'Shared add + first page + focused metadata',
    'measured_shared_remove_save_page_focus':'Shared remove + first page + focused metadata',
    'measured_dataset_add_save_plus_first_page':'Protocol add + first page',
    'measured_dataset_remove_save_plus_first_page':'Protocol remove + first page',
    'page_first_suggestions_after_shared_add':'Autocomplete after page-first shared add',
    'metadata_fields_cold':'First registered metadata-field definitions request',
    'metadata_fields_warm':'Warm registered metadata-field definitions request',
}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--after-prefix',default='scientist-workflow-after-');p.add_argument('--output',type=Path,required=True)
    p.add_argument('--baseline-only',action='store_true');a=p.parse_args();receipts={};paths={}
    for stage,prefix in [('baseline','scientist-workflow-baseline-')]+([] if a.baseline_only else [('after',a.after_prefix)]):
        receipts[stage]={};paths[stage]={}
        for size in SIZES:
            path=a.directory/(prefix+str(size)+'.json');value=json.loads(path.read_text())
            if not value['passed']:raise ValueError('Failed receipt: '+str(path))
            if value['epochs']!=size or value['samples']!=20 or value['tags_per_annotation']!=5 or value['protocols']!=2:
                raise ValueError('Mismatched workflow contract: '+str(path))
            if not value['source_unchanged'] or not value['owned_native_runtime_stopped']:
                raise ValueError('Source stability or cleanup failed: '+str(path))
            if value['source_inventory_before']!=value['source_inventory_after']:
                raise ValueError('Changed source inventory: '+str(path))
            if stage=='after' and (not value['harness_unchanged'] or not value['page_cells']):
                raise ValueError('After harness or page payload changed: '+str(path))
            receipts[stage][size]=value;paths[stage][size]=str(path)
        stage_values=list(receipts[stage].values())
        if any(value['harness_sha256']!=stage_values[0]['harness_sha256'] or value['source_inventory_before']!=stage_values[0]['source_inventory_before'] for value in stage_values):
            raise ValueError('Matrix source or harness mismatch: '+stage)
    result={'receipts':paths,'sizes':SIZES,'scope':'Native disposable MySQL/Flask/index/durable hooks; synthetic acquisition; no browser timing claim.',
        'baseline_harness_hashes':sorted({value['harness_sha256'] for value in receipts['baseline'].values()}),'comparisons':{},'new_page_first':{}}
    result['receipt_validation']={stage:{'harness_sha256':next(iter(values.values()))['harness_sha256'],
        'python_source_files':len(next(iter(values.values()))['source_inventory_before']),
        'source_roots':sorted({value['source_root'] for value in values.values()}),
        'all_passed':True,'matching_source_and_harness_across_sizes':True,'all_owned_native_runtimes_stopped':True}
        for stage,values in receipts.items()}
    lines=['# Scientist multi-tag workflow measurements','',
        'Each size runs 20 sequential native cycles on a disposable project, with three author profiles, five tags per annotation, inherited cell tags and two independent protocol scopes. Cold setup requests have one sample and are labeled separately; their repeated p50/p95 value is not a tail-latency estimate. Tag predicates use the same all/any/not structure as the view filter. Exact full memberships, page order, author chips, case/Unicode distinctions and final durable state were checked. Times are milliseconds; cells show p50 / p95.','',
        'The original baseline runs use the retained frozen source tree. After runs retain those summary→page operation sequences and separately measure the new page-first flow. After pages also include exact filtered cell counts for the new UI, so they return additional data and are not byte-identical baseline requests. The first page after a save precedes suggestions/summary in the separate page-first flow, so it includes index maintenance.','']
    if 'after' in receipts:
        lines+=['## Current interaction sequence','',
            '| Epochs | Shared add + first page | Shared add + page + focused metadata | A → B → A pages |',
            '| ---: | ---: | ---: | ---: |']
        for size in SIZES:
            cells=[]
            for key in ('measured_shared_add_save_plus_first_page','measured_shared_add_save_page_focus','measured_page_first_A_B_A'):
                value=receipts['after'][size]['operations'][key]
                cells.append(f"{value['p50_seconds']*1000:.1f} / {value['p95_seconds']*1000:.1f}")
            lines.append(f'| {size:,} | '+ ' | '.join(cells)+' |')
        lines+=['', 'These are measured sequential backend request times with exact correctness checks. They exclude browser rendering/network latency and any optimistic-revision preflight. Cold initialization and warm-autocomplete tradeoffs remain visible in the detailed comparisons below.','']
    for key,label in COMMON.items():
        lines+=['## '+label,'','| Epochs | Baseline p50 / p95 | After p50 / p95 | p50 speedup |','| ---: | ---: | ---: | ---: |']
        result['comparisons'][key]={}
        for size in SIZES:
            old=receipts['baseline'][size]['operations'][key];new=receipts.get('after',{}).get(size,{}).get('operations',{}).get(key)
            row={'baseline':{'p50_ms':old['p50_seconds']*1000,'p95_ms':old['p95_seconds']*1000}}
            old_text=f"{row['baseline']['p50_ms']:.1f} / {row['baseline']['p95_ms']:.1f}"
            if new:
                row['after']={'p50_ms':new['p50_seconds']*1000,'p95_ms':new['p95_seconds']*1000};row['p50_speedup']=old['p50_seconds']/new['p50_seconds']
                new_text=f"{row['after']['p50_ms']:.1f} / {row['after']['p95_ms']:.1f}";ratio=f"{row['p50_speedup']:.2f}×"
            else:new_text=ratio='pending'
            result['comparisons'][key][size]=row;lines.append(f'| {size:,} | {old_text} | {new_text} | {ratio} |')
        lines.append('')
    if 'after' in receipts:
        lines+=['## Measured page-first flow','','These are direct after-version measurements, not an inferred browser speedup. The baseline page timings followed a summary request and therefore cannot serve as a cold, summary-free first-after-edit comparison.','']
        for key,label in PAGE_FIRST.items():
            values={size:receipts['after'][size]['operations'][key] for size in SIZES}
            result['new_page_first'][key]={size:{'p50_ms':value['p50_seconds']*1000,'p95_ms':value['p95_seconds']*1000} for size,value in values.items()}
            lines+=['### '+label,'','| Epochs | p50 / p95 |','| ---: | ---: |']
            for size,value in result['new_page_first'][key].items():lines.append(f"| {size:,} | {value['p50_ms']:.1f} / {value['p95_ms']:.1f} |")
            lines.append('')
    lines+=['## Evidence and limits','',
        '- Raw samples, nearest-rank quantiles, SQL session counters, full Python inventories, source origins and cleanup outcomes are retained in the timing receipts; CPU profiles are retained in the baseline receipts and the separately linked final diagnostic receipt.',
        '- The four baseline receipts share one original harness and one Python source inventory; the four final receipts share one v2 harness and one final Python source inventory. Every receipt verifies the selected source stayed unchanged and its owned native MySQL runtime stopped.',
        '- Warm autocomplete is an intentional tradeoff: the baseline could return its two-second cached vocabulary without checking current authority. The new path checks fresh authority on each request, so this case is slower while avoiding the stale window and full post-edit vocabulary rescans. The table reports both cases rather than implying every operation improved.',
        '- SQL session deltas include the status collector’s small fixed overhead; they are comparative counters, not exact zero-query assertions.',
        '- Sequential server bundles sum their constituent measured requests. They do not simulate browser scheduling or network/rendering latency. Frontend request-count/lifecycle evidence belongs to the separate mounted tests.',
        '- Save measurements are durable mutation requests with known optimistic revisions. A selected-record editor may additionally fetch revisions before submitting; those preflight requests are not included in the mutation timing.',
        '- The page-first A/B/A filters do not mention the edited workflow-selected tag. Their memberships can be reused after unrelated edits. Changing a tag literal used by the active filter still requires exact invalidation/rematching; the affected marker-filter samples occur after the primary page has already maintained the index.',
        '- Baseline peak RSS includes the final full recovery-mirror verification and separate profiles. V2 additionally records the process high-water mark before that final recovery load; neither is a pure live-page memory measurement.',
        '- The complete scripted cycle contains multiple filters, additions, removals, autocomplete queries and independent oracles; its wall time must not be described as one tag-save latency.','']
    if 'after' in receipts:
        lines+=['## Validation accompanying the final source','',
            '- [Frozen final gate summary](frozen-scientist-tag-workflow-round2/summary.json): all nine implemented gates passed at 100,000 epochs; captured source manifest `a0ca699563e7f1fd17c2243cc736c0ea72814abfdf31214425e218638a247442`, with unchanged source, dependencies and native runtime.',
            '- [Native authority result](frozen-scientist-tag-workflow-round2/native-authority.json) and [log](frozen-scientist-tag-workflow-round2/native-authority.log): actual disposable MySQL authority and scoped-token tests passed.',
            '- [Mounted frontend regression log](frozen-scientist-tag-workflow-round2/gates/frontend_regressions.log) and [production build log](frozen-scientist-tag-workflow-round2/gates/frontend_build.log). The frozen [workflow request tests](frozen-scientist-tag-workflow-round2/snapshot/workspace-app/src/workflowResponsiveness.test.js) cover 500, 1,000, 5,000 and 100,000 epoch fixtures. Together with the [curation lifecycle tests](frozen-scientist-tag-workflow-round2/snapshot/workspace-app/src/inspectorCurationLifecycle.test.js), they cover stale navigation and storage failures.',
            '- [Separate final 100,000-epoch CPU-profile receipt](scientist-workflow-after-round2-100000-profile.json) used two diagnostic cycles; its timings are excluded from the final 20-sample tables.',
            '- These results cover the scripted synthetic acquisition and native persistence path. The gate summary retains separate unexecuted release trials including physical large H5 waveform round trips, real-browser revision races, full process-kill/power-loss recovery, clean-machine restores and lab NAS soak. Passing this workflow benchmark does not establish overall release readiness.','']
    for stage,by_size in paths.items():
        lines.append(stage.capitalize()+': '+', '.join(f'[{size:,} epochs]({Path(path).name})' for size,path in by_size.items())+'.')
    a.output.write_text('\n'.join(lines)+'\n');a.output.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
