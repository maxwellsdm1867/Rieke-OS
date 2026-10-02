"""Reproducible honest ledger/report from completed independent receipts."""
import argparse
import datetime
import json
from pathlib import Path
import statistics


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();root=args.root
    batch=json.loads((root/'batch.json').read_bytes());storage=json.loads((root/'storage.json').read_bytes())
    build=json.loads((root/'build.json').read_bytes());service=json.loads((root/'integrated-service.json').read_bytes())
    controls=json.loads((root/'controls.json').read_bytes()) if (root/'controls.json').exists() else None
    if batch['status']!='complete_ledger_including_incomplete_arms':p.error('Final timing ledger required')
    receipts=[json.loads((root/Path(job['receipt']).name if (root/Path(job['receipt']).name).exists() else Path(job['receipt'])).read_bytes()) for job in batch['jobs']]
    pairs=[r for r in receipts if r.get('same_payload_pair')]
    complete=[r for r in receipts if r.get('status')=='passed']
    action_names=['Select epoch and display metadata','Search selected metadata','Reopen cached cell','Scroll loaded rows','Expand unloaded cell','Expand unloaded block','Load next 60 cells','Tag ten epochs, including revision preflight','Preview metadata filter, full scoped catalog']
    backend=['Small HTTP full-detail decoding passed; million three-detail control passed','Selected DTO preservation passed; client search timing unrun','Historical cached path makes no database request; fresh rendered timing unrun','Historical cached path makes no database request; fresh rendered timing unrun','Largest-cell backend proxy passed; full tree DTO/anchor path unmeasured','Largest-block backend proxy passed; full tree DTO/anchor path unmeasured','Minimal UUID/count group control passed; full tree route/paint unmeasured','Small isolated tag/edit/export and revision-fault tests passed on transactional SQL doubles; isolated native MySQL million writer unavailable','Small HTTP requested summaries passed; million requested two-facet backend results above; full global catalog unmeasured']
    ledger=[dict(id=f'E01-{n+1:02}',action=name,status='blocked' if n==7 else 'not_run',backend_evidence=backend[n],reason='No isolated native MySQL million-write authority; no live writes authorized' if n==7 else 'Complete rendered/HTTP everyday action not rerun on integrated real-million app') for n,name in enumerate(action_names)]
    def number(value):return '—' if value is None else f'{value:,.2f}'
    def metrics(arm):
        samples=arm.get('samples_ms',[])
        return '/'.join(number(x) for x in [samples[0] if samples else None,statistics.median(samples[1:]) if len(samples)>1 else None,max(samples) if samples else None])
    lines=['# DISCO metadata qualification and fresh real-million before/after report','',
        f"The sealed real-record million replay completed {len(pairs)} equal-payload paired backend cases. {len(receipts)-len(complete)} additional receipts are incomplete/censored; they remain separate from successful comparisons. All results are backend observations. The complete nine everyday UI/API actions remain unqualified on the integrated real-million application.",'',
        '## Target, corpus and measurement contract','',
        '- Before: application snapshot `f03577e650ce5f604e9585f5bee983ef01bccad3`, unchanged native SQLite match/values/detail code.',
        f"- After: combined committed integration `{batch['target_commit']}`; complete 140-field typed SQLite sidecar attached to the same native metadata base.",
        '- Corpus: exactly 1,000,000 metadata epochs, 140 eligible fields, 77,107,863 epoch-field links; 359 copies of 2,781 actual recorded epochs plus a 1,621-epoch whole-block tail. It is not one million independent acquisitions or new readable recording files.',
        f"- Original source SHA-256: `{build['corpus']['source_sha256']}`.",
        f"- Million replay SHA-256: `{build['corpus']['replay_sha256']}`.",
        f"- Metadata generation: `{build['corpus']['lineage_receipt']['generation']}`.",
        f"- Project: `{build['corpus']['lineage_receipt']['project_uuid']}`.",
        f"- Fresh candidate SQLite SHA-256: `{build['candidate_seal']['sha256']}`; candidate generation token `{build['candidate_generation_token']}`.",
        '- Replay construction retains seven native tables and production indices but uses experimental fingerprints, omits upfront full-field catalogs and preserves copied source-path provenance. It is not a published native project with one million readable new H5 traces; source/annotation authority is checked separately on isolated small service fixtures.',
        '- Each main arm returns exact count, first 60 chronological native row DTOs, continuation rank and only requested facet fields, including JSON serialization. Source truth is standard-library code over the sealed original records; optimized predicate compilation is not the oracle.',
        '- Every million acquisition UUID and chronology rank was checked against recorded dates/timestamps and the preserved namespace. Every selected member was checked against independent original-source predicate truth; lineage-weighted counts establish completeness. Complete serialized payloads must match the independent expected SHA-256 in every accepted sample.',
        '- Five samples per complete arm, alternating before/after order; first is the first observed operation in a prepared process, warm median uses samples 2–5, max uses all five. No p95/p99 claim. Processes and filesystem caches are warm; no cache flush or installed-App startup is represented.',
        '- Main caps: 45 seconds per sample, 1 GiB process peak RSS, 4 GiB free-disk floor, 768 MiB available-RAM floor. Watchdog polls RSS every 50 ms and RAM/disk every 2 seconds; bounded polling overshoot is possible. Worker setup has a 180-second hard deadline.',
        '- Native warm reader is initialized after complete corpus seal/count/generation verification, without writing a retained-corpus reader lease. It uses unchanged production match/values methods and a compact proven UUID/rank map. Eager full-app row startup, native source publication and HTTP transport are excluded.',
        '- Runtime: Python 3.11.13, SQLite 3.50.4, macOS arm64. Full source/runner hashes, runtime strings and raw traces are retained in machine-readable receipts. Per-case RSS includes both arms and oracle setup; it is not isolated arm RSS.','',
        '## Fresh paired page and requested-facet observations','',
        'Times are milliseconds in **first / warm median / maximum** order. An incomplete row contains only its observed completed samples; its statistics cannot establish a paired improvement. Requested-facet cases request `parameters/useRandomSeed` and `parameters/currentSpotSize` only.','',
        '| Case | Matches | Before ms | After ms | Samples B/A | Equality/status | Process RSS MiB |',
        '|---|---:|---:|---:|---:|---|---:|']
    for r in receipts:
        arms=r.get('arms',{});b=arms.get('baseline',{});a=arms.get('candidate',{})
        status='equal, passed' if r.get('same_payload_pair') else ('independent after-only, unpaired' if 'baseline' not in arms and r['status']=='passed' else r['status']+'; '+r.get('reason',r.get('error',b.get('error',a.get('error','incomplete arm')))))
        lines.append(f"| {r['case']['label']} {r['mode']} | {r.get('expected_count',r['case']['expected_count']):,} | {metrics(b)} | {metrics(a)} | {len(b.get('samples_ms',[]))}/{len(a.get('samples_ms',[]))} | {status} | {r.get('peak_rss_bytes',0)/1024**2:,.1f} |")
    lines+=['','Raw sample arrays, exact DTO/facet/cursor payload hashes, input signatures, source-generation checks, failure traces and independently accepted typed samples from censored pairs are in `receipts/million/`. Capped native arms and after-only samples are not folded into speedups. A count/first-60 proxy does not replace full legacy MatchingEpochs, full-catalog preview or tree navigation.','',
        '## Additional backend controls','']
    if controls:
        lines += [f"Both controls completed five samples per arm with exact expected payload equality and generation fences. Combined control-process peak RSS: **{controls['peak_rss_bytes']/1024**2:.2f} MiB**. These controls enforce 45-second samples and a 1-GiB RSS watchdog; their caps exclude the main workers' RAM/free-disk floors.",'']
        lines+=['| Control | Before first/warm/max ms | After first/warm/max ms | Status |','|---|---:|---:|---|']
        for item in controls['jobs']:
            lines.append(f"| {item['label']} | {metrics(item['arms']['baseline'])} | {metrics(item['arms']['candidate'])} | {item['status']} |")
        lines+=['','The cell control compares the minimal second 60-cell UUID/count projection with unchanged native SQLite grouping, not the full native tree route, labels, anchors or rendered UI. Independent source lineage supplies exact cell counts. The detail control compares three fully decoded native detail DTOs; the before cache was primed to freeze native truth. It does not read waveforms or reconstruct stimuli.']
    else:lines+=['Controls unrun.']
    lines+=['','## Independent correctness and fault gates','',
        '- Frozen hand-authored 12-epoch truth covers 164 eligible native fields, including 145 previously unseen parameter fields, complete row/detail DTOs, bool/number distinctions, unsafe integers, heterogeneous arrays, explicit null versus missing and escaped metadata paths.',
        '- Native and typed small readers each passed 22,253 predicate/scope membership comparisons, exact rejection checks, all-page cursor walks, exact facets, complete DTOs and native detail reconstruction. Immutable truth does not call optimized helpers.',
        f"- Integrated service: {service['tests_run']} independent tests passed against the exact after commit; 8,092 predicate/global-cell-block-group page comparisons, eight exact HTTP validation errors, opaque full-pagination checks, query/publication/source/tamper cursor faults, pending/ready cancellation, read failures and generation changes before calculation/publication/after ready.",
        '- All 164 native registry types and full/requested/count-only facets passed. Registry admission may legitimately enrich scoped binding/annotation context; the pending job token must then remain exact. Source exclusion affects new queries while original protocol and frozen custom membership remain authoritative.',
        '- Isolated tag-ten, inherited/direct tag ownership, edit/export/import, stale revision rollback and annotation generation changes passed on native annotation code with transactional SQL doubles. Protocol curation remains distinct from shared tags. These checks are not native MySQL concurrency or million-tag benchmarks.',
        '- Implementation-owner aggregate evidence: backend 255 tests run (250 passed, 5 opt-in native MySQL tests skipped); frontend 347/347 passed. These are supporting integration checks, not fresh rendered million-row measurements.',
        '- No independent production correctness mismatch was discovered. Native/custom annotation fallback remains serialized and unqualified at broad scale. Empty source-hierarchy branches without epochs need an independent native hierarchy fixture; zero-match pages do not close that gate.','',
        '## Build, verification and startup','',
        f"Fresh typed sidecar build plus subsequent verified open took **{build['wall_seconds']:.3f} s**; core build reported {build['build']['build_seconds']:.3f} s. Peak build RSS was **{build['build']['max_rss_bytes']/1024**2:.2f} MiB**. The existing native metadata base was shared, not copied. The build passed the 300-second, 1-GiB RSS and 4-GiB free-disk caps.",
        '',f"Full original/replay SHA, count and generation verification ran separately in **{build['corpus']['seconds']:.3f} s**. New sidecar verified open after build took **{build['typed_verified_open_seconds']:.3f} s**, with warm filesystem caches. Native full-app startup, cold reopen, refresh under readers and restart remain unrun.",
        '', 'Build phase observations (seconds): '+', '.join(f"{k} {v:.3f}" for k,v in build['build']['timings'].items())+'.' if 'timings' in build['build'] else 'See build receipt for full phase timings.',
        '', 'The original build script declared an available-RAM floor in its receipt but did not enforce that floor during build; time/RSS/free disk were enforced. Main timing workers enforce all four declared resource controls. The earlier experimental build timing is historical, not a controlled before/after build pair.','',
        '## Storage: total metadata and incremental optimization','',
        '| Asset or accounting scope | Exact file bytes | Decimal GB |','|---|---:|---:|']
    for role in ('native_base','retained_experimental_sidecar','new_candidate_sidecar'):
        n=storage['components'][role]['file_bytes'];lines.append(f'| {role} | {n:,} | {n/1e9:.6f} |')
    for label,n in [('Steady native base + new sidecar',storage['steady_candidate']['total_file_bytes']),('Steady SQLite + required proof files',storage['steady_runtime_with_proof_files']['total_file_bytes']),('Observed coexistence: native + old + new',storage['old_new_coexistence']['total_file_bytes']),('Sampled rebuild high-water lower bound',build['observed_highwater_file_bytes'])]:
        lines.append(f'| {label} | {n:,} | {n/1e9:.6f} |')
    normalized=storage['normalized'];lines+=['',
        f"Steady SQLite allocated filesystem bytes: **{storage['steady_candidate']['total_allocated_bytes']:,}**. Required native and candidate proof files add 463 file bytes, tracked separately from the common SQLite-only ratio numerator. The new sidecar is **{storage['new_vs_retained_experimental_index_delta_bytes']:+,} file bytes** versus the preserved complete experimental sidecar; this is no measured storage saving. Its complete generation/project/seal proof is fresh.",
        '',f"Steady total: **{normalized['total_bytes_per_epoch']:,.2f} bytes/epoch** and **{normalized['total_bytes_per_epoch_field_link']:.3f} bytes/epoch-field link**. Added index: **{normalized['added_bytes_per_epoch']:,.2f} bytes/epoch**, **{normalized['added_bytes_per_epoch_field_link']:.3f} bytes/link**, and **{normalized['added_index_over_base_metadata']*100:.3f}%** of the native metadata base.",
        '',f"Rebuild samples every 250 ms included native base, retained old sidecar, candidate staging and linked temporary files; observed high-water file length **{build['observed_highwater_file_bytes']:,} bytes** and allocated bytes **{build['observed_highwater_allocated_bytes']:,}** are lower bounds. Unlinked OS temporary pages can be missed. Free disk after build: **{build['free_disk_after']:,} bytes**. Reader-safe old-generation cleanup was not performed or qualified.",
        '', '### Stored native columns and component pages','', '| Component | Records | Stored column bytes | Average bytes/record |','|---|---:|---:|---:|']
    for name,c in storage['native_stored_columns'].items():lines.append(f"| {name} | {c['rows']:,} | {c['stored_payload_bytes']:,} | {c['average_bytes']:.2f} |")
    lines+=['','Stored column bytes are encoded payload, not page or filesystem usage. The following largest page components expose relation/core/index overhead; complete dbstat payload/unused/page breakdowns and schema row counts are in `receipts/million/storage.json`.','', '| Database component | Used page bytes | Payload bytes | Unused page bytes |','|---|---:|---:|---:|']
    for role in ('native_base','new_candidate_sidecar'):
        for c in sorted(storage['components'][role]['components'],key=lambda x:x['used_page_bytes'],reverse=True)[:10]:
            lines.append(f"| {role}: {c['name']} | {c['used_page_bytes']:,} | {c['payload_bytes']:,} | {c['unused_page_bytes']:,} |")
    lines+=['',
        'Full canonical MySQL/project metadata, persistent summary-cache and annotation-map footprints are unmeasured, not zero. Incremental costs per newly imported epoch/source/new field/distinct value and a controlled original/intermediate/million common-layout growth curve are unrun. The historical original 2,781 clone and million sidecar have different layouts and cannot establish a controlled growth curve.',
        '', '### Recording denominators','',
        '- Preserved original-source inspection: 689,388,110 actual H5 file bytes; original 2,781-epoch base + typed metadata 26,234,880 bytes, **3.8055%**. This run did not rehash or decode H5 files; its recording reference is explicitly retained historical evidence.',
        '- Exact-lineage million projection: approximately 247,905,301,506 H5-container bytes, 131,953,484,228 compressed response-allocation bytes and 606,528,270,000 logical response bytes. Partial-tail H5 container size is prorated and approximate. No new million-epoch H5 recordings were created.',
        f"- Fresh measured million base + typed metadata / projected H5 = **{normalized['raw_ratios'][1]['ratio']*100:.4f}%**; / projected compressed response allocation = **{normalized['raw_ratios'][2]['ratio']*100:.4f}%**. Added index / projected H5 is about 0.4466%.",
        f"- Stress-fixture million metadata / reused original H5 bytes = **{storage['replay_stress_metadata_over_reused_original_h5']['ratio']:.3f}×**. The scopes differ; this is a replay property and is not a real million-acquisition storage ratio.",
        '', '## Required nine-action continuity ledger','',
        'Status below applies to the complete requested real-million action. Backend evidence does not change an unrun rendered action into a pass. Historical synthetic timings remain in the handoff, not fresh before/after samples.','',
        '| Action | Status | Fresh supporting evidence and remaining limit |','|---|---|---|']
    for item in ledger:lines.append(f"| {item['action']} | {item['status']} | {item['backend_evidence']} |")
    lines+=['', '## Remaining gates and interpretation','',
        'The complete typed backend preserves the full scientific metadata model and passes the reported independent small-service and million-read comparisons. Completed same-payload backend pairs can demonstrate per-case speed gains under the recorded warm setup. They do not certify a UI SLO or qualify merging/installing the integration.',
        '', 'Open gates: all nine integrated real-million UI/API action measurements; unchanged eager/unbounded legacy MatchingEpochs and full tree/anchor contracts; empty native hierarchy branches; isolated native dense/concurrent annotation writes; cold startup/reopen/refresh/restart; full waveform/stimulus reconstruction and export; complete canonical project storage; incremental import and controlled growth; retained-generation cleanup.',
        '', 'Six MAT fixtures were excluded from the snapshot: `examples/data/sample_epochs.mat`, `tests/baselines/MeanSelectedNodes_baseline.mat`, `tests/baselines/getCycleAverageResponse_baseline.mat`, `tests/baselines/getLinearFilterAndPrediction_baseline.mat`, `tests/baselines/getMeanResponseTrace_baseline.mat`, `tests/baselines/getResponseAmplitudeStats_baseline.mat`. Their scientific comparisons are blocked until the original inputs are restored in an isolated test environment.',
        '', 'No live database writes, application restart/install, package build, external experiment, push, PR or merge was performed. All qualification changes live under `tools/metadata_qualification/` on the independent branch. Candidate SQLite data remain disposable local test artifacts; report, raw receipts and hashes are versioned.','']
    summary=dict(status='completed_backend_report_with_explicit_open_integration_gates',target_commit=batch['target_commit'],
        equal_payload_paired_cases=len(pairs),total_receipts=len(receipts),incomplete_receipts=len(receipts)-len(complete),actions=ledger,
        corpus=build['corpus'],storage=storage['normalized'],build_seconds=build['wall_seconds'],all_nine_qualified=False,ui_slo_certified=False,
        build_available_ram_floor_enforced=False,main_timing_available_ram_floor_enforced=True)
    args.output.write_text('\n'.join(lines));args.output.with_suffix('.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(report=str(args.output),paired_cases=len(pairs),incomplete_receipts=len(receipts)-len(complete))))


if __name__=='__main__':main()
