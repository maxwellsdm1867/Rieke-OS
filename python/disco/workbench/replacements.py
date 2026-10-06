"""Frozen full-change proposals. Replacement intent is never an additive union."""
from __future__ import annotations

import copy
import datetime as dt
import uuid

from recording_workspace import now
from disco.workbench.diff import summarize_diff
from disco.workbench.recipes import checksum
from disco.workbench.workbench import WorkbenchConflict, _members
from workspace_protocol_identity import protocol_compatibility


def is_replacement(summary):
    counts = summary.get('diff_counts', {})
    return summary.get('review_kind') == 'replacement' or bool(counts.get('removed') or counts.get('changed'))


def records(manager, protocol):
    return [row for row in (manager.suggestions.Table & dict(project_uuid=manager.project,
        protocol_uuid=protocol)).to_dicts() if is_replacement(row['summary'])]


def preview(manager, protocol, revision, actor, *, query_guard=None):
    manager.key(protocol, revision, actor)
    summary, baseline, candidate = manager.proposal(protocol, revision)
    if not is_replacement(summary):
        raise ValueError('This proposal uses additive review')
    binding = manager.history.protocol_binding(protocol)
    if not binding or binding['version'] != summary['baseline_binding_version'] or binding['revision_uuid'] != baseline['revision_uuid']:
        raise WorkbenchConflict('The frozen protocol baseline changed; submit a fresh proposal')
    previous, proposed = _members(baseline), _members(candidate)
    scope = manager.service.source_scope()
    from disco.navigation.tag_predicates import TagPredicates, referenced_fields
    fields = referenced_fields(candidate['predicate'])
    annotation = TagPredicates(manager.service).snapshot(fields)[1] if fields else None
    if candidate.get('annotation_scope', {}).get('revision') != (annotation or {}).get('revision'):
        raise WorkbenchConflict('Predicate annotations changed; submit a fresh proposal')
    if any(manager.service._fingerprints.get(key) != value for key, value in proposed.items()):
        raise WorkbenchConflict('Frozen candidate metadata changed; submit a fresh proposal')
    if any(manager.service.rows[key]['source_sha256'] not in scope['active_source_revisions'] for key in proposed):
        raise WorkbenchConflict('Candidate sources are no longer eligible')
    compatibility = protocol_compatibility(manager.service, protocol, proposed)
    # An explicit removal review can empty an existing protocol. Initial creation
    # and incoming exports keep their separate nonempty-selection requirements.
    if not proposed:
        compatibility['compatible'] = True
    if not compatibility['compatible']:
        raise ValueError('Candidate contains epochs from another acquisition protocol')
    delta = dict(added=sorted(proposed.keys() - previous.keys()), removed=sorted(previous.keys() - proposed.keys()),
        changed=sorted(key for key in previous.keys() & proposed.keys() if previous[key] != proposed[key]))
    shared = getattr(manager.service, 'shared_annotations', None)
    evidence = dict(protocol_uuid=protocol, candidate_revision_uuid=revision, actor=actor,
        candidate_recipe_sha256=candidate['content_sha256'], baseline_recipe_sha256=baseline['content_sha256'],
        expected_binding_version=binding['version'],
        expected_query_revision=query_guard() if query_guard else manager.state(protocol)[2],
        source_scope_revision=scope['revision'], annotation_scope_revision=(annotation or {}).get('revision'),
        shared_annotations_revision=shared.snapshot()['revision'] if shared else None,
        current_fingerprints_sha256=checksum({key: manager.service._fingerprints.get(key)
            for key in previous.keys() | proposed.keys()}))
    token = checksum(evidence)
    result = dict(contract_version=1, review_kind='replacement', **evidence,
        candidate_scope_revision=token, expected_candidate_scope_revision=token,
        diff=delta, diff_counts={key: len(value) for key, value in delta.items()},
        diff_summary=summarize_diff(manager.service.rows, previous, proposed), compatibility=compatibility,
        previous_count=len(previous), next_count=len(proposed))
    result['preview_sha256'] = checksum(result)
    return result


def queue_items(manager, protocol, actor):
    items, pending, cells, witnesses = [], set(), {}, []
    for row in sorted(records(manager, protocol), key=lambda row: row['summary']['created_at'], reverse=True):
        summary = row['summary']
        revision = summary['candidate_revision_uuid']
        receipts = (manager.tables[2] & dict(project_uuid=manager.project, protocol_uuid=protocol,
            candidate_revision_uuid=revision)).to_dicts()
        accepted = any(item['receipt'].get('kind') == 'workbench_replacement_accepted' for item in receipts)
        baseline = manager.history.get(summary['baseline_revision_uuid'])['recipe']
        candidate = manager.history.get(revision)['recipe']
        old, new = _members(baseline), _members(candidate)
        affected = {key for key in old.keys() | new.keys() if old.get(key) != new.get(key)}
        binding = manager.history.protocol_binding(protocol)
        superseded = bool(binding and (binding['version'] != summary['baseline_binding_version']
            or binding['revision_uuid'] != summary['baseline_revision_uuid']))
        resolved = accepted or superseded
        status, error = 'accepted' if accepted else 'superseded' if superseded else 'pending', None
        try:
            value = preview(manager, protocol, revision, actor) if not resolved else None
        except (WorkbenchConflict, ValueError) as exc:
            status, error, value = 'conflict', str(exc), None
        if not resolved:
            pending |= affected
            for key in affected:
                cell = summary.get('affected_cell_uuids', {}).get(key) or summary.get('incoming_cell_uuids', {}).get(key)
                if not cell and key in manager.service.rows:
                    cell = manager.service.rows[key]['cell_uuid']
                if cell:
                    cells[key] = cell
        item = {key: copy.deepcopy(value) for key, value in summary.items() if key not in ('incoming_cell_uuids', 'affected_cell_uuids')}
        item.update(review_kind='replacement', status=status, pending_epoch_count=0 if resolved else len(affected),
            root='/protocols/' + protocol + '/workbench/candidates/' + revision)
        if error:
            item['review_error'] = error
        items.append(item)
        witnesses.append(dict(revision=revision, status=status, scope=value['candidate_scope_revision'] if value else None))
    return items, pending, cells, witnesses


def submit(manager, protocol, revision, actor, body, validated_record):
    request_hash = checksum(dict(kind='workbench_replacement_proposal', actor=actor, revision=revision, **body))
    operation = str(uuid.UUID(body['operation_uuid']))
    existing = manager.receipt(operation, actor, request_hash)
    if existing:
        return existing
    source = validated_record['recipe']
    members = _members(source)
    compatibility = protocol_compatibility(manager.service, protocol, members)
    if members and not compatibility['compatible']:
        raise ValueError('Candidate contains epochs from another acquisition protocol')
    # Freeze only the current destination; never widen its starter membership.
    manager.suggestions.freeze_baselines(actor, manager.state, revision_guard=manager.revision_guard,
        protocol_uuid=protocol)
    binding = manager.history.protocol_binding(protocol)
    frozen = dict(predicate=copy.deepcopy(source['predicate']), splits=source['splits'],
        membership=copy.deepcopy(source['epochs']), matched_count=len(members), total_source=len(manager.service.rows),
        metadata_fingerprint_version=source['metadata_fingerprint_version'], source_revisions=source['source_revisions'],
        source_scope=source['source_scope'], tree=dict(split_order=source['tree_view']['fields']),
        **({'annotation_scope': source['annotation_scope']} if source.get('annotation_scope') else {}))
    old = _members(binding['recipe'])
    delta = dict(added=sorted(members.keys() - old.keys()), removed=sorted(old.keys() - members.keys()),
        changed=sorted(key for key in old.keys() & members.keys() if old[key] != members[key]))
    affected = set().union(*map(set, delta.values()))
    table = manager.suggestions.Table
    guard = manager.revision_guard(protocol)
    query_revision = manager.state(protocol)[2]
    with manager.service.dj.conn().transaction:
        if guard() != query_revision:
            raise WorkbenchConflict('Protocol authority changed during proposal submission')
        candidate = manager.history.create(frozen, manager.service.sources, manager.service.project_dir / 'catalog.json',
            actor, name=source['name'], parent_revision_uuid=binding['revision_uuid'], _in_transaction=True)
        timestamp = now()
        summary = dict(suggestion_uuid=operation, protocol_uuid=protocol,
            protocol_name=manager.service.protocols[protocol]['definition']['name'],
            candidate_revision_uuid=candidate['revision_uuid'], baseline_revision_uuid=binding['revision_uuid'],
            baseline_binding_version=binding['version'], source_revision_uuid=revision,
            source_filename='Predicate search', source_sha256='', created_at=timestamp,
            source_scope_revision=source['source_scope']['revision'], review_kind='replacement', origin='predicate',
            diff_counts={key: len(value) for key, value in delta.items()}, diff_summary=summarize_diff(manager.service.rows, old, members),
            affected_cell_uuids={key: manager.service.rows[key]['cell_uuid'] for key in affected if key in manager.service.rows},
            previous_count=len(old), next_count=len(members))
        table.insert1(dict(project_uuid=manager.project, suggestion_uuid=operation, protocol_uuid=protocol,
            created_at=dt.datetime.fromisoformat(timestamp).astimezone(dt.timezone.utc).replace(tzinfo=None), summary=summary))
        receipt = dict(contract_version=1, review_kind='replacement', kind='workbench_replacement_proposed',
            operation_uuid=operation, candidate_revision_uuid=candidate['revision_uuid'], protocol_uuid=protocol,
            root='/protocols/' + protocol + '/workbench/candidates/' + candidate['revision_uuid'], proposal=summary)
        manager.tables[2].insert1(dict(project_uuid=manager.project, operation_uuid=operation, protocol_uuid=protocol,
            candidate_revision_uuid=candidate['revision_uuid'], actor=actor, request_sha256=request_hash, receipt=receipt))
        manager._event(actor, 'protocol_update_suggested', receipt, operation)
    return receipt


def accept(manager, protocol, revision, actor, body):
    request_hash = checksum(dict(kind='workbench_replacement_accept', protocol_uuid=protocol,
        candidate_revision_uuid=revision, actor=actor, **body))
    existing = manager.receipt(body['operation_uuid'], actor, request_hash)
    if existing:
        return existing
    value = preview(manager, protocol, revision, actor)
    for field in ('expected_candidate_scope_revision', 'expected_binding_version', 'expected_query_revision', 'preview_sha256'):
        if body[field] != value[field] or (field == 'expected_binding_version' and type(body[field]) is not int):
            raise WorkbenchConflict('Full-change preview changed; review again before accepting')
    if type(body['confirm_removals']) is not bool or (value['diff_counts']['removed'] and not body['confirm_removals']):
        raise ValueError('Explicit confirmation of protocol removals is required')
    candidate = manager.history.get(revision)['recipe']
    proposed = _members(candidate)
    source_context = dict(source_scope_revision=value['source_scope_revision'], incoming=proposed, previous={})
    manager.verify_sources(source_context, proposed)
    guard, _ = manager.transaction_authority(protocol)
    with manager.service.dj.conn().transaction:
        again = manager.receipt(body['operation_uuid'], actor, request_hash)
        if again:
            return again
        if preview(manager, protocol, revision, actor, query_guard=guard)['preview_sha256'] != value['preview_sha256']:
            raise WorkbenchConflict('Full-change authority changed during acceptance')
        manager.verify_sources(source_context, proposed)
        binding = manager.history.bind(revision, protocol, value['expected_binding_version'], actor, value['diff'],
            value['previous_count'], expected_query_revision=value['expected_query_revision'], current_query_revision=guard,
            diff_summary=value['diff_summary'], _in_transaction=True, _lock_held=True)
        receipt = dict(**value, kind='workbench_replacement_accepted', operation_uuid=str(uuid.UUID(body['operation_uuid'])),
            binding=binding, event_uuid=str(uuid.uuid4()), accepted_epoch_count=value['diff_counts']['added'],
            removed_epoch_count=value['diff_counts']['removed'], changed_epoch_count=value['diff_counts']['changed'])
        manager.tables[2].insert1(dict(project_uuid=manager.project, operation_uuid=receipt['operation_uuid'],
            protocol_uuid=protocol, candidate_revision_uuid=revision, actor=actor, request_sha256=request_hash, receipt=receipt))
        manager._event(actor, 'workbench_replacement_accepted', receipt, receipt['operation_uuid'], event_uuid=receipt['event_uuid'])
    return receipt


def register_routes(app, manager, guarded, body, db_lock, resolve_actor):
    from flask import jsonify
    root = '/api/protocols/<protocol>/workbench/candidates/<revision>'

    @app.get(root + '/replacement-preview')
    def workbench_replacement_preview(protocol, revision):
        with guarded(protocol, revision) as actor:
            value = preview(manager, protocol, revision, actor)
            if preview(manager, protocol, revision, actor)['preview_sha256'] != value['preview_sha256']:
                raise WorkbenchConflict('Full-change authority changed during preview')
            return jsonify(value)

    @app.post(root + '/replacement-accept')
    def workbench_replacement_accept(protocol, revision):
        value = body({'expected_candidate_scope_revision', 'expected_binding_version', 'expected_query_revision',
            'preview_sha256', 'operation_uuid', 'confirm_removals'})
        with db_lock:
            manager.tables
            actor = resolve_actor()
            request_hash = checksum(dict(kind='workbench_replacement_accept', protocol_uuid=protocol,
                candidate_revision_uuid=revision, actor=actor, **value))
            existing = manager.receipt(value['operation_uuid'], actor, request_hash)
            if existing:
                return jsonify(existing)
        with guarded(protocol, revision) as actor:
            return jsonify(accept(manager, protocol, revision, actor, value))
