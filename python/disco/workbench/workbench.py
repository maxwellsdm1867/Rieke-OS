"""Native, frozen incoming review and additive publication (contract v1).

Proposal B, candidate C, current main M and actor draft remain separate.
No method here runs C's predicate to reconstruct its saved membership.
Callers hold DB, registration and annotation guards for the whole operation.
"""
from __future__ import annotations

import base64
import contextlib
import contextvars
import copy
import datetime as dt
import json
import time
import uuid

from workspace_audit import build_audit_payload
from disco.decisions.curation import RevisionConflict
from disco.workbench.diff import summarize_diff
from disco.workbench.recipes import checksum
from workspace_protocol_identity import require_protocol_compatibility
from disco.operation_timing import elapsed
from workspace_service import WorkspaceService, _FrozenProtocolBinding


_PROTOCOL_SUMMARY = WorkspaceService.protocol
_CELL_SUMMARY = WorkspaceService._cell_summary


class _FrozenReadProjections:
    """One retained frozen input; fresh adapters still own live read policy.

    Immutable candidate/base/main inputs determine pending membership. A selected
    view adds its exact UUID set. Drafts and annotations stay on fresh adapters:
    this retains computation, never a context or authority receipt.
    """
    def __init__(self):
        self.entry = None

    def bind(self, service, context):
        from disco.metadata.disk_index import DiskMetadataIndex
        from disco.navigation.tree_pages import _structural_contract
        index = getattr(service, 'disk_index', None)
        key = None
        dependencies = ('project_uuid', 'protocol_uuid', 'candidate_revision_uuid', 'candidate_recipe_sha256',
                        'baseline_revision_uuid', 'baseline_recipe_sha256', 'main_revision_uuid',
                        'main_recipe_sha256', 'expected_binding_version', 'expected_query_revision')
        if (isinstance(index, DiskMetadataIndex) and _structural_contract(service)
                and all(field in context for field in dependencies)):
            service._ready()
            index._check()
            view = checksum(sorted(context['_view_ids'])) if '_view_ids' in context else None
            witness = {field: context[field] for field in dependencies if field != 'expected_query_revision'}
            # An unbound main is not an immutable recipe. Keep its live query
            # proof; bound-main draft/annotation changes do not alter membership.
            if context['main_revision_uuid'] is None:
                witness['unbound_query_revision'] = context['expected_query_revision']
            projection_revision = checksum(dict(witness, metadata_generation=index.generation, selected_view=view))
            key = (id(index), id(service.rows), id(service.details),
                   id(service.cells), id(service.protocols), id(service._fingerprints),
                   projection_revision)
            if self.entry is not None and self.entry[0] == key:
                return self.entry[1]
        # Release the previous candidate, including its bounded navigation
        # caches, rather than multiplying cache budgets across actors/views.
        self.entry = None
        recipe = copy.copy(context['candidate'])
        recipe['epochs'] = [dict(uuid=identity, metadata_hash=fingerprint)
            for identity, fingerprint in context['pending'].items()
            if '_view_ids' not in context or identity in context['_view_ids']]
        binding = dict(version=1, revision_uuid=recipe['revision_uuid'], recipe=recipe)
        provider = _FrozenProtocolBinding(context['protocol_uuid'], binding, service.binding,
            read_scope_revision=projection_revision if key is not None else None)
        if key is not None:
            self.entry = key, provider
        return provider


class WorkbenchConflict(ValueError):
    pass


def workbench_tables(dj):
    schema = dj.Schema('recording_workspace')

    @schema
    class WorkbenchDraft(dj.Manual):
        definition = """
        project_uuid: varchar(36)
        protocol_uuid: varchar(36)
        candidate_revision_uuid: varchar(36)
        actor: varchar(255)
        ---
        version: int unsigned
        selection_mode: varchar(16)
        deferred: bool
        """

    @schema
    class WorkbenchDecision(dj.Manual):
        definition = """
        -> WorkbenchDraft
        epoch_uuid: varchar(36)
        ---
        metadata_hash: char(64)
        selected: bool
        reviewed: bool
        excluded: bool
        """

    @schema
    class WorkbenchReceipt(dj.Manual):
        definition = """
        project_uuid: varchar(36)
        operation_uuid: varchar(36)
        ---
        protocol_uuid: varchar(36)
        candidate_revision_uuid: varchar(36)
        actor: varchar(255)
        request_sha256: char(64)
        receipt: json
        """
    return WorkbenchDraft, WorkbenchDecision, WorkbenchReceipt


_recipe_reads = contextvars.ContextVar('workbench_recipe_reads', default=None)
# A per-proposal loop (queue, cumulative snapshot) reads each protocol's
# revision once instead of once per proposal. Opening/closing read checks and
# publication guards stay outside the loop and read fresh; binding writes clear it.
_revision_memo = contextvars.ContextVar('workbench_revision_memo', default=None)


class _RecipeReads:
    """Privately owned recipes for one context derivation, never a read receipt."""
    def __init__(self, history):
        from disco.decisions.explorer import is_canonical_binding_reader
        self.history = history
        self.canonical = is_canonical_binding_reader(history.protocol_binding)
        self.records, self.members = {}, {}

    def get(self, revision):
        if not self.canonical:
            return self.history.get(revision)
        revision = str(uuid.UUID(revision))
        if revision not in self.records:
            self.records[revision] = self.history.get(revision)
        return self.records[revision]


def _members(recipe):
    reads = _recipe_reads.get()
    key = id(recipe)
    if reads is not None and reads.canonical and key in reads.members:
        saved_recipe, members = reads.members[key]
        if saved_recipe is recipe:
            return members
    members = {row['uuid']: row['metadata_hash'] for row in recipe['epochs']}
    if len(members) != len(recipe['epochs']):
        raise ValueError('Frozen membership contains duplicate epoch identities')
    if reads is not None and reads.canonical:
        reads.members[key] = (recipe, members)
    return members


class ProtocolWorkbench:
    def __init__(self, service, history, suggestions, state, revision_guard, *, tables=None, read_revision=None):
        self.service, self.history, self.suggestions = service, history, suggestions
        self.state, self.revision_guard = state, revision_guard
        self.read_revision = read_revision
        self._read_revision_state = state
        self.project = service.project['project_uuid']
        self._tables = tables
        self.selection_manifests = {}
        self._read_projections = _FrozenReadProjections()
        self._pool_cache = {}

    @property
    def tables(self):
        if self._tables is None:
            self._tables = workbench_tables(self.service.dj)  # DDL outside data transactions.
        return self._tables

    def key(self, protocol, revision, actor):
        if not isinstance(actor, str) or not actor or len(actor) > 255:
            raise ValueError('Expected a resolved server actor/profile')
        protocol, revision = str(uuid.UUID(protocol)), str(uuid.UUID(revision))
        if protocol not in self.service.protocols:
            raise KeyError('Protocol not found in this project')
        return dict(project_uuid=self.project, protocol_uuid=protocol,
                    candidate_revision_uuid=revision, actor=actor)

    @contextlib.contextmanager
    def _context_reads(self):
        # Dependency discovery runs before this scope. Closing context always
        # creates its own scope, including nested/reentrant reads and failures.
        token = _recipe_reads.set(_RecipeReads(self.history))
        try:
            yield
        finally:
            _recipe_reads.reset(token)

    def _recipe(self, revision):
        reads = _recipe_reads.get()
        return (reads.get(revision) if reads is not None and reads.history is self.history
                else self.history.get(revision))['recipe']

    def proposal(self, protocol, revision):
        rows = (self.suggestions.Table & dict(project_uuid=self.project,
            protocol_uuid=protocol)).to_dicts()
        found = [row['summary'] for row in rows if row['summary']['candidate_revision_uuid'] == revision]
        if not found:
            raise KeyError('Incoming candidate not found for this protocol in this project')
        candidate = self._recipe(revision)
        baseline = self._recipe(found[0]['baseline_revision_uuid'])
        if candidate.get('parent_revision_uuid') != baseline['revision_uuid']:
            raise ValueError('Incoming candidate baseline does not match its sealed parent')
        return found[0], baseline, candidate

    def draft(self, key):
        headers = (self.tables[0] & key).to_dicts()
        header = headers[0] if headers else dict(**key, version=0, selection_mode='selected', deferred=False)
        decisions = {row['epoch_uuid']: row for row in (self.tables[1] & key).to_dicts()}
        return header, decisions

    def original_records(self, protocol):
        return [row for row in (self.suggestions.Table & dict(project_uuid=self.project, protocol_uuid=protocol)).to_dicts()
                if row['summary'].get('kind') != 'workbench_pending_union']

    def origin_recipes(self, protocol, candidate):
        origins = []
        for witness in candidate.get('pending_union_provenance', {}).get('origins', []):
            summary, baseline, recipe = self.proposal(protocol, witness['candidate_revision_uuid'])
            if (summary.get('kind') == 'workbench_pending_union' or recipe['content_sha256'] != witness['recipe_sha256']):
                raise WorkbenchConflict('Cumulative candidate origin authority changed')
            origins.append((summary, baseline, recipe))
        return origins

    def cumulative_draft(self, protocol, actor):
        records = (self.suggestions.Table & dict(project_uuid=self.project, protocol_uuid=protocol)).to_dicts()
        records.sort(key=lambda row: (row['summary']['created_at'], row['suggestion_uuid']), reverse=True)
        for row in records:
            if row['summary'].get('kind') == 'workbench_pending_union':
                key = self.key(protocol, row['summary']['candidate_revision_uuid'], actor)
                if (self.tables[0] & key).to_dicts():
                    return self.draft(key)
        return None

    def review_decisions(self, protocol, actor):
        """The actor's latest review decisions: the combined review draft, or
        before one exists, their individual proposal drafts (left out wins)."""
        cumulative = self.cumulative_draft(protocol, actor)
        if cumulative:
            return cumulative
        merged, deferred = {}, False
        for row in self.original_records(protocol):
            key = self.key(protocol, row['summary']['candidate_revision_uuid'], actor)
            if not (self.tables[0] & key).to_dicts():
                continue
            header, decisions = self.draft(key)
            deferred |= bool(header['deferred'])
            for identity, decision in decisions.items():
                earlier = merged.get(identity)
                if earlier and earlier['metadata_hash'] == decision['metadata_hash']:
                    excluded = bool(earlier['excluded'] or decision['excluded'])
                    decision = dict(decision, excluded=excluded,
                        selected=False if excluded else bool(earlier['selected'] and decision['selected']),
                        reviewed=bool(earlier['reviewed'] and decision['reviewed']))
                merged[identity] = decision
        return dict(deferred=deferred), merged

    def _additive_lineage(self, main, baseline, protocol, version, baseline_version):
        """A superset alone is insufficient: prove every actual parent transition."""
        seen = set()
        transitions = (self.tables[2] & dict(project_uuid=self.project, protocol_uuid=protocol)).to_dicts()
        # An undo rebinds main to the exact revision it had before a merge.
        # Rewind across it to that revision's original binding version.
        undos = {row['receipt']['binding']['version']: row['receipt'] for row in transitions
                 if row['receipt'].get('kind') == 'workbench_undo'}
        def rewind(main, version):
            for _ in range(1000):
                undo = undos.get(version)
                if not undo or undo['binding']['revision_uuid'] != main['revision_uuid']:
                    break
                version = undo['restored_binding_version']
            return version
        while True:
            if main['revision_uuid'] == baseline['revision_uuid'] and version == baseline_version:
                break
            version = rewind(main, version)
            if main['revision_uuid'] == baseline['revision_uuid']:
                break
            identity = main['revision_uuid']
            if identity in seen or len(seen) >= 1000 or main.get('membership_kind') != 'additive_union':
                return False
            seen.add(identity)
            parent = main.get('parent_revision_uuid')
            publication = main.get('additive_publication', {})
            if not parent or publication.get('previous_revision_uuid') != parent:
                return False
            previous = self._recipe(parent)
            matches = [row['receipt'] for row in transitions if row['receipt'].get('binding', {}).get('revision_uuid') == identity
                       and row['receipt']['binding'].get('version') == version
                       and row['receipt'].get('expected_binding_version') == version - 1
                       and row['receipt'].get('resulting_recipe_sha256') == main['content_sha256']
                       and row['receipt'].get('accepted_epoch_count', 0) > 0]
            if len(matches) != 1 or version <= baseline_version:
                return False
            old, current = _members(previous), _members(main)
            if any(current.get(key) != value for key, value in old.items()):
                return False
            main = previous
            version -= 1
        return main['content_sha256'] == baseline['content_sha256'] and version == baseline_version

    def transaction_authority(self, protocol):
        """Capture native receipts before SQL, then attest them under its locks.

        Native token() intentionally refuses an active transaction. Frozen
        publication checks must validate its captured receipts with the locked
        authority, rather than substituting a legacy revision or missing token.
        """
        query_guard = self.revision_guard(protocol)
        tracker = getattr(self.service, '_explore_state_generation', None)
        tokens = {}
        read_context = dict(predicate={'all': []}, protocol_uuid=protocol, filters={})
        read_witness = None
        if tracker is not None:
            from disco.metadata.explore_queries import generation as read_generation
            # Establish the service's publication identity before creating any
            # shallow read adapter, and capture the complete outside-SQL proof.
            read_witness = read_generation(self.service, read_context)
            from disco.navigation.tag_predicates import referenced_fields
            predicates = [self.history.get(row['summary']['candidate_revision_uuid'])['recipe']['predicate']
                for row in self.original_records(protocol)]
            binding = self.history.protocol_binding(protocol)
            if binding:
                predicates.append(binding['recipe']['predicate'])
            fields = set().union(*(referenced_fields(predicate) for predicate in predicates))
            protocols = {protocol} | {field.split('/')[1] for field in fields if field.startswith('curation/')}
            for origin in [None, *sorted(protocols)]:
                token = tracker.token(origin)
                if token is None:
                    raise WorkbenchConflict('Native annotation authority is unavailable before publication')
                tokens[origin] = token
        def guard():
            for token in tokens.values():
                tracker.assert_current_locked(token)
            return query_guard()
        def generation(context):
            from disco.metadata.explore_queries import generation as read_generation
            if tracker is None:
                return read_generation(self.service, context)
            guard()
            class LockedReceipts:
                def token(self, origin=None):
                    if origin not in tokens:
                        raise WorkbenchConflict('Uncaptured annotation authority requested during publication')
                    return tokens[origin]
            scoped = copy.copy(self.service)
            scoped._explore_state_generation = LockedReceipts()
            # Only the service-local adapter uses captured, locked-attested
            # tokens. The native tracker and its transaction refusal stay intact.
            current = read_generation(scoped, context)
            if context != read_context or current != read_witness:
                raise WorkbenchConflict('Frozen read authority changed during publication')
            return current
        return guard, generation

    def context(self, protocol, revision, actor, *, query_revision_guard=None):
        with elapsed("disco.workbench.workbench", "context"), self._context_reads():
            key = self.key(protocol, revision, actor)
            summary, baseline, candidate = self.proposal(protocol, revision)
            header, decisions = self.draft(key)
            reads = _recipe_reads.get()
            # Canonical contexts freshly verify main below. Avoid constructing
            # the detached cached recipe that would immediately be discarded.
            binding = (self.history.protocol_binding_header(protocol) if reads.canonical
                       else self.history.protocol_binding(protocol))
            if query_revision_guard is None:
                # A bound main owns its saved membership below. A fresh native
                # revision proof can avoid materializing unused curation rows;
                # unsupported/custom/unbound readers keep the full-state oracle.
                memo = _revision_memo.get()
                fresh = (binding and reads.canonical and self.read_revision is not None
                         and self.state is self._read_revision_state)
                if fresh and memo is not None and protocol in memo:
                    query_revision = memo[protocol]
                else:
                    query_revision = self.read_revision(protocol) if fresh else None
                    if fresh and memo is not None and query_revision is not None:
                        memo[protocol] = query_revision
                if query_revision is None:
                    result, _, query_revision = self.state(protocol)
                else:
                    result = None
            else:
                query_revision = query_revision_guard()
                result = self.service.query_result(protocol) if binding is None else None
            main = None
            if binding:
                # A binding's UUID cache is not fresh recipe storage authority.
                main = self._recipe(binding['revision_uuid']) if reads.canonical else binding['recipe']
            previous = _members(main) if main else _members(result)
            base, proposed = _members(baseline), _members(candidate)
            incoming = {key: value for key, value in proposed.items() if key not in base}
            base_conflicts = {key for key in base.keys() & proposed.keys() if base[key] != proposed[key]}
            main_conflicts = {key for key, value in previous.items() if self.service._fingerprints.get(key) != value}
            conflicts = base_conflicts | main_conflicts | {key for key in incoming.keys() & previous.keys() if incoming[key] != previous[key]}
            # Frozen browse refuses changed/missing rows; it cannot claim current values are old metadata.
            unavailable = {key for key, value in proposed.items() if self.service._fingerprints.get(key) != value}
            scope = self.service.source_scope()
            active = set(scope['active_source_revisions'])
            ineligible = {key for key in incoming if key in self.service.rows
                          and self.service.rows[key]['source_sha256'] not in active}
            ineligible_main = {key for key in previous if key in self.service.rows
                               and self.service.rows[key]['source_sha256'] not in active}
            from disco.navigation.tag_predicates import TagPredicates, referenced_fields
            fields = referenced_fields(candidate['predicate'])
            annotation = TagPredicates(self.service).snapshot(fields)[1] if fields else None
            annotation_changed = (candidate.get('annotation_scope', {}).get('revision') !=
                                  (annotation or {}).get('revision'))
            origin_witnesses, origins_valid = [], True
            for summary_origin, baseline_origin, origin in self.origin_recipes(protocol, candidate):
                origin_fields = referenced_fields(origin['predicate'])
                witness = TagPredicates(self.service).snapshot(origin_fields)[1] if origin_fields else None
                annotation_changed |= origin.get('annotation_scope', {}).get('revision') != (witness or {}).get('revision')
                origins_valid &= bool(main and self._additive_lineage(main, baseline_origin, protocol,
                    binding['version'], summary_origin['baseline_binding_version']))
                origin_witnesses.append(dict(candidate_revision_uuid=origin['revision_uuid'], recipe_sha256=origin['content_sha256'],
                    annotation_scope_revision=(witness or {}).get('revision')))
            shared = getattr(self.service, 'shared_annotations', None)
            shared_snapshot = shared.snapshot() if shared else None
            shared_revision = shared_snapshot['revision'] if shared_snapshot else None
            valid_base = bool(main and self._additive_lineage(main, baseline, protocol,
                binding['version'], summary['baseline_binding_version'])) and origins_valid
            pending = {key: value for key, value in incoming.items() if key not in previous}
            evidence = dict(contract_version=1, project_uuid=self.project, protocol_uuid=protocol,
                actor=actor, candidate_revision_uuid=revision, candidate_recipe_sha256=candidate['content_sha256'],
                baseline_revision_uuid=baseline['revision_uuid'], baseline_recipe_sha256=baseline['content_sha256'],
                main_revision_uuid=main['revision_uuid'] if main else None,
                main_recipe_sha256=main['content_sha256'] if main else None,
                expected_binding_version=binding['version'] if binding else 0,
                expected_query_revision=query_revision, source_scope_revision=scope['revision'],
                shared_annotations_revision=shared_revision, annotation_scope_revision=(annotation or {}).get('revision'),
                origin_witnesses=origin_witnesses,
                draft_version=header['version'], decisions_sha256=checksum(decisions),
                selection_mode=header['selection_mode'], deferred=bool(header['deferred']),
                incoming_sha256=checksum(incoming), current_fingerprints_sha256=checksum(
                    {key: self.service._fingerprints.get(key) for key in proposed.keys() | previous.keys()}))
            evidence['candidate_scope_revision'] = checksum(evidence)
            return dict(**evidence, _shared_annotation_snapshot=shared_snapshot,
                summary=summary, baseline=baseline, candidate=candidate, main=main,
                previous=previous, incoming=incoming, pending=pending, decisions=decisions,
                conflicts=conflicts, base_conflicts=base_conflicts, main_conflicts=main_conflicts,
                unavailable=unavailable, ineligible=ineligible,
                blocked_main=ineligible_main, annotation_changed=annotation_changed, valid_base=valid_base,
                source_scope=scope, already_present=set(incoming) & set(previous))

    @staticmethod
    def superseded(context):
        """An original proposal frozen against a main that a later save replaced.

        Its diff describes the replaced main and query, so it is neither a
        conflict nor publishable. A replacement main is the current query's full
        result, so leftover additions no longer match it; later imports diff
        against the replacement.
        """
        summary = context['summary']
        return (summary.get('kind') != 'workbench_pending_union' and context['main'] is not None
                and not context['valid_base']
                and context['expected_binding_version'] > summary['baseline_binding_version'])

    def seen_sources(self, main):
        """Recordings main was defined against: those present when its query was
        last saved, its pinned set created or its baseline frozen. Merges do not
        change it, so an unmerged rest of a new recording stays new."""
        seen = 0
        while main.get('membership_kind') == 'additive_union' and seen < 10000:
            main = self._recipe(main['additive_publication']['previous_revision_uuid'])
            seen += 1
        return frozenset(main.get('source_revisions', ()))

    def pending_pool(self, protocol):
        """New data for main: epochs from recordings main has not seen that its
        saved query matches and a merge accepts.

        Epochs from recordings main already saw were reviewed when main was
        defined, so leaving them out of main is never re-offered. Imports,
        query or pinned updates, merges, undo and metadata refreshes change the
        inputs, and only then is the pool recomputed.
        """
        from disco.navigation.tag_predicates import TagPredicates, referenced_fields
        from workspace_protocol_identity import protocol_ids, protocol_key
        binding = self.history.protocol_binding_header(protocol)
        if not binding:
            return dict(pool={}, main=None, binding=None, reason=None, annotation=None, scope=None, key=None)
        scope = self.service.source_scope()
        main = self._recipe(binding['revision_uuid'])
        fields = referenced_fields(main['predicate'])
        annotation = TagPredicates(self.service).snapshot(fields)[1] if fields else None
        fingerprints = self.service._fingerprints
        key = checksum(dict(binding=[binding['revision_uuid'], binding['version']], scope=scope['revision'],
            annotation=(annotation or {}).get('revision'), fingerprints=fingerprints,
            definition=self.service.protocols[protocol]['definition'].get('query')))
        cached = self._pool_cache.get(protocol)
        if cached and cached['key'] == key:
            return cached
        members = _members(main)
        active = set(scope['active_source_revisions'])
        reason, pool = None, {}
        if any(fingerprints.get(identity) != value for identity, value in members.items()):
            reason = 'Main contains epochs whose recorded metadata changed; save the query again to update main.'
        elif any(self.service.rows[identity]['source_sha256'] not in active for identity in members):
            reason = 'Main contains epochs from a recording that is excluded from queries; include it again in Data stores.'
        else:
            allowed = protocol_ids(self.service, protocol)
            seen = self.seen_sources(main)
            for identity in self.service.match_predicate(main['predicate'])[1]:
                row = self.service.rows[identity]
                if (identity not in members and row['source_sha256'] in active and row['source_sha256'] not in seen
                        and protocol_key(row.get('protocol_name')) in allowed):
                    pool[identity] = fingerprints[identity]
        value = dict(pool=pool, main=main, binding=binding, reason=reason, annotation=annotation, scope=scope, key=key)
        self._pool_cache[protocol] = value
        return value

    @staticmethod
    @contextlib.contextmanager
    def revision_memo():
        token = _revision_memo.set(_revision_memo.get() if _revision_memo.get() is not None else {})
        try:
            yield
        finally:
            _revision_memo.reset(token)

    @staticmethod
    def main_blocked(context):
        """Main itself cannot take additions: its saved epochs' metadata changed or
        one of its recordings is excluded. Applies to every proposal alike."""
        if context['main_conflicts']:
            return 'Main contains epochs whose recorded metadata changed; save the query again to update main.'
        if context['blocked_main']:
            return 'Main contains epochs from a recording that is excluded from queries; include it again in Data stores.'
        return None

    def mergeable(self, context):
        """The pending epochs this proposal can actually add to main right now.

        A proposal that cannot publish contributes nothing, so pending never
        lists an epoch that a merge would refuse.
        """
        if (self.superseded(context) or not context['valid_base'] or context['annotation_changed']
                or self.main_blocked(context)):
            return set()
        # A merge refuses epochs recorded under a protocol ID the entry does not
        # list (pinned entries list every ID they span), so they are not pending.
        from workspace_protocol_identity import protocol_ids, protocol_key
        allowed = protocol_ids(self.service, context['protocol_uuid'])
        return {key for key in context['pending']
                if key not in context['ineligible'] and key not in context['unavailable']
                and protocol_key(self.service.rows.get(key, {}).get('protocol_name')) in allowed}

    @staticmethod
    def check_scope(context, expected):
        if not isinstance(expected, str) or expected != context['candidate_scope_revision']:
            raise WorkbenchConflict('Candidate, main, sources, annotations or draft changed; reload the frozen context')

    @staticmethod
    def publishable(context, selected):
        # base_conflicts describe main epochs inside the proposal's own frozen
        # snapshot; additions carry the current main forward unchanged.
        if context['main_conflicts'] or selected & (context['unavailable'] | context['conflicts']):
            raise WorkbenchConflict('Frozen epoch fingerprints changed or are unavailable; explicit reconciliation required')
        if selected & context['ineligible'] or context['blocked_main']:
            raise WorkbenchConflict('Source eligibility blocks publication; reconcile excluded sources explicitly')
        if context['annotation_changed']:
            raise WorkbenchConflict('Candidate predicate annotations changed; save and review a fresh proposal')
        if ProtocolWorkbench.superseded(context):
            raise WorkbenchConflict('A newer saved query replaced the main dataset this proposal was made from; '
                                    'its remaining epochs do not match the current query')
        if not context['valid_base']:
            raise WorkbenchConflict('Candidate has an unrelated or replacement base; review a fresh proposal')

    def decision(self, context, identity):
        saved = context['decisions'].get(identity, {})
        valid = (saved.get('metadata_hash') == context['incoming'][identity]
                 and identity not in context['unavailable'])
        excluded = bool(saved.get('excluded')) if valid else False
        return dict(selected=(context['selection_mode'] == 'all' or (valid and bool(saved.get('selected')))) and not excluded,
                    reviewed=bool(saved.get('reviewed')) if valid else False, excluded=excluded)

    def selection(self, context, mode, source_sha256=None):
        if mode == 'source':
            if not isinstance(source_sha256, str) or not source_sha256:
                raise ValueError('Source merge requires an exact recording identity')
            scoped = {key for key in context['pending']
                      if self.service.rows.get(key, {}).get('source_sha256') == source_sha256}
            if not scoped:
                raise WorkbenchConflict('This recording has no pending additions in the frozen candidate')
            return {key for key in scoped if key not in context['ineligible'] | context['unavailable']
                    and not self.decision(context, key)['excluded']}
        if source_sha256 is not None:
            raise ValueError('Recording identity is only valid for source merge mode')
        if mode not in ('all', 'selected') or mode != context['selection_mode']:
            raise ValueError('Preview mode must agree with the saved draft selection_mode')
        if mode == 'all':
            selected = {key for key in context['pending'] if key not in context['ineligible'] | context['unavailable']
                        and not self.decision(context, key)['excluded']}
        else:
            # Preserve exact saved intent. Explicitly selected blocked epochs
            # must reject publication, never disappear from a selected preview.
            selected = {key for key in context['pending'] if context['decisions'].get(key, {}).get('selected')
                        and context['decisions'][key].get('reviewed') and not context['decisions'][key].get('excluded')}
        return selected

    def patch(self, protocol, revision, actor, body):
        context = self.context(protocol, revision, actor)
        self.check_scope(context, body['expected_candidate_scope_revision'])
        if type(body['expected_version']) is not int or body['expected_version'] != context['draft_version']:
            raise WorkbenchConflict('Review draft version changed')
        items = body.get('decisions', [])
        if not isinstance(items, list) or len(items) > 250:
            raise ValueError('A draft patch accepts at most 250 decisions')
        parsed, seen = [], set()
        for item in items:
            if not isinstance(item, dict) or set(item) - {'epoch_uuid', 'selected', 'reviewed', 'excluded'} or 'epoch_uuid' not in item:
                raise ValueError('Malformed review decision')
            identity = str(uuid.UUID(item['epoch_uuid']))
            if identity in seen or identity not in context['pending'] or identity in context['unavailable']:
                raise ValueError('Duplicate, changed or out-of-candidate review epoch')
            if not set(item) & {'selected', 'reviewed', 'excluded'} or any(type(value) is not bool for field, value in item.items() if field != 'epoch_uuid'):
                raise ValueError('Review decisions must be boolean')
            seen.add(identity)
            old = self.decision(context, identity)
            changed = {**old, **{field: value for field, value in item.items() if field != 'epoch_uuid'}}
            if changed['excluded']:
                changed['selected'] = False  # Exclusion wins, never removes current main.
            parsed.append(dict(epoch_uuid=identity, metadata_hash=context['incoming'][identity], **changed))
        mode = body.get('selection_mode', context['selection_mode'])
        if mode not in ('selected', 'all') or ('deferred' in body and type(body['deferred']) is not bool):
            raise ValueError('Invalid selection mode or deferred flag')
        key = self.key(protocol, revision, actor)
        # Caller holds the same cross-process protocol lock as binding/curation.
        with self.service.dj.conn().transaction:
            current, _ = self.draft(key)
            if current['version'] != context['draft_version']:
                raise WorkbenchConflict('Review draft version changed')
            row = dict(**key, version=context['draft_version'] + 1, selection_mode=mode,
                       deferred=body.get('deferred', context['deferred']))
            (self.tables[0].update1 if context['draft_version'] else self.tables[0].insert1)(row)
            for item in parsed:
                row = dict(**key, **item)
                (self.tables[1].update1 if item['epoch_uuid'] in context['decisions'] else self.tables[1].insert1)(row)
        return self.context(protocol, revision, actor)

    def finish(self, context, body):
        """Finish a cumulative review: leave out every epoch still pending.

        Left-out epochs keep their exclusion across later preparations until
        the user re-allows them; main is unchanged.
        """
        if context['summary'].get('kind') != 'workbench_pending_union':
            raise ValueError('Finish review applies to the combined incoming review')
        self.check_scope(context, body['expected_candidate_scope_revision'])
        if type(body['expected_version']) is not int or body['expected_version'] != context['draft_version']:
            raise WorkbenchConflict('Review draft version changed')
        key = self.key(context['protocol_uuid'], context['candidate_revision_uuid'], context['actor'])
        remaining = sorted(identity for identity in context['pending'] if not self.decision(context, identity)['excluded'])
        with self.service.dj.conn().transaction:
            current, _ = self.draft(key)
            if current['version'] != context['draft_version']:
                raise WorkbenchConflict('Review draft version changed')
            draft = dict(**key, version=context['draft_version'] + 1, selection_mode='selected', deferred=context['deferred'])
            (self.tables[0].update1 if context['draft_version'] else self.tables[0].insert1)(draft)
            for identity in remaining:
                saved = context['decisions'].get(identity, {})
                valid = saved.get('metadata_hash') == context['incoming'][identity]
                row = dict(**key, epoch_uuid=identity, metadata_hash=context['incoming'][identity], selected=False,
                           reviewed=bool(saved.get('reviewed')) if valid else False, excluded=True)
                (self.tables[1].update1 if identity in context['decisions'] else self.tables[1].insert1)(row)
            self._event(context['actor'], 'workbench_review_finished', dict(protocol_uuid=context['protocol_uuid'],
                candidate_revision_uuid=context['candidate_revision_uuid'], left_out_epoch_count=len(remaining),
                left_out_epoch_uuids=remaining), str(uuid.uuid4()))
        return self.context(context['protocol_uuid'], context['candidate_revision_uuid'], context['actor'])

    def selection_manifest(self, context, token, *, complete=True):
        if not isinstance(token, str):
            raise ValueError('Selection token must be text')
        now = time.monotonic()
        for key, value in list(self.selection_manifests.items()):
            if now - value['touched'] > 900:
                del self.selection_manifests[key]
        value = self.selection_manifests.get(token)
        owner = (self.project, context['protocol_uuid'], context['candidate_revision_uuid'],
                 context['actor'], context['candidate_scope_revision'])
        if value is None or value['owner'] != owner or complete and not value['complete']:
            raise WorkbenchConflict('The exact selection expired or changed. Select or open the selected view again.')
        value['touched'] = now
        return value

    def append_selection_manifest(self, context, body):
        if not isinstance(body['upload_uuid'], str):
            raise ValueError('Selection upload requires a UUID')
        token = str(uuid.UUID(body['upload_uuid']))
        ids, offset, total = body['epoch_uuids'], body['offset'], body['total']
        if (type(offset) is not int or type(total) is not int or not 0 <= offset <= total
                or not 1 <= total <= len(context['pending']) or not isinstance(ids, list)
                or not 1 <= len(ids) <= 1000 or offset + len(ids) > total):
            raise ValueError('Selection upload requires complete bounded batches and an exact pending count')
        if any(not isinstance(key, str) or str(uuid.UUID(key)) != key for key in ids):
            raise ValueError('Selection upload requires canonical epoch UUIDs')
        if len(set(ids)) != len(ids) or set(ids) - context['pending'].keys():
            raise ValueError('Selection contains duplicate or out-of-candidate epochs')
        if set(ids) & context['unavailable']:
            raise WorkbenchConflict('Selected recording metadata changed or is unavailable')
        if token not in self.selection_manifests:
            if offset:
                raise WorkbenchConflict('Selection upload is missing its first batch')
            # Bound ephemeral uploads, never scientific selection cardinality.
            if len(self.selection_manifests) >= 32:
                oldest = min(self.selection_manifests, key=lambda key: self.selection_manifests[key]['touched'])
                del self.selection_manifests[oldest]
            self.selection_manifests[token] = dict(owner=(self.project, context['protocol_uuid'],
                context['candidate_revision_uuid'], context['actor'], context['candidate_scope_revision']),
                ids=[], seen=set(), total=total, complete=False, touched=time.monotonic())
        value = self.selection_manifest(context, token, complete=False)
        if total != value['total']:
            raise WorkbenchConflict('Selection upload count changed')
        if offset < len(value['ids']):
            if value['ids'][offset:offset + len(ids)] != ids:
                raise WorkbenchConflict('Selection upload retry differs from its original batch')
        else:
            if offset != len(value['ids']) or value['seen'].intersection(ids):
                raise WorkbenchConflict('Selection upload has missing or duplicate epochs')
            value['ids'].extend(ids)
            value['seen'].update(ids)
        value['complete'] = len(value['ids']) == total
        if value['complete']:
            value['sha256'] = checksum(value['ids'])
        return dict(selection_token=token, count=len(value['ids']), total=total,
                    complete=value['complete'], selection_sha256=value.get('sha256'))

    def prepare_selection(self, context, ids, body):
        self.check_scope(context, body['expected_candidate_scope_revision'])
        if type(body['expected_version']) is not int or body['expected_version'] != context['draft_version']:
            raise WorkbenchConflict('Review draft version changed')
        if type(body['review']) is not bool:
            raise ValueError('Explicit selection review must be boolean')
        selected = set(ids)
        if not selected or selected - context['pending'].keys():
            raise ValueError('Select exact pending epochs before review')
        self.publishable(context, selected)
        if any(self.decision(context, key)['excluded'] for key in ids):
            raise ValueError('Selected epochs are excluded. Adjust the selection or explicitly change their exclusions.')
        if not body['review'] and any(not self.decision(context, key)['reviewed'] for key in ids):
            raise ValueError('Review the selected epochs before continuing')
        # Only the complete server draft can clear previous selected choices.
        affected = selected | {key for key in context['pending'] if context['decisions'].get(key, {}).get('selected')}
        rows = []
        key = self.key(context['protocol_uuid'], context['candidate_revision_uuid'], context['actor'])
        for identity in sorted(affected):
            if identity not in selected:
                saved = context['decisions'][identity]
                rows.append(dict(**key, epoch_uuid=identity, metadata_hash=saved['metadata_hash'],
                    selected=False, reviewed=bool(saved.get('reviewed')), excluded=bool(saved.get('excluded'))))
                continue
            decision = self.decision(context, identity)
            decision['selected'] = identity in selected
            if identity in selected and body['review']:
                decision['reviewed'] = True
            rows.append(dict(**key, epoch_uuid=identity, metadata_hash=context['incoming'][identity], **decision))
        with self.service.dj.conn().transaction:
            current, _ = self.draft(key)
            if current['version'] != context['draft_version']:
                raise WorkbenchConflict('Review draft version changed')
            draft = dict(**key, version=context['draft_version'] + 1, selection_mode='selected', deferred=context['deferred'])
            (self.tables[0].update1 if context['draft_version'] else self.tables[0].insert1)(draft)
            for row in rows:
                (self.tables[1].update1 if row['epoch_uuid'] in context['decisions'] else self.tables[1].insert1)(row)
        return self.context(context['protocol_uuid'], context['candidate_revision_uuid'], context['actor'])

    def preview(self, context, body):
        self.check_scope(context, body['expected_candidate_scope_revision'])
        if type(body['expected_draft_version']) is not int or body['expected_draft_version'] != context['draft_version']:
            raise WorkbenchConflict('Review draft changed')
        selected = self.selection(context, body['mode'], body.get('source_sha256'))
        self.publishable(context, selected)
        if not selected:
            if context['ineligible']:
                raise WorkbenchConflict('No eligible incoming additions remain; excluded sources require reconciliation')
            raise ValueError('Choose reviewed incoming additions before publication')
        require_protocol_compatibility(self.service, context['protocol_uuid'], selected)
        accepted = selected - context['previous'].keys()
        preview = dict(contract_version=1, candidate_scope_revision=context['candidate_scope_revision'],
            expected_draft_version=context['draft_version'], mode=body['mode'],
            expected_binding_version=context['expected_binding_version'],
            expected_query_revision=context['expected_query_revision'],
            selected_sha256=checksum({key: context['incoming'][key] for key in sorted(selected)}),
            selected_epoch_count=len(selected), accepted_epoch_count=len(accepted),
            already_present_epoch_count=len(selected) - len(accepted),
            retained_epoch_count=len(context['previous']), next_epoch_count=len(context['previous']) + len(accepted),
            accepted_cell_count=len({self.service.rows[key]['cell_uuid'] for key in accepted}))
        if body['mode'] == 'source':
            preview['source_sha256'] = body['source_sha256']
        preview['preview_sha256'] = checksum(preview)
        return preview, selected, accepted

    def receipt(self, operation, actor, request_hash=None):
        rows = (self.tables[2] & dict(project_uuid=self.project, operation_uuid=str(uuid.UUID(operation)))).to_dicts()
        if not rows:
            return None
        row = rows[0]
        if row['actor'] != actor or (request_hash is not None and row['request_sha256'] != request_hash):
            raise WorkbenchConflict('Operation UUID already used by another actor or request')
        return copy.deepcopy(row['receipt'])

    def accept(self, protocol, revision, actor, body):
        request_hash = self.accept_request_hash(protocol, revision, actor, body)
        existing = self.receipt(body['operation_uuid'], actor, request_hash)
        if existing:
            return existing  # Receipt precedes stale binding/draft checks, including after restart.
        context = self.context(protocol, revision, actor)
        preview, selected, accepted = self.preview(context, body)
        if (body['preview_sha256'] != preview['preview_sha256'] or type(body['expected_binding_version']) is not int
                or body['expected_binding_version'] != preview['expected_binding_version']
                or body['expected_query_revision'] != preview['expected_query_revision']):
            raise WorkbenchConflict('Additive preview changed; compare again before accepting')
        guard, _ = self.transaction_authority(protocol)
        self.verify_sources(context, selected | context['previous'].keys())
        union = {**context['previous'], **{key: context['incoming'][key] for key in accepted}}
        main = context['main']
        publication = dict(previous_revision_uuid=main['revision_uuid'], main_recipe_sha256=main['content_sha256'],
            baseline_revision_uuid=context['baseline_revision_uuid'], baseline_recipe_sha256=context['baseline_recipe_sha256'],
            candidate_revision_uuid=revision, candidate_recipe_sha256=context['candidate_recipe_sha256'],
            preview_sha256=preview['preview_sha256'], selected_sha256=preview['selected_sha256'],
            actor=actor, draft_version=context['draft_version'], operation_uuid=body['operation_uuid'])
        if body['mode'] == 'source':
            publication['source_sha256'] = body['source_sha256']
        frozen = dict(predicate=copy.deepcopy(main['predicate']), splits=main['splits'],
            membership=[dict(uuid=key, metadata_hash=value) for key, value in sorted(union.items())],
            matched_count=len(union), total_source=len(self.service.rows), metadata_fingerprint_version=2,
            source_revisions=sorted({self.service.rows[key]['source_sha256'] for key in union}),
            source_scope=context['source_scope'], tree=dict(split_order=main['tree_view']['fields']),
            additive_publication=publication,
            **({'annotation_scope': main['annotation_scope']} if main.get('annotation_scope') else {}))
        diff = dict(added=sorted(accepted), removed=[], changed=[])
        connection = self.service.dj.conn()
        # Route owns destination advisory lock. Recipe, binding, audit and receipt commit together.
        with connection.transaction:
            again = self.receipt(body['operation_uuid'], actor, request_hash)
            if again:
                return again
            self.check_scope(self.context(protocol, revision, actor, query_revision_guard=guard),
                context['candidate_scope_revision'])
            if accepted:
                record = self.history.create(frozen, self.service.sources, self.service.project_dir / 'catalog.json', actor,
                    name=main['name'], parent_revision_uuid=main['revision_uuid'], _in_transaction=True)
                (_revision_memo.get() or {}).clear()
                saved = self.history.bind(record['revision_uuid'], protocol, preview['expected_binding_version'], actor,
                    diff, len(context['previous']), expected_query_revision=preview['expected_query_revision'],
                    current_query_revision=guard, diff_summary=summarize_diff(self.service.rows, context['previous'], union),
                    _in_transaction=True, _lock_held=True)
            else:
                record = dict(revision_uuid=main['revision_uuid'], recipe=main)
                saved = dict(version=context['expected_binding_version'], revision_uuid=main['revision_uuid'], event_uuid=None)
            self.verify_sources(context, selected | context['previous'].keys())
            receipt = dict(**preview, operation_uuid=str(uuid.UUID(body['operation_uuid'])), protocol_uuid=protocol,
                candidate_revision_uuid=revision, actor=actor, binding=saved, event_uuid=str(uuid.uuid4()),
                candidate_recipe_sha256=context['candidate_recipe_sha256'],
                baseline_revision_uuid=context['baseline_revision_uuid'], baseline_recipe_sha256=context['baseline_recipe_sha256'],
                binding_event_uuid=saved['event_uuid'],
                resulting_recipe_sha256=record['recipe']['content_sha256'],
                accepted_epoch_uuids=sorted(accepted), selected_epoch_uuids=sorted(selected),
                accepted_fingerprints={key: context['incoming'][key] for key in sorted(accepted)},
                resolved_draft_version=context['draft_version'], export_state='not_requested')
            self.tables[2].insert1(dict(project_uuid=self.project, operation_uuid=receipt['operation_uuid'],
                protocol_uuid=protocol, candidate_revision_uuid=revision, actor=actor,
                request_sha256=request_hash, receipt=receipt))
            self._event(actor, 'workbench_additions_accepted', receipt, receipt['operation_uuid'], event_uuid=receipt['event_uuid'])
        return receipt

    def undo(self, protocol, actor, body):
        """Restore main to its exact revision before one additive merge.

        Only the latest change to main can be undone: main must still be the
        revision that merge published. The undone epochs become pending again.
        """
        operation = str(uuid.UUID(body['operation_uuid']))
        if type(body['expected_binding_version']) is not int:
            raise ValueError('Undo requires the merge receipt binding version')
        undo_operation = str(uuid.uuid5(uuid.UUID(self.project), 'workbench-undo:' + operation))
        request_hash = checksum(dict(kind='workbench_undo', protocol_uuid=protocol, actor=actor, **body))
        existing = self.receipt(undo_operation, actor, request_hash)
        if existing:
            return existing
        rows = (self.tables[2] & dict(project_uuid=self.project, operation_uuid=operation)).to_dicts()
        merged = rows[0]['receipt'] if rows else None
        if (not merged or merged.get('protocol_uuid') != protocol or merged.get('kind') == 'workbench_undo'
                or not merged.get('accepted_epoch_uuids') or not isinstance(merged.get('binding'), dict)):
            raise ValueError('Only a merge that added epochs can be undone')
        binding = self.history.protocol_binding_header(protocol)
        if (not binding or binding['version'] != body['expected_binding_version']
                or binding['version'] != merged['binding']['version']
                or binding['revision_uuid'] != merged['binding']['revision_uuid']):
            raise WorkbenchConflict('Main changed after this merge, so it can no longer be undone safely.')
        current = self._recipe(binding['revision_uuid'])
        previous_uuid = current.get('additive_publication', {}).get('previous_revision_uuid')
        if not previous_uuid or current.get('parent_revision_uuid') != previous_uuid:
            raise WorkbenchConflict('This merge has no recorded previous main to restore.')
        previous = self._recipe(previous_uuid)
        removed = sorted(_members(current).keys() - _members(previous).keys())
        if removed != sorted(merged['accepted_epoch_uuids']):
            raise WorkbenchConflict('Main does not match this merge; it cannot be undone safely.')
        with self.service.dj.conn().transaction:
            again = self.receipt(undo_operation, actor, request_hash)
            if again:
                return again
            (_revision_memo.get() or {}).clear()
            saved = self.history.bind(previous_uuid, protocol, binding['version'], actor,
                dict(added=[], removed=removed, changed=[]), len(_members(current)),
                _in_transaction=True, _lock_held=True)
            receipt = dict(contract_version=1, kind='workbench_undo', operation_uuid=undo_operation,
                undone_operation_uuid=operation, protocol_uuid=protocol, actor=actor,
                binding=dict(version=saved['version'], revision_uuid=previous_uuid, event_uuid=saved['event_uuid']),
                restored_revision_uuid=previous_uuid, restored_binding_version=merged['expected_binding_version'],
                removed_epoch_uuids=removed, removed_epoch_count=len(removed))
            self.tables[2].insert1(dict(project_uuid=self.project, operation_uuid=undo_operation, protocol_uuid=protocol,
                candidate_revision_uuid=merged['candidate_revision_uuid'], actor=actor,
                request_sha256=request_hash, receipt=receipt))
            self._event(actor, 'workbench_merge_undone', receipt, undo_operation)
        return receipt

    @staticmethod
    def accept_request_hash(protocol, revision, actor, body):
        return checksum(dict(protocol_uuid=protocol, candidate_revision_uuid=revision, actor=actor, **body))

    def _event(self, actor, action, payload, operation, *, event_uuid=None):
        event_uuid = event_uuid or str(uuid.uuid4())
        self.history.Event.insert1(dict(project_uuid=self.project, event_uuid=event_uuid,
            occurred_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None), actor=actor, action=action,
            payload=build_audit_payload(action, actor, payload, operation_uuid=operation,
                context={'project_uuid': self.project})))
        return event_uuid

    def verify_sources(self, context, identities):
        scope = self.service.source_scope()
        if scope['revision'] != context['source_scope_revision']:
            raise WorkbenchConflict('Source registration changed during publication')
        sources = set()
        for identity in identities:
            expected = context['incoming'].get(identity, context['previous'].get(identity))
            if self.service._fingerprints.get(identity) != expected:
                raise WorkbenchConflict('Epoch fingerprint changed during publication')
            source = self.service.rows[identity]['source_sha256']
            if source not in scope['active_source_revisions']:
                raise WorkbenchConflict('Selected source is ineligible')
            sources.add(source)
        for source in sorted(sources):
            self.service._verified_source(self.service.manifests[source])

    def frozen_service(self, context):
        with elapsed("disco.workbench.workbench", "frozen_service"):
            if context['unavailable'] & context['pending'].keys():
                raise WorkbenchConflict('Frozen candidate metadata is unavailable or changed; browsing cannot reconstruct it')
            scoped = copy.copy(self.service)
            provider = self._read_projections.bind(self.service, context)
            scoped.binding_provider = provider
            scoped.binding_header_provider = provider.header if provider.read_scope_revision is not None else None
            scoped._tree_catalog_cache = {}
            scoped._epoch_page_cache = None
            scoped._tree_scope_cache = {}
            scoped._tree_page_scope_cache = None
            scoped._registered_tree_cache = None if '_view_ids' in context else getattr(self.service, '_registered_tree_cache', None)
            def decisions(protocol, fingerprints):
                return {key: dict(included=True, reviewed=False, review_state='unreviewed',
                    tags=[], revision=0, metadata_fingerprint=value, approval_stale=False)
                    for key, value in fingerprints.items() if key in context['pending']}
            scoped.curation_provider = decisions
            # Display coverage uses shared annotations only. It never grants review
            # or main membership, and finish() rechecks the shared scope witness.
            coverage_index = None
            def annotation_coverage(rows):
                nonlocal coverage_index
                snapshot = context.get('_shared_annotation_snapshot')
                if snapshot is None:
                    return None
                if coverage_index is None:
                    if snapshot['revision'] != context['shared_annotations_revision']:
                        raise WorkbenchConflict('Shared annotations changed while reading tree coverage')
                    coverage_index = {'cell': set(), 'epoch': set()}
                    for record in snapshot['records']:
                        if record['tags']:
                            coverage_index[record['target_kind']].add(record['target_uuid'])
                return dict(total_epochs=len(rows), tagged_epochs=sum(
                    row['epoch_uuid'] in coverage_index['epoch'] or row['cell_uuid'] in coverage_index['cell']
                    for row in rows))
            scoped.tree_annotation_coverage = annotation_coverage
            return scoped

    def queue(self, protocol, actor, limit=20, cursor=None):
        with elapsed("disco.workbench.workbench", "queue"):
            if type(limit) is not int or not 1 <= limit <= 100:
                raise ValueError('Queue page limit must be 1–100')
            protocol = str(uuid.UUID(protocol))
            if protocol not in self.service.protocols:
                raise KeyError('Unknown protocol')
            state = self.pending_pool(protocol)
            pool = state['pool']
            header, decisions = self.review_decisions(protocol, actor)
            left_out = sorted(identity for identity, saved in decisions.items()
                              if saved.get('excluded') and pool.get(identity) == saved['metadata_hash'])
            pending = set(pool) - set(left_out)
            records = self.original_records(protocol)
            records.sort(key=lambda row: (row['summary']['created_at'], row['suggestion_uuid']), reverse=True)
            accepted = {row['candidate_revision_uuid'] for row in (self.tables[2] & dict(
                project_uuid=self.project, protocol_uuid=protocol)).proj('candidate_revision_uuid').to_dicts()}
            items = []
            for row in records:
                summary = row['summary']
                mine = set(summary.get('incoming_cell_uuids', {})) & pending
                status = ('pending' if mine else 'accepted' if summary['candidate_revision_uuid'] in accepted else 'covered')
                items.append(dict(**{key: value for key, value in summary.items() if key != 'incoming_cell_uuids'},
                    status=status, pending_epoch_count=len(mine), eligible_pending_epoch_count=len(mine)))
            rows = self.service.rows
            cells = {rows[identity]['cell_uuid'] for identity in pending}
            main_cells = {rows[identity]['cell_uuid'] for identity in _members(state['main'])} if state['main'] else set()
            filenames = {source['source_sha256']: source.get('filename') for source in self.service.sources}
            by_source = {}
            for identity in pending:
                sha = rows[identity]['source_sha256']
                by_source[sha] = by_source.get(sha, 0) + 1
            recordings = sorted((dict(source_sha256=sha, filename=filenames.get(sha) or sha, epoch_count=count)
                                 for sha, count in by_source.items()), key=lambda item: item['filename'])
            revision = checksum(dict(project_uuid=self.project, protocol_uuid=protocol, actor=actor, pool=state['key'],
                pending=checksum(pool), left_out=left_out, deferred=bool(header.get('deferred')),
                # Review edits advance the draft version. Initializing a draft starts
                # at the carried version, so preparation never changes its own fence.
                draft_version=max(header.get('version', 1) - 1, 0),
                items=[(item['candidate_revision_uuid'], item['status']) for item in items]))
            offset = 0
            if cursor:
                try:
                    saved = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                    if set(saved) != {'revision', 'offset'} or type(saved['offset']) is not int or saved['offset'] < 0:
                        raise ValueError()
                    if saved['revision'] != revision:
                        raise WorkbenchConflict('Review queue changed; restart pagination')
                    offset = saved['offset']
                except (ValueError, TypeError, UnicodeError) as error:
                    if isinstance(error, WorkbenchConflict):
                        raise
                    raise ValueError('Malformed queue cursor') from error
            end = offset + limit
            next_cursor = base64.urlsafe_b64encode(json.dumps(dict(revision=revision, offset=end)).encode()).decode() if end < len(items) else None
            return dict(contract_version=1, candidates=items[offset:end], pending_epoch_count=len(pending),
                pending_cell_count=len(cells), pending_cell_count_available=True,
                eligible_pending_epoch_count=len(pending), eligible_pending_cell_count=len(cells),
                pending_new_cell_count=len(cells - main_cells), pending_recordings=recordings,
                left_out_epoch_count=len(left_out), main_blocked_reason=state['reason'],
                queue_revision=revision, next_cursor=next_cursor, total_candidate_count=len(items),
                capabilities=dict(frozen_browse=True, drafts=True, additive_accept=True,
                    incoming_export=getattr(self, 'incoming_export', False),
                    cumulative_pending_browse=getattr(self, 'cumulative_pending_browse', False), initial_page=True,
                    merge_all=True))

def public_receipt(receipt):
    result = copy.deepcopy({key: value for key, value in receipt.items()
                           if key not in {'accepted_fingerprints', 'selected_epoch_uuids', 'accepted_epoch_uuids'}})
    if 'accepted_epoch_uuids' not in receipt:
        return result
    ids = receipt['accepted_epoch_uuids']
    result.update(accepted_epoch_uuids=ids[:250], accepted_epoch_uuids_total=len(ids),
                  accepted_epoch_uuids_truncated=len(ids) > 250)
    return result


_PREPARED_CONTEXT = ProtocolWorkbench.context
_PREPARED_FROZEN_SERVICE = ProtocolWorkbench.frozen_service


def register_workbench_routes(app, service, history, suggestions, state, revision_guard,
                              db_lock, registration_locks, *, read_revision=None):
    import os
    from flask import jsonify, request
    from workspace_service import validate_filters
    from disco.navigation.tag_predicates import annotation_locks
    from disco.navigation.tree_pages import TreePages, StaleTreePage
    manager = ProtocolWorkbench(service, history, suggestions, state, revision_guard, read_revision=read_revision)
    if hasattr(service.dj, 'Schema'):
        manager.tables  # Additive DDL before startup recovery/checkpoint capture.
    app.extensions['protocol_workbench'] = manager
    from workspace_trace_views import TraceViews, TraceViewConflict
    from disco.decisions.annotations import SharedAnnotations
    canonical_default_profile = SharedAnnotations.default_profile
    def display_policy():
        from workspace_protocol_state import ProtocolStateReader
        reader = app.extensions.get('protocol_state_reader')
        return (type(reader) is ProtocolStateReader and reader._native_contract() and
                (getattr(service, 'shared_annotations', None) is None or
                 (type(service.shared_annotations) is SharedAnnotations and
                  SharedAnnotations.default_profile is canonical_default_profile)) and
                manager.state is manager._read_revision_state and
                getattr(manager.context, '__func__', None) is _PREPARED_CONTEXT and
                getattr(manager.frozen_service, '__func__', None) is _PREPARED_FROZEN_SERVICE)
    trace_views = TraceViews(service, policy=display_policy)
    app.extensions['trace_views'] = trace_views

    def actor():
        shared = getattr(service, 'shared_annotations', None)
        from disco.decisions.author_preferences import selected_author
        profile = selected_author() or (shared.default_profile if shared else None)
        return profile['profile_uuid'] if profile else os.environ.get('USER', 'local-user')

    def display_actor():
        # Canonical fallback is pure local UUID derivation; never dispatch an
        # overridable annotation property on this independent display route.
        from disco.decisions.author_preferences import selected_author
        profile = selected_author()
        shared = getattr(service, 'shared_annotations', None)
        if profile is None and shared is not None:
            profile = canonical_default_profile.fget(shared)
        return profile['profile_uuid'] if profile else os.environ.get('USER', 'local-user')

    def body(required, optional=(), *, query_options=()):
        if request.args.keys() - set(query_options) or any(len(request.args.getlist(key)) != 1 for key in request.args) or (request.content_length is not None and request.content_length > 65536):
            raise ValueError('Workbench body must be at most 64KiB with no URL options')
        value = request.get_json()
        if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
            raise ValueError('Malformed Workbench request; required fences or supported fields missing')
        return dict(value)

    def query_filters(allowed=()):
        allowed = {*allowed, 'selection_token'}
        fields = {'epoch_uuid', 'cell_uuid', 'cell_type', 'group_label', 'tag', 'tagged', 'tag_predicate', 'metadata_predicate'}
        if request.args.keys() - fields - set(allowed) or any(len(request.args.getlist(key)) != 1 for key in request.args):
            raise ValueError('Unknown or repeated Workbench query option')
        return validate_filters({key: value for key, value in request.args.items() if key in fields})

    @contextlib.contextmanager
    def guarded(protocol, revision=None, filters=None):
        with db_lock, registration_locks():
            manager.tables  # Declare native tables before transactions/annotation locks.
            predicates = []
            if revision:
                candidate_recipe = manager.proposal(protocol, revision)[2]
                predicates.append(candidate_recipe['predicate'])
                predicates.extend(origin[2]['predicate'] for origin in manager.origin_recipes(protocol, candidate_recipe))
            else:
                # Queue summaries read every candidate's annotation witness.
                restriction = dict(project_uuid=manager.project)
                if protocol is not None:
                    restriction['protocol_uuid'] = protocol
                records = (suggestions.Table & restriction).to_dicts()
                predicates.extend(history.get(row['summary']['candidate_revision_uuid'])['recipe']['predicate'] for row in records)
            for field in ('metadata_predicate', 'tag_predicate'):
                if (filters or {}).get(field):
                    value = filters[field]
                    predicates.append(json.loads(value) if isinstance(value, str) else value)
            # Discover each independently admitted AST separately. Combining
            # 128-node trees would truncate the bounded dependency scanner.
            from disco.navigation.tag_predicates import TagPredicates, referenced_fields
            fields = set().union(*(referenced_fields(predicate) for predicate in predicates))
            definitions = {field['id']: field for field in TagPredicates(service).definitions()}
            if fields - definitions.keys():
                raise ValueError('Unknown annotation predicate authority')
            origins = set(service.protocols) if protocol is None else {protocol}
            protocols = origins | {definitions[field]['annotation_scope']['protocol_uuid'] for field in fields
                if definitions[field]['annotation_scope']['kind'] == 'protocol_curation'}
            with annotation_locks(service, {'all': []}, extra_protocols=protocols):
                # Reuse schema attestation only within one read response.
                # Scope generations remain live, and the closing attestation
                # must succeed before any response is published. Mutations
                # retain their independent transaction authority checks.
                from workspace_state_generation import StateGenerationAuthority
                tracker = getattr(service, '_explore_state_generation', None)
                readonly = request.method == 'GET' or request.endpoint in {
                    'workbench_preview', 'workbench_tree_page', 'workbench_candidate_summary', 'workbench_selection_summary', 'workbench_tree_selection', 'workbench_list_selection', 'workbench_selection_manifest'}
                contract = (tracker.response_contract() if readonly and type(tracker) is StateGenerationAuthority
                            else contextlib.nullcontext())
                with contract:
                    yield actor()

    def start_read(context, filters=None):
        from disco.metadata.explore_queries import generation, StaleQuery
        token = request.args.get('selection_token') if request.method == 'GET' else ((request.get_json(silent=True) or {}).get('selection_token') if request.endpoint != 'workbench_selected_review' else None)
        # An ordinary epoch predicate is not a View selected receipt. New
        # clients use the explicitly advertised selection-manifest contract.
        if token is not None:
            context['_view_ids'] = manager.selection_manifest(context, token)['seen']
        context['_read_context'] = dict(predicate={'all': []}, protocol_uuid=context['protocol_uuid'], filters=filters or {})
        try:
            context['_read_generation'] = (context['_transaction_authority'][1](context['_read_context'])
                if '_transaction_authority' in context else generation(service, context['_read_context']))
        except StaleQuery as error:
            raise WorkbenchConflict(str(error)) from error
        return context

    def checked(protocol, revision, owner, expected, filters=None):
        context = manager.context(protocol, revision, owner)
        manager.check_scope(context, expected)
        return start_read(context, filters)

    def finish(context, value):
        display_membership = context
        filters = context.get('_read_context', {}).get('filters', {})
        if '_view_ids' in context and filters and trace_views._canonical():
            # Capture exactly the selected display intersection, including every
            # pre-existing metadata/tag filter. This runs under the ordinary
            # guarded preparation and its closing generation checks, never on
            # the independent sample-read route. Keep tree/mutation context intact.
            scoped = manager.frozen_service(context)
            display_membership = dict(context, _view_ids={row['epoch_uuid']
                for row in scoped.filtered_rows(context['protocol_uuid'], filters)})
        if '_read_generation' in context:
            from disco.metadata.explore_queries import generation, StaleQuery
            try:
                current = (context['_transaction_authority'][1](context['_read_context'])
                    if '_transaction_authority' in context else generation(service, context['_read_context']))
            except StaleQuery as error:
                raise WorkbenchConflict(str(error)) from error
            if current != context['_read_generation']:
                raise WorkbenchConflict('Metadata or filter annotation authority changed during the frozen read')
            value['generation'] = current
        guard = context.get('_transaction_authority', (None,))[0]
        manager.check_scope(manager.context(context['protocol_uuid'], context['candidate_revision_uuid'], context['actor'],
                            query_revision_guard=guard),
                            context['candidate_scope_revision'])
        value.update(candidate_scope_revision=context['candidate_scope_revision'],
            query_revision=context['candidate_scope_revision'], expected_binding_version=context['expected_binding_version'])
        display_context = trace_views.prepare(display_membership)
        if display_context is not None:
            value['trace_read_context'] = display_context
        return value

    def row_decisions(context, rows):
        shared = getattr(service, 'shared_annotations', None)
        annotations = shared.for_epochs([service.rows[row['epoch_uuid']] for row in rows]) if shared else {}
        for row in rows:
            row['review_decision'] = manager.decision(context, row['epoch_uuid'])
            if annotations:
                row['annotations'] = annotations[row['epoch_uuid']]

    def public_context(context, filters=None, *, transaction_authority=None, include_initial_page=False):
        if transaction_authority is not None:
            context['_transaction_authority'] = transaction_authority
        start_read(context, filters)
        scoped = manager.frozen_service(context)
        summary_options = ({'cross_protocols': False}
            if (getattr(scoped.protocol, '__func__', None) is _PROTOCOL_SUMMARY
                and getattr(scoped._cell_summary, '__func__', None) is _CELL_SUMMARY) else {})
        protocol = copy.deepcopy(scoped.protocol(context['protocol_uuid'], filters, **summary_options))
        protocol.update(query_revision=context['candidate_scope_revision'],
            expected_query_revision=context['expected_query_revision'], expected_binding_version=context['expected_binding_version'],
            source_eligibility=dict(excluded_epoch_count=len(context['ineligible']), propagation_required=bool(context['ineligible']),
                source_scope_revision=context['source_scope_revision']), review_scope='incoming_candidate')
        ids = sorted(context['decisions'])
        payload = dict(contract_version=1, actor=context['actor'], source_additive_accept=True, selection_manifests=True, protocol=protocol, tree_column_pages=True, selection_summary=True, tree_selection=True, list_selection=True,
            candidate_revision_uuid=context['candidate_revision_uuid'], candidate_recipe_sha256=context['candidate_recipe_sha256'],
            expected_query_revision=context['expected_query_revision'],
            draft=dict(draft_version=context['draft_version'], selection_mode=context['selection_mode'], deferred=context['deferred'],
                decisions=[dict(epoch_uuid=key, **manager.decision(context, key)) for key in ids[:250]],
                decisions_total=len(ids), decisions_truncated=len(ids) > 250),
            counts=dict(incoming_epochs=len(context['incoming']), pending_epochs=len(context['pending']),
                pending_cells=len({service.rows[key]['cell_uuid'] for key in context['pending']}),
                already_present_epochs=len(context['already_present']), conflicting_epochs=len(context['conflicts']),
                excluded_epochs=sum(manager.decision(context, key)['excluded'] for key in context['incoming'])),
            ineligible_incoming_epoch_count=len(context['ineligible']),
            publication_blocked=bool(context['base_conflicts'] or context['main_conflicts']
                or context['blocked_main'] or context['annotation_changed'] or not context['valid_base']))
        page = None
        if include_initial_page:
            page = scoped.epoch_page(context['protocol_uuid'], filters, 0, 60, include_cells=True)
            page.pop('_shared_annotation_generation', None)
            row_decisions(context, page['epochs'])
        result = finish(context, payload)
        if page is None:
            return result
        page.update({key: result[key] for key in ('generation', 'candidate_scope_revision',
            'query_revision', 'expected_binding_version')})
        if 'trace_read_context' in result:
            page['trace_read_context'] = dict(result['trace_read_context'])
        # Keep the fresh projection separate from durable prepare receipt data.
        bootstrap = dict(contract_version=1, kind='workbench_initial_page', context=result, page=page,
            actor=context['actor'], project_uuid=context['project_uuid'], protocol_uuid=context['protocol_uuid'],
            candidate_revision_uuid=context['candidate_revision_uuid'],
            root='/protocols/' + context['protocol_uuid'] + '/workbench/candidates/' + context['candidate_revision_uuid'],
            request=dict(filters=filters or {}, offset=0, limit=60, include_cells=True))
        return dict(result, bootstrap=bootstrap)

    @app.errorhandler(WorkbenchConflict)
    def conflict(error):
        return jsonify(error=str(error), code='workbench_conflict'), 409

    root = '/api/protocols/<protocol>/workbench'
    candidate = root + '/candidates/<revision>'

    @app.get(root)
    def workbench_queue(protocol):
        query_filters({'limit', 'cursor'})
        if request.args.keys() - {'limit', 'cursor'}:
            raise ValueError('Queue accepts pagination only')
        with guarded(protocol) as owner:
            return jsonify(manager.queue(protocol, owner, int(request.args.get('limit', 20)), request.args.get('cursor')))

    @app.get('/api/workbench/summary')
    def workbench_summary():
        if request.args:
            raise ValueError('Project Workbench summary takes no options')
        counts = []
        with guarded(None) as owner:
            for protocol in service.protocols:
                value = manager.queue(protocol, owner, 1)
                # The same pending pool the Overview card and Workbench read, so
                # the import review, badges and cards cannot disagree.
                counts.append(dict(protocol_uuid=protocol, **{key: value[key] for key in
                    ('pending_cell_count', 'pending_epoch_count', 'queue_revision', 'eligible_pending_epoch_count',
                     'eligible_pending_cell_count', 'pending_new_cell_count', 'pending_recordings',
                     'left_out_epoch_count', 'main_blocked_reason', 'capabilities')}))
        return jsonify(contract_version=1, workbench_counts=counts)

    @app.get(candidate + '/context')
    def workbench_context(protocol, revision):
        filters = query_filters({'candidate_scope_revision', 'include_initial_page'})
        include = request.args.get('include_initial_page', 'false')
        if include not in ('true', 'false'):
            raise ValueError('include_initial_page must be true or false')
        with guarded(protocol, revision, filters) as owner:
            context = manager.context(protocol, revision, owner)
            if 'candidate_scope_revision' in request.args:
                manager.check_scope(context, request.args['candidate_scope_revision'])
            return jsonify(public_context(context, filters, include_initial_page=include == 'true'))

    @app.post(candidate + '/selection-manifest')
    def workbench_selection_manifest(protocol, revision):
        value = body({'candidate_scope_revision', 'upload_uuid', 'offset', 'total', 'epoch_uuids'})
        with guarded(protocol, revision) as owner:
            context = checked(protocol, revision, owner, value['candidate_scope_revision'])
            return jsonify(finish(context, manager.append_selection_manifest(context, value)))

    @app.post(candidate + '/selected-review')
    def workbench_selected_review(protocol, revision):
        value = body({'expected_candidate_scope_revision', 'expected_version', 'selection_token', 'review'})
        with guarded(protocol, revision) as owner:
            context = manager.context(protocol, revision, owner)
            ids = manager.selection_manifest(context, value['selection_token'])['ids']
            return jsonify(public_context(manager.prepare_selection(context, ids, value)))

    @app.patch(candidate + '/draft')
    def workbench_patch(protocol, revision):
        value = body({'expected_version', 'expected_candidate_scope_revision'}, {'decisions', 'selection_mode', 'deferred'})
        with guarded(protocol, revision) as owner:
            return jsonify(public_context(manager.patch(protocol, revision, owner, value)))

    @app.post(root + '/undo')
    def workbench_undo(protocol):
        value = body({'operation_uuid', 'expected_binding_version'})
        with guarded(protocol) as owner:
            receipt = manager.undo(str(uuid.UUID(protocol)), owner, value)
            return jsonify(binding=receipt['binding'], restored_revision_uuid=receipt['restored_revision_uuid'],
                           removed_epoch_count=receipt['removed_epoch_count'], operation_uuid=receipt['operation_uuid'])

    @app.post(candidate + '/finish')
    def workbench_finish(protocol, revision):
        value = body({'expected_version', 'expected_candidate_scope_revision'})
        with guarded(protocol, revision) as owner:
            return jsonify(public_context(manager.finish(manager.context(protocol, revision, owner), value)))

    @app.post(candidate + '/preview')
    def workbench_preview(protocol, revision):
        value = body({'expected_candidate_scope_revision', 'expected_draft_version', 'mode'}, {'source_sha256'})
        with guarded(protocol, revision) as owner:
            return jsonify(manager.preview(manager.context(protocol, revision, owner), value)[0])

    @app.post(candidate + '/accept')
    def workbench_accept(protocol, revision):
        value = body({'expected_candidate_scope_revision', 'expected_draft_version', 'mode', 'preview_sha256',
                      'expected_binding_version', 'expected_query_revision', 'operation_uuid'}, {'source_sha256'})
        with db_lock:
            manager.tables
            owner = actor()
            existing = manager.receipt(value['operation_uuid'], owner,
                manager.accept_request_hash(protocol, revision, owner, value))
            if existing:
                return jsonify(public_receipt(existing))
        with guarded(protocol, revision) as owner:
            service.refresh()
            return jsonify(public_receipt(manager.accept(protocol, revision, owner, value)))

    @app.get(candidate + '/epochs')
    def workbench_epochs(protocol, revision):
        filters = query_filters({'candidate_scope_revision', 'offset', 'limit', 'anchor_uuid', 'include_cells'})
        with guarded(protocol, revision, filters) as owner:
            context = checked(protocol, revision, owner, request.args.get('candidate_scope_revision'), filters)
            include = request.args.get('include_cells', 'false')
            if include not in ('true', 'false'):
                raise ValueError('include_cells must be true or false')
            page = manager.frozen_service(context).epoch_page(protocol, filters, int(request.args.get('offset', 0)),
                int(request.args.get('limit', 80)), anchor_uuid=request.args.get('anchor_uuid'), include_cells=include == 'true')
            page.pop('_shared_annotation_generation', None)
            row_decisions(context, page['epochs'])
            return jsonify(finish(context, page))

    @app.get(candidate + '/epochs/<epoch>')
    def workbench_epoch(protocol, revision, epoch):
        query_filters({'candidate_scope_revision'})
        with guarded(protocol, revision) as owner:
            context = checked(protocol, revision, owner, request.args.get('candidate_scope_revision'))
            row = manager.frozen_service(context).epoch(epoch, protocol)
            row_decisions(context, [row])
            return jsonify(finish(context, row))

    @app.errorhandler(TraceViewConflict)
    def trace_view_conflict(error):
        return jsonify(error=str(error), code='trace_view_conflict'), 409

    @app.get('/api/trace-views/<token>/epochs/<epoch>/display')
    def prepared_trace_display(token, epoch):
        from workspace_trace_geometry import (ALGORITHM, CONTENT_TYPE, GeometryUnavailable,
            MAX_SAMPLES, prepare_display_geometry, encode_display_geometry)
        from workspace_trace_binary import begin_trace_timing, mark_trace_timing, read_trace_batch
        if (set(request.args) != {'stream_uuid', 'count', 'physical_width', 'algorithm'} or
                any(len(request.args.getlist(key)) != 1 for key in request.args) or
                request.args['algorithm'] != ALGORITHM or
                request.headers.get('X-Disco-Trace-Priority') == 'background' or
                not any(media == CONTENT_TYPE and quality > 0 for media, quality in request.accept_mimetypes)):
            raise ValueError('Display geometry requires explicit foreground whole-view options')
        count, width = int(request.args['count']), float(request.args['physical_width'])
        if not 0 < count <= MAX_SAMPLES or not 0 < width <= 16384:
            raise ValueError('Display geometry window exceeds its bound')
        timing = begin_trace_timing()
        owner = display_actor()
        witness = trace_views.capture(token, epoch, owner)
        mark_trace_timing(timing, 'open')
        from workspace_trace_native import capture_native_timing, NATIVE_TIMING_METRICS
        with capture_native_timing(timing):
            batch = read_trace_batch(service, epoch, request.args['stream_uuid'], 0,
                min(count, 100000), (count + 99999) // 100000, binary=True, timing=timing, foreground=True)
            if batch.get('total_samples') != count:
                raise ValueError('Display geometry sample count changed')
            try:
                geometry = prepare_display_geometry(batch, width)
            except GeometryUnavailable as error:
                # Only this explicit non-reduction case permits the client to use
                # its ordinary exact prepared read. Identity failures never do.
                return jsonify(error=str(error), code='trace_geometry_unavailable'), 409
        mark_trace_timing(timing, 'read')
        geometry = trace_views.finish(token, epoch, owner, witness, geometry)
        mark_trace_timing(timing, 'close')
        response = app.response_class(encode_display_geometry(geometry, dumps=app.json.dumps), mimetype=CONTENT_TYPE)
        mark_trace_timing(timing, 'encode')
        if timing is not None:
            response.headers['Server-Timing'] = ', '.join(
                f'trace_{stage};dur={timing[stage]:.3f}' for stage in
                ('open', 'capture', 'samples', 'validate', 'read', 'close', 'encode',
                 *NATIVE_TIMING_METRICS)
                if stage in timing)
        response.vary.add('Accept')
        return response

    @app.get('/api/trace-views/<token>/epochs/<epoch>/trace')
    def prepared_trace(token, epoch):
        # Display-only historical membership: no SQL, DB lock, tag/draft reads,
        # or current-candidate claims. Mutation endpoints never accept this token.
        if (request.args.keys() - {'stream_uuid', 'start', 'count', 'chunks'} or
                any(len(request.args.getlist(key)) != 1 for key in request.args) or
                request.headers.get('X-Disco-Trace-Priority') == 'background'):
            raise ValueError('Display trace requires unique foreground window options')
        from workspace_trace_binary import (begin_trace_timing, mark_trace_timing,
            read_trace_batch, trace_batch_response, wants_binary_trace)
        timing = begin_trace_timing()
        owner = display_actor()
        entry = trace_views.capture(token, epoch, owner)
        mark_trace_timing(timing, 'open')
        start, count = int(request.args.get('start', 0)), int(request.args.get('count', 20000))
        binary = wants_binary_trace()
        if 'chunks' in request.args:
            result = read_trace_batch(service, epoch, request.args['stream_uuid'], start, count,
                int(request.args['chunks']), binary=binary, timing=timing, foreground=True)
        else:
            result = service.trace(epoch, request.args['stream_uuid'], start, count)
        mark_trace_timing(timing, 'read')
        result = trace_views.finish(token, epoch, owner, entry, result)
        mark_trace_timing(timing, 'close')
        return trace_batch_response(app, result, timing, binary=binary) if 'chunks' in request.args else jsonify(result)

    @app.get(candidate + '/epochs/<epoch>/trace')
    def workbench_trace(protocol, revision, epoch):
        query_filters({'candidate_scope_revision', 'stream_uuid', 'start', 'count', 'chunks'})
        from workspace_trace_binary import (begin_trace_timing, mark_trace_timing, trace_batch_response,
            wants_binary_trace, read_trace_batch)
        binary = wants_binary_trace() if 'chunks' in request.args else False
        timing = begin_trace_timing() if 'chunks' in request.args else None
        with guarded(protocol, revision) as owner:
            context = checked(protocol, revision, owner, request.args.get('candidate_scope_revision'))
            scoped = manager.frozen_service(context)
            if epoch not in context['pending']:
                raise ValueError('Trace epoch is outside the frozen incoming candidate')
            if 'chunks' in request.args:
                if request.headers.get('X-Disco-Trace-Priority') == 'background':
                    raise ValueError('Trace batches require a foreground request')
                mark_trace_timing(timing, 'open')
                result = read_trace_batch(scoped, epoch, request.args.get('stream_uuid'),
                    int(request.args.get('start', 0)), int(request.args.get('count', 20000)),
                    int(request.args['chunks']), binary=binary, timing=timing)
                mark_trace_timing(timing, 'read')
            else:
                result = scoped.trace(epoch, request.args.get('stream_uuid'),
                    int(request.args.get('start', 0)), int(request.args.get('count', 20000)))
            result = finish(context, result)
        # Samples and response fences are detached. Complete the closing guards
        # before encoding so a large window does not block unrelated DB reads.
        if 'chunks' in request.args:
            mark_trace_timing(timing, 'close')
            return trace_batch_response(app, result, timing, binary=binary)
        return jsonify(result)

    @app.get(candidate + '/tree')
    def workbench_tree(protocol, revision):
        filters = query_filters({'candidate_scope_revision', 'splits'})
        with guarded(protocol, revision, filters) as owner:
            context = checked(protocol, revision, owner, request.args.get('candidate_scope_revision'), filters)
            value = manager.frozen_service(context).tree(protocol, filters, request.args.get('splits', context['candidate']['splits']))
            return jsonify(finish(context, value))

    @app.get(candidate + '/tree-fields')
    def workbench_fields(protocol, revision):
        filters = query_filters({'candidate_scope_revision', 'splits'})
        with guarded(protocol, revision, filters) as owner:
            context = checked(protocol, revision, owner, request.args.get('candidate_scope_revision'), filters)
            value = manager.frozen_service(context).tree_fields(protocol, filters, splits=request.args.get('splits'))
            return jsonify(finish(context, copy.deepcopy(value)))

    @app.post(candidate + '/tree/page')
    def workbench_tree_page(protocol, revision):
        value = body({'candidate_scope_revision'}, {'filters', 'splits', 'path', 'offset', 'limit', 'revision', 'anchor_uuid',
            'include_ancestors', 'ancestor_offsets', 'counts_only', 'selection_token'})
        value.pop('selection_token', None)
        expected = value.pop('candidate_scope_revision')
        include_ancestors = value.pop('include_ancestors', False)
        ancestor_offsets = value.pop('ancestor_offsets', [])
        if (type(include_ancestors) is not bool or not isinstance(ancestor_offsets, list)
                or len(ancestor_offsets) > 8
                or any(offset is not None and (type(offset) is not int or not 0 <= offset <= 10_000_000) for offset in ancestor_offsets)
                or ancestor_offsets and not include_ancestors):
            raise ValueError('Malformed tree column navigation options')
        filters = validate_filters(value.get('filters'))
        with guarded(protocol, revision, filters) as owner:
            context = checked(protocol, revision, owner, expected, filters)
            try:
                pager = TreePages(manager.frozen_service(context))
                if include_ancestors:
                    page, parents = pager.column_pages(dict(protocol_uuid=protocol, **value), ancestor_offsets)
                else:
                    page, parents = pager.page(dict(protocol_uuid=protocol, **value)), []
            except StaleTreePage as error:
                raise WorkbenchConflict(str(error)) from error
            if page.get('epochs'):
                row_decisions(context, page['epochs'])
            result = finish(context, page)
            if include_ancestors:
                # Every page is freshly read under the same locks and closing
                # authority check; no retained client page grants permission.
                for parent in parents:
                    parent.update({key: result[key] for key in ('generation', 'candidate_scope_revision',
                        'query_revision', 'expected_binding_version')})
                result['ancestor_pages'] = parents
            return jsonify(result)

    @app.post(candidate + '/tree/selection')
    def workbench_tree_selection(protocol, revision):
        value = body({'candidate_scope_revision', 'revision', 'path', 'expected_count'}, {'filters', 'splits', 'selection_token'})
        value.pop('selection_token', None)
        expected = value.pop('candidate_scope_revision')
        count = value.pop('expected_count')
        if type(count) is not int or count < 1 or not isinstance(value['revision'], str):
            raise ValueError('Tree selection requires a current revision and a positive exact epoch count')
        filters = validate_filters(value.get('filters'))
        with guarded(protocol, revision, filters) as owner:
            context = checked(protocol, revision, owner, expected, filters)
            if count > len(context['pending']):
                raise WorkbenchConflict('The complete branch count changed. Refresh this view.')
            pager = TreePages(manager.frozen_service(context))
            try:
                result = pager.selection(dict(protocol_uuid=protocol, **value), count, max_count=len(context['pending']))
            except StaleTreePage as error:
                raise WorkbenchConflict(str(error)) from error
            return jsonify(finish(context, result))

    @app.post(candidate + '/list-selection')
    def workbench_list_selection(protocol, revision):
        value = body({'candidate_scope_revision', 'cells'}, {'filters', 'selection_token'})
        cells = value['cells']
        if (not isinstance(cells, list) or len(cells) > 1000
                or any(not isinstance(cell, dict) or set(cell) != {'cell_uuid', 'epochs'}
                    or not isinstance(cell['cell_uuid'], str) or type(cell['epochs']) is not int or cell['epochs'] < 0 for cell in cells)):
            raise ValueError('Selection requires exact cell counts in batches of at most 1,000 cells')
        cells = [dict(cell_uuid=str(uuid.UUID(cell['cell_uuid'])), epochs=cell['epochs']) for cell in cells]
        if len({cell['cell_uuid'] for cell in cells}) != len(cells):
            raise ValueError('Selection requires unique cells')
        filters = validate_filters(value.get('filters'))
        with guarded(protocol, revision, filters) as owner:
            context = checked(protocol, revision, owner, value['candidate_scope_revision'], filters)
            scoped = manager.frozen_service(context)
            result, seen = [], set()
            # Use the existing page reader, including custom overrides, so its
            # chronology and cell-filter semantics remain exact. Only admission
            # is shared; each bounded page is still checked for completeness.
            for cell in cells:
                identities = []
                for offset in range(0, max(1, cell['epochs']), 60):
                    page = scoped.epoch_page(protocol, {**filters, 'cell_uuid': cell['cell_uuid']}, offset, 60)
                    rows = page.get('epochs')
                    if (page.get('total') != cell['epochs'] or page.get('offset') != offset
                            or not isinstance(rows, list) or len(rows) != min(60, cell['epochs'] - offset)):
                        raise WorkbenchConflict('Incoming cell membership changed during selection')
                    for row in rows:
                        identity = row.get('epoch_uuid')
                        if (identity not in context['pending'] or row.get('cell_uuid') != cell['cell_uuid']
                                or identity in seen):
                            raise WorkbenchConflict('Incoming selection contains duplicate or unavailable identities')
                        seen.add(identity)
                        identities.append(identity)
                result.append(dict(**cell, epoch_uuids=identities))
            return jsonify(finish(context, dict(cells=result, count=len(seen),
                epoch_uuids=[identity for cell in result for identity in cell['epoch_uuids']])))

    @app.post(candidate + '/selection-summary')
    def workbench_selection_summary(protocol, revision):
        value = body({'candidate_scope_revision'}, {'epoch_uuids', 'selection_token'})
        if ('epoch_uuids' in value) == ('selection_token' in value):
            raise ValueError('Selection summary requires exactly one selection source')
        supplied = value.get('epoch_uuids', [])
        if not isinstance(supplied, list) or len(supplied) > 1000 or any(not isinstance(key, str) for key in supplied):
            raise ValueError('Selection summary requires at most 1,000 epoch UUIDs')
        try:
            ids = [str(uuid.UUID(key)) for key in supplied]
        except (ValueError, AttributeError) as error:
            raise ValueError('Selection summary requires valid epoch UUIDs') from error
        if len(set(ids)) != len(ids):
            raise ValueError('Selection summary requires distinct epoch UUIDs')
        with guarded(protocol, revision) as owner:
            context = checked(protocol, revision, owner, value['candidate_scope_revision'])
            if 'selection_token' in value:
                ids = manager.selection_manifest(context, value['selection_token'])['ids']
            if set(ids) - set(context['pending']):
                raise ValueError('Selected epochs are outside the frozen incoming candidate')
            if set(ids) & context['unavailable']:
                raise WorkbenchConflict('Selected frozen recording metadata changed or is unavailable')
            cells = {}
            for key in ids:
                row = service.rows.get(key)
                if row is None or not row.get('cell_uuid'):
                    raise WorkbenchConflict('Selected recording metadata is unavailable')
                identity, cell_type = row['cell_uuid'], row.get('cell_type')
                if cell_type is not None and not isinstance(cell_type, str):
                    raise WorkbenchConflict('Selected cell type is unavailable')
                cell = dict(cell_uuid=identity, cell_type=cell_type)
                if identity in cells and cells[identity] != cell:
                    raise WorkbenchConflict('Selected recordings disagree on recorded cell type')
                cells[identity] = cell
            return jsonify(finish(context, dict(epoch_uuids=ids, counts=dict(epochs=len(ids), cells=len(cells)),
                cells=[cells[key] for key in sorted(cells)])))

    @app.post(candidate + '/summary')
    def workbench_candidate_summary(protocol, revision):
        value = body({'candidate_scope_revision'}, {'filters', 'selection_token'})
        filters = validate_filters(value.get('filters'))
        with guarded(protocol, revision, filters) as owner:
            context = checked(protocol, revision, owner, value['candidate_scope_revision'], filters)
            scoped = manager.frozen_service(context)
            counts = scoped._counts(scoped.filtered_rows(protocol, filters))
            return jsonify(finish(context, dict(counts=counts, matched_count=counts['epochs'],
                filters=filters, filters_sha256=checksum(filters), distributions_available=False)))

    from disco.workbench.workbench_exports import register_workbench_export_routes
    register_workbench_export_routes(app, manager, app.extensions['curation_store'], db_lock, guarded, actor, body)
    from disco.workbench.workbench_pending import register_pending_routes
    register_pending_routes(app, manager, db_lock, guarded, actor, body, public_context)
