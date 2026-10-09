"""Incoming-only exports; acceptance and export have separate durable receipts.

Artifacts stage on the filesystem. Dataset, audit and export receipt publish in
one native transaction. A failed export never rebinds or rolls back acceptance.
"""
from __future__ import annotations

import copy
from pathlib import Path
import uuid

from recording_workspace import digest, now, write_json
from disco.workbench.candidate_exports import FORMATS, _default_curation
from workspace_protocol_identity import require_protocol_compatibility
from disco.workbench.recipes import checksum, prepare_export, save_snapshot, seal
from disco.projects.storage import managed_directory
from disco.workbench.workbench import WorkbenchConflict, public_receipt


def formats_for_candidate(candidate):
    from disco.navigation.tree import joint_components
    fields = []
    for field in candidate['tree_view']['fields']:
        fields.extend(joint_components(field) if field.startswith('joint/') else [field])
    # The MATLAB adapter currently groups acquisition metadata only. Preserve
    # annotation grouping faithfully in JSON/SQLite rather than silently changing it.
    unsupported = any(field.startswith(('annotations/', 'curation/')) for field in fields)
    return sorted(FORMATS - {'matlab-mat'} if unsupported else FORMATS)


def accepted_export_context(manager, protocol, operation, actor):
    receipt = manager.receipt(operation, actor)
    if not receipt or receipt.get('protocol_uuid') != protocol or 'accepted_fingerprints' not in receipt:
        raise KeyError('Acceptance receipt not found for this actor and protocol')
    record = manager.history.get(receipt['candidate_revision_uuid'])
    candidate = record['recipe']
    fingerprints = receipt['accepted_fingerprints']
    if candidate['content_sha256'] != receipt.get('candidate_recipe_sha256'):
        raise WorkbenchConflict('Acceptance candidate recipe changed')
    if not fingerprints:
        raise ValueError('This acceptance added no new epochs to export')
    shared = getattr(manager.service, 'shared_annotations', None)
    scope = manager.service.source_scope()
    context = dict(protocol_uuid=protocol, actor=actor, candidate_revision_uuid=receipt['candidate_revision_uuid'],
        accept_operation_uuid=operation, accepted_receipt_sha256=checksum(receipt),
        candidate_recipe_sha256=candidate['content_sha256'], source_scope_revision=scope['revision'],
        shared_annotations_revision=shared.snapshot()['revision'] if shared else None,
        fingerprints_sha256=checksum(fingerprints), current_fingerprints_sha256=checksum(
            {key: manager.service._fingerprints.get(key) for key in fingerprints}))
    context['export_scope_revision'] = checksum(context)
    return dict(**context, incoming=fingerprints, previous={}, source_scope=scope,
                candidate=candidate, receipt=receipt)


def publish_incoming_export(manager, store, context, fingerprints, actor, options, *, acceptance=None):
    service, history = manager.service, manager.history
    format = options['format']
    if not isinstance(format, str) or format not in FORMATS:
        raise ValueError('Unsupported incoming export format')
    if format not in formats_for_candidate(context['candidate']):
        raise ValueError('MATLAB export cannot preserve this annotation grouping; choose reference JSON or SQLite')
    name = options.get('name')
    if name is not None and (not isinstance(name, str) or len(name) > 120):
        raise ValueError('Export name must be text of at most 120 characters')
    if not fingerprints:
        raise ValueError('No new reviewed incoming additions remain to export')
    require_protocol_compatibility(service, context['protocol_uuid'], fingerprints)
    manager.verify_sources(context, fingerprints)
    operation = str(uuid.UUID(options['operation_uuid']))
    request_hash = checksum(dict(kind='workbench_incoming_export', protocol_uuid=context['protocol_uuid'],
        candidate_revision_uuid=context['candidate_revision_uuid'], actor=actor, accept_operation_uuid=acceptance, **options))
    existing = manager.receipt(operation, actor, request_hash)
    if existing:
        return existing
    scope_uuid = str(uuid.uuid5(uuid.UUID(manager.project), 'workbench-export:' + operation))
    if scope_uuid in service.protocols or history.protocol_binding(scope_uuid):
        raise ValueError('Incoming export-only scope collides with a protocol')
    saved = store.read(scope_uuid, list(fingerprints), fingerprints)
    if any(value['revision'] for value in saved.values()):
        raise ValueError('Incoming export-only scope unexpectedly contains scientific curation')
    candidate = context['candidate']
    source_revisions = sorted({service.rows[key]['source_sha256'] for key in fingerprints})
    scope = dict(kind='workbench_incoming', target_protocol_uuid=context['protocol_uuid'],
        candidate_revision_uuid=context['candidate_revision_uuid'], candidate_recipe_sha256=candidate['content_sha256'],
        baseline_revision_uuid=candidate['parent_revision_uuid'], actor=actor, export_operation_uuid=operation,
        export_only_scope_uuid=scope_uuid, accept_operation_uuid=acceptance,
        selection_sha256=checksum(fingerprints), incoming_epoch_count=len(fingerprints),
        curation_policy='native_scientific_approval_unchanged; branch_review_is_selection_provenance',
        selection_authority='committed_acceptance_delta' if acceptance else 'frozen_review_preview',
        **({'acceptance_receipt_sha256': context['accepted_receipt_sha256'],
            'preview_sha256': context['receipt']['preview_sha256']} if acceptance else
           {'candidate_scope_revision': context['candidate_scope_revision'],
            'draft_version': context['draft_version'], 'preview_sha256': options['preview_sha256']}))
    query = dict(version=2, kind='source_predicate', predicate=copy.deepcopy(candidate['predicate']))
    snapshot = dict(format='recording-query-snapshot', version=1, snapshot_uuid=str(uuid.uuid4()), created_at=now(),
        project_uuid=manager.project, protocol_uuid=scope_uuid, catalog_ref=candidate['catalog_ref'],
        query=query, query_sha256=checksum(query), metadata_fingerprint_version=2,
        view=dict(group_by=candidate['tree_view']['fields'], layout='landscape'),
        source_revisions=source_revisions, source_scope=copy.deepcopy(context['source_scope']), export_scope=scope,
        epochs=[dict(uuid=key, metadata_hash=value) for key, value in sorted(fingerprints.items())])
    shared = getattr(service, 'shared_annotations', None)
    if shared:
        snapshot['shared_annotations_revision'] = shared.snapshot()['revision']
    # Original predicate witnesses remain provenance, not permission to rerun
    # a query and widen an accepted or reviewed exact epoch selection.
    if candidate.get('annotation_scope'):
        snapshot['origin_annotation_scope'] = copy.deepcopy(candidate['annotation_scope'])
    name = (name or '').strip() or 'Incoming additions · ' + now()[:19].replace('T', ' ')
    recipe = prepare_export(seal(snapshot), sorted(fingerprints), destination=format,
        review_policy='include_unreviewed', actor=actor,
        options=dict(name=name, filters={}, split_order=candidate['splits'], export_scope=scope,
            tree_view=candidate['tree_view']))
    output = managed_directory(service.project_dir, 'exports') / recipe['export_uuid']
    output.mkdir(parents=True, exist_ok=False)
    artifact = output / 'recordings.json'
    try:
        save_snapshot(output / 'recipe.json', recipe)
        records = []
        for key in sorted(fingerprints, key=lambda key: (service.rows[key]['date'], service.rows[key]['start_time'], key)):
            row = service.epoch(key)
            row['curation'] = _default_curation(fingerprints[key])
            records.append(row)
        if shared:
            annotations = shared.for_epochs([service.rows[row['epoch_uuid']] for row in records])
            for row in records:
                row['annotations'] = annotations[row['epoch_uuid']]
        package = dict(format='recording-reference-package', version=1, recipe=recipe, epochs=records,
            sources=[dict(source_sha256=source['source_sha256'], source_path=source['source_path'])
                for source in service.sources if source['source_sha256'] in source_revisions],
            export_scope=scope, waveforms='references-only; original H5 files must remain accessible')
        if format == 'linked-sqlite':
            from workspace_linked_sqlite import prepare_linked_package, build_linked_export_bundle
            package = prepare_linked_package(package, service.manifests, service.project_dir,
                                             grouping_sources=service.sources)
            artifact = build_linked_export_bundle(package, output)
        else:
            write_json(artifact, package)
        if format == 'wheeler-sqlite':
            from workspace_sqlite import build_sqlite_export
            from disco.decisions.external_tags import prepare_return_folder
            artifact = output / 'recordings.sqlite'
            build_sqlite_export(package, artifact)
            prepare_return_folder(output, package)
        elif format == 'matlab-mat':
            from workspace_matlab import build_matlab_export
            result = build_matlab_export(service, recipe, output / 'matlab', epoch_records=records)
            write_json(output / 'matlab/export-report.json', {key: value for key, value in result.items()
                if key not in {'mat_path', 'recipe_path'}})
            artifact = Path(result['mat_path'])
        manager.verify_sources(context, fingerprints)
        if shared and shared.snapshot()['revision'] != snapshot['shared_annotations_revision']:
            raise WorkbenchConflict('Shared annotations changed while preparing incoming export')
        receipt = None
        def commit_receipt(result):
            nonlocal receipt
            # Invoked inside DatasetRevision's native data transaction.
            manager.verify_sources(context, fingerprints)
            receipt = dict(**result, operation_uuid=operation, protocol_uuid=context['protocol_uuid'],
                candidate_revision_uuid=context['candidate_revision_uuid'], actor=actor,
                accept_operation_uuid=acceptance, export_state='complete', format=format, name=name,
                recipe_sha256=recipe['content_sha256'], export_scope=scope,
                download_url='/api/exports/' + result['dataset_uuid'] + '/download')
            manager.tables[2].insert1(dict(project_uuid=manager.project, operation_uuid=operation,
                protocol_uuid=context['protocol_uuid'], candidate_revision_uuid=context['candidate_revision_uuid'],
                actor=actor, request_sha256=request_hash, receipt=receipt))
            manager._event(actor, 'workbench_incoming_exported', receipt, operation)
        store.record_dataset_revision(recipe, actor=actor, expected_revisions={key: 0 for key in fingerprints},
            artifact_path=str(artifact), artifact_sha256=digest(artifact), publication_callback=commit_receipt)
        return receipt
    except Exception as error:
        try:
            write_json(output / 'failure.json', dict(at=now(), status='failed', error=str(error),
                artifact_published=False, export_scope=scope, acceptance_retained=bool(acceptance)))
        except OSError:
            pass
        raise


def register_workbench_export_routes(app, manager, store, db_lock, guarded, actor, body):
    from flask import jsonify, request
    root = '/api/protocols/<protocol>/workbench'
    candidate_root = root + '/candidates/<revision>'
    receipt_root = root + '/receipts/<operation>'

    def existing_export(protocol, revision, acceptance, value):
        with db_lock:
            owner = actor()
            request_hash = checksum(dict(kind='workbench_incoming_export', protocol_uuid=protocol,
                candidate_revision_uuid=revision, actor=owner, accept_operation_uuid=acceptance, **value))
            return manager.receipt(value['operation_uuid'], owner, request_hash)

    @app.get(receipt_root)
    def workbench_receipt(protocol, operation):
        if request.args:
            raise ValueError('Receipt lookup accepts no query options')
        with db_lock:
            receipt = manager.receipt(operation, actor())
            if not receipt or receipt.get('protocol_uuid') != protocol:
                raise KeyError('Workbench receipt not found')
            return jsonify(public_receipt(receipt))

    @app.post(candidate_root + '/exports')
    def workbench_incoming_export(protocol, revision):
        value = body({'expected_candidate_scope_revision', 'expected_draft_version', 'mode', 'preview_sha256',
                      'expected_binding_version', 'expected_query_revision', 'operation_uuid', 'format'}, {'name'})
        existing = existing_export(protocol, revision, None, value)
        if existing:
            return jsonify(existing)
        with guarded(protocol, revision) as owner:
            existing = existing_export(protocol, revision, None, value)
            if existing:
                return jsonify(existing)
            manager.service.refresh()
            context = manager.context(protocol, revision, owner)
            preview, _, additions = manager.preview(context, value)
            if (value['preview_sha256'] != preview['preview_sha256']
                    or type(value['expected_binding_version']) is not int
                    or value['expected_binding_version'] != preview['expected_binding_version']
                    or value['expected_query_revision'] != preview['expected_query_revision']):
                raise WorkbenchConflict('Incoming export preview changed; review the new delta')
            result = publish_incoming_export(manager, store, context,
                {key: context['incoming'][key] for key in additions}, owner, value)
            return jsonify(result), 201

    @app.get(receipt_root + '/export-context')
    def workbench_accept_export_context(protocol, operation):
        if request.args:
            raise ValueError('Acceptance export context accepts no query options')
        with db_lock:
            receipt = manager.receipt(operation, actor())
            if not receipt or receipt.get('protocol_uuid') != protocol or 'accepted_fingerprints' not in receipt:
                raise KeyError('Acceptance receipt not found')
        with guarded(protocol, receipt['candidate_revision_uuid']) as owner:
            context = accepted_export_context(manager, protocol, operation, owner)
            manager.verify_sources(context, context['incoming'])
            return jsonify(export_scope_revision=context['export_scope_revision'], accepted_epoch_count=len(context['incoming']),
                accept_operation_uuid=operation, candidate_revision_uuid=context['candidate_revision_uuid'],
                formats=formats_for_candidate(context['candidate']))

    @app.post(receipt_root + '/exports')
    def workbench_accept_export(protocol, operation):
        value = body({'expected_export_scope_revision', 'format', 'operation_uuid'}, {'name'})
        with db_lock:
            receipt = manager.receipt(operation, actor())
            if not receipt or receipt.get('protocol_uuid') != protocol or 'accepted_fingerprints' not in receipt:
                raise KeyError('Acceptance receipt not found')
        revision = receipt['candidate_revision_uuid']
        existing = existing_export(protocol, revision, operation, value)
        if existing:
            return jsonify(existing)
        with guarded(protocol, revision) as owner:
            existing = existing_export(protocol, revision, operation, value)
            if existing:
                return jsonify(existing)
            manager.service.refresh()
            context = accepted_export_context(manager, protocol, operation, owner)
            if value['expected_export_scope_revision'] != context['export_scope_revision']:
                raise WorkbenchConflict('Acceptance export source or annotation evidence changed; reload export context')
            result = publish_incoming_export(manager, store, context, context['incoming'], owner, value, acceptance=operation)
            return jsonify(result), 201

    manager.incoming_export = True
