"""Draft policy from actual field definitions; no application behavior changed."""
import collections,hashlib,json,sqlite3
from pathlib import Path
OUT=Path('/PATH/TO/LOCAL_HOME/.codex/visualizations/2026/09/30/44e8c032-ebe9-5595-a229-ef960d4865bd/disco-metadata-priorities')
OUT.mkdir(exist_ok=True)
profile=Path('/PATH/TO/LOCAL_HOME/.codex/visualizations/2026/09/30/44e8c032-ebe9-5595-a229-ef960d4865bd/disco-real-data-evals/profile/real-metadata-profile.json')
data=json.loads(profile.read_text());observed={f['id']:f for f in data['query_fields']}
base={'epoch','date','cell','block','block time','cell type','group label','group','protocol'}
conditions={'properties/bathTemperature','metadata/cell/properties/type','metadata/group/properties/externalSolutionAdditions','metadata/group/properties/internalSolutionAdditions','metadata/group/properties/pipetteSolution','metadata/group/properties/recordingTechnique','metadata/group/properties/seriesResistanceCompensation'}
visual={'backgroundIntensity','contrast','centerOffset','rotation','maskDiameter','splitField','spotDiameter','currentSpotSize','spotIntensity','temporalFrequency'}
mean={'frequencyCutoff','currentMean','currentSD','useRandomSeed'}
history={'isControl','history1','history2','target','history1Mean','history1SD','history2Mean','history2SD','targetMean','targetSD','segmentTime','frequencyCutoff','useRandomSeed'}
reconstruction={'NDF','amp','backgroundIntensity','canvasSize','centerOffset','contrast','gain','lightPath','maskDiameter','microdisplayBrightness','microdisplayBrightnessValue','micronsPerPixel','monitorRefreshRate','ndfs','numberOfAverages','preTime','prerender','rotation','sampleRate','splitField','spotDiameter','stimTime','tailTime','temporalFrequency','trueCanvasSize','randomizeOrder','spotIntensity','spotSizes','controlMode','firstHistoryID','frequencyCutoff','history1','history1Mean','history1SD','history1Seed','history2','history2Mean','history2SD','history2Seed','historyNoiseVersion','isControl','numberOfFilters','samplesPerBlock','samplesPerSegment','segmentTime','sequenceShuffleSeed','shuffleSequence','stimulusGenerator','stimulusGeneratorVersion','stimulusSampleRate','target','targetMean','targetSD','targetSeed','totalDurationMs','trialNumber','useRandomSeed','currentMean','currentSD','interpulseInterval','seed','stdv','frameTimesMs'}
c=sqlite3.connect('file:/private/tmp/disco-real-data-evals-20261001/engines/real.sqlite?mode=ro&immutable=1',uri=True)
fields=[]
for field,raw in c.execute('SELECT field_id,definition_json FROM fields ORDER BY field_no'):
 definition=json.loads(raw);leaf=field.rsplit('/',1)[-1]
 owner=field.split('/')[1] if field.startswith('metadata/') else 'epoch' if field.startswith(('parameters/','properties/')) else {'cell':'cell','cell type':'cell','block':'block','block time':'block','group':'group','group label':'group'}.get(field,'epoch')
 parameter=field.startswith(('parameters/','metadata/block/parameters/'))
 packs=[]
 if parameter:
  if leaf in visual:packs.append('visual')
  if leaf in mean:packs.append('mean-noise')
  if leaf in history:packs.append('history-noise')
 priority='common-navigation' if field in base else 'common-scientific' if field in conditions else 'protocol-specific' if packs else 'on-demand'
 item=dict(id=field,source_path=definition['path'],owner=owner,owner_status='Path ownership; any inheritance or epoch override must be proven before consolidation',priority=priority,protocol_packs=packs,index_candidate=priority!='on-demand',query_route='Existing typed/native general metadata path remains available for every one of the 140 eligible fields',default_display='bounded row context' if field in base else 'condition panel' if field in conditions else 'active protocol preset' if packs else 'detail on demand',facet_policy='Compute only when requested in current scope',possible_reconstruction_dependency=leaf in reconstruction,reconstruction_policy='Protocol-specific full native metadata and referenced stimulus/device/calibration bundle; this registry is not a complete dependency whitelist',observed=dict(present=observed[field]['present_epochs'],missing=observed[field]['missing_epochs'],null=observed[field]['null_epochs'],types=observed[field]['types'],distinct=observed[field]['cardinality_including_null']))
 if field.endswith('/controlMode'):item['semantic_note']='Observed numeric 0/1 protocol option; do not equate with current/voltage clamp without generator/acquisition specification.'
 if field.endswith('/centerOffset'):item['semantic_note']='Observed visual stimulus position offset. User separately confirmed pipette/amplifier offsets are important.'
 if field in conditions and observed[field]['null_epochs']==2781:item['semantic_note']='All mounted-cache values are null; preserve importance and distinguish recorded null from unloaded or absent. Check original acquisition/import before declaring unavailable.'
 if field=='metadata/group/properties/externalSolutionAdditions':item['semantic_note']='Actual cache value is the string [] (not array or null); preserve native type. Structured interpretation requires a verified source encoding contract.'
 if field=='metadata/group/properties/seriesResistanceCompensation':item['semantic_note']='Actual cache value is integer 0; this is a compensation setting, not measured series resistance.'
 fields.append(item)
c.close()
result=dict(status='proposal_not_runtime_configuration',native_fields=140,real_epochs=2781,field_counts=dict(collections.Counter(f['priority'] for f in fields)),source_profile_sha256=hashlib.sha256(profile.read_bytes()).hexdigest(),common_source_conditions=sorted(conditions),protocol_pack_leaves=dict(visual=sorted(visual),mean_noise=sorted(mean),history_noise=sorted(history)),additional_concepts=[dict(id='source_revision',status='Native core source hash exists; preserve source/experiment keys beyond the 140-field UI catalog'),dict(id='scoped_tags',status='Separate mutable annotation path; preserve existing cell-tag inheritance and protocol/dataset tag scopes'),dict(id='pipette_amplifier_offset',status='User-confirmed priority; no matching field identified in the 140 query fields or 340 cached raw detail paths; audit acquisition/device source, do not substitute visual centerOffset'),dict(id='clamp_mode',status='Science priority; capture explicit amplifier/acquisition state when available, keep distinct from recordingTechnique and numeric protocol controlMode')],fields=fields)
assert len(fields)==140 and len({f['id'] for f in fields})==140
(OUT/'draft-field-policy.json').write_text(json.dumps(result,indent=2)+'\n')
rows=['# Draft classification of all 140 observed query fields','','Draft only. Importance, queryability, indexing, default display, and reconstruction requirements are separate. No source values or application policies changed.','',f"Counts of field paths (aliases included): {result['field_counts']}",'','| Source field | Owner | Proposed query priority | Possible reconstruction dependency | Present / null / missing in 2,781 real epochs |','|---|---|---|---|---|']
for f in fields:rows.append(f"| `{f['id']}` | {f['owner']} | {f['priority']} {', '.join(f['protocol_packs'])} | {'Protocol-dependent' if f['possible_reconstruction_dependency'] else 'Review generator dependencies'} | {f['observed']['present']} / {f['observed']['null']} / {f['observed']['missing']} |")
(OUT/'FIELD-LIST.md').write_text('\n'.join(rows)+'\n')
print(json.dumps(dict(fields=140,counts=result['field_counts'],runtime_changed=False)))
