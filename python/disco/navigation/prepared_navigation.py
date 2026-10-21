"""Explicitly prepared native navigation, fenced by publication and saved bindings.

Ordinary reads never rebuild a missing projection. Unsupported/custom adapters
retain their canonical reader; supported scopes return an explicit preparation
state when their proof cannot be continued.
"""
from __future__ import annotations

import copy
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

from disco.navigation.publication_changes import PreparationRequired, capture_changes
from disco.workbench.recipes import checksum


@dataclass(frozen=True)
class PreparedScope:
    body: dict
    tree: object
    catalog: dict
    definitions: dict
    order: list
    witness: object
    binding: object
    watermark: object
    revision: str
    family_counts: tuple
    duration_error: str | None = None


class PreparedNavigation:
    """One project-owned collection of explicit prepared views.

    Metadata preparation is intentionally separate from GET/page latency. A
    direct sealed membership delta (including its undo) patches the persistent
    tree; exact duration folding runs on one worker and never holds the DB lock.
    """
    def __init__(self, pager, lock, *, byte_budget=768 * 1024 * 1024):
        self.pager, self.service, self.lock = pager, pager.service, lock
        self.byte_budget = byte_budget
        self.entries = {}
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='disco-tree-duration')
        self.closed = False
        self.jobs = {}

    def supported(self):
        from workspace_service import publication_serial
        from disco.metadata.disk_index import DiskMetadataIndex
        from disco.navigation.tree_pages import _structural_contract
        return (not self.closed and publication_serial(self.service) is not None
                and type(getattr(self.service, 'disk_index', None)) is DiskMetadataIndex
                and _structural_contract(self.service)
                and getattr(self.service, '_recovery_tracker', None) is not None)

    @staticmethod
    def scope(body):
        if not isinstance(body, dict):
            raise ValueError('Tree preparation requires a scope object')
        return {name: copy.deepcopy(body[name]) for name in ('protocol_uuid', 'predicate', 'filters', 'splits') if name in body}

    @staticmethod
    def key(body):
        return checksum({'protocol_uuid': body.get('protocol_uuid'),
            'predicate': body.get('predicate', {'all': []}), 'filters': body.get('filters', {}),
            'splits': body.get('splits', 'date,cell,block')})

    def witness(self, body):
        from workspace_service import publication_serial
        service = self.service
        service.disk_index._check()
        value = {'publication': publication_serial(service), 'index': service.disk_index.generation,
                 'source_scope': service.source_scope()['revision']}
        # Annotation-dependent filters have their own live authority. Their
        # invalidation requires explicit preparation, never a hidden scope scan.
        from disco.navigation.tag_predicates import referenced_fields
        from disco.navigation.tree import joint_components
        splits = body.get('splits', 'date,cell,block')
        if not isinstance(splits, str):
            raise ValueError('Tree split order must be text')
        fields = []
        for field in splits.replace('→', ',').split(','):
            field = field.strip()
            fields.extend(joint_components(field) if field.startswith('joint/') else [field])
        annotation_splits = [field for field in fields if field.startswith(('annotations/', 'curation/'))]
        if (annotation_splits or any(name in body.get('filters', {}) for name in ('tag', 'tagged', 'tag_predicate', 'metadata_predicate'))
                or referenced_fields(body.get('predicate', {'all': []}))):
            from disco.metadata.explore_queries import generation
            value['annotations'] = generation(service, {'protocol_uuid': body.get('protocol_uuid'),
                'filters': body.get('filters', {}), 'predicate': body.get('predicate', {'all': []}),
                'summary_fields': annotation_splits})
        return value

    def binding(self, body):
        protocol = body.get('protocol_uuid')
        provider = getattr(self.service, 'binding_header_provider', None)
        return copy.deepcopy(provider(protocol)) if protocol and provider else None

    def revision(self, body, witness, binding, legacy=None):
        if body.get('protocol_uuid') is None:
            return legacy
        return checksum({'version': 3, 'project_uuid': self.service.project['project_uuid'],
            'scope': self.key(body), 'publication': witness,
            'binding': {key: binding.get(key) for key in ('version', 'revision_uuid')} if binding else None})

    def prepare(self, body):
        from disco.navigation.prepared_tree import PreparedTree
        if not self.supported():
            return {'status': 'unsupported'}
        body = self.scope(body)
        started = time.monotonic()
        tracker = self.service._recovery_tracker
        before, binding, watermark = self.witness(body), self.binding(body), tracker.token()
        if watermark is None:
            raise PreparationRequired('Recovery authority is unavailable')
        rows, catalog, values, definitions, order, legacy = self.pager._build_scope(body)
        ranks = {row['epoch_uuid']: (row['date'], row['start_time'], row['epoch_uuid']) for row in rows}
        if not order:
            values = dict.fromkeys(ranks, {})
        tree = PreparedTree.build(rows, values, definitions, order, scope_keys=ranks)
        if (self.witness(body) != before or self.binding(body) != binding or tracker.token() != watermark):
            raise PreparationRequired('Tree authority changed during preparation')
        family_counts = [0, 0, 0]
        for row in rows:
            family_counts[self._family_slot(row)] += 1
        entry = PreparedScope(body, tree, catalog, definitions, order, before, binding, watermark,
                              self.revision(body, before, binding, legacy), tuple(family_counts))
        key = self.key(body)
        size = tree.estimated_bytes
        if size > self.byte_budget:
            raise PreparationRequired('Tree exceeds the prepared navigation memory budget')
        retained = sum(item.tree.estimated_bytes for name, item in self.entries.items() if name != key)
        while self.entries and (retained + size > self.byte_budget or len(self.entries) >= 32):
            oldest = next(iter(self.entries))
            old = self._discard(oldest)
            if oldest != key:
                retained -= old.tree.estimated_bytes
        self._discard(key)
        self.entries[key] = entry
        return {'status': 'ready', 'resource': 'tree', 'revision': entry.revision,
                'epochs': len(rows), 'estimated_bytes': size,
                'elapsed_ms': (time.monotonic() - started) * 1000}

    def _delta(self, entry, binding):
        """Ask the scientific owner for an already-verified bounded delta."""
        from disco.decisions.explorer import ExplorerHistory
        owner = getattr(getattr(self.service, 'binding_header_provider', None), '__self__', None)
        if type(owner) is not ExplorerHistory or not entry.binding or not binding:
            raise PreparationRequired('A new dataset requires explicit tree preparation')
        previous, current = entry.binding['revision_uuid'], binding['revision_uuid']
        if previous == current:
            return {}, []
        delta = owner.prepared_delta(previous, current, limit=20000)
        if delta is None:
            raise PreparationRequired('Dataset proof requires explicit tree preparation')
        return delta['added'], delta['removed']

    @staticmethod
    def _family_slot(row):
        name = str(row.get('protocol_name', '')).rsplit('.', 1)[-1]
        return {'VariableHistoryNoiseCurInject': 0, 'VariableMeanNoiseCurInject': 1}.get(name, 2)

    @staticmethod
    def _family(counts):
        total = sum(counts)
        return ('history-noise' if counts[0] == total else 'mean-noise' if counts[1] == total else None) if total else None

    def verify(self, entry):
        """Closing fence for every prepared page, anchor and selection response."""
        if (not self.supported() or self.witness(entry.body) != entry.witness
                or self.binding(entry.body) != entry.binding
                or self.service._recovery_tracker.token() != entry.watermark):
            raise PreparationRequired('Tree authority changed while reading; retry this view')

    def _discard(self, key):
        entry = self.entries.pop(key, None)
        job = self.jobs.get(key)
        if job is not None:
            job.cancel()
        return entry

    def read(self, body):
        if not self.supported():
            return None
        scope = self.scope(body)
        key = self.key(scope)
        entry = self.entries.get(key)
        if entry is None:
            raise PreparationRequired('This layout requires preparation')
        if self.witness(scope) != entry.witness:
            raise PreparationRequired('Tree publication changed')
        tracker = self.service._recovery_tracker
        current = tracker.token()
        if current is None:
            raise PreparationRequired('Recovery authority is unavailable')
        binding = self.binding(scope)
        if current != entry.watermark or binding != entry.binding:
            def read_changes(plan):
                keys = getattr(plan, 'keys', {})
                if any(keys.get(name) for name in ('source', 'protocol_workspace', 'data_store_state')):
                    raise PreparationRequired('Saved source or protocol publication changed')
                latest = self.binding(scope)
                if latest == entry.binding:
                    return latest, {}, []
                if scope.get('filters') or scope.get('predicate', {'all': []}) != {'all': []}:
                    raise PreparationRequired('Filtered dataset membership requires preparation')
                added, removed = self._delta(entry, latest)
                if len(added) + len(removed) > 20000:
                    raise PreparationRequired('Dataset change exceeds bounded navigation catch-up')
                for identity, fingerprint in added.items():
                    if self.service._fingerprints.get(identity) != fingerprint:
                        raise PreparationRequired('New member metadata no longer matches its sealed revision')
                return latest, added, removed
            watermark, (binding, added, removed) = capture_changes(tracker, entry.watermark, read_changes)
            if self.witness(scope) != entry.witness:
                raise PreparationRequired('Tree publication changed during catch-up')
            tree = entry.tree
            family_counts = list(entry.family_counts)
            for identity in added:
                family_counts[self._family_slot(self.service.rows[identity])] += 1
            for identity in removed:
                family_counts[self._family_slot(self.service.rows[identity])] -= 1
            if added or removed:
                rows = [self.service.rows[identity] for identity in added]
                columns = set()
                for field in entry.order:
                    columns.update(entry.definitions[field].get('components') or [field])
                values = self.service.disk_index.values(ids=list(added), fields=sorted(columns)) if added else {}
                tree = tree.apply(additions=rows, removals=removed, values=values,
                    scope_keys={row['epoch_uuid']: (row['date'], row['start_time'], row['epoch_uuid']) for row in rows})
                retained = sum(item.tree.estimated_bytes for name, item in self.entries.items() if name != key)
                if retained + tree.estimated_bytes > self.byte_budget:
                    raise PreparationRequired('Changed tree exceeds the prepared navigation memory budget')
            updated = replace(entry, tree=tree, binding=binding, watermark=watermark,
                family_counts=tuple(family_counts), catalog={**entry.catalog, 'protocol_family': self._family(family_counts)},
                duration_error=None if added or removed else entry.duration_error,
                revision=self.revision(scope, entry.witness, binding, entry.revision))
            self.entries[key] = entry = updated
            if added or removed:
                self._finish_durations(key, entry)
        return entry

    def _finish_durations(self, key, entry):
        if self.closed:
            return
        # At most one queued replacement per retained view (32 views maximum).
        # Edits do not accumulate obsolete chains of persistent snapshots.
        previous = self.jobs.get(key)
        if previous is not None:
            previous.cancel()
        future = self.worker.submit(entry.tree.finish_durations)
        self.jobs[key] = future
        def completed(job):
            try:
                if job.cancelled():
                    return
                tree = job.result()
                if self.closed:
                    return
                with self.lock:
                    current = self.entries.get(key)
                    if (not self.closed and current is not None and current.tree is entry.tree
                            and current.witness == entry.witness):
                        self.entries[key] = replace(current, tree=tree, duration_error=None)
            except Exception:
                if not self.closed:
                    with self.lock:
                        current = self.entries.get(key)
                        if current is not None and current.tree is entry.tree:
                            self.entries[key] = replace(current, duration_error='Exact duration calculation failed. Prepare this view again.')
            finally:
                with self.lock:
                    if self.jobs.get(key) is job:
                        self.jobs.pop(key, None)
        future.add_done_callback(completed)

    def reset(self):
        for key in tuple(self.entries):
            self._discard(key)

    def close(self):
        self.closed = True
        self.worker.shutdown(wait=True, cancel_futures=True)
        self.entries.clear()
