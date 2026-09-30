"""One-off saved search exports with no protocol workspace or implicit curation.

The legacy protocol_uuid column carries a deterministic export-only scope UUID.
The explicit explorer_candidate scope in every recipe identifies its meaning;
no protocol, binding, pin, or curation record is created.
"""
from __future__ import annotations

import copy
import contextlib
import os
from pathlib import Path
import uuid
import zipfile

from recording_workspace import digest, now, write_json
from workspace_recipes import checksum, member_map, prepare_export, save_snapshot, seal
from workspace_storage import managed_directory

FORMATS = {'reference-json','wheeler-sqlite','epictree-mat'}


class StaleCandidateExport(ValueError):
    pass


def candidate_scope_uuid(project_uuid, revision_uuid):
    project, revision = str(uuid.UUID(project_uuid)), str(uuid.UUID(revision_uuid))
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'recording-workspace:explorer-export:'+project+':'+revision))


def _default_curation(fingerprint):
    return {'included':True,'reviewed':False,'review_state':'unreviewed','tags':[],
            'revision':0,'metadata_fingerprint':fingerprint,'approval_stale':False}


def export_candidate(service, store, history, revision_uuid, **options):
    shared=getattr(service,'shared_annotations',None)
    with shared.lock() if shared else contextlib.nullcontext():
        return _export_candidate_locked(service,store,history,revision_uuid,**options)


def _export_candidate_locked(service, store, history, revision_uuid, *, format,
                     expected_recipe_sha256, name=None, actor='local-user'):
    """Caller holds the app DB lock and project registration lock throughout."""
    if not isinstance(format,str) or format not in FORMATS:
        raise ValueError('Unsupported export format')
    if not isinstance(revision_uuid,str):
        raise ValueError('Candidate identity must be a UUID string')
    revision_uuid=str(uuid.UUID(revision_uuid))
    if not isinstance(expected_recipe_sha256,str) or len(expected_recipe_sha256)!=64 or any(
            char not in '0123456789abcdef' for char in expected_recipe_sha256):
        raise ValueError('Expected the saved candidate recipe SHA256')
    if name is not None and (not isinstance(name,str) or len(name)>120):
        raise ValueError('Export name must be text of at most 120 characters')
    managed_directory(service.project_dir, 'exports')  # Reject live redirects before reads or publication.
    record=history.get(revision_uuid)
    candidate=record['recipe']
    if candidate['content_sha256']!=expected_recipe_sha256:
        raise StaleCandidateExport('Saved candidate identity changed; reload before exporting')
    if candidate['project_uuid']!=service.project['project_uuid'] or store.project_uuid!=service.project['project_uuid']:
        raise ValueError('Candidate export belongs to another project')
    service.refresh()
    preview=service.explore_preview(candidate['predicate'],candidate['splits'],include_tree=False)
    saved=member_map(candidate)
    current=member_map({'epochs':preview['membership']})
    if (saved!=current or candidate.get('metadata_fingerprint_version')!=preview['metadata_fingerprint_version']
            or set(candidate['source_revisions'])!=set(preview['source_revisions'])
            or candidate.get('source_scope',{}).get('revision')!=preview['source_scope']['revision']
            or candidate.get('annotation_scope',{}).get('revision')!=preview.get('annotation_scope',{}).get('revision')):
        raise StaleCandidateExport('Saved search is stale. Rerun and save the updated result before exporting')
    if not saved:
        raise ValueError('A one-off export requires at least one matching epoch')
    scope_uuid=candidate_scope_uuid(service.project['project_uuid'],revision_uuid)
    if scope_uuid in service.protocols or history.protocol_binding(scope_uuid) is not None:
        raise ValueError('Export-only scope collides with an existing protocol workspace')
    # Never inherit a protocol's masks/tags accidentally, even if an external
    # client has manually inserted records using this reserved scope identity.
    current_decisions=store.read(scope_uuid,list(saved),{key:item['metadata_hash'] for key,item in saved.items()})
    if any(item['revision']!=0 for item in current_decisions.values()):
        raise ValueError('Export-only scope unexpectedly contains protocol curation')
    used_sources={service.rows[key]['source_sha256'] for key in saved}
    for source_sha in sorted(used_sources):
        service._verified_source(service.manifests[source_sha])
    grouping=preview['tree']['split_order']
    fields={field['id']:field for field in preview['catalog']['fields']}
    name=(name or '').strip() or ((candidate.get('name') or 'Search')[:85]+' · '+now()[:19].replace('T',' '))
    scope={'kind':'explorer_candidate','revision_uuid':revision_uuid,'candidate_recipe_sha256':expected_recipe_sha256,
        'export_only_scope_uuid':scope_uuid,'protocol_workspace_created':False,
        'curation_policy':'all_candidate_epochs_included_unreviewed_no_implicit_protocol_tags_or_masks'}
    query={'version':2,'kind':'source_predicate','predicate':copy.deepcopy(candidate['predicate'])}
    snapshot={'format':'recording-query-snapshot','version':1,'snapshot_uuid':str(uuid.uuid4()),'created_at':now(),
        'project_uuid':service.project['project_uuid'],'protocol_uuid':scope_uuid,
        'catalog_ref':candidate['catalog_ref'],'query':query,'query_sha256':checksum(query),
        'metadata_fingerprint_version':preview['metadata_fingerprint_version'],
        'view':{'group_by':grouping,'layout':'landscape'},'source_revisions':candidate['source_revisions'],
        'source_scope':copy.deepcopy(candidate['source_scope']), 'export_scope':scope,
        'epochs':[saved[key] for key in sorted(saved)]}
    shared=getattr(service,'shared_annotations',None)
    if shared:snapshot['shared_annotations_revision']=shared.snapshot()['revision']
    if 'annotation_scope' in candidate:
        snapshot['annotation_scope']=copy.deepcopy(candidate['annotation_scope'])
    snapshot=seal(snapshot)
    recipe=prepare_export(snapshot,sorted(saved),destination=format,review_policy='include_unreviewed',actor=actor,
        options={'name':name,'filters':{},'split_order':candidate['splits'],'export_scope':scope,
            'tree_view':{'format':'recording-tree-view','version':1,
                'fields':[{key:fields[field][key] for key in ('id','label','path','category','components') if key in fields[field]}
                          for field in grouping]}})
    output=managed_directory(service.project_dir,'exports')/recipe['export_uuid']
    output.mkdir(parents=True,exist_ok=False)
    artifact=output/'recordings.json'
    try:
        save_snapshot(output/'recipe.json',recipe)
        records=[]
        for key in sorted(saved,key=lambda identity:(service.rows[identity]['date'],service.rows[identity]['start_time'][11:],identity)):
            epoch=service.epoch(key)
            epoch['curation']=_default_curation(saved[key]['metadata_hash'])
            records.append(epoch)
        if shared:
            annotations=shared.for_epochs([service.rows[record['epoch_uuid']] for record in records])
            for record in records:record['annotations']=annotations[record['epoch_uuid']]
        package={'format':'recording-reference-package','version':1,'recipe':recipe,'epochs':records,
            'sources':[{'source_sha256':source['source_sha256'],'source_path':source['source_path']}
                for source in service.sources if source['source_sha256'] in candidate['source_revisions']],
            'export_scope':scope,'waveforms':'references-only; original H5 files must remain accessible'}
        write_json(artifact,package)
        if format=='wheeler-sqlite':
            from workspace_sqlite import build_sqlite_export
            artifact=output/'recordings.sqlite'
            build_sqlite_export(package,artifact)
            from workspace_external_tags import prepare_return_folder
            prepare_return_folder(output,package)
        elif format=='epictree-mat':
            from workspace_matlab import build_matlab_export
            from workspace_matlab_masks import write_ugm
            matlab_dir=output/'matlab'
            matlab=build_matlab_export(service,recipe,matlab_dir,epoch_records=records)
            write_ugm(matlab_dir/'selection.ugm',matlab['epoch_order'],[True]*len(matlab['epoch_order']),metadata={
                'project_uuid':recipe['project_uuid'],'protocol_uuid':scope_uuid,
                'dataset_uuid':recipe['export_uuid'],'export_uuid':recipe['export_uuid'],
                'query_sha256':recipe['query_sha256'],'recipe_sha256':recipe['content_sha256'],
                'mat_file_basename':'recordings','source_scope_revision':preview['source_scope']['revision']})
            write_json(matlab_dir/'export-report.json',{key:value for key,value in matlab.items()
                if key not in {'mat_path','launch_script_path','recipe_path'}})
            (matlab_dir/'README.txt').write_text(
                'One-off saved search export\n\n'
                'This bundle contains the exact saved candidate, without creating a protocol workspace.\n'
                'All candidate epochs are included and unreviewed. No protocol tags or masks are implicitly merged.\n'
                'Explicit scoped tag predicates and their saved evidence are in recipe.json/query_snapshot.\n'
                'Add the current EpicTreeGUI checkout to MATLAB path, then run launch_epictree.m.\n'
                'tree_layout.m reconstructs the saved grouping; it does not rerun the query.\n'
                'Original H5 files must remain accessible. Traces load lazily and verify source SHA256.\n'
                'selection.ugm is matched by UUID; Save Epoch Mask updates this extracted bundle only.\n'
                'Returning a mask to an unrelated protocol requires an explicit matching scope; this export creates none.\n')
            artifact=output/'epictree-bundle.zip'
            with zipfile.ZipFile(artifact,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
                bundle.write(output/'recordings.json','recordings.json')
                bundle.write(output/'recipe.json','recipe.json')
                for file in sorted(matlab_dir.iterdir()):bundle.write(file,file.name)
        from workspace_tag_predicates import annotation_locks
        with annotation_locks(service,candidate['predicate'],extra_protocols=[scope_uuid]):
            if candidate.get('annotation_scope'):
                from workspace_tag_predicates import TagPredicates,referenced_fields
                _,evidence=TagPredicates(service).snapshot(referenced_fields(candidate['predicate']))
                if evidence['revision']!=candidate['annotation_scope']['revision']:
                    raise StaleCandidateExport('Queried tags changed while preparing the export; rerun the saved search')
            for source_sha in sorted(used_sources):
                service._verified_source(service.manifests[source_sha])
            result=store.record_dataset_revision(recipe,actor=actor,expected_revisions={key:0 for key in saved},
                artifact_path=str(artifact),artifact_sha256=digest(artifact))
    except Exception as error:
        try:
            write_json(output/'failure.json',{'at':now(),'status':'failed','error':str(error),
                'artifact_published':False,'export_scope':scope})
        except OSError:
            pass  # Preserve the original failure; SQL publication did not succeed.
        raise
    return {**result,'name':name,'format':format,'export_scope':scope,
            'download_url':'/api/exports/'+result['dataset_uuid']+'/download'}


def register_candidate_export_routes(app,service,store,history,db_lock,registration_locks):
    from flask import jsonify,request
    @app.post('/api/explore/revisions/<revision_uuid>/exports')
    def candidate_export(revision_uuid):
        if request.args or (request.content_length is not None and request.content_length>16384):
            raise ValueError('Candidate export options must be at most16KiB with no URL parameters')
        try:body=request.get_json()
        except (RecursionError,OverflowError) as error:
            raise ValueError('Candidate export options exceed JSON limits') from error
        if not isinstance(body,dict) or set(body)-{'name','format','expected_recipe_sha256'} or not {'format','expected_recipe_sha256'}<=set(body):
            raise ValueError('Candidate export requires format and expected_recipe_sha256 only, with an optional name')
        with db_lock,registration_locks():
            try:
                result=export_candidate(service,store,history,revision_uuid,actor=os.environ.get('USER','local-user'),**body)
            except StaleCandidateExport as error:
                return jsonify(error=str(error),code='stale_candidate_export'),409
        return jsonify(result),201
