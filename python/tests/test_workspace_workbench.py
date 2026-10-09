"""Additive authority tests: isolated transactional SQL doubles, no native data."""
import copy
import contextlib
import json
import unittest
import uuid
from unittest.mock import patch

from test_workspace_suggestions import ImportSuggestionTests
from test_workspace_curation import Table
from disco.workbench.workbench import ProtocolWorkbench, WorkbenchConflict


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        fixture = ImportSuggestionTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
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
        self.author = patch('disco.decisions.author_preferences.selected_author', return_value={'profile_uuid': 'actor-one'})
        self.author.start()
        self.addCleanup(self.author.stop)
        job = fixture.run_import()
        self.assertIn(job['status'], ('complete', 'complete_with_warnings'), job)
        self.assertTrue(self.case.suggestion_rows.rows, job)
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

    def list_selection(self, context, cells=None, **extra):
        cell = self.case.service.rows[self.added]['cell_uuid']
        return self.case.client.post(self.root + '/list-selection', headers=self.case.headers, json=dict(
            candidate_scope_revision=context['candidate_scope_revision'],
            cells=cells if cells is not None else [dict(cell_uuid=cell, epochs=1)], **extra))

    def test_list_selection_matches_paged_order_and_closes_once_without_writes(self):
        context = self.get_context()
        self.assertIs(context['list_selection'], True)
        cell = self.case.service.rows[self.added]['cell_uuid']
        before = [copy.deepcopy(table.rows) for table in self.tables]
        with patch.object(self.manager, 'context', wraps=self.manager.context) as reads:
            response = self.list_selection(context)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(reads.call_count, 2)
        result = response.get_json()
        self.assertEqual(result['epoch_uuids'], [self.added])
        self.assertEqual(result['cells'], [dict(cell_uuid=cell, epochs=1, epoch_uuids=[self.added])])
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['candidate_scope_revision'], context['candidate_scope_revision'])
        self.assertEqual([table.rows for table in self.tables], before)
        self.assertEqual(self.list_selection(context, []).get_json()['epoch_uuids'], [])
        for cells in [[dict(cell_uuid=cell, epochs=True)], [dict(cell_uuid=cell, epochs=1001)],
                      [dict(cell_uuid=cell, epochs=1)] * 2, [dict(cell_uuid='bad', epochs=1)], [dict(cell_uuid=None, epochs=1)],
                      [dict(cell_uuid=123, epochs=1)], [dict(cell_uuid=[], epochs=1)]]:
            self.assertEqual(self.list_selection(context, cells).status_code, 400)
        for cells in [[dict(cell_uuid=cell, epochs=0)], [dict(cell_uuid=cell, epochs=2)],
                      [dict(cell_uuid=str(uuid.uuid4()), epochs=1)]]:
            self.assertEqual(self.list_selection(context, cells).status_code, 409)
        filtered = self.list_selection(context, filters={'cell_type': 'does-not-match'})
        self.assertEqual(filtered.status_code, 409)

    def test_list_selection_exact_thousand_keeps_chronological_page_order(self):
        from disco.workbench.recipes import checksum
        source = self.case.service.rows[self.added]
        recipe_row = next(row for row in self.case.explorer_revisions.rows if row['revision_uuid'] == self.revision)
        recipe = recipe_row['recipe']
        for index in range(999):
            identity = str(uuid.UUID(int=index + 10000))
            self.case.service.rows[identity] = dict(source, epoch_uuid=identity)
            self.case.service._fingerprints[identity] = self.case.service._fingerprints[self.added]
            recipe['epochs'].append(dict(uuid=identity, metadata_hash=self.case.service._fingerprints[identity]))
        for key in ('epoch_count', 'matched_count'):
            recipe[key] = recipe_row['summary'][key] = len(recipe['epochs'])
        recipe.pop('content_sha256'); recipe['content_sha256'] = checksum(recipe)
        context = self.get_context()
        response = self.list_selection(context, [dict(cell_uuid=source['cell_uuid'], epochs=1000)])
        self.assertEqual(response.status_code, 200, response.get_json())
        expected = sorted([self.added, *[str(uuid.UUID(int=index + 10000)) for index in range(999)]])
        self.assertEqual(response.get_json()['epoch_uuids'], expected)
        self.assertEqual(response.get_json()['count'], 1000)
        self.assertEqual(self.list_selection(context, [dict(cell_uuid=source['cell_uuid'], epochs=1001)]).status_code, 400)

    def test_list_selection_custom_pages_and_closing_changes_fail_closed(self):
        context = self.get_context()
        original = self.manager.frozen_service
        for change in ('partial', 'wrong-cell', 'draft', 'source', 'recipe'):
            with self.subTest(change=change):
                before_tables = [copy.deepcopy(table.rows) for table in self.case.connection.tables]
                original_scope = self.case.service.source_scope
                def altered(ctx):
                    scoped = original(ctx)
                    page = scoped.epoch_page
                    def read(*args, **kwargs):
                        result = page(*args, **kwargs)
                        if change == 'partial': result['epochs'] = []
                        elif change == 'wrong-cell': result['epochs'][0]['cell_uuid'] = str(uuid.uuid4())
                        elif change == 'draft':
                            self.tables[0].insert1(dict(**self.manager.key(self.protocol, self.revision, 'actor-one'),
                                version=99, selection_mode='selected', deferred=False))
                        elif change == 'source':
                            self.case.service.source_scope = lambda: {**original_scope(), 'revision': 'changed'}
                        elif change == 'recipe':
                            row = next(row for row in self.case.explorer_revisions.rows if row['revision_uuid'] == self.revision)
                            row['recipe']['epochs'][0]['metadata_hash'] = 'f' * 64
                        return result
                    scoped.epoch_page = read
                    return scoped
                with patch.object(self.manager, 'frozen_service', side_effect=altered):
                    response = self.list_selection(context)
                self.assertIn(response.status_code, (400, 409), response.get_json())
                self.assertNotIn('epoch_uuids', response.get_json())
                self.case.service.source_scope = original_scope
                for table, rows in zip(self.case.connection.tables, before_tables): table.rows[:] = rows
                self.assertEqual(self.list_selection(context).status_code, 200, 'Failed read must not poison the next read')

    def test_optional_context_bootstrap_matches_fresh_context_and_page(self):
        plain = self.get_context()
        with patch.object(self.manager, 'context', wraps=self.manager.context) as contexts:
            response = self.case.client.get(self.root + '/context?include_initial_page=true')
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(contexts.call_count, 2)
        value = response.get_json()
        bootstrap = value.pop('bootstrap')
        self.assertEqual(value, plain)
        self.assertEqual(bootstrap['context'], plain)
        page = self.case.client.get(self.root + '/epochs', query_string=dict(
            candidate_scope_revision=plain['candidate_scope_revision'], offset=0, limit=60, include_cells='true')).get_json()
        self.assertEqual(bootstrap['page'], page)
        self.assertEqual(bootstrap['actor'], 'actor-one')
        for query in ('include_initial_page=bad', 'include_initial_page=true&include_initial_page=false'):
            self.assertEqual(self.case.client.get(self.root + '/context?' + query).status_code, 400)
        self.assertNotIn('bootstrap', self.get_context())

    def test_bootstrap_closing_check_discards_context_and_page(self):
        original = self.manager.frozen_service
        def changing(context):
            scoped = original(context)
            page = scoped.epoch_page
            def read(*args, **kwargs):
                result = page(*args, **kwargs)
                self.tables[0].insert1(dict(**self.manager.key(self.protocol, self.revision, 'actor-one'),
                    version=1, selection_mode='selected', deferred=True))
                return result
            scoped.epoch_page = read
            return scoped
        with patch.object(self.manager, 'frozen_service', side_effect=changing):
            response = self.case.client.get(self.root + '/context?include_initial_page=true')
        self.assertEqual(response.status_code, 409)
        self.assertNotIn('bootstrap', response.get_json())
        self.assertNotIn('protocol', response.get_json())

    def test_context_rechecks_warmed_main_recipe_storage(self):
        context = self.manager.context(self.protocol, self.revision, 'actor-one')
        self.manager.history.protocol_binding(self.protocol)
        row = next(row for row in self.case.explorer_revisions.rows if row['revision_uuid'] == context['main_revision_uuid'])
        original = copy.deepcopy(row['recipe'])
        row['recipe']['epochs'][0]['metadata_hash'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.manager.context(self.protocol, self.revision, 'actor-one')
        row['recipe'] = original
        self.assertEqual(self.manager.context(self.protocol, self.revision, 'actor-one')['candidate_scope_revision'], context['candidate_scope_revision'])

    def test_custom_recipe_reader_retains_calls_and_nested_context_isolation(self):
        expected = self.manager.context(self.protocol, self.revision, 'actor-one')
        reader = self.manager.history.get
        calls = []
        def custom(revision):
            calls.append(revision)
            return reader(revision)
        with patch.object(self.manager.history, 'get', side_effect=custom):
            actual = self.manager.context(self.protocol, self.revision, 'actor-one')
        self.assertEqual(actual['candidate_scope_revision'], expected['candidate_scope_revision'])
        self.assertEqual(len(calls), 2, 'Custom recipe readers retain the original per-proposal read calls')
        state = self.manager.state
        nested = []
        def reentrant(protocol):
            with patch.object(self.manager, 'state', side_effect=state):
                nested.append(self.manager.context(protocol, self.revision, 'actor-two'))
            return state(protocol)
        with patch.object(self.manager, 'state', side_effect=reentrant):
            actual = self.manager.context(self.protocol, self.revision, 'actor-one')
        self.assertEqual(actual['candidate_scope_revision'], expected['candidate_scope_revision'])
        self.assertEqual(nested[0]['actor'], 'actor-two')
        actual['candidate']['epochs'].clear()
        self.assertEqual(self.manager.context(self.protocol, self.revision, 'actor-one')['candidate_scope_revision'], expected['candidate_scope_revision'])

    def test_tree_selection_matches_complete_pages_with_one_closing_check(self):
        context = self.get_context()
        self.assertIs(context['tree_selection'], True)
        base = dict(candidate_scope_revision=context['candidate_scope_revision'], splits='date,cell,block')
        root = self.case.client.post(self.root + '/tree/page', json={**base, 'limit': 60, 'counts_only': True}, headers=self.case.headers).get_json()
        body = {**base, 'revision': root['revision'], 'path': [], 'expected_count': root['total_epochs']}
        before = [copy.deepcopy(table.rows) for table in self.tables]
        with patch.object(self.manager, 'context', wraps=self.manager.context) as reads:
            response = self.case.client.post(self.root + '/tree/selection', json=body, headers=self.case.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(reads.call_count, 2)
        self.assertEqual(response.get_json()['epoch_uuids'], [self.added])
        self.assertEqual(response.get_json()['count'], 1)
        self.assertEqual(response.get_json()['revision'], root['revision'])
        for patch_body in [{'expected_count': True}, {'expected_count': 0}, {'expected_count': 1001}, {'offset': 0}, {'limit': 1000}, {'anchor_uuid': self.added}, {'counts_only': False}, {'revision': None}]:
            invalid = self.case.client.post(self.root + '/tree/selection', json={**body, **patch_body}, headers=self.case.headers)
            self.assertEqual(invalid.status_code, 400, invalid.get_json())
        for patch_body in [{'expected_count': 2}, {'revision': 'a' * 64}, {'candidate_scope_revision': 'old'}]:
            stale = self.case.client.post(self.root + '/tree/selection', json={**body, **patch_body}, headers=self.case.headers)
            self.assertEqual(stale.status_code, 409, stale.get_json())
        from disco.navigation.tree_pages import TreePages
        with patch.object(TreePages, 'page', return_value={**root, 'selection': {'count': 1001}}) as pages:
            large = self.case.client.post(self.root + '/tree/selection', json=body, headers=self.case.headers)
        self.assertEqual(large.status_code, 409)
        self.assertEqual(pages.call_count, 1, 'Actual count must reject before descendant traversal')
        original, calls = self.manager.context, []
        def changed(*args, **kwargs):
            value = original(*args, **kwargs); calls.append(value)
            return {**value, 'candidate_scope_revision': 'changed'} if len(calls) == 2 else value
        with patch.object(self.manager, 'context', side_effect=changed):
            closed = self.case.client.post(self.root + '/tree/selection', json=body, headers=self.case.headers)
        self.assertEqual(closed.status_code, 409)
        self.assertNotIn('epoch_uuids', closed.get_json())
        self.assertEqual([table.rows for table in self.tables], before)

    def test_selection_summary_is_exact_bounded_read_only_and_scope_fenced(self):
        context = self.get_context()
        self.assertIs(context['selection_summary'], True)
        body = dict(candidate_scope_revision=context['candidate_scope_revision'], epoch_uuids=[self.added])
        before = [copy.deepcopy(table.rows) for table in self.tables]
        response = self.case.client.post(self.root + '/selection-summary', json=body, headers=self.case.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        value = response.get_json()
        self.assertEqual(value['epoch_uuids'], [self.added])
        self.assertEqual(value['counts'], dict(epochs=1, cells=1))
        row = self.case.service.rows[self.added]
        self.assertEqual(value['cells'], [dict(cell_uuid=row['cell_uuid'], cell_type=row.get('cell_type'))])
        self.assertEqual(value['candidate_scope_revision'], context['candidate_scope_revision'])
        self.assertEqual([table.rows for table in self.tables], before)
        empty = self.case.client.post(self.root + '/selection-summary', json={**body, 'epoch_uuids': []}, headers=self.case.headers)
        self.assertEqual(empty.status_code, 200, empty.get_json())
        self.assertEqual(empty.get_json()['counts'], dict(epochs=0, cells=0))
        outside = next(key for key in self.case.service.rows if key != self.added)
        for ids in [[self.added, self.added.upper()], [outside], [str(uuid.uuid4())], ['bad'], [True], None, [self.added] * 1001]:
            with self.subTest(ids=str(ids)[:90]):
                invalid = self.case.client.post(self.root + '/selection-summary', json={**body, 'epoch_uuids': ids}, headers=self.case.headers)
                self.assertEqual(invalid.status_code, 400, invalid.get_json())
        stale = self.case.client.post(self.root + '/selection-summary', json={**body, 'candidate_scope_revision': 'old'}, headers=self.case.headers)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual([table.rows for table in self.tables], before)

    def test_selection_summary_rejects_changed_present_metadata_and_missing_rows(self):
        context = self.get_context()
        body = dict(candidate_scope_revision=context['candidate_scope_revision'], epoch_uuids=[self.added])
        row = self.case.service.rows.pop(self.added)
        missing = self.case.client.post(self.root + '/selection-summary', json=body, headers=self.case.headers)
        self.assertEqual(missing.status_code, 409, missing.get_json())
        self.case.service.rows[self.added] = row
        self.case.service._fingerprints[self.added] = 'c' * 64
        fresh = self.manager.context(self.protocol, self.revision, 'actor-one')
        changed = self.case.client.post(self.root + '/selection-summary', json={**body,
            'candidate_scope_revision': fresh['candidate_scope_revision']}, headers=self.case.headers)
        self.assertEqual(changed.status_code, 409, changed.get_json())

    def test_selection_summary_closing_scope_discards_counts(self):
        context = self.get_context()
        original, calls = self.manager.context, []
        def changed(*args, **kwargs):
            value = original(*args, **kwargs)
            calls.append(value)
            if len(calls) == 2:
                value = {**value, 'candidate_scope_revision': 'changed-during-read'}
            return value
        with patch.object(self.manager, 'context', side_effect=changed):
            response = self.case.client.post(self.root + '/selection-summary', json=dict(
                candidate_scope_revision=context['candidate_scope_revision'], epoch_uuids=[self.added]), headers=self.case.headers)
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertNotIn('counts', response.get_json())

    def test_column_batch_matches_fresh_pages_with_one_closing_scope_check(self):
        context = self.get_context()
        self.assertIs(context['tree_column_pages'], True)
        body = dict(candidate_scope_revision=context['candidate_scope_revision'],
                    splits='date,cell,block', anchor_uuid=self.added, limit=1)
        with patch.object(self.manager, 'context', wraps=self.manager.context) as reads:
            response = self.case.client.post(self.root + '/tree/page', json={**body,
                'include_ancestors': True, 'ancestor_offsets': [999, None, 999]}, headers=self.case.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(reads.call_count, 2)  # Opening and closing authority, not once per ancestor.
        batch = response.get_json()
        parents = batch.pop('ancestor_pages')
        self.assertEqual(len(parents), 3)
        self.assertEqual([row['epoch_uuid'] for row in batch['epochs']], [self.added])
        legacy = self.case.client.post(self.root + '/tree/page', json=body, headers=self.case.headers)
        self.assertEqual(batch, legacy.get_json())
        for depth, parent in enumerate(parents):
            self.assertEqual(parent['path'], batch['path'][:depth])
            self.assertEqual(parent['offset'], batch['ancestors'][depth]['parent_offset'])
            request = {key: value for key, value in body.items() if key != 'anchor_uuid'}
            request.update(path=parent['path'], offset=parent['offset'], revision=batch['revision'])
            fresh = self.case.client.post(self.root + '/tree/page', json=request, headers=self.case.headers)
            self.assertEqual(fresh.status_code, 200, fresh.get_json())
            self.assertEqual(parent, fresh.get_json())

    def test_count_only_column_batch_skips_statistics_and_preserves_authority(self):
        context = self.get_context()
        body = dict(candidate_scope_revision=context['candidate_scope_revision'],
                    splits='date,cell,block', anchor_uuid=self.added, include_ancestors=True)
        legacy = self.case.client.post(self.root + '/tree/page', json=body, headers=self.case.headers).get_json()
        original = self.manager.frozen_service
        def frozen(*args, **kwargs):
            value = original(*args, **kwargs)
            def no_coverage(rows):
                raise AssertionError('Count-only must not request branch coverage')
            value.tree_annotation_coverage = no_coverage
            return value
        with patch.object(self.manager, 'frozen_service', side_effect=frozen), patch(
                'disco.navigation.tree_pages._summary', side_effect=AssertionError('Full bucket statistics')):
            response = self.case.client.post(self.root + '/tree/page', json={**body, 'counts_only': True}, headers=self.case.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        for page in [legacy, *legacy['ancestor_pages']]:
            for row in [page, page['selection'], *page['branches'], *page['ancestors']]:
                for key in ('cells', 'duration_seconds', 'shared_tag_coverage'):
                    row.pop(key, None)
        self.assertEqual(response.get_json(), legacy)
        for value in (None, 1, 0, 'true'):
            bad = self.case.client.post(self.root + '/tree/page', json={**body, 'counts_only': value}, headers=self.case.headers)
            self.assertEqual(bad.status_code, 400, bad.get_json())

    def test_column_batch_validates_bounds_and_closing_scope(self):
        context = self.get_context()
        body = dict(candidate_scope_revision=context['candidate_scope_revision'], splits='date,cell,block')
        invalid = [{'include_ancestors': 1}, {'include_ancestors': 'true'},
                   {'ancestor_offsets': [0]}, {'include_ancestors': True, 'ancestor_offsets': [0] * 9}]
        invalid.extend(dict(include_ancestors=True, ancestor_offsets=value)
                       for value in (True, {}, '0', [True], [-1], [0.5], ['0'], [10_000_001]))
        for options in invalid:
            with self.subTest(options=options):
                response = self.case.client.post(self.root + '/tree/page', json={**body, **options}, headers=self.case.headers)
                self.assertEqual(response.status_code, 400, response.get_json())
        empty = self.case.client.post(self.root + '/tree/page', json={**body,
            'include_ancestors': True}, headers=self.case.headers).get_json()
        self.assertEqual(empty['ancestor_pages'], [])
        original, calls = self.manager.context, []
        def changed(*args, **kwargs):
            value = original(*args, **kwargs)
            calls.append(value)
            if len(calls) == 2:
                value = {**value, 'candidate_scope_revision': 'changed-after-parent-reads'}
            return value
        with patch.object(self.manager, 'context', side_effect=changed):
            response = self.case.client.post(self.root + '/tree/page', json={**body,
                'anchor_uuid': self.added, 'include_ancestors': True}, headers=self.case.headers)
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertNotIn('ancestor_pages', response.get_json())

    def test_read_contract_closes_before_publication_and_never_wraps_mutations(self):
        from workspace_state_generation import StateGenerationAuthority
        tracker = StateGenerationAuthority(self.case.connection, self.case.service.project['project_uuid'])
        tracker.token = lambda protocol=None: dict(protocol_uuid=protocol, generation=1)
        calls = []
        @contextlib.contextmanager
        def contract():
            calls.append('open')
            try:
                yield
            finally:
                calls.append('close')
        tracker.response_contract = contract
        with patch.object(self.case.service, '_explore_state_generation', tracker, create=True):
            context = self.get_context()
            self.assertEqual(calls, ['open', 'close'])
            calls.clear()
            saved = self.save(context, [])
            self.assertEqual(saved.status_code, 200, saved.get_json())
            self.assertEqual(calls, [])
            context = saved.get_json()
            page = self.case.client.post(self.root + '/tree/page', json=dict(
                candidate_scope_revision=context['candidate_scope_revision'], splits='cell'), headers=self.case.headers)
            self.assertEqual(page.status_code, 200, page.get_json())
            self.assertEqual(calls, ['open', 'close'])

    def test_failed_closing_read_attestation_discards_workbench_response(self):
        from workspace_state_generation import StateGenerationAuthority
        tracker = StateGenerationAuthority(self.case.connection, self.case.service.project['project_uuid'])
        tracker.token = lambda protocol=None: dict(protocol_uuid=protocol, generation=1)
        @contextlib.contextmanager
        def changed_contract():
            yield
            raise ValueError('Native database contract changed while reading the response')
        tracker.response_contract = changed_contract
        with patch.object(self.case.service, '_explore_state_generation', tracker, create=True):
            response = self.case.client.get(self.root + '/context')
            self.assertEqual(response.status_code, 400, response.get_json())
            self.assertNotIn('candidate_scope_revision', response.get_json())
            self.assertIn('contract changed', response.get_json()['error'])
        self.assertIn('candidate_scope_revision', self.get_context())

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

    def test_candidate_summary_echoes_generation_and_rejects_a_changed_filter_authority(self):
        context = self.get_context()
        body = dict(candidate_scope_revision=context['candidate_scope_revision'], filters={'cell_uuid': self.added})
        response = self.case.client.post(self.root + '/summary', json=body, headers=self.case.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['filters'], body['filters'])
        self.assertTrue(response.get_json()['generation'])
        witness = ['before']
        original = type(self.case.service).filtered_rows
        def mutate_during_calculation(scoped, *args, **kwargs):
            rows = original(scoped, *args, **kwargs)
            witness[0] = 'after'
            return rows
        with patch('disco.metadata.explore_queries.generation', side_effect=lambda *args: {'annotation': witness[0]}), \
                patch.object(type(self.case.service), 'filtered_rows', mutate_during_calculation):
            response = self.case.client.post(self.root + '/summary', json=body, headers=self.case.headers)
        self.assertEqual(response.status_code, 409, response.get_json())
        self.assertNotIn('counts', response.get_json())

    def coverage_annotations(self):
        from disco.decisions.annotations import SharedAnnotations
        profiles = Table(('project_uuid', 'profile_uuid'))
        records = Table(('project_uuid', 'target_kind', 'target_uuid', 'profile_uuid'))
        self.case.connection.tables.extend([profiles, records])
        store = SharedAnnotations(self.case.service, (profiles, records, self.case.events))
        self.case.service.shared_annotations = store
        return store

    def test_tree_shared_tag_coverage_inherits_deduplicates_and_removes(self):
        shared = self.coverage_annotations()
        rows = list(self.case.service.rows.values())[:2]
        records = []
        def snapshot():
            return dict(revision=str(records), records=copy.deepcopy(records))
        with patch.object(shared, 'snapshot', side_effect=snapshot):
            def coverage():
                context = self.manager.context(self.protocol, self.revision, 'actor-one')
                return self.manager.frozen_service(context).tree_annotation_coverage(rows)
            self.assertEqual(coverage(), dict(total_epochs=2, tagged_epochs=0))
            records.append(dict(target_kind='epoch', target_uuid=rows[0]['epoch_uuid'], tags=['one']))
            self.assertEqual(coverage()['tagged_epochs'], 1)
            records.append(dict(target_kind='cell', target_uuid=rows[1]['cell_uuid'], tags=['other']))
            self.assertEqual(coverage()['tagged_epochs'], 2)
            records.append(dict(target_kind='epoch', target_uuid=rows[1]['epoch_uuid'], tags=['duplicate']))
            self.assertEqual(coverage()['tagged_epochs'], 2)
            for record in records:
                record['tags'] = []
            self.assertEqual(coverage()['tagged_epochs'], 0)
            context = self.manager.context(self.protocol, self.revision, 'actor-one')
            scoped = self.manager.frozen_service(context)
            records.append(dict(target_kind='cell', target_uuid=rows[0]['cell_uuid'], tags=['changed']))
            with patch.object(shared, 'snapshot', side_effect=AssertionError('Coverage must reuse captured snapshot')):
                self.assertEqual(scoped.tree_annotation_coverage(rows)['tagged_epochs'], 0)
            self.assertNotEqual(context['candidate_scope_revision'],
                self.manager.context(self.protocol, self.revision, 'actor-one')['candidate_scope_revision'])
        with patch.object(self.case.service, 'shared_annotations', None):
            context = self.manager.context(self.protocol, self.revision, 'actor-one')
            self.assertIsNone(self.manager.frozen_service(context).tree_annotation_coverage(rows))

    def test_frozen_tree_coverage_is_scope_fenced_and_review_does_not_create_tags(self):
        shared = self.coverage_annotations()
        snapshot = shared.snapshot()
        # Review/selection is independent from shared tags.
        context = self.get_context()
        self.assertNotIn('_shared_annotation_snapshot', context)
        context = self.save(context, [dict(epoch_uuid=self.added, selected=True, reviewed=True)]).get_json()
        def read(token):
            return self.case.client.post(self.root + '/tree/page', json=dict(
                candidate_scope_revision=token, splits='cell'), headers=self.case.headers)
        response = read(context['candidate_scope_revision'])
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['branches'][0]['shared_tag_coverage'],
                         dict(total_epochs=1, tagged_epochs=0))
        changed = dict(snapshot, revision='changed', records=[dict(target_kind='epoch',
            target_uuid=self.added, tags=['checked'])])
        with patch.object(shared, 'snapshot', return_value=changed):
            self.assertEqual(read(context['candidate_scope_revision']).status_code, 409)
            fresh = self.get_context()
            response = read(fresh['candidate_scope_revision'])
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertEqual(response.get_json()['branches'][0]['shared_tag_coverage'],
                             dict(total_epochs=1, tagged_epochs=1))
        # A read that changes after coverage evaluation cannot publish green.
        original = self.manager.frozen_service
        def changing(context):
            scoped = original(context)
            coverage = scoped.tree_annotation_coverage
            def changed_after(rows):
                result = coverage(rows)
                shared.snapshot = lambda: changed
                return result
            scoped.tree_annotation_coverage = changed_after
            return scoped
        with patch.object(shared, 'snapshot', return_value=snapshot), patch.object(self.manager, 'frozen_service', side_effect=changing):
            response = read(context['candidate_scope_revision'])
            self.assertEqual(response.status_code, 409, response.get_json())
        accepted = self.accept(self.accepted_request())
        self.assertEqual(accepted.status_code, 200, accepted.get_json())
        self.assertEqual(shared.snapshot(), snapshot, 'Merging must never author shared tags')

    def test_frozen_tree_leaf_has_saved_proposal_decision_without_scientific_curation(self):
        context = self.get_context()
        context = self.save(context, [dict(epoch_uuid=self.added, reviewed=True, excluded=True)]).get_json()
        body = dict(candidate_scope_revision=context['candidate_scope_revision'], splits='cell')
        branches = self.case.client.post(self.root + '/tree/page', json=body, headers=self.case.headers)
        self.assertEqual(branches.status_code, 200, branches.get_json())
        branch = branches.get_json()['branches'][0]
        page = self.case.client.post(self.root + '/tree/page', json={**body, 'path': [branch['key']],
            'revision': branches.get_json()['revision']}, headers=self.case.headers)
        self.assertEqual(page.status_code, 200, page.get_json())
        self.assertEqual(page.get_json()['kind'], 'epochs')
        leaf = page.get_json()['epochs'][0]
        self.assertEqual(leaf['epoch_uuid'], self.added)
        self.assertEqual(leaf['review_decision'], dict(selected=False, reviewed=True, excluded=True))
        self.assertNotIn('curation', leaf)  # Structural tree DTO stays structural.
        detail = self.case.client.get(self.root + '/epochs/' + self.added, query_string={
            'candidate_scope_revision': context['candidate_scope_revision']})
        self.assertEqual(detail.status_code, 200, detail.get_json())
        self.assertEqual(detail.get_json()['review_decision'], leaf['review_decision'])
        self.assertTrue(detail.get_json()['curation']['included'])
        self.assertFalse(detail.get_json()['curation']['reviewed'])
        self.assertEqual(detail.get_json()['curation']['revision'], 0)
        self.assertFalse(self.case.curation.rows)

    def test_scoped_predicate_dependency_intersects_only_frozen_incoming_across_read_surfaces(self):
        if not hasattr(self.case.service, 'validate_metadata_filters'):
            self.skipTest('Compose the protocol-scoped-predicate commits to qualify this adapter')
        token = self.get_context()['candidate_scope_revision']
        for predicate, count in (({'field': 'parameters/example', 'operator': 'eq', 'value': 0}, 1),
                                 ({'field': 'parameters/example', 'operator': 'eq', 'value': 1}, 0)):
            filters = {'metadata_predicate': json.dumps(predicate)}
            page = self.case.client.get(self.root + '/epochs', query_string=dict(candidate_scope_revision=token, **filters))
            self.assertEqual(page.status_code, 200, page.get_json())
            self.assertEqual(page.get_json()['total'], count)
            self.assertTrue(all(row['epoch_uuid'] == self.added for row in page.get_json()['epochs']))
            summary = self.case.client.post(self.root + '/summary', json=dict(candidate_scope_revision=token, filters=filters), headers=self.case.headers)
            self.assertEqual(summary.status_code, 200, summary.get_json())
            self.assertEqual(summary.get_json()['matched_count'], count)
            self.assertEqual(json.loads(summary.get_json()['filters']['metadata_predicate']), predicate)
            self.assertEqual(summary.get_json()['candidate_scope_revision'], token)
            tree = self.case.client.post(self.root + '/tree/page', json=dict(candidate_scope_revision=token, filters=filters, splits='cell'), headers=self.case.headers)
            self.assertEqual(tree.status_code, 200, tree.get_json())
            self.assertEqual(tree.get_json()['total_epochs'], count)
        foreign = {'field': 'curation/00000000-0000-4000-8000-000000000000/tags', 'operator': 'contains', 'value': 'QC'}
        response = self.case.client.post(self.root + '/summary', json=dict(candidate_scope_revision=token, filters={'metadata_predicate': json.dumps(foreign)}), headers=self.case.headers)
        self.assertEqual(response.status_code, 400, response.get_json())

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

    def test_accepted_pending_scope_is_empty_and_new_empty_accept_never_rebinds(self):
        first = self.accept(self.accepted_request()).get_json()
        version = first['binding']['version']
        context = self.get_context()
        self.assertEqual(context['protocol']['counts']['epochs'], 0)
        context = self.save(context, selection_mode='all').get_json()
        response = self.case.client.post(self.root + '/preview', json=dict(mode='all',
            expected_candidate_scope_revision=context['candidate_scope_revision'], expected_draft_version=context['draft']['draft_version']), headers=self.case.headers)
        self.assertEqual(response.status_code, 400, response.get_json())
        self.assertEqual(self.case.explorer_history.protocol_binding(self.protocol)['version'], version)
        self.assertTrue(first['event_uuid'])
        event = next(row for row in self.case.events.rows if row['event_uuid'] == first['event_uuid'])
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

    def test_recovery_closure_crosses_multiple_250_batches_and_missing_parent_refuses(self):
        from workspace_state_snapshot import capture
        project = self.case.service.project['project_uuid']
        baseline = str(uuid.uuid4())
        recipes = {baseline: dict(revision_uuid=baseline, project_uuid=project, parent_revision_uuid=None)}
        suggestions = []
        for _ in range(261):
            parent, candidate = str(uuid.uuid4()), str(uuid.uuid4())
            recipes[parent] = dict(revision_uuid=parent, project_uuid=project, parent_revision_uuid=baseline)
            recipes[candidate] = dict(revision_uuid=candidate, project_uuid=project, parent_revision_uuid=parent)
            suggestions.append(dict(project_uuid=project, summary=dict(candidate_revision_uuid=candidate, baseline_revision_uuid=baseline)))
        orphan = str(uuid.uuid4())
        recipes[orphan] = dict(revision_uuid=orphan, project_uuid=project, parent_revision_uuid=None)
        class ClosureConnection:
            def __init__(self): self.batches = []; self.answer = []
            def query(self, sql, args=None, as_dict=False):
                if 'information_schema.tables' in sql:
                    self.answer = [('protocol_suggestion',), ('explorer_revision',)]
                elif sql.startswith('SHOW COLUMNS'):
                    self.answer = [('summary', 'json')]
                elif '`protocol_suggestion`' in sql:
                    self.answer = suggestions
                elif '`explorer_revision`' in sql:
                    identities = args[1:]
                    self.batches.append(len(identities))
                    self.answer = [recipes[key] for key in identities if key in recipes]
                else:
                    raise AssertionError(sql)
                return self
            def fetchall(self): return self.answer
        connection = ClosureConnection()
        from pathlib import Path
        (Path(self.case.service.project_dir) / 'project.json').write_text(json.dumps(self.case.service.project))
        state = capture(self.case.service.project_dir, connection)
        self.assertEqual(len(state['tables']['explorer_revision']), 523)
        self.assertNotIn(orphan, {row['revision_uuid'] for row in state['tables']['explorer_revision']})
        self.assertGreater(len(connection.batches), 2)
        self.assertLessEqual(max(connection.batches), 250)
        recipes.pop(next(row['parent_revision_uuid'] for row in recipes.values() if row['parent_revision_uuid'] not in (baseline, None)))
        with self.assertRaisesRegex(ValueError, 'dependency is unavailable'):
            capture(self.case.service.project_dir, ClosureConnection())

    def test_recovery_dependency_order_and_old_recovery_header_remain_supported(self):
        from workspace_state_snapshot import restore_table_order, LEGACY_TABLES
        from test_workspace_recovery_store import scientific_fixture, canonical
        import disco.backup.recovery_store as recovery
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
                    self.answer = [('project_uuid', 'varchar(36)', 'NO', 'PRI', None, ''),
                                   ('id', 'int', 'NO', 'PRI', None, '')]
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
