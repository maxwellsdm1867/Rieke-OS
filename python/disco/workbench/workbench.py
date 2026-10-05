"""Native, frozen incoming review and additive publication (contract v1).

Proposal B, candidate C, current main M and actor draft remain separate.
No method here runs C's predicate to reconstruct its saved membership.
Callers hold DB, registration and annotation guards for the whole operation.
"""
from __future__ import annotations

import base64
import contextlib
import copy
import datetime as dt
import json
import uuid

from workspace_audit import build_audit_payload
from disco.decisions.curation import RevisionConflict
from disco.workbench.diff import summarize_diff
from disco.workbench.recipes import checksum
from workspace_protocol_identity import require_protocol_compatibility


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


def _members(recipe):
    members = {row['uuid']: row['metadata_hash'] for row in recipe['epochs']}
    if len(members) != len(recipe['epochs']):
        raise ValueError('Frozen membership contains duplicate epoch identities')
    return members


class ProtocolWorkbench:
    def __init__(self, service, history, suggestions, state, revision_guard, *, tables=None):
        self.service, self.history, self.suggestions = service, history, suggestions
        self.state, self.revision_guard = state, revision_guard
        self.project = service.project['project_uuid']
        self._tables = tables

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

    def proposal(self, protocol, revision):
        rows = (self.suggestions.Table & dict(project_uuid=self.project,
            protocol_uuid=protocol)).to_dicts()
        found = [row['summary'] for row in rows if row['summary']['candidate_revision_uuid'] == revision]
        if not found:
            raise KeyError('Incoming candidate not found for this protocol in this project')
        candidate = self.history.get(revision)['recipe']
        baseline = self.history.get(found[0]['baseline_revision_uuid'])['recipe']
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

    def _additive_lineage(self, main, baseline, protocol, version, baseline_version):
        """A superset alone is insufficient: prove every actual parent transition."""
        seen = set()
        transitions = (self.tables[2] & dict(project_uuid=self.project, protocol_uuid=protocol)).to_dicts()
        while main['revision_uuid'] != baseline['revision_uuid']:
            identity = main['revision_uuid']
            if identity in seen or len(seen) >= 1000 or main.get('membership_kind') != 'additive_union':
                return False
            seen.add(identity)
            parent = main.get('parent_revision_uuid')
            publication = main.get('additive_publication', {})
            if not parent or publication.get('previous_revision_uuid') != parent:
                return False
            previous = self.history.get(parent)['recipe']
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
        key = self.key(protocol, revision, actor)
        summary, baseline, candidate = self.proposal(protocol, revision)
        header, decisions = self.draft(key)
        binding = self.history.protocol_binding(protocol)
        if query_revision_guard is None:
            result, _, query_revision = self.state(protocol)
        else:
            query_revision = query_revision_guard()
            result = self.service.query_result(protocol) if binding is None else None
        main = binding['recipe'] if binding else None
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
        shared_revision = shared.snapshot()['revision'] if shared else None
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
        return dict(**evidence, summary=summary, baseline=baseline, candidate=candidate, main=main,
            previous=previous, incoming=incoming, pending=pending, decisions=decisions,
            conflicts=conflicts, base_conflicts=base_conflicts, main_conflicts=main_conflicts,
            unavailable=unavailable, ineligible=ineligible,
            blocked_main=ineligible_main, annotation_changed=annotation_changed, valid_base=valid_base,
            source_scope=scope, already_present=set(incoming) & set(previous))

    @staticmethod
    def check_scope(context, expected):
        if not isinstance(expected, str) or expected != context['candidate_scope_revision']:
            raise WorkbenchConflict('Candidate, main, sources, annotations or draft changed; reload the frozen context')

    @staticmethod
    def publishable(context, selected):
        if context['base_conflicts'] or context['main_conflicts'] or selected & (context['unavailable'] | context['conflicts']):
            raise WorkbenchConflict('Frozen epoch fingerprints changed or are unavailable; explicit reconciliation required')
        if selected & context['ineligible'] or context['blocked_main']:
            raise WorkbenchConflict('Source eligibility blocks publication; reconcile excluded sources explicitly')
        if context['annotation_changed']:
            raise WorkbenchConflict('Candidate predicate annotations changed; save and review a fresh proposal')
        if not context['valid_base']:
            raise WorkbenchConflict('Candidate has an unrelated or replacement base; review a fresh proposal')

    def decision(self, context, identity):
        saved = context['decisions'].get(identity, {})
        valid = (saved.get('metadata_hash') == context['incoming'][identity]
                 and identity not in context['unavailable'])
        excluded = bool(saved.get('excluded')) if valid else False
        return dict(selected=(context['selection_mode'] == 'all' or (valid and bool(saved.get('selected')))) and not excluded,
                    reviewed=bool(saved.get('reviewed')) if valid else False, excluded=excluded)

    def selection(self, context, mode):
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

    def preview(self, context, body):
        self.check_scope(context, body['expected_candidate_scope_revision'])
        if type(body['expected_draft_version']) is not int or body['expected_draft_version'] != context['draft_version']:
            raise WorkbenchConflict('Review draft changed')
        selected = self.selection(context, body['mode'])
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
        if context['unavailable'] & context['pending'].keys():
            raise WorkbenchConflict('Frozen candidate metadata is unavailable or changed; browsing cannot reconstruct it')
        scoped = copy.copy(self.service)
        recipe = copy.copy(context['candidate'])
        recipe['epochs'] = [dict(uuid=key, metadata_hash=value) for key, value in context['pending'].items()]
        binding = dict(version=1, revision_uuid=recipe['revision_uuid'], recipe=recipe)
        scoped.binding_provider = lambda protocol: binding if protocol == context['protocol_uuid'] else self.service.binding(protocol)
        scoped.binding_header_provider = None
        scoped._tree_catalog_cache = {}
        scoped._epoch_page_cache = None
        scoped._tree_scope_cache = {}
        scoped._tree_page_scope_cache = None
        scoped._registered_tree_cache = getattr(self.service, '_registered_tree_cache', None)
        def decisions(protocol, fingerprints):
            return {key: dict(included=True, reviewed=False, review_state='unreviewed',
                tags=[], revision=0, metadata_fingerprint=value, approval_stale=False)
                for key, value in fingerprints.items() if key in context['pending']}
        scoped.curation_provider = decisions
        return scoped

    def queue(self, protocol, actor, limit=20, cursor=None):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Queue page limit must be 1–100')
        protocol = str(uuid.UUID(protocol))
        if protocol not in self.service.protocols:
            raise KeyError('Unknown protocol')
        records = self.original_records(protocol)
        records.sort(key=lambda row: (row['summary']['created_at'], row['suggestion_uuid']), reverse=True)
        items, pending, eligible_union, cell_ids, witnesses = [], set(), set(), {}, []
        cumulative = self.cumulative_draft(protocol, actor)
        historical_conflict = False
        if cumulative:
            review_header, cumulative_decisions = cumulative
        else:
            from disco.workbench.workbench_pending import draft_carry
            try:
                review_header, cumulative_decisions, _ = draft_carry(self, protocol, actor, self.service._fingerprints)
            except WorkbenchConflict:
                review_header, cumulative_decisions = {}, None
                historical_conflict = True
        raw_pending = {}
        def excluded(context, key):
            if cumulative_decisions is None:
                return self.decision(context, key)['excluded']
            decision = cumulative_decisions.get(key, {})
            return decision.get('metadata_hash') == context['incoming'][key] and bool(decision.get('excluded'))
        for row in records:
            revision = row['summary']['candidate_revision_uuid']
            context = self.context(protocol, revision, actor)
            raw_pending.update(context['pending'])
            accepted_receipts = (self.tables[2] & dict(project_uuid=self.project, protocol_uuid=protocol,
                candidate_revision_uuid=revision)).to_dicts()
            eligible = set(context['pending']) - context['ineligible'] - context['unavailable'] - context['conflicts']
            eligible = {key for key in eligible if not excluded(context, key)}
            blocked = not context['valid_base'] or context['annotation_changed'] or bool(context['conflicts'] or context['unavailable'] or context['blocked_main'])
            status = ('conflict' if blocked else 'source_blocked' if context['ineligible'] else
                      'accepted' if not context['pending'] and accepted_receipts else
                      'covered' if not context['pending'] else 'deferred' if context['deferred'] else
                      'pending' if context['main_revision_uuid'] == context['baseline_revision_uuid'] else 'pending_rebased')
            unmerged = {key for key in context['pending'] if not excluded(context, key)}
            pending |= unmerged
            for key in unmerged:
                saved_cell = row['summary'].get('incoming_cell_uuids', {}).get(key)
                if saved_cell:
                    cell_ids[key] = saved_cell
                elif key not in context['unavailable']:
                    cell_ids[key] = self.service.rows[key]['cell_uuid']
            if not blocked:
                eligible_union |= eligible
            items.append(dict(**{key: value for key, value in row['summary'].items() if key != 'incoming_cell_uuids'},
                status=status, pending_epoch_count=len(unmerged), eligible_pending_epoch_count=len(eligible) if not blocked else 0,
                candidate_scope_revision=context['candidate_scope_revision'], draft_version=context['draft_version']))
            witnesses.append(context['candidate_scope_revision'])
        # Initializing a draft must not create a queue-refresh/prepare feedback
        # loop. Its initial version is neutral; actual subsequent CAS mutations
        # and effective decisions remain queue fences. Recipe IDs are separate.
        review_witness = dict(version_delta=max(review_header.get('version', 1) - 1, 0) if cumulative else 0,
            deferred=bool(review_header.get('deferred')), historical_conflict=historical_conflict,
            decisions={key: {field: saved[field] for field in ('metadata_hash', 'selected', 'reviewed', 'excluded')}
                for key, saved in (cumulative_decisions or {}).items() if raw_pending.get(key) == saved['metadata_hash']})
        revision = checksum(dict(project_uuid=self.project, protocol_uuid=protocol, actor=actor,
                                 witnesses=witnesses, items=items, cumulative_review=review_witness))
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
            pending_cell_count=len(set(cell_ids.values())) if pending <= cell_ids.keys() else None,
            pending_cell_count_available=pending <= cell_ids.keys(), eligible_pending_epoch_count=len(eligible_union),
            eligible_pending_cell_count=len({self.service.rows[key]['cell_uuid'] for key in eligible_union}),
            queue_revision=revision, next_cursor=next_cursor, total_candidate_count=len(items),
            capabilities=dict(frozen_browse=True, drafts=True, additive_accept=True,
                incoming_export=getattr(self, 'incoming_export', False),
                cumulative_pending_browse=getattr(self, 'cumulative_pending_browse', False)))


def public_receipt(receipt):
    result = copy.deepcopy({key: value for key, value in receipt.items()
                           if key not in {'accepted_fingerprints', 'selected_epoch_uuids', 'accepted_epoch_uuids'}})
    if 'accepted_epoch_uuids' not in receipt:
        return result
    ids = receipt['accepted_epoch_uuids']
    result.update(accepted_epoch_uuids=ids[:250], accepted_epoch_uuids_total=len(ids),
                  accepted_epoch_uuids_truncated=len(ids) > 250)
    return result


def register_workbench_routes(app, service, history, suggestions, state, revision_guard,
                              db_lock, registration_locks):
    import os
    from flask import jsonify, request
    from workspace_service import validate_filters
    from disco.navigation.tag_predicates import annotation_locks
    from disco.navigation.tree_pages import TreePages, StaleTreePage
    manager = ProtocolWorkbench(service, history, suggestions, state, revision_guard)
    if hasattr(service.dj, 'Schema'):
        manager.tables  # Additive DDL before startup recovery/checkpoint capture.
    app.extensions['protocol_workbench'] = manager

    def actor():
        shared = getattr(service, 'shared_annotations', None)
        from disco.decisions.author_preferences import selected_author
        profile = selected_author() or (shared.default_profile if shared else None)
        return profile['profile_uuid'] if profile else os.environ.get('USER', 'local-user')

    def body(required, optional=()):
        if request.args or (request.content_length is not None and request.content_length > 65536):
            raise ValueError('Workbench body must be at most 64KiB with no URL options')
        value = request.get_json()
        if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
            raise ValueError('Malformed Workbench request; required fences or supported fields missing')
        return value

    def query_filters(allowed=()):
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
                yield actor()

    def start_read(context, filters=None):
        from disco.metadata.explore_queries import generation, StaleQuery
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
        return value

    def row_decisions(context, rows):
        shared = getattr(service, 'shared_annotations', None)
        annotations = shared.for_epochs([service.rows[row['epoch_uuid']] for row in rows]) if shared else {}
        for row in rows:
            row['review_decision'] = manager.decision(context, row['epoch_uuid'])
            if annotations:
                row['annotations'] = annotations[row['epoch_uuid']]

    def public_context(context, filters=None, *, transaction_authority=None):
        if transaction_authority is not None:
            context['_transaction_authority'] = transaction_authority
        start_read(context, filters)
        scoped = manager.frozen_service(context)
        protocol = copy.deepcopy(scoped.protocol(context['protocol_uuid'], filters))
        protocol.update(query_revision=context['candidate_scope_revision'],
            expected_query_revision=context['expected_query_revision'], expected_binding_version=context['expected_binding_version'],
            source_eligibility=dict(excluded_epoch_count=len(context['ineligible']), propagation_required=bool(context['ineligible']),
                source_scope_revision=context['source_scope_revision']), review_scope='incoming_candidate')
        ids = sorted(context['decisions'])
        return finish(context, dict(contract_version=1, protocol=protocol,
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
                or context['blocked_main'] or context['annotation_changed'] or not context['valid_base'])))

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
                counts.append(dict(protocol_uuid=protocol, **{key: value[key] for key in
                    ('pending_cell_count', 'pending_epoch_count', 'queue_revision')}))
        return jsonify(contract_version=1, workbench_counts=counts)

    @app.get(candidate + '/context')
    def workbench_context(protocol, revision):
        filters = query_filters({'candidate_scope_revision'})
        with guarded(protocol, revision, filters) as owner:
            context = manager.context(protocol, revision, owner)
            if 'candidate_scope_revision' in request.args:
                manager.check_scope(context, request.args['candidate_scope_revision'])
            return jsonify(public_context(context, filters))

    @app.patch(candidate + '/draft')
    def workbench_patch(protocol, revision):
        value = body({'expected_version', 'expected_candidate_scope_revision'}, {'decisions', 'selection_mode', 'deferred'})
        with guarded(protocol, revision) as owner:
            return jsonify(public_context(manager.patch(protocol, revision, owner, value)))

    @app.post(candidate + '/preview')
    def workbench_preview(protocol, revision):
        value = body({'expected_candidate_scope_revision', 'expected_draft_version', 'mode'})
        with guarded(protocol, revision) as owner:
            return jsonify(manager.preview(manager.context(protocol, revision, owner), value)[0])

    @app.post(candidate + '/accept')
    def workbench_accept(protocol, revision):
        value = body({'expected_candidate_scope_revision', 'expected_draft_version', 'mode', 'preview_sha256',
                      'expected_binding_version', 'expected_query_revision', 'operation_uuid'})
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

    @app.get(candidate + '/epochs/<epoch>/trace')
    def workbench_trace(protocol, revision, epoch):
        query_filters({'candidate_scope_revision', 'stream_uuid', 'start', 'count'})
        with guarded(protocol, revision) as owner:
            context = checked(protocol, revision, owner, request.args.get('candidate_scope_revision'))
            scoped = manager.frozen_service(context)
            if epoch not in context['pending']:
                raise ValueError('Trace epoch is outside the frozen incoming candidate')
            return jsonify(finish(context, scoped.trace(epoch, request.args.get('stream_uuid'),
                int(request.args.get('start', 0)), int(request.args.get('count', 20000)))))

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
        value = body({'candidate_scope_revision'}, {'filters', 'splits', 'path', 'offset', 'limit', 'revision', 'anchor_uuid'})
        expected = value.pop('candidate_scope_revision')
        filters = validate_filters(value.get('filters'))
        with guarded(protocol, revision, filters) as owner:
            context = checked(protocol, revision, owner, expected, filters)
            try:
                page = TreePages(manager.frozen_service(context)).page(dict(protocol_uuid=protocol, **value))
            except StaleTreePage as error:
                raise WorkbenchConflict(str(error)) from error
            if page.get('epochs'):
                row_decisions(context, page['epochs'])
            return jsonify(finish(context, page))

    @app.post(candidate + '/summary')
    def workbench_candidate_summary(protocol, revision):
        value = body({'candidate_scope_revision'}, {'filters'})
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
