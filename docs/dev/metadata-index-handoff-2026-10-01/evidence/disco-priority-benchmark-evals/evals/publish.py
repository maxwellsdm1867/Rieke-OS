"""Preserve measured results, source seals and runnable isolated prototypes."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path('/private/tmp/disco-priority-benchmark-20261001')
PRE=Path('/private/tmp/disco-real-million-20261001')
DEST=Path('/PATH/TO/LOCAL_HOME/.codex/visualizations/2026/09/30/44e8c032-ebe9-5595-a229-ef960d4865bd/disco-priority-benchmark-evals')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def main():
    a=json.loads((ROOT/'evals/comparison.json').read_text())
    b=json.loads((ROOT/'evals/scoped-comparison.json').read_text())
    c=json.loads((ROOT/'evals/priority-all-fields.json').read_text())
    assert a['status']==b['status']=='complete' and a['source_stats_unchanged'] and b['source_stats_unchanged'] and c['all_passed']
    expected={PRE/'base.sqlite':'7e03e05e97885505f227e1b0938b34f303229db90ddcdd1f7e40f40d6b55e2b6',Path('/private/tmp/disco-real-data-evals-20261001/engines/real.sqlite'):'0427f38b01fad730941c3161d67a4fd6ae75988344527648cc066771b983147e'}
    repo=Path('/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/python')
    expected.update({repo/'workspace_disk_index.py':'bc38a7d0859a0d41edb1fd31b05048211ff4c94a30092003fc1b79b6fa2425a2',repo/'workspace_predicates.py':'c8b7a4b44a8c051b0216eaaa939f4278ea591c41772a7ec9af8e8899756aa2bd',repo/'workspace_metadata_objects.py':'8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd'})
    preservation=[]
    for path,digest in expected.items():
        actual=sha(path);assert actual==digest,str(path)
        preservation.append({'path':str(path),'sha256':actual,'unchanged':True})
    DEST.mkdir(parents=True,exist_ok=True)
    for folder in ['usage','model','evals']:
        for p in (ROOT/folder).iterdir():
            if p.is_file() and p.suffix in ('.py','.json','.md','.log'):
                target=DEST/folder/p.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    shutil.copy2(ROOT/'hot-fields.json',DEST/'hot-fields.json')
    dep=DEST/'previous-model';dep.mkdir(exist_ok=True)
    for p in (PRE/'typed').glob('*.py'):shutil.copy2(p,dep/p.name)
    shutil.copy2(PRE/'base.receipt.json',DEST/'replay-receipt.json')
    (DEST/'preservation.json').write_text(json.dumps(preservation,indent=2)+'\n')
    lines=['# Protocol metadata experiment — 2026-10-01','',
    '**Decision: keep all 140 fields indexed and queryable. Prioritize requested summaries and structural scope, rather than remove uncommon fields from the query engine.**','',
    '## Actual usage and data','',
    'Read-only inspection of saved protocol trees, presets, latest query records and retained HTTP logs found 18 distinct underlying identity/scientific paths. Saved layouts use currentSpotSize for ExpandingSpots and joint(history1, history2, target) for the two noise protocols; retained log axes also include mean, SD, frequency cutoff, control and segment time. The existing mean-noise layout is reported as saved, not silently corrected. Each protocol has 72–101 present paths, versus 140 across the project. See [audit](usage/REPORT.md) and exact field presence counts. Request counts include automation and refreshes, and most POST bodies are absent, so these records cannot prove 80% of human operations.','',
    'The candidate preferred 28 paths combine observed usage, identity and your scientific priorities (NDF, light path, bath temperature, solutions and recording conditions). Pipette/amplifier offsets were not found in the cached field inventory; visual centerOffset is not a substitute. Some recording-condition fields are entirely null or constant in this snapshot. Tags remain important but the retained annotation contains none.','',
    'The million-row experiment reuses a sealed replay of 2,781 real mounted epochs: 359 complete replicas plus 1,621 whole-block tail records. Scientific values, missing/null, arrays and hierarchy are preserved; replay identities are namespaced. It is not a million independent recordings: scientific value cardinalities repeat. The selected cell contains 687 epochs. No live MySQL query, app restart, package rebuild or source-data mutation was performed.','',
    '## Same-output comparison: full140 versus preferred28','',
    'Both candidates reuse the same proved core index. The preferred candidate keeps 19 scientific dictionaries with 107 values, routes nine identity paths through the existing core, and lazily creates typed dictionaries for uncommon fields in its connection. All 140 fields remain available. Each case uses five interleaved samples per arm with alternating order; the table reports the median of samples 2–5. Timings include exact counts, requested facets, 60 native DTO rows and JSON serialization. All 15 cases had identical serialized payload hashes and independently replayed real-source match counts.','',
    '| Action | Full140 (ms) | Preferred28 (ms) |','|---|---:|---:|']
    for entry in a['results']:
        lines.append(f"| {entry['label']} | {entry['arms']['full']['warm_median_ms']:.2f} | {entry['arms']['priority']['warm_median_ms']:.2f} |")
    lines.extend(['',
    'Narrowing the dictionaries did not produce a convincing speed advantage. Several uncommon queries regress even after their first materialization; initial materialization itself took roughly 0.05–4 ms for these fields. The full model already looks up requested fields rather than scanning all 140. Keep the full model for this workload.','',
    'The 57,344-byte hot-file build took 1.159 seconds, mostly integrity/size accounting, but reuses the prebuilt million-row core: it is not a total index-build or app-startup cost. A standalone projected asset is estimated at 772.37 MB versus 1,107.03 MB for the full auxiliary index (about 30% auxiliary savings). This experiment still attaches the complete full file, so it achieves no physical storage reduction. Including the 7.196 GB native replay, the estimated total saving would be only about 4%; no standalone reduced asset was built.','',
    '## Same-output fix: search the structural scope first','',
    'The slow cell queries constructed project-wide membership lists before applying the cell filter. FullScopedSidecar changes generic scientific leaves to correlated EXISTS for explicit cell, block or group scopes, point-reading the epoch/field entry first. Missing uses NOT EXISTS. It retains all 140 dictionaries, validation, exact counts, missing/null semantics, arrays, Boolean compounds, chronology cursors and DTOs. Global and protocol-only SQL are unchanged. No index rebuild is required.','',
    '| Action | Full140 previous (ms) | Full140 scoped (ms) |','|---|---:|---:|'])
    for entry in b['results']:
        lines.append(f"| {entry['label']} | {entry['arms']['full']['warm_median_ms']:.2f} | {entry['arms']['scoped']['warm_median_ms']:.2f} |")
    lines.extend(['',
    'The same five-sample interleaved method was used. Every payload matched both the previous arm and the original full140 A/B receipt. Fixture qualification independently checks 1,185 predicates across all 140 fields, five matching validation rejections, 15 compound predicates and full-field facets across cell/block/group. The preferred-field fallback separately passes all 140 fixture field queries and an exact all-field facet payload. A summaries-harness API typo was corrected after the paired scope timings completed; verified paired receipts were retained and summary timing ran separately.','',
    '## Compute only the summaries the screen requests','',
    'Using the full140 engine, same selected cell and no scientific filter:',
    '| Requested output | Median (ms) |','|---|---:|'])
    for label,entry in b['requested_summaries']['arms'].items():lines.append(f"| {label} | {entry['warm_median_ms']:.2f} |")
    lines.extend(['',
    'The four fields were currentSpotSize, bathTemperature, NDF and lightPath. Counts, rows and cursor are identical; each selected facet exactly equals its entry in the full140 result. This deliberately returns fewer summaries, so it is a workflow saving, not a same-payload engine speedup. Keep the complete field chooser; compute active tree/filter summaries first and request uncommon distributions on demand. Detailed metadata and reconstruction/export data remain complete. A background uncommon-field service was not needed for the winning full-index experiment and has not been implemented in the app.','',
    '## Remaining gaps and regression baseline','',
    'A million epochs does not make every operation fast. Global two-field facets still take about 3.2 seconds and the ExpandingSpots summary scans 668,034 matching epochs in about 3.1 seconds. The structural fix intentionally does not change those global/protocol plans. Cold filesystem startup, UI rendering, native registration/import, waveform loading, stimulus reconstruction and live concurrent tagging were not requalified here. Replay cannot reproduce one million distinct scientific values or a highly populated tag collection.','',
    'All nine historical everyday UI baselines are retained below; these were not remeasured and must not be replaced with database-only times:',
    '| Everyday action | Historical median | Current qualification |',
    '|---|---:|---|',
    '| Select epoch and display metadata | 96 ms | Exact metadata DTO retained; UI not retimed |',
    '| Search selected metadata | 32 ms | Predicate/count/page/facet engine measured; UI not retimed |',
    '| Reopen cached cell | 65 ms | Cache/UI path not retimed |',
    '| Scroll loaded rows | 33 ms | Browser rendering not retimed |',
    '| Expand unloaded cell | 2.48 s | Bounded cell query measured; UI expansion not retimed |',
    '| Expand unloaded block | 2.40 s | Block semantic fixture qualified; UI expansion not retimed |',
    '| Load next 60 cells | 2.14 s | Earlier group paging experiment retained; not remeasured here |',
    '| Tag ten epochs | 52 ms | No live tagging test or writes |',
    '| Preview metadata filter | 3.90 s | Exact count, 60 rows and requested facets measured; UI not retimed |','',
    '## Artifacts and reproduction','',
    'The running DISCO application and main application source remain unchanged. Prototypes and benchmark databases live in /private/tmp/disco-priority-benchmark-20261001; this report preserves scripts, checksums, receipts and usage evidence without copying large databases. Source replay SHA-256, actual source snapshot SHA-256 and three protected application modules were rechecked after timings; index stat identities were unchanged. See preservation.json, evals/comparison.json, evals/scoped-comparison.json, model/scoped-fixture-smoke.json and evals/priority-all-fields.json.','',
    'Local reproduction uses /PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/.rieke-runtime/venv/bin/python -B and the saved evals/compare.py, evals/scoped_compare.py and evals/priority_all_fields.py against the named sealed databases. Scripts retain local experiment paths; copied previous-model files preserve their dependencies. Remove the scoped receipt before rerunning scoped_compare.py to repeat paired timing rather than resume completed cases.',''])
    (DEST/'RESULTS.md').write_text('\n'.join(lines))
    manifest={str(p.relative_to(DEST)):sha(p) for p in DEST.rglob('*') if p.is_file() and p.name!='SHA256.json'}
    (DEST/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'published':str(DEST),'files':len(manifest),'preservation_passed':True}))
if __name__=='__main__':main()
