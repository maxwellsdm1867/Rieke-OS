"""Explicit, reusable cumulative pending snapshots; no live recipe substitution."""
from __future__ import annotations

import copy
import datetime as dt
import json
import uuid

from recording_workspace import now
from disco.workbench.recipes import checksum
from disco.navigation.tag_predicates import TagPredicates, referenced_fields
from disco.workbench.workbench import WorkbenchConflict
from disco.operation_timing import elapsed


_CONTENT_FIELDS = ('protocol_uuid', 'main_revision_uuid', 'main_recipe_sha256', 'binding_version',
    'origins', 'pending_sha256', 'source_scope_revision', 'annotation_scope_revision',
    'current_fingerprints_sha256')
_AUTHORITY_FIELDS = frozenset((*_CONTENT_FIELDS, 'query_revision', 'shared_annotations_revision'))


def content_identity(authority):
    """Recipe reuse only; live read/command authority still uses the full snapshot."""
    if set(authority) != _AUTHORITY_FIELDS:
        raise WorkbenchConflict('Cumulative content identity requires complete recognized authority')
    return checksum(dict(version=1, **{key: authority[key] for key in _CONTENT_FIELDS}))


def reusable_candidate(manager, protocol, actor, snapshot, suggestion_uuid):
    """Find an exact sealed cohort, including candidates prepared by older builds.

    Prefer this actor's current draft so an annotation refresh keeps the mounted
    root. Creation provenance stays immutable; the new receipt carries today's
    full authority. Neither matching counts nor matching UUIDs alone suffice.
    """
    table = manager.suggestions.Table
    rows = [row for row in (table & dict(project_uuid=manager.project, protocol_uuid=protocol)).to_dicts()
            if row['summary'].get('kind') == 'workbench_pending_union']
    rows.sort(key=lambda row: (row['summary']['created_at'], row['suggestion_uuid']), reverse=True)
    current = next((row for row in rows if (manager.tables[0] & manager.key(protocol,
        row['summary']['candidate_revision_uuid'], actor)).to_dicts()), None)
    rows.sort(key=lambda row: (row is not current, row['suggestion_uuid'] != suggestion_uuid))
    expected = {**snapshot['main_members'], **snapshot['pending']}
    for row in rows:
        summary = row['summary']
        record = manager.history.get(summary['candidate_revision_uuid'])
        recipe = record['recipe']
        provenance = recipe.get('pending_union_provenance', {})
        authority = {key: value for key, value in provenance.items() if key != 'snapshot_sha256'}
        matches = (set(authority) == _AUTHORITY_FIELDS
            and provenance.get('snapshot_sha256') == checksum(authority)
            and content_identity(authority) == snapshot['content_sha256'])
        if not matches:
            if row['suggestion_uuid'] == suggestion_uuid:
                raise WorkbenchConflict('Prepared content identity collision')
            continue
        members = {item['uuid']: item['metadata_hash'] for item in recipe['epochs']}
        if (members != expected or len(members) != len(recipe['epochs'])
                or recipe.get('parent_revision_uuid') != snapshot['main']['revision_uuid']
                or summary.get('baseline_revision_uuid') != snapshot['main']['revision_uuid']
                or summary.get('baseline_binding_version') != snapshot['authority']['binding_version']):
            raise WorkbenchConflict('Prepared content does not match its sealed cohort')
        return summary, record
    return None


def snapshot_authority(manager, protocol, actor, *, query_revision_guard=None):
    binding = manager.history.protocol_binding(protocol)
    if not binding:
        raise WorkbenchConflict('Cumulative review requires an immutable main baseline')
    main = binding['recipe']
    pending, origins = {}, []
    if query_revision_guard is not None:
        # Inside one locked transaction the guard's answer cannot change between
        # proposals; attest it once instead of once per proposal.
        attested = query_revision_guard()
        query_revision_guard = lambda: attested
    with manager.revision_memo():
        contexts = [manager.context(protocol, row['summary']['candidate_revision_uuid'], actor,
            query_revision_guard=query_revision_guard)
            for row in sorted(manager.original_records(protocol), key=lambda row: row['summary']['candidate_revision_uuid'])]
    for context in contexts:
        # Only mergeable epochs enter the combined review; a proposal that
        # cannot publish contributes nothing instead of refusing preparation.
        mergeable = manager.mergeable(context)
        if not mergeable:
            continue
        for identity, fingerprint in ((key, context['pending'][key]) for key in sorted(mergeable)):
            if identity in pending and pending[identity] != fingerprint:
                raise WorkbenchConflict('Original incoming proposals disagree on a native epoch fingerprint')
            pending[identity] = fingerprint
        origins.append(dict(candidate_revision_uuid=context['candidate_revision_uuid'],
            recipe_sha256=context['candidate_recipe_sha256'], baseline_revision_uuid=context['baseline_revision_uuid'],
            baseline_recipe_sha256=context['baseline_recipe_sha256'],
            annotation_scope_revision=context['annotation_scope_revision']))
    main_members = {row['uuid']: row['metadata_hash'] for row in main['epochs']}
    scope = manager.service.source_scope()
    fields = referenced_fields(main['predicate'])
    annotation = TagPredicates(manager.service).snapshot(fields)[1] if fields else None
    shared = getattr(manager.service, 'shared_annotations', None)
    authority = dict(protocol_uuid=protocol, main_revision_uuid=main['revision_uuid'],
        main_recipe_sha256=main['content_sha256'], binding_version=binding['version'],
        query_revision=query_revision_guard() if query_revision_guard is not None else manager.state(protocol)[2],
        origins=origins, pending_sha256=checksum(pending),
        source_scope_revision=scope['revision'], annotation_scope_revision=(annotation or {}).get('revision'),
        shared_annotations_revision=shared.snapshot()['revision'] if shared else None,
        current_fingerprints_sha256=checksum({key: manager.service._fingerprints.get(key) for key in pending.keys() | main_members.keys()}))
    return dict(authority=authority, sha256=checksum(authority), content_sha256=content_identity(authority), main=main, pending=pending,
        main_members=main_members, scope=scope, annotation=annotation)


def draft_carry(manager, protocol, actor, pending):
    previous = manager.cumulative_draft(protocol, actor)
    if previous:
        header, decisions = previous
        return header, decisions, [dict(candidate_revision_uuid=header['candidate_revision_uuid'], draft_version=header['version'])]
    merged, witnesses, deferred = {}, [], False
    for row in manager.original_records(protocol):
        key = manager.key(protocol, row['summary']['candidate_revision_uuid'], actor)
        headers = (manager.tables[0] & key).to_dicts()
        if not headers:
            continue
        header, decisions = manager.draft(key)
        witnesses.append(dict(candidate_revision_uuid=key['candidate_revision_uuid'], draft_version=header['version']))
        deferred |= bool(header['deferred'])
        for identity, decision in decisions.items():
            if pending.get(identity) != decision['metadata_hash']:
                continue
            if identity in merged and any(merged[identity][field] != decision[field] for field in ('selected', 'reviewed', 'excluded')):
                # Overlapping proposals disagree: leaving an epoch out wins, and
                # it is never silently selected.
                earlier = merged[identity]
                excluded = bool(earlier['excluded'] or decision['excluded'])
                decision = dict(decision, excluded=excluded, selected=False if excluded else bool(earlier['selected'] and decision['selected']),
                                reviewed=bool(earlier['reviewed'] and decision['reviewed']))
            merged[identity] = decision
    return dict(deferred=deferred), merged, witnesses


def register_pending_routes(app, manager, db_lock, guarded, actor, body, public_context):
    from flask import jsonify, request

    @app.post('/api/protocols/<protocol>/workbench/prepare')
    def workbench_prepare(protocol):
        with elapsed("disco.workbench.workbench_pending", "workbench_prepare"):
            value = body({'expected_queue_revision'}, {'operation_uuid'}, query_options={'include_initial_page'})
            include = request.args.get('include_initial_page', 'false')
            if include not in ('true', 'false'):
                raise ValueError('include_initial_page must be true or false')
            include_page = include == 'true'
            if not isinstance(value['expected_queue_revision'], str):
                raise ValueError('Expected an authoritative queue revision')
            protocol = str(uuid.UUID(protocol))
            with db_lock:
                owner = actor()
                request_hash = checksum(dict(kind='workbench_prepare', protocol_uuid=protocol, actor=owner, **value))
                operation = str(uuid.UUID(value['operation_uuid'])) if 'operation_uuid' in value else str(uuid.uuid5(uuid.UUID(manager.project), request_hash))
                existing = manager.receipt(operation, owner, request_hash)
                if existing and not include_page:
                    return jsonify(existing)
            with guarded(protocol) as owner:
                existing = manager.receipt(operation, owner, request_hash)
                if existing:
                    if not include_page:
                        return jsonify(existing)
                    fresh = public_context(manager.context(protocol, existing['candidate_revision_uuid'], owner),
                        include_initial_page=True)
                    return jsonify(dict(existing, bootstrap=fresh['bootstrap']))
                manager.service.refresh()
                queue = manager.queue(protocol, owner, 1)
                if value['expected_queue_revision'] != queue['queue_revision']:
                    raise WorkbenchConflict('Incoming queue changed; reload it before cumulative preparation')
                snapshot = snapshot_authority(manager, protocol, owner)
                originals = manager.original_records(protocol)
                if not originals:
                    raise ValueError('No immutable incoming proposal history is available')
                suggestion_uuid = str(uuid.uuid5(uuid.UUID(manager.project), 'workbench-pending-content-v1:' + snapshot['content_sha256']))
                table = manager.suggestions.Table
                old_header, old_decisions, carried_from = draft_carry(manager, protocol, owner, snapshot['pending'])
                transaction_authority = manager.transaction_authority(protocol)
                with manager.service.dj.conn().transaction:
                    existing = manager.receipt(operation, owner, request_hash)
                    if existing:
                        if not include_page:
                            return jsonify(existing)
                        fresh = public_context(manager.context(protocol, existing['candidate_revision_uuid'], owner,
                            query_revision_guard=transaction_authority[0]), transaction_authority=transaction_authority,
                            include_initial_page=True)
                        # The transaction must exit before this response can be
                        # published. Replay still receives no fresh-v1 header.
                        return jsonify(dict(existing, bootstrap=fresh['bootstrap']))
                    reused = reusable_candidate(manager, protocol, owner, snapshot, suggestion_uuid)
                    if reused:
                        summary, record = reused
                        recipe = record['recipe']
                    else:
                        union = {**snapshot['main_members'], **snapshot['pending']}
                        main = snapshot['main']
                        provenance = dict(snapshot_sha256=snapshot['sha256'], **snapshot['authority'])
                        preview = dict(predicate=copy.deepcopy(main['predicate']), splits=main['splits'],
                            membership=[dict(uuid=key, metadata_hash=union[key]) for key in sorted(union)], matched_count=len(union),
                            total_source=len(manager.service.rows), metadata_fingerprint_version=2,
                            source_scope=snapshot['scope'], source_revisions=sorted({manager.service.rows[key]['source_sha256']
                                for key in union if key in manager.service.rows}), tree=dict(split_order=main['tree_view']['fields']),
                            pending_union_provenance=provenance,
                            **({'annotation_scope': snapshot['annotation']} if snapshot['annotation'] else {}))
                        record = manager.history.create(preview, manager.service.sources, manager.service.project_dir / 'catalog.json', owner,
                            name='Accumulated incoming', parent_revision_uuid=main['revision_uuid'], _in_transaction=True)
                        recipe = record['recipe']
                        timestamp = now()
                        summary = dict(kind='workbench_pending_union', suggestion_uuid=suggestion_uuid, protocol_uuid=protocol,
                            protocol_name=manager.service.protocols[protocol]['definition']['name'], created_at=timestamp,
                            candidate_revision_uuid=record['revision_uuid'], baseline_revision_uuid=main['revision_uuid'],
                            baseline_binding_version=snapshot['authority']['binding_version'],
                            source_filename='Accumulated incoming', source_sha256='', source_scope_revision=snapshot['scope']['revision'],
                            diff_counts=dict(added=len(snapshot['pending']), removed=0, changed=0),
                            incoming_cell_uuids={key: manager.service.rows[key]['cell_uuid'] for key in snapshot['pending'] if key in manager.service.rows},
                            previous_count=len(snapshot['main_members']), next_count=len(union))
                        table.insert1(dict(project_uuid=manager.project, suggestion_uuid=suggestion_uuid, protocol_uuid=protocol,
                            created_at=dt.datetime.fromisoformat(timestamp).astimezone(dt.timezone.utc).replace(tzinfo=None), summary=summary))
                    revision = summary['candidate_revision_uuid']
                    key = manager.key(protocol, revision, owner)
                    initialized = False
                    carried_count = 0
                    if not (manager.tables[0] & key).to_dicts():
                        # New UUIDs never inherit an earlier 'all' consent. This
                        # initialization runs once, including after a lost reply.
                        initialized = True
                        manager.tables[0].insert1(dict(**key, version=max(1, old_header.get('version', 1)),
                            selection_mode='selected', deferred=bool(old_header.get('deferred'))))
                        for identity, saved in old_decisions.items():
                            if snapshot['pending'].get(identity) == saved['metadata_hash']:
                                manager.tables[1].insert1(dict(**key, epoch_uuid=identity, metadata_hash=saved['metadata_hash'],
                                    **{field: bool(saved[field]) for field in ('selected', 'reviewed', 'excluded')}))
                                carried_count += 1
                    if snapshot_authority(manager, protocol, owner,
                            query_revision_guard=transaction_authority[0])['sha256'] != snapshot['sha256']:
                        raise WorkbenchConflict('Cumulative source, annotation or main authority changed during preparation')
                    context = public_context(manager.context(protocol, revision, owner,
                        query_revision_guard=transaction_authority[0]), transaction_authority=transaction_authority,
                        include_initial_page=include_page)
                    bootstrap = context.pop('bootstrap', None)
                    result = dict(contract_version=1, kind='workbench_pending_union', candidate_revision_uuid=revision,
                        root='/protocols/' + protocol + '/workbench/candidates/' + revision,
                        candidate_scope_revision=context['candidate_scope_revision'], context=context,
                        queue_revision=value['expected_queue_revision'], prepare_operation_uuid=operation,
                        operation_uuid=operation, protocol_uuid=protocol, actor=owner,
                        snapshot_sha256=snapshot['sha256'], origin_count=len(snapshot['authority']['origins']), reused=bool(reused),
                        draft_initialization=dict(initialized=initialized, carried_from=carried_from if initialized else [],
                            carried_decision_count=carried_count),
                        counts=context['counts'], storage=dict(revision_count_delta=0 if reused else 1,
                            recipe_json_bytes=len(json.dumps(recipe, sort_keys=True, separators=(',', ':')).encode())))
                    manager.tables[2].insert1(dict(project_uuid=manager.project, operation_uuid=operation,
                        protocol_uuid=protocol, candidate_revision_uuid=revision, actor=owner, request_sha256=request_hash, receipt=result))
                    manager._event(owner, 'workbench_queue_prepared', result, operation)
                # This response computed and closed its context in this request.
                # The durable receipt body stays exact; replay returns above
                # must never acquire this response-local freshness signal.
                response = jsonify(dict(result, bootstrap=bootstrap) if bootstrap is not None else result)
                response.headers['X-Disco-Workbench-Context'] = 'fresh-v1'
            return response, 200 if reused else 201

    manager.cumulative_pending_browse = True
