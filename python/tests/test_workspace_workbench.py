"""Additive authority tests: isolated transactional SQL doubles, no native data."""
import copy
import json
import unittest
import uuid
from unittest.mock import patch

from test_workspace_suggestions import ImportSuggestionTests
from test_workspace_curation import Table
from workspace_workbench import ProtocolWorkbench, WorkbenchConflict


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        fixture = ImportSuggestionTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.case = fixture, fixture.case
        self.manager = self.case.app.extensions['protocol_workbench']
        self.tables = (Table(('project_uuid', 'protocol_uuid', 'candidate_revision_uuid', 'actor')),
            Table(('project_uuid', 'protocol_uuid', 'candidate_revision_uuid', 'actor', 'epoch_uuid')),
            Table(('project_uuid', 'operation_uuid')))
        self.case.connection.tables.extend(self.tables)
        self.manager._tables = self.tables
        verified = patch.object(self.case.service, '_verified_source', return_value=(fixture.source, None))
        verified.start()
        self.addCleanup(verified.stop)
        # Resolve a deterministic local actor; no user's author preference file is read/written.
        self.author = patch('workspace_author_preferences.selected_author', return_value={'profile_uuid': 'actor-one'})
        self.author.start()
        self.addCleanup(self.author.stop)
        fixture.run_import()
        # Import preflight's source table uses a real fixture digest; the inherited
        # service deliberately uses 'a'*64 as its pre-existing metadata source.
        if not any(row['source_sha256'] == 'a' * 64 for row in self.case.sources.rows):
            self.case.sources.insert1(dict(project_uuid=self.case.service.project['project_uuid'], source_sha256='a' * 64))
        self.protocol = self.case.service.protocol_id
        self.revision = self.case.suggestion_rows.rows[0]['summary']['candidate_revision_uuid']
        self.root = self.case.base + '/workbench/candidates/' + self.revision
        self.added = next(key for key in self.case.service.rows if key not in fixture.before_ids)

    def get_context(self, root=None):
        response = self.case.client.get((root or self.root) + '/context')
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def save(self, context, decisions=(), **extra):
        return self.case.client.patch(self.root + '/draft', json=dict(
            expected_version=context['draft']['draft_version'], expected_candidate_scope_revision=context['candidate_scope_revision'],
            decisions=list(decisions), **extra), headers=self.case.headers)

    def accepted_request(self, mode='all'):
        context = self.get_context()
        context = self.save(context, selection_mode=mode).get_json()
        request = dict(expected_candidate_scope_revision=context['candidate_scope_revision'],
            expected_draft_version=context['draft']['draft_version'], mode=mode)
        preview = self.case.client.post(self.root + '/preview', json=request, headers=self.case.headers)
        self.assertEqual(preview.status_code, 200, preview.get_json())
        request.update(**{field: preview.get_json()[field] for field in
            ('preview_sha256', 'expected_binding_version', 'expected_query_revision')}, operation_uuid=str(uuid.uuid4()))
        return request

    def accept(self, request, root=None):
        return self.case.client.post((root or self.root) + '/accept', json=request, headers=self.case.headers)

    def test_frozen_incoming_browse_does_not_run_recipe_or_include_main_and_context_fences_every_surface(self):
        # A frozen reader owns its scope cache; it must not mutate live browsing.
        live_cache = (None, {'live': object()}, {})
        self.case.service._tree_page_scope_cache = live_cache
        scoped = self.manager.frozen_service(self.manager.context(self.protocol, self.revision, 'actor-one'))
        self.assertIsNone(scoped._tree_page_scope_cache)
        self.assertIs(self.case.service._tree_page_scope_cache, live_cache)
        with patch.object(self.case.service, 'explore_preview', side_effect=AssertionError('Frozen reads must not rerun')):
            context = self.get_context()
            self.assertEqual(context['protocol']['counts']['epochs'], 1)
            self.assertEqual(context['counts']['pending_cells'], 1)
            token = context['candidate_scope_revision']
            page = self.case.client.get(self.root + '/epochs', query_string={'candidate_scope_revision': token, 'include_cells': 'true'})
            self.assertEqual(page.status_code, 200, page.get_json())
            self.assertEqual([row['epoch_uuid'] for row in page.get_json()['epochs']], [self.added])
            self.assertFalse(page.get_json()['epochs'][0]['review_decision']['reviewed'])
            tree = self.case.client.post(self.root + '/tree/page', json={'candidate_scope_revision': token, 'splits': 'cell'}, headers=self.case.headers)
            self.assertEqual(tree.status_code, 200, tree.get_json())
            summary = self.case.client.post(self.root + '/summary', json={'candidate_scope_revision': token,
                'filters': {'cell_uuid': self.added}}, headers=self.case.headers)
            self.assertEqual(summary.status_code, 200, summary.get_json())
            self.assertEqual(summary.get_json()['matched_count'], 0)
            self.assertFalse(summary.get_json()['distributions_available'])
            for path in ('/epochs', '/tree', '/tree-fields', '/epochs/' + self.added, '/epochs/' + self.added + '/trace'):
                self.assertEqual(self.case.client.get(self.root + path).status_code, 409, path)
            outside = self.case.client.get(self.root + '/epochs/' + self.fixture.before_ids[0], query_string={'candidate_scope_revision': token})
            self.assertEqual(outside.status_code, 400)
            anchor = self.case.client.get(self.root + '/epochs', query_string={'candidate_scope_revision': token, 'anchor_uuid': self.fixture.before_ids[0]})
            self.assertEqual(anchor.status_code, 400)
            with patch.object(self.case.service, 'trace', side_effect=AssertionError('Do not read outside scope')):
                trace = self.case.client.get(self.root + '/epochs/' + self.fixture.before_ids[0] + '/trace', query_string={'candidate_scope_revision': token, 'stream_uuid': str(uuid.uuid4())})
                self.assertEqual(trace.status_code, 400)

    def test_draft_cas_atomic_validation_actor_isolation_and_epoch_fingerprint_invalidation(self):
        context = self.get_context()
        saved = self.save(context, [dict(epoch_uuid=self.added, selected=True, reviewed=True)])
        self.assertEqual(saved.status_code, 200, saved.get_json())
        self.assertEqual(saved.get_json()['draft']['draft_version'], 1)
        stale = self.save(context, [dict(epoch_uuid=self.added, excluded=True)])
        self.assertEqual(stale.status_code, 409)
        before = copy.deepcopy([table.rows for table in self.tables])
        for invalid in ([dict(epoch_uuid=self.added, selected=1)],
                        [dict(epoch_uuid=self.added, reviewed=True), dict(epoch_uuid=self.fixture.before_ids[0], excluded=True)],
                        [dict(epoch_uuid=self.added, reviewed=True)] * 2):
            response = self.save(saved.get_json(), invalid)
            self.assertEqual(response.status_code, 400, response.get_json())
            self.assertEqual([table.rows for table in self.tables], before)
        other = self.manager.context(self.protocol, self.revision, 'actor-two')
        self.assertEqual(other['draft_version'], 0)
        self.assertFalse(self.manager.decision(other, self.added)['reviewed'])
        self.case.service._fingerprints[self.added] = 'c' * 64
        stale = self.case.client.get(self.root + '/epochs', query_string={'candidate_scope_revision': saved.get_json()['candidate_scope_revision']})
        self.assertEqual(stale.status_code, 409)
        fresh = self.manager.context(self.protocol, self.revision, 'actor-one')
        self.assertFalse(self.manager.decision(fresh, self.added)['reviewed'])
        self.assertTrue(fresh['unavailable'])

    def test_selected_requires_review_and_exclusion_wins_without_changing_main_curation(self):
        context = self.get_context()
        context = self.save(context, [dict(epoch_uuid=self.added, selected=True)]).get_json()
        preview = self.case.client.post(self.root + '/preview', json=dict(
            expected_candidate_scope_revision=context['candidate_scope_revision'],
            expected_draft_version=context['draft']['draft_version'], mode='selected'), headers=self.case.headers)
        self.assertEqual(preview.status_code, 400)
        context = self.save(context, [dict(epoch_uuid=self.added, selected=True, reviewed=True, excluded=True)]).get_json()
        self.assertFalse(context['draft']['decisions'][0]['selected'])
        self.assertTrue(context['draft']['decisions'][0]['excluded'])
        self.assertFalse(self.case.curation.rows)
        queue = self.case.client.get(self.case.base + '/workbench').get_json()
        self.assertEqual(queue['pending_cell_count'], 0)

    def test_accept_retains_main_curation_publishes_union_provenance_and_retry_after_restart_never_rebinds(self):
        response = self.case.client.post(self.case.base + '/curation', json=self.case.curation_body(
            {'tags_add': ['Preserve'], 'included': False}, [self.fixture.before_ids[0]]), headers=self.case.headers)
        self.assertEqual(response.status_code, 200)
        previous_curation = copy.deepcopy(self.case.curation.rows)
        request = self.accepted_request()
        accepted = self.accept(request)
        self.assertEqual(accepted.status_code, 200, accepted.get_json())
        receipt = accepted.get_json()
        self.assertEqual(receipt['accepted_epoch_uuids'], [self.added])
        binding = self.case.explorer_history.protocol_binding(self.protocol)
        self.assertEqual({row['uuid'] for row in binding['recipe']['epochs']}, set(self.fixture.before_ids) | {self.added})
        self.assertEqual(binding['recipe']['membership_kind'], 'additive_union')
        self.assertEqual(binding['recipe']['additive_publication']['candidate_revision_uuid'], self.revision)
        self.assertEqual(self.case.curation.rows, previous_curation)
        self.assertNotEqual(binding['revision_uuid'], self.revision)
        before = copy.deepcopy([table.rows for table in self.case.connection.tables])
        repeated = self.accept(request)
        self.assertEqual(repeated.get_json(), receipt)
        self.assertEqual([table.rows for table in self.case.connection.tables], before)
        with patch.object(self.case.service, 'refresh', side_effect=ValueError('Source unavailable')), \
             patch.object(self.manager, 'proposal', side_effect=ValueError('Candidate unavailable')):
            repeated = self.accept(request)
        self.assertEqual(repeated.get_json(), receipt)
        reloaded = ProtocolWorkbench(self.case.service, self.case.explorer_history, self.case.protocol_suggestions,
            self.manager.state, self.manager.revision_guard, tables=self.tables)
        self.assertEqual(reloaded.accept(self.protocol, self.revision, 'actor-one', request)['operation_uuid'], request['operation_uuid'])
        changed = self.accept({**request, 'mode': 'selected'})
        self.assertEqual(changed.status_code, 409)
        queue = self.case.client.get(self.case.base + '/workbench').get_json()
        self.assertEqual(queue['candidates'][0]['status'], 'accepted')
        self.assertEqual(queue['pending_epoch_count'], 0)

    def test_actual_binding_version_transition_rejects_rebinding_old_additive_recipe(self):
        receipt = self.accept(self.accepted_request()).get_json()
        baseline = self.case.suggestion_rows.rows[0]['summary']['baseline_revision_uuid']
        self.case.explorer_history.bind(baseline, self.protocol, 2, 'fixture', {}, 3)
        self.case.explorer_history.bind(receipt['binding']['revision_uuid'], self.protocol, 3, 'fixture', {}, 2)
        context = self.manager.context(self.protocol, self.revision, 'actor-one')
        self.assertFalse(context['valid_base'])

    def test_noop_accept_has_acceptance_audit_event_without_rebinding(self):
        first = self.accept(self.accepted_request()).get_json()
        version = first['binding']['version']
        request = self.accepted_request()
        second = self.accept(request).get_json()
        self.assertEqual(second['accepted_epoch_count'], 0)
        self.assertEqual(second['binding']['version'], version)
        self.assertIsNone(second['binding_event_uuid'])
        self.assertTrue(second['event_uuid'])
        event = next(row for row in self.case.events.rows if row['event_uuid'] == second['event_uuid'])
        self.assertEqual(event['action'], 'workbench_additions_accepted')

    def test_blocked_pending_counts_are_not_fabricated_empty_and_selected_eligible_addition_can_publish(self):
        self.fixture.source_sha = 'd' * 64
        eligible = self.fixture.add_recording()
        baseline = self.case.explorer_history.protocol_binding(self.protocol)
        result = self.case.protocol_suggestions.rerun([dict(protocol_uuid=self.protocol, protocol_name='Fixture',
            binding_version=baseline['version'], revision_uuid=baseline['revision_uuid'], recipe=baseline['recipe'])],
            'd' * 64, 'next.h5', 'actor-one')
        revision = result['suggestions'][0]['candidate_revision_uuid']
        source = self.case.service.rows[self.added]['source_sha256']
        self.case.data_store_states.insert1(dict(project_uuid=self.case.service.project['project_uuid'], source_sha256=source,
            query_excluded=True, archived=False, frozen=False, version=1, updated_at=None,
            actor='actor-one', server_actor='actor-one', reason='test'))
        queue = self.case.client.get(self.case.base + '/workbench').get_json()
        self.assertEqual(queue['pending_epoch_count'], 2)
        self.assertEqual(queue['eligible_pending_epoch_count'], 1)
        root = self.case.base + '/workbench/candidates/' + revision
        context = self.get_context(root)
        saved = self.case.client.patch(root + '/draft', json=dict(expected_version=0,
            expected_candidate_scope_revision=context['candidate_scope_revision'], selection_mode='selected',
            decisions=[dict(epoch_uuid=key, selected=True, reviewed=True) for key in (eligible, self.added)]), headers=self.case.headers).get_json()
        request = dict(expected_candidate_scope_revision=saved['candidate_scope_revision'], expected_draft_version=1, mode='selected')
        blocked = self.case.client.post(root + '/preview', json=request, headers=self.case.headers)
        self.assertEqual(blocked.status_code, 409, blocked.get_json())
        # Exact saved intent cannot silently lose the blocked selection. The
        # actor must deliberately remove B before eligible A can publish.
        saved = self.case.client.patch(root + '/draft', json=dict(expected_version=1,
            expected_candidate_scope_revision=saved['candidate_scope_revision'],
            decisions=[dict(epoch_uuid=self.added, selected=False)]), headers=self.case.headers).get_json()
        request.update(expected_candidate_scope_revision=saved['candidate_scope_revision'], expected_draft_version=2)
        preview = self.case.client.post(root + '/preview', json=request, headers=self.case.headers)
        self.assertEqual(preview.status_code, 200, preview.get_json())
        request.update(**{field: preview.get_json()[field] for field in
            ('preview_sha256', 'expected_binding_version', 'expected_query_revision')}, operation_uuid=str(uuid.uuid4()))
        accepted = self.accept(request, root)
        self.assertEqual(accepted.status_code, 200, accepted.get_json())
        self.assertEqual(accepted.get_json()['accepted_epoch_uuids'], [eligible])

    def test_cumulative_overlapping_history_distinct_counts_stable_cursor_and_proven_lineage(self):
        # A later immutable proposal includes the earlier incoming row, plus another epoch on that SAME cell.
        baseline = self.case.explorer_history.protocol_binding(self.protocol)
        self.fixture.source_sha = 'd' * 64
        new = self.fixture.add_recording(same_cell=True)
        self.case.service.rows[new]['cell_uuid'] = self.case.service.rows[self.added]['cell_uuid']
        result = self.case.protocol_suggestions.rerun([dict(protocol_uuid=self.protocol, protocol_name='Fixture',
            binding_version=baseline['version'], revision_uuid=baseline['revision_uuid'], recipe=baseline['recipe'])],
            'd' * 64, 'next.h5', 'actor-one')
        self.assertEqual(result['counts']['created_count'], 1)
        second = result['suggestions'][0]['candidate_revision_uuid']
        queue = self.case.client.get(self.case.base + '/workbench?limit=1').get_json()
        self.assertEqual(queue['pending_epoch_count'], 2)
        self.assertEqual(queue['pending_cell_count'], 1)
        self.assertEqual(queue['total_candidate_count'], 2)
        cursor = queue['next_cursor']
        self.assertTrue(cursor)
        next_page = self.case.client.get(self.case.base + '/workbench', query_string={'limit': 1, 'cursor': cursor})
        self.assertEqual(next_page.status_code, 200)
        self.assertNotEqual(queue['candidates'][0]['candidate_revision_uuid'], next_page.get_json()['candidates'][0]['candidate_revision_uuid'])
        self.assertEqual(self.accept(self.accepted_request()).status_code, 200)
        changed = self.case.client.get(self.case.base + '/workbench', query_string={'cursor': cursor})
        self.assertEqual(changed.status_code, 409)
        context = self.manager.context(self.protocol, second, 'actor-one')
        self.assertTrue(context['valid_base'])
        self.assertEqual(set(context['pending']), {new})
        self.assertEqual(self.case.client.get(self.case.base + '/workbench').get_json()['pending_epoch_count'], 1)

    def test_accept_audit_or_receipt_failure_rolls_back_everything_and_retry_is_safe(self):
        request = self.accepted_request()
        before = copy.deepcopy([table.rows for table in self.case.connection.tables])
        insert = self.case.events.insert1
        def fail(row):
            if row['action'] == 'workbench_additions_accepted':
                raise RuntimeError('Audit unavailable')
            insert(row)
        self.case.app.config['TESTING'] = False
        with patch.object(self.case.events, 'insert1', side_effect=fail):
            failed = self.accept(request)
        self.assertEqual(failed.status_code, 500)
        self.assertEqual([table.rows for table in self.case.connection.tables], before)
        self.assertEqual(self.accept(request).status_code, 200)

    def test_full_main_export_uses_combined_curated_cohort(self):
        accepted = self.accept(self.accepted_request())
        self.assertEqual(accepted.status_code, 200)
        export = self.case.client.post(self.case.base + '/exports', json=dict(name='Combined',
            review_policy='include_unreviewed', filters={}, query_revision=self.case.revision(), split_order='cell'), headers=self.case.headers)
        self.assertEqual(export.status_code, 201, export.get_json())
        package = json.loads(self.case.client.get(export.get_json()['download_url']).data)
        self.assertEqual({row['epoch_uuid'] for row in package['epochs']}, set(self.fixture.before_ids) | {self.added})
        self.assertEqual(len(package['epochs']), 3)

    def test_unrelated_replacement_and_missing_native_uuid_fail_closed(self):
        self.case.explorer_history.bind(self.revision, self.protocol, 1, 'fixture', {}, 2)
        context = self.get_context()
        self.assertTrue(context['publication_blocked'])
        preview = self.case.client.post(self.root + '/preview', json=dict(expected_candidate_scope_revision=context['candidate_scope_revision'],
            expected_draft_version=context['draft']['draft_version'], mode='selected'), headers=self.case.headers)
        self.assertEqual(preview.status_code, 409)
        del self.case.service._fingerprints[self.added]
        del self.case.service.rows[self.added]
        self.assertEqual(self.case.client.get(self.root + '/context').status_code, 400)

    def test_recovery_keeps_candidate_and_union_ids_instead_of_requery_remapping(self):
        from workspace_state_snapshot import compact_queries
        receipt = self.accept(self.accepted_request()).get_json()
        state = {'tables': {'explorer_revision': copy.deepcopy(self.case.explorer_revisions.rows),
                           'protocol_suggestion': copy.deepcopy(self.case.suggestion_rows.rows),
                           'workbench_receipt': copy.deepcopy(self.tables[2].rows)}}
        before = copy.deepcopy(state)
        with patch.object(self.case.service, 'match_predicate', side_effect=AssertionError('Never remap Workbench authorities')):
            compact_queries(state, self.case.service)
        self.assertEqual(state, before)

    def test_recovery_dependency_order_and_old_recovery_header_remain_supported(self):
        from workspace_state_snapshot import restore_table_order, LEGACY_TABLES
        from test_workspace_recovery_store import scientific_fixture, canonical
        import workspace_recovery_store as recovery
        import tempfile
        from pathlib import Path
        order = restore_table_order({'workbench_decision': [], 'workbench_draft': []})
        self.assertEqual(order, ['workbench_draft', 'workbench_decision'])
        self.assertEqual(list(reversed(order)), ['workbench_decision', 'workbench_draft'])
        state, keys = scientific_fixture()
        state['tables'] = {key: value for key, value in state['tables'].items() if key in LEGACY_TABLES}
        with tempfile.TemporaryDirectory() as folder:
            with patch('workspace_state_snapshot.TABLES', LEGACY_TABLES):
                recovery.write(folder, state=state, keys=keys, watermark={'authority': 'fixture', 'generation': 0})
            item = recovery.inspect(folder)
            self.assertEqual(canonical(recovery.load_database(item['path'])), canonical(state))

    def test_real_restore_control_flow_enforces_fk_order_and_migrates_legacy_to_empty_review_state(self):
        import contextlib
        import tempfile
        from pathlib import Path
        from workspace_state_snapshot import restore, serialized, TABLES, LEGACY_TABLES
        project = self.case.service.project['project_uuid']
        class FKConnection:
            def __init__(self, populated):
                self.values = {'workbench_draft': [1] if populated else [], 'workbench_decision': [1] if populated else []}
                self.answer = []
            def query(self, sql, args=None):
                if 'information_schema.tables' in sql:
                    self.answer = [(table,) for table in self.values]
                elif sql.startswith('SHOW COLUMNS'):
                    self.answer = [('project_uuid', 'varchar'), ('id', 'int')]
                else:
                    table = next(name for name in self.values if '`' + name + '`' in sql)
                    if sql.startswith('DELETE'):
                        if table == 'workbench_draft' and self.values['workbench_decision']:
                            raise ValueError('FK child still exists')
                        self.values[table] = []
                    elif sql.startswith('INSERT'):
                        if table == 'workbench_decision' and not self.values['workbench_draft']:
                            raise ValueError('FK parent missing')
                        self.values[table].append(args[1])
                return self
            def fetchall(self): return self.answer
            @property
            @contextlib.contextmanager
            def transaction(self): yield
        for populated in (False, True):
            for legacy in (False, True):
                with self.subTest(populated=populated, legacy=legacy), tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    (root / 'protocols').mkdir()
                    (root / 'backups/app-state').mkdir(parents=True)
                    state = dict(format='rieke-app-state', version=1, project={'project_uuid': project},
                        source_sha256s=[], source_references=[], protocols={}, tables={table: [] for table in TABLES})
                    current = copy.deepcopy(state)
                    current['tables']['workbench_draft'] = [dict(project_uuid=project, id=1)]
                    current['tables']['workbench_decision'] = [dict(project_uuid=project, id=1)]
                    if legacy:
                        state['tables'] = {table: [] for table in LEGACY_TABLES}
                    else:
                        state = copy.deepcopy(current)
                    snapshot = root / 'snapshot.json'
                    snapshot.write_text(serialized(state))
                    connection = FKConnection(populated)
                    with patch('workspace_state_snapshot.capture', return_value=current), patch('workspace_state_snapshot.save', return_value='saved'):
                        self.assertEqual(restore(root, connection, snapshot), 'saved')
                    self.assertEqual(connection.values, {'workbench_draft': [] if legacy else [1], 'workbench_decision': [] if legacy else [1]})

    def test_stale_preview_source_block_changed_values_wrong_protocol_and_replacement_ancestry_reject(self):
        request = self.accepted_request()
        context = self.get_context()
        self.save(context, deferred=True)
        self.assertEqual(self.accept(request).status_code, 409)
        request = self.accepted_request()
        self.case.service.rows[self.added]['protocol_name'] = 'other'
        self.assertEqual(self.accept(request).status_code, 400)
        self.case.service.rows[self.added]['protocol_name'] = 'example'
        self.case.service._fingerprints[self.added] = 'c' * 64
        self.assertEqual(self.accept(request).status_code, 409)
        self.case.service._fingerprints[self.added] = 'b' * 64
        # Source exclusion stays inspectable but cannot be published.
        source = self.case.service.rows[self.added]['source_sha256']
        self.case.data_store_states.insert1(dict(project_uuid=self.case.service.project['project_uuid'],
            source_sha256=source, query_excluded=True, archived=False, frozen=False, version=1,
            updated_at=None, actor='actor-one', server_actor='actor-one', reason='test'))
        context = self.get_context()
        self.assertEqual(context['ineligible_incoming_epoch_count'], 1)
        self.assertEqual(self.case.client.get(self.root + '/epochs', query_string={'candidate_scope_revision': context['candidate_scope_revision']}).status_code, 200)
        preview = self.case.client.post(self.root + '/preview', json=dict(expected_candidate_scope_revision=context['candidate_scope_revision'],
            expected_draft_version=context['draft']['draft_version'], mode='all'), headers=self.case.headers)
        self.assertEqual(preview.status_code, 409)


if __name__ == '__main__':
    unittest.main()
