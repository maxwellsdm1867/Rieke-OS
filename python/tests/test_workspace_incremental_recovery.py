"""Incremental recovery mirror equals a full capture, on a disposable native server.

Real DataJoint table declarations, a synthetic project and owned MySQL only.
Opt-in like the other native recovery proofs (RIEKE_TEST_NATIVE_MYSQL=1).
"""
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

import workspace_state_snapshot as snapshot

WHEN = dt.datetime(2026, 10, 17, 12)


def ident(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'disco-incremental-recovery/' + '/'.join(map(str, parts))))


class NativeRecoveryProject:
    """Owned native project seeded with Workbench-sized authored state."""

    def __init__(self, *, epochs=400, revisions=12, receipts=20, annotations=1500):
        import datajoint as dj
        import workspace_native_mysql as native
        from workspace_projects import create_project
        self.temporary = tempfile.TemporaryDirectory(prefix='rieke-incremental-recovery-')
        self.root = Path(create_project(Path(self.temporary.name) / 'projects', 'Incremental recovery fixture')['path'])
        self.native = native
        native.ensure_native_database(self.root)
        for key, value in native.connection_parameters(self.root).items():
            if key in ('host', 'port', 'user', 'password'):
                dj.config['database.' + key] = value
        self.dj = dj
        self.connection = dj.conn(reset=True)
        from recording_workspace import workspace_tables
        from disco.decisions.annotations import annotation_tables
        from disco.decisions.curation import curation_tables
        from disco.decisions.explorer import explorer_table, protocol_binding_table
        from disco.decisions.annotation_groups import group_receipt_table
        from disco.navigation.search_presets import preset_tables
        from disco.workbench.suggestions import suggestion_table
        from disco.workbench.workbench import workbench_tables
        for factory in (workspace_tables, annotation_tables, curation_tables, explorer_table, protocol_binding_table,
                        group_receipt_table, preset_tables, suggestion_table, workbench_tables):
            factory(dj)
        self.project = json.loads((self.root / 'project.json').read_text())['project_uuid']
        self.protocol = ident('protocol')
        self.epochs = [ident('epoch', number) for number in range(epochs)]
        self.service = SimpleNamespace()
        self.seed(revisions, receipts, annotations)

    def close(self):
        try:
            self.connection.close()
        finally:
            self.native.stop_native_database(self.root)
            self.temporary.cleanup()

    def many(self, sql, rows):
        if rows:
            with self.connection._conn.cursor() as cursor:
                cursor.executemany(sql, rows)

    def recipe(self, revision, parent, members, origins=None):
        value = {'revision_uuid': revision, 'parent_revision_uuid': parent,
                 'predicate': {'all': [{'field': 'cell.type', 'operator': 'eq', 'value': 'ON'}]},
                 'epochs': [{'uuid': epoch, 'metadata_hash': '%064x' % number} for number, epoch in enumerate(members)]}
        if origins is not None:
            value['pending_union_provenance'] = {'origins': origins}
        return json.dumps(value)

    def revision(self, name, parent=None, members=None, origins=None):
        revision = ident('revision', name)
        members = self.epochs if members is None else members
        self.connection.query('INSERT INTO recording_workspace.explorer_revision VALUES (%s,%s,%s,%s,%s,%s,%s)',
            args=(self.project, revision, WHEN, 'Revision ' + str(name), parent,
                  json.dumps({'revision_uuid': revision, 'epoch_count': len(members)}),
                  self.recipe(revision, parent, members, origins)))
        return revision

    def seed(self, revisions, receipts, annotations):
        project = self.project
        chain = [self.revision('initial')]
        for number in range(revisions):
            chain.append(self.revision(number, chain[-1]))
        self.chain = chain
        self.orphan = self.revision('orphan')  # History only: never mirrored.
        self.baseline = self.revision('suggestion-baseline')
        self.suggested = self.revision('suggestion-candidate', self.baseline)
        origin_a, origin_b = self.revision('origin-a'), self.revision('origin-b')
        self.union = self.revision('union', chain[-1], origins=[
            {'candidate_revision_uuid': origin_a, 'baseline_revision_uuid': origin_b}])
        self.candidate = self.revision('candidate', self.union)
        protocols = self.root / 'protocols'
        protocols.mkdir(exist_ok=True)
        (protocols / (self.protocol + '.json')).write_text(json.dumps(
            {'protocol_uuid': self.protocol, 'initial_revision_uuid': chain[0]}))
        self.connection.query('INSERT INTO recording_workspace.protocol_binding VALUES (%s,%s,%s,1,%s)',
                              args=(project, self.protocol, chain[-1], WHEN))
        self.suggestion = ident('suggestion')
        self.connection.query('INSERT INTO recording_workspace.protocol_suggestion VALUES (%s,%s,%s,%s,%s)',
            args=(project, self.suggestion, self.protocol, WHEN, json.dumps(
                {'baseline_revision_uuid': self.baseline, 'candidate_revision_uuid': self.suggested})))
        self.connection.query('INSERT INTO recording_workspace.workbench_draft VALUES (%s,%s,%s,%s,1,%s,0)',
                              args=(project, self.protocol, self.candidate, 'scientist', 'explicit'))
        self.many('INSERT INTO recording_workspace.workbench_decision VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0)',
                  [(project, self.protocol, self.candidate, 'scientist', epoch, '%064x' % number, number % 2, number % 3 == 0)
                   for number, epoch in enumerate(self.epochs)])
        self.many('INSERT INTO recording_workspace.workbench_receipt VALUES (%s,%s,%s,%s,%s,%s,%s)',
                  [(project, ident('receipt', number), self.protocol, chain[number % len(chain)], 'scientist', '%064x' % number,
                    json.dumps({'binding': {'revision_uuid': chain[(number + 1) % len(chain)], 'version': number},
                                'accepted': self.epochs[:20]})) for number in range(receipts)])
        profile = ident('profile')
        self.connection.query('INSERT INTO recording_workspace.annotation_profile VALUES (%s,%s,%s,%s,%s)',
                              args=(project, profile, 'Scientist', WHEN, 'scientist'))
        self.many('INSERT INTO recording_workspace.shared_annotation VALUES (%s,%s,%s,%s,%s,%s,1,%s)',
                  [(project, 'epoch', ident('target', number), profile, json.dumps(['QC', 'tag-%d' % (number % 7)]),
                    'Scientist', WHEN) for number in range(annotations)])
        self.many('INSERT INTO recording_workspace.curation VALUES (%s,%s,%s,1,%s,%s,1,%s)',
                  [(project, self.protocol, epoch, json.dumps(['kept']), 'approved', '%064x' % number)
                   for number, epoch in enumerate(self.epochs)])
        self.preset = ident('preset')
        self.connection.query('INSERT INTO recording_workspace.search_preset VALUES (%s,%s,%s,%s,%s,%s,0,2,%s,%s)',
            args=(project, self.preset, 'ON cells', '', json.dumps({'all': []}), 'cell', WHEN, 'scientist'))
        for version in (1, 2):
            self.connection.query('INSERT INTO recording_workspace.search_preset_version VALUES (%s,%s,%s,%s)',
                                  args=(project, self.preset, version, json.dumps({'version': version})))
        self.connection.query('INSERT INTO recording_workspace.annotation_group_receipt VALUES (%s,%s,%s,%s,%s,%s,%s)',
            args=(project, ident('group'), 'scientist', profile, '0' * 64, json.dumps({'changed': 3}), WHEN))

    def merge(self, name):
        """What a Workbench accept commits: a revision, binding, receipt, draft cleanup."""
        bound = self.connection.query('SELECT revision_uuid,version FROM recording_workspace.protocol_binding '
            'WHERE project_uuid=%s', args=(self.project,)).fetchone()
        with self.connection.transaction:
            revision = self.revision('merge-' + str(name), bound[0], members=self.epochs[:len(self.epochs) // 2])
            self.connection.query('UPDATE recording_workspace.protocol_binding SET revision_uuid=%s,version=version+1 '
                                  'WHERE project_uuid=%s', args=(revision, self.project))
            self.connection.query('INSERT INTO recording_workspace.workbench_receipt VALUES (%s,%s,%s,%s,%s,%s,%s)',
                args=(self.project, ident('merge-receipt', name), self.protocol, self.candidate, 'scientist', '1' * 64,
                      json.dumps({'binding': {'revision_uuid': revision, 'version': int(bound[1]) + 1}})))
            self.connection.query('DELETE FROM recording_workspace.workbench_decision WHERE project_uuid=%s', args=(self.project,))
            self.connection.query('DELETE FROM recording_workspace.workbench_draft WHERE project_uuid=%s', args=(self.project,))
        return revision

    def save(self, **kwargs):
        return snapshot.save(self.root, self.connection, service=self.service, **kwargs)

    def mirror(self):
        return snapshot.load(self.root / 'app-state.json')

    def full(self):
        return snapshot.capture(self.root, self.connection)


def canonical(state):
    return ({key: value for key, value in state.items() if key != 'tables'},
            {table: sorted(snapshot.serialized(row) for row in rows) for table, rows in state['tables'].items()})


@unittest.skipUnless(os.environ.get('RIEKE_TEST_NATIVE_MYSQL') == '1', 'opt-in disposable native recovery proof')
class IncrementalRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = NativeRecoveryProject(epochs=300, revisions=6, receipts=8, annotations=200)
        self.addCleanup(self.fixture.close)

    def assertMirrorIsFullCapture(self):
        self.assertEqual(canonical(self.fixture.mirror()), canonical(self.fixture.full()))

    def test_workbench_writes_are_incremental_and_equal_full_capture(self):
        fixture = self.fixture
        first = fixture.save()
        self.assertFalse(first['incremental'])
        self.assertMirrorIsFullCapture()
        mirrored = {row['revision_uuid'] for row in fixture.mirror()['tables']['explorer_revision']}
        self.assertNotIn(fixture.orphan, mirrored)
        self.assertTrue({fixture.union, fixture.suggested, fixture.baseline} <= mirrored)
        writes = [
            lambda: fixture.merge(1),
            lambda: fixture.merge(2),
            # A suggestion removed: its revisions leave the closure.
            lambda: fixture.connection.query('DELETE FROM recording_workspace.protocol_suggestion WHERE project_uuid=%s',
                                             args=(fixture.project,)),
            # A preset saved as a new current version: the old one leaves.
            lambda: (fixture.connection.query('INSERT INTO recording_workspace.search_preset_version VALUES (%s,%s,3,%s)',
                        args=(fixture.project, fixture.preset, json.dumps({'version': 3}))),
                     fixture.connection.query('UPDATE recording_workspace.search_preset SET version=3 WHERE project_uuid=%s',
                        args=(fixture.project,))),
            # Annotations, curation and a revision referenced only by a protocol file.
            lambda: (fixture.connection.query("UPDATE recording_workspace.shared_annotation SET tags='[\"edited\"]',revision=2 "
                        'WHERE project_uuid=%s LIMIT 3', args=(fixture.project,)),
                     fixture.connection.query('DELETE FROM recording_workspace.curation WHERE project_uuid=%s AND epoch_uuid=%s',
                        args=(fixture.project, fixture.epochs[0]))),
            lambda: (fixture.root / 'protocols' / (fixture.protocol + '.json')).write_text(json.dumps(
                {'protocol_uuid': fixture.protocol, 'initial_revision_uuid': fixture.orphan})),
        ]
        for number, write in enumerate(writes):
            with self.subTest(write=number):
                write()
                result = fixture.save()
                self.assertTrue(result['incremental'], result)
                self.assertTrue(result['changed'])
                self.assertMirrorIsFullCapture()
        mirrored = {row['revision_uuid'] for row in fixture.mirror()['tables']['explorer_revision']}
        self.assertIn(fixture.orphan, mirrored)
        self.assertFalse({fixture.suggested, fixture.baseline} & mirrored)
        self.assertEqual([row['version'] for row in fixture.mirror()['tables']['search_preset_version']], [3])

    def test_incremental_mirror_restores_exactly_like_a_full_capture_snapshot(self):
        fixture = self.fixture
        fixture.save()
        fixture.merge(1)
        fixture.save()
        fixture.connection.query('DELETE FROM recording_workspace.protocol_suggestion WHERE project_uuid=%s', args=(fixture.project,))
        self.assertTrue(fixture.save()['incremental'])
        expected = canonical(fixture.full())
        saved = Path(fixture.temporary.name).resolve() / 'saved'
        saved.mkdir()
        incremental_copy = saved / 'incremental.sqlite'
        pointer = json.loads((fixture.root / 'app-state.json').read_text())
        shutil.copyfile(fixture.root / pointer['store'], incremental_copy)
        full_copy = saved / 'full.json'
        full_copy.write_text(snapshot.serialized(fixture.full()))
        for source in (incremental_copy, full_copy):
            with self.subTest(source=source.name):
                # Lose authored state after the backup, then restore offline.
                fixture.merge('lost-' + source.stem)
                fixture.connection.query('DELETE FROM recording_workspace.shared_annotation WHERE project_uuid=%s',
                                         args=(fixture.project,))
                snapshot.restore(fixture.root, fixture.connection, source)
                restored = canonical(fixture.full())
                self.assertEqual(restored[1], expected[1])

    def test_existing_full_and_v1_snapshots_continue_with_deltas(self):
        fixture = self.fixture
        # A v1 JSON snapshot from an older app: the first save rebuilds fully.
        (fixture.root / 'app-state.json').write_text(snapshot.serialized(fixture.full()))
        self.assertFalse(fixture.save()['incremental'])
        # Simulate a mirror written by the previous app (full capture only).
        with patch.object(snapshot, 'recovery_delta', return_value=None):
            fixture.merge(1)
            self.assertFalse(fixture.save()['incremental'])
        fixture.merge(2)
        self.assertTrue(fixture.save()['incremental'])
        self.assertMirrorIsFullCapture()

    def test_write_without_backup_is_covered_by_the_next_save_after_restart(self):
        fixture = self.fixture
        fixture.save()
        fixture.merge(1)  # Committed, then the process stops before its backup.
        fixture.service = SimpleNamespace()  # New process: new authority object.
        fixture.save()
        self.assertMirrorIsFullCapture()
        fixture.merge(2)
        with patch('disco.backup.recovery_store._write_rows', side_effect=OSError('Disk full')):
            with self.assertRaisesRegex(OSError, 'Disk full'):
                fixture.save()
        # The failed backup rolled back: the mirror still shows the earlier
        # state and the authority requires a full reconciliation next time
        # (unchanged behavior), after which saves are incremental again.
        self.assertNotEqual(canonical(fixture.mirror()), canonical(fixture.full()))
        self.assertFalse(fixture.save()['incremental'])
        self.assertMirrorIsFullCapture()
        fixture.merge(3)
        self.assertTrue(fixture.save()['incremental'])
        self.assertMirrorIsFullCapture()


if __name__ == '__main__':
    unittest.main()
