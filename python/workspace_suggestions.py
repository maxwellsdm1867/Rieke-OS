"""Persistent post-import query candidates; never apply new membership automatically."""
from __future__ import annotations

import copy
import datetime as dt
from pathlib import Path
import uuid

from recording_workspace import now
from workspace_audit import build_audit_payload
from workspace_diff import summarize_diff
from workspace_recipes import checksum


def suggestion_table(dj):
    schema = dj.Schema('recording_workspace')

    @schema
    class ProtocolSuggestion(dj.Manual):
        definition = """
        project_uuid: varchar(36)
        suggestion_uuid: varchar(36)
        ---
        protocol_uuid: varchar(36)
        created_at: datetime
        summary: json
        """
    return ProtocolSuggestion


class ProtocolSuggestions:
    def __init__(self, service, history, *, table=None):
        self.service, self.history = service, history
        self.project_uuid = service.project['project_uuid']
        self._table = table

    @property
    def Table(self):
        if self._table is None:
            self._table = suggestion_table(self.service.dj)
        return self._table

    def freeze_baselines(self, actor, state):
        """Caller holds project/database guards, before launching the importer.

        Starter files are live acquisition queries. Convert only their current
        exact cohort to a binding, before new source rows can widen that query.
        Existing bindings, curation, and scientific membership remain unchanged.
        """
        baselines = []
        for identity, workspace in self.service.protocols.items():
            binding = self.history.protocol_binding(identity)
            if binding is None:
                definition = workspace['definition']
                clauses = definition['query'].get('all', [])
                if len(clauses) != 1 or clauses[0].get('field') != 'EpochBlock.protocol_name' or clauses[0].get('operator') != 'eq':
                    raise ValueError('Cannot freeze unsupported starter query before import')
                predicate = {'field': 'protocol', 'operator': 'eq', 'value': clauses[0]['value']}
                grouping = definition.get('view', {}).get('group_by', ['date', 'cell', 'block'])
                known = {field['id'] for field in self.service.tree_fields(identity)['fields']}
                splits = ','.join(grouping) if all(field in known for field in grouping) else 'date,cell,block'
                result, _, revision = state(identity)
                members = copy.deepcopy(result['epochs'])
                preview = {'predicate': predicate, 'splits': splits,
                    'membership': members, 'matched_count': len(members), 'total_source': len(self.service.rows),
                    'metadata_fingerprint_version': 2, 'source_revisions': result['source_revisions'],
                    'source_scope': self.service.source_scope(), 'tree': self.service.tree(identity, splits=splits)}
                empty_diff = {'added': [], 'removed': [], 'changed': []}
                fingerprints = {row['uuid']: row['metadata_hash'] for row in members}
                self.history.create_and_bind(preview, self.service.sources,
                    self.service.project_dir / 'catalog.json', actor,
                    protocol_uuid=identity, expected_version=0, expected_query_revision=revision,
                    current_query_revision=lambda key=identity: state(key)[2],
                    diff=empty_diff, previous_count=len(members),
                    diff_summary=summarize_diff(self.service.rows, fingerprints, fingerprints),
                    name=definition['name'], reason='pre_import_baseline_freeze')
                binding = self.history.protocol_binding(identity)
            baselines.append({'protocol_uuid': identity, 'protocol_name': workspace['definition']['name'],
                'binding_version': binding['version'], 'revision_uuid': binding['revision_uuid'],
                'recipe': copy.deepcopy(binding['recipe'])})
        return baselines

    def rerun(self, baselines, source_sha256, source_filename, actor):
        """Persist changed candidates independently; query failures are warnings.

        Caller holds project/database guards after a successful import/refresh.
        Transactionally pair each candidate with its suggestion and audit entry.
        A deterministic suggestion UUID deduplicates repeated job completion.
        """
        counts = {'created_count': 0, 'unchanged_count': 0, 'failed_count': 0, 'deduplicated_count': 0}
        warnings, created = [], []
        for baseline in baselines:
            identity = baseline['protocol_uuid']
            try:
                recipe = baseline['recipe']
                preview = self.service.explore_preview(recipe['predicate'], recipe['splits'])
                previous = {row['uuid']: row['metadata_hash'] for row in recipe['epochs']}
                proposed = {row['uuid']: row['metadata_hash'] for row in preview['membership']}
                diff = {'added': sorted(proposed.keys() - previous.keys()),
                        'removed': sorted(previous.keys() - proposed.keys()),
                        'changed': sorted(key for key in previous.keys() & proposed.keys() if previous[key] != proposed[key])}
                if not any(diff.values()):
                    counts['unchanged_count'] += 1
                    continue
                key = checksum({'source': source_sha256, 'protocol': identity,
                    'baseline': baseline['revision_uuid'], 'binding_version': baseline['binding_version'],
                    'predicate': recipe['predicate'], 'splits': recipe['splits'],
                    'source_scope_revision': preview['source_scope']['revision'], 'membership': proposed})
                suggestion_uuid = str(uuid.uuid5(uuid.UUID(self.project_uuid), key))
                table = self.Table  # Declare outside the data transaction (DDL commits).
                if (table & {'project_uuid': self.project_uuid, 'suggestion_uuid': suggestion_uuid}).to_dicts():
                    counts['deduplicated_count'] += 1
                    continue
                with self.service.dj.conn().transaction:
                    candidate = self.history.create(preview, self.service.sources,
                        self.service.project_dir / 'catalog.json', actor,
                        name=baseline['protocol_name'], parent_revision_uuid=baseline['revision_uuid'], _in_transaction=True)
                    timestamp = now()
                    summary = {'suggestion_uuid': suggestion_uuid, 'protocol_uuid': identity,
                        'protocol_name': baseline['protocol_name'], 'candidate_revision_uuid': candidate['revision_uuid'],
                        'baseline_revision_uuid': baseline['revision_uuid'], 'baseline_binding_version': baseline['binding_version'],
                        'source_sha256': source_sha256, 'source_filename': Path(source_filename).name,
                        'created_at': timestamp, 'source_scope_revision': preview['source_scope']['revision'],
                        'diff_counts': {name: len(values) for name, values in diff.items()},
                        'diff_summary': summarize_diff(self.service.rows, previous, proposed),
                        'previous_count': len(previous), 'next_count': len(proposed)}
                    occurred = dt.datetime.fromisoformat(timestamp).astimezone(dt.timezone.utc).replace(tzinfo=None)
                    table.insert1({'project_uuid': self.project_uuid, 'suggestion_uuid': suggestion_uuid,
                        'protocol_uuid': identity, 'created_at': occurred, 'summary': summary})
                    payload = build_audit_payload('protocol_update_suggested', actor,
                        {**summary, 'epoch_count': len(proposed), 'working_dataset_membership_changed': False},
                        operation_uuid=suggestion_uuid, actor_kind='system', context={'project_uuid': self.project_uuid})
                    self.history.Event.insert1({'event_uuid': suggestion_uuid, 'project_uuid': self.project_uuid,
                        'occurred_at': occurred, 'actor': actor, 'action': 'protocol_update_suggested', 'payload': payload})
                created.append(summary)
                counts['created_count'] += 1
            except Exception as error:
                counts['failed_count'] += 1
                warnings.append({'stage': 'protocol_query', 'protocol_uuid': identity, 'message': str(error)})
        return {'counts': counts, 'suggestions': created, 'warnings': warnings}

    def list(self):
        """Only persisted summaries and current binding/scope headers; no reruns."""
        rows = (self.Table & {'project_uuid': self.project_uuid}).proj('summary', 'created_at').fetch(
            as_dict=True, order_by='created_at DESC, suggestion_uuid DESC')
        latest = {}
        # SQL datetime may truncate subsecond precision; use the immutable
        # ISO timestamp inside each summary to select the actual latest run.
        for row in sorted(rows, key=lambda item: (item['summary']['created_at'], item['suggestion_uuid']), reverse=True):
            summary = row['summary']
            latest.setdefault(summary['protocol_uuid'], copy.deepcopy(summary))
        scope_revision = self.service.source_scope()['revision']
        for identity, item in latest.items():
            binding = self.history.protocol_binding(identity)
            if binding and binding['revision_uuid'] == item['candidate_revision_uuid']:
                status = 'applied'
            elif not binding or binding['version'] != item['baseline_binding_version'] or binding['revision_uuid'] != item['baseline_revision_uuid']:
                status = 'superseded'
            elif scope_revision != item['source_scope_revision']:
                status = 'stale'
            else:
                status = 'pending'
            item['status'] = status
        return {'suggestions': list(latest.values()),
                'counts': {status: sum(item['status'] == status for item in latest.values())
                           for status in ('pending', 'applied', 'superseded', 'stale')}}
