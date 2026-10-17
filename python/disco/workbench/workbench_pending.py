"""The combined incoming review: current main plus its pending pool.

The pool is the diff between main's saved query and main (``pending_pool``).
One immutable candidate exists per main revision and pool; it is reused until
either changes, so preparation proves nothing beyond the current main.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid

from recording_workspace import now
from disco.workbench.recipes import checksum
from disco.workbench.workbench import WorkbenchConflict
from disco.operation_timing import elapsed


def prepare_pool_candidate(manager, protocol, actor):
    """Return (summary, recipe, created, carried) for main plus its pending pool.

    Caller holds the protocol locks and an open SQL transaction. Earlier
    combined-review decisions carry forward only for unchanged fingerprints;
    new epochs never inherit an earlier 'all' consent.
    """
    state = manager.pending_pool(protocol)
    if state['binding'] is None:
        raise WorkbenchConflict('Combined review requires a saved main dataset')
    main, pool = state['main'], state['pool']
    content = checksum(dict(version=2, protocol_uuid=protocol, main_revision_uuid=main['revision_uuid'],
        main_recipe_sha256=main['content_sha256'], binding_version=state['binding']['version'],
        pool=checksum(pool), source_scope_revision=state['scope']['revision'],
        annotation_scope_revision=(state['annotation'] or {}).get('revision')))
    suggestion_uuid = str(uuid.uuid5(uuid.UUID(manager.project), 'workbench-pool-v2:' + content))
    table = manager.suggestions.Table
    rows = (table & dict(project_uuid=manager.project, suggestion_uuid=suggestion_uuid)).to_dicts()
    created = not rows
    if rows:
        summary = rows[0]['summary']
        recipe = manager.history.get(summary['candidate_revision_uuid'])['recipe']
    else:
        union = {row['uuid']: row['metadata_hash'] for row in main['epochs']}
        union.update(pool)
        preview = dict(predicate=main['predicate'], splits=main['splits'],
            membership=[dict(uuid=key, metadata_hash=union[key]) for key in sorted(union)], matched_count=len(union),
            total_source=len(manager.service.rows), metadata_fingerprint_version=2, source_scope=state['scope'],
            source_revisions=sorted({manager.service.rows[key]['source_sha256'] for key in union}),
            tree=dict(split_order=main['tree_view']['fields']),
            pending_union_provenance=dict(kind='pending_pool', content_sha256=content, origins=[]),
            **({'annotation_scope': state['annotation']} if state['annotation'] else {}))
        record = manager.history.create(preview, manager.service.sources, manager.service.project_dir / 'catalog.json',
            actor, name='Accumulated incoming', parent_revision_uuid=main['revision_uuid'], _in_transaction=True)
        recipe = record['recipe']
        timestamp = now()
        summary = dict(kind='workbench_pending_union', suggestion_uuid=suggestion_uuid, protocol_uuid=protocol,
            protocol_name=manager.service.protocols[protocol]['definition']['name'], created_at=timestamp,
            candidate_revision_uuid=record['revision_uuid'], baseline_revision_uuid=main['revision_uuid'],
            baseline_binding_version=state['binding']['version'], source_filename='Accumulated incoming',
            source_sha256='', source_scope_revision=state['scope']['revision'],
            diff_counts=dict(added=len(pool), removed=0, changed=0),
            incoming_cell_uuids={key: manager.service.rows[key]['cell_uuid'] for key in pool},
            previous_count=len(main['epochs']), next_count=len(union))
        table.insert1(dict(project_uuid=manager.project, suggestion_uuid=suggestion_uuid, protocol_uuid=protocol,
            created_at=dt.datetime.fromisoformat(timestamp).astimezone(dt.timezone.utc).replace(tzinfo=None),
            summary=summary))
    revision = summary['candidate_revision_uuid']
    key = manager.key(protocol, revision, actor)
    carried = dict(initialized=False, carried_from=[], carried_decision_count=0)
    if not (manager.tables[0] & key).to_dicts():
        previous = manager.cumulative_draft(protocol, actor)
        header, decisions = manager.review_decisions(protocol, actor)
        manager.tables[0].insert1(dict(**key, version=max(1, header.get('version', 1)), selection_mode='selected',
                                       deferred=bool(header.get('deferred'))))
        count = 0
        for identity, saved in decisions.items():
            if pool.get(identity) == saved['metadata_hash']:
                manager.tables[1].insert1(dict(**key, epoch_uuid=identity, metadata_hash=saved['metadata_hash'],
                    **{field: bool(saved[field]) for field in ('selected', 'reviewed', 'excluded')}))
                count += 1
        carried = dict(initialized=True, carried_decision_count=count, carried_from=[] if not previous else
            [dict(candidate_revision_uuid=header['candidate_revision_uuid'], draft_version=header['version'])])
    return summary, recipe, created, carried, content


def register_pending_routes(app, manager, db_lock, guarded, actor, body, public_context):
    from flask import jsonify, request

    def queue_fence(protocol, owner, expected):
        if not isinstance(expected, str):
            raise ValueError('Expected an authoritative queue revision')
        if expected != manager.queue(protocol, owner, 1)['queue_revision']:
            raise WorkbenchConflict('Incoming data changed; reload it before reviewing or merging')

    @app.post('/api/protocols/<protocol>/workbench/prepare')
    def workbench_prepare(protocol):
        with elapsed("disco.workbench.workbench_pending", "workbench_prepare"):
            value = body({'expected_queue_revision'}, {'operation_uuid'}, query_options={'include_initial_page'})
            include = request.args.get('include_initial_page', 'false')
            if include not in ('true', 'false'):
                raise ValueError('include_initial_page must be true or false')
            include_page = include == 'true'
            protocol = str(uuid.UUID(protocol))
            with guarded(protocol) as owner:
                request_hash = checksum(dict(kind='workbench_prepare', protocol_uuid=protocol, actor=owner, **value))
                operation = (str(uuid.UUID(value['operation_uuid'])) if 'operation_uuid' in value
                             else str(uuid.uuid5(uuid.UUID(manager.project), request_hash)))
                existing = manager.receipt(operation, owner, request_hash)
                if (existing and 'operation_uuid' not in value
                        and manager.queue(protocol, owner, 1)['queue_revision'] == value['expected_queue_revision']):
                    # The queue is unchanged, but tag or curation edits may have made
                    # the replayed body stale; prepare that as a new operation.
                    current = manager.context(protocol, existing['candidate_revision_uuid'], owner)
                    if current['candidate_scope_revision'] != existing['candidate_scope_revision']:
                        operation = str(uuid.uuid5(uuid.UUID(manager.project),
                                                   request_hash + ':' + current['candidate_scope_revision']))
                        existing = manager.receipt(operation, owner, request_hash)
                if existing:
                    if not include_page:
                        return jsonify(existing)
                    fresh = public_context(manager.context(protocol, existing['candidate_revision_uuid'], owner),
                        include_initial_page=True)
                    return jsonify(dict(existing, bootstrap=fresh['bootstrap']))
                queue_fence(protocol, owner, value['expected_queue_revision'])
                transaction_authority = manager.transaction_authority(protocol)
                with manager.service.dj.conn().transaction:
                    existing = manager.receipt(operation, owner, request_hash)
                    if existing:
                        if not include_page:
                            return jsonify(existing)
                        fresh = public_context(manager.context(protocol, existing['candidate_revision_uuid'], owner,
                            query_revision_guard=transaction_authority[0]), transaction_authority=transaction_authority,
                            include_initial_page=True)
                        # Replay never carries the fresh-context header.
                        return jsonify(dict(existing, bootstrap=fresh['bootstrap']))
                    summary, recipe, created, carried, content = prepare_pool_candidate(manager, protocol, owner)
                    revision = summary['candidate_revision_uuid']
                    context = public_context(manager.context(protocol, revision, owner,
                        query_revision_guard=transaction_authority[0]), transaction_authority=transaction_authority,
                        include_initial_page=include_page)
                    bootstrap = context.pop('bootstrap', None)
                    result = dict(contract_version=1, kind='workbench_pending_union', candidate_revision_uuid=revision,
                        root='/protocols/' + protocol + '/workbench/candidates/' + revision,
                        candidate_scope_revision=context['candidate_scope_revision'], context=context,
                        queue_revision=value['expected_queue_revision'], prepare_operation_uuid=operation,
                        operation_uuid=operation, protocol_uuid=protocol, actor=owner, snapshot_sha256=content,
                        origin_count=0, reused=not created, draft_initialization=carried, counts=context['counts'],
                        storage=dict(revision_count_delta=int(created),
                            recipe_json_bytes=len(json.dumps(recipe, sort_keys=True, separators=(',', ':')).encode())))
                    manager.tables[2].insert1(dict(project_uuid=manager.project, operation_uuid=operation,
                        protocol_uuid=protocol, candidate_revision_uuid=revision, actor=owner,
                        request_sha256=request_hash, receipt=result))
                    manager._event(owner, 'workbench_queue_prepared', result, operation)
                # The transaction exits before publication; replay never carries this header.
                response = jsonify(dict(result, bootstrap=bootstrap) if bootstrap is not None else result)
                response.headers['X-Disco-Workbench-Context'] = 'fresh-v1'
            return response, 201 if created else 200

    @app.post('/api/protocols/<protocol>/workbench/merge-all')
    def workbench_merge_all(protocol):
        """Add every pending, not left-out epoch to main in one request.

        The queue revision the scientist saw is the consent fence. The same
        operation UUID replays its receipt instead of merging twice.
        """
        with elapsed("disco.workbench.workbench_pending", "workbench_merge_all"):
            value = body({'expected_queue_revision', 'operation_uuid'})
            protocol = str(uuid.UUID(protocol))
            operation = str(uuid.UUID(value['operation_uuid']))
            with guarded(protocol) as owner:
                existing = manager.receipt(operation, owner)
                if existing:
                    from disco.workbench.workbench import public_receipt
                    return jsonify(public_receipt(existing))
                queue_fence(protocol, owner, value['expected_queue_revision'])
                with manager.service.dj.conn().transaction:
                    summary = prepare_pool_candidate(manager, protocol, owner)[0]
                revision = summary['candidate_revision_uuid']
                context = manager.context(protocol, revision, owner)
                if context['selection_mode'] != 'all':
                    context = manager.patch(protocol, revision, owner, dict(expected_version=context['draft_version'],
                        expected_candidate_scope_revision=context['candidate_scope_revision'], selection_mode='all'))
                preview = manager.preview(context, dict(expected_candidate_scope_revision=context['candidate_scope_revision'],
                    expected_draft_version=context['draft_version'], mode='all'))[0]
                receipt = manager.accept(protocol, revision, owner, dict(
                    expected_candidate_scope_revision=context['candidate_scope_revision'],
                    expected_draft_version=context['draft_version'], mode='all', operation_uuid=operation,
                    **{key: preview[key] for key in ('preview_sha256', 'expected_binding_version', 'expected_query_revision')}))
                from disco.workbench.workbench import public_receipt
                return jsonify(public_receipt(receipt))

    manager.cumulative_pending_browse = True
