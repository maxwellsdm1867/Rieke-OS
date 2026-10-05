"""Atomic source removal and crash recovery with disposable files/SQL doubles."""
import contextlib
import copy
import json
from pathlib import Path
import re
import tempfile
import types
import unittest
from unittest.mock import patch
import uuid

from disco.projects.datastore_deletion import DataStoreDeletion, managed_recording, prune_preview
from disco.projects.datastores import DataStores
from disco.decisions.explorer import ExplorerHistory
from disco.workbench.recipes import checksum
if __package__:
    from .test_workspace_curation import Table, Connection
else:
    from test_workspace_curation import Table, Connection


def uid(n):
    return str(uuid.UUID(int=n))


class Relation(Table):
    def __and__(self, restriction):
        if isinstance(restriction, str):
            number = int(re.search(r'!= (\d+)', restriction)[1])
            restriction = [{'id': row['id']} for row in self.rows if row['experiment_id'] != number]
        return Relation(self.keys, self.rows, self.restrictions + (restriction,), self.projected, self.read_log)
    def __bool__(self):
        return bool(self.to_dicts())
    def __len__(self):
        return len(self.to_dicts())
    def fetch1(self):
        rows = self.to_dicts()
        if len(rows) != 1:
            raise ValueError('Expected exactly one row')
        return rows[0]
    def delete_quick(self):
        selected = self.to_dicts()
        self.rows[:] = [row for row in self.rows if row not in selected]
    def delete(self, *, transaction, prompt):
        assert not transaction and not prompt
        self.delete_quick()


class DeletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.path = self.root / 'raw-uploads/retained/source.h5'
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b'corrupted H5 which must not need a reader')
        self.identity = 'a' * 64
        self.project = uid(1)
        self.sources = Relation(('source_sha256',), [{'source_sha256': self.identity,
            'project_uuid': self.project, 'experiment_id': 1, 'experiment_uuid': uid(2),
            'manifest': {'source_sha256': self.identity, 'source_path': str(self.path),
                'source_filename': 'original.h5', 'counts': {'epochs': 1, 'cells': 1}}}])
        self.states = Relation(('project_uuid', 'source_sha256'))
        self.events = Relation(('event_uuid',))
        self.experiments = Relation(('id',), [{'id': 1, 'h5_uuid': uid(2)}, {'id': 2, 'h5_uuid': uid(3)}])
        self.epochs = Relation(('id',), [{'id': 10, 'experiment_id': 1, 'h5_uuid': uid(10)}, {'id': 11, 'experiment_id': 2, 'h5_uuid': uid(11)}])
        self.cells = Relation(('id',), [{'id': 20, 'experiment_id': 1, 'h5_uuid': uid(20)}, {'id': 21, 'experiment_id': 2, 'h5_uuid': uid(21)}])
        self.curation = Relation(('project_uuid', 'protocol_uuid', 'epoch_uuid'), [{'project_uuid': self.project, 'protocol_uuid': uid(4), 'epoch_uuid': uid(10), 'review_state': 'approved'}, {'project_uuid': self.project, 'protocol_uuid': uid(4), 'epoch_uuid': uid(11), 'review_state': 'approved'}])
        self.annotations = Relation(('target_uuid',), [{'project_uuid': self.project, 'target_kind': 'cell', 'target_uuid': uid(20)}, {'project_uuid': self.project, 'target_kind': 'cell', 'target_uuid': uid(21)}])
        self.bindings = Relation(('project_uuid', 'protocol_uuid'))
        self.revisions = Relation(('project_uuid', 'revision_uuid'))
        self.exports = Relation(('dataset_uuid',), [{'dataset_uuid': uid(100), 'source_sha256': self.identity}])
        self.connection = Connection([self.sources, self.states, self.events, self.experiments, self.epochs, self.cells, self.curation, self.annotations, self.bindings, self.revisions, self.exports])
        self.dj = types.SimpleNamespace(conn=lambda: self.connection)
        self.history = ExplorerHistory(self.dj, self.project, event_table=self.events, revision_table=self.revisions, binding_table=self.bindings)
        self.service = types.SimpleNamespace(project_dir=self.root, project={'project_uuid': self.project}, dj=self.dj,
            sources=[{'source_sha256': self.identity}], shared_annotations=types.SimpleNamespace(Annotation=self.annotations))
        self.stores = DataStores(self.service, types.SimpleNamespace(Curation=self.curation), self.history, state_table=self.states, source_table=self.sources, event_table=self.events)
        self.deletion = DataStoreDeletion(self.stores, catalog=types.SimpleNamespace(Experiment=self.experiments, Epoch=self.epochs, Cell=self.cells))
        self.revision = self.deletion.describe(self.identity)['registration_revision']
        self.initial = copy.deepcopy(self.sources.rows[0])

    def delete(self):
        return self.deletion.delete(self.identity, self.revision, confirmed=True)

    def pin(self):
        preview = {'membership': [{'uuid': uid(10), 'metadata_hash': 'b'*64}, {'uuid': uid(11), 'metadata_hash': 'c'*64}],
            'matched_count': 2, 'total_source': 2, 'predicate': {'field': 'protocol', 'operator': 'eq', 'value': 'Protocol'},
            'splits': 'cell', 'tree': {'split_order': ['cell']}, 'metadata_fingerprint_version': 2}
        revision = self.history.create(preview, self.service.sources, self.root/'catalog.json', 'tester', name='Pinned protocol')
        self.history.bind(revision['revision_uuid'], uid(4), 0, 'tester', {}, 0)
        return revision

    def test_corrupt_and_missing_managed_files_are_removed_without_h5_reads(self):
        for missing in (False, True):
            if missing:
                self.setUp()
                self.path.unlink()
            with patch('h5py.File', side_effect=AssertionError('Deletion cannot read waveform')):
                result = self.delete()
            self.assertEqual(result['stage'], 'completed')
            self.assertFalse(self.path.exists())
            self.assertFalse(self.sources.rows)
            self.assertEqual(self.experiments.rows, [{'id': 2, 'h5_uuid': uid(3)}])
            self.assertEqual([row['epoch_uuid'] for row in self.curation.rows], [uid(11)])
            self.assertEqual([row['target_uuid'] for row in self.annotations.rows], [uid(21)])
            self.assertTrue(self.exports.rows)

    def test_pinned_membership_is_pruned_atomically_and_historical_recipe_preserved(self):
        prior = self.pin()
        result = self.delete()
        current = self.history.protocol_binding(uid(4))
        self.assertEqual([row['uuid'] for row in current['recipe']['epochs']], [uid(11)])
        self.assertEqual(current['version'], 2)
        self.assertEqual(self.history.get(prior['revision_uuid']), prior)
        self.assertEqual(result['affected_protocol_uuids'], [uid(4)])
        self.assertEqual(current['recipe']['source_revisions'], [])

    def test_audit_failure_rolls_back_bindings_catalog_annotations_and_restores_file(self):
        self.pin()
        before = copy.deepcopy([table.rows for table in self.connection.tables])
        original_insert = self.events.insert1
        def fail(row):
            if row['action'] == 'data_store_deleted':
                raise RuntimeError('audit unavailable')
            original_insert(row)
        with patch.object(self.events, 'insert1', side_effect=fail), self.assertRaisesRegex(RuntimeError, 'audit unavailable'):
            self.delete()
        self.assertEqual([table.rows for table in self.connection.tables], before)
        self.assertEqual(self.path.read_bytes(), b'corrupted H5 which must not need a reader')
        self.assertEqual(json.loads(self.deletion._journal(self.identity).read_text())['stage'], 'rolled_back')

    def test_external_original_retained_and_symlink_managed_locator_rejected(self):
        original = self.root / 'external.h5'
        original.write_bytes(b'external original')
        self.sources.rows[0]['manifest']['source_path'] = str(original)
        self.revision = self.deletion.describe(self.identity)['registration_revision']
        self.assertFalse(self.deletion.describe(self.identity)['managed_file'])
        self.delete()
        self.assertEqual(original.read_bytes(), b'external original')
        linked = self.root / 'raw-uploads/link.h5'
        linked.symlink_to(original)
        with self.assertRaisesRegex(ValueError, 'symbolic'):
            managed_recording(self.root, linked)

    def test_confirmation_and_exact_registration_revision_precede_mutations(self):
        before = copy.deepcopy(self.sources.rows)
        with self.assertRaisesRegex(ValueError, 'confirmation'):
            self.deletion.delete(self.identity, self.revision, confirmed=False)
        with self.assertRaisesRegex(ValueError, 'registration changed'):
            self.deletion.delete(self.identity, 'stale', confirmed=True)
        self.assertEqual(self.sources.rows, before)
        self.assertTrue(self.path.exists())
        self.assertFalse(self.events.rows)

    def test_file_cleanup_failure_is_visible_and_retryable_after_catalog_commit(self):
        unlink = Path.unlink
        def fail(path, *args, **kwargs):
            if path.name == 'recording.h5':
                raise PermissionError('file cleanup unavailable')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail), self.assertRaisesRegex(PermissionError, 'cleanup unavailable'):
            self.delete()
        self.assertFalse(self.sources.rows)
        self.assertFalse(self.path.exists())
        self.assertEqual(json.loads(self.deletion._journal(self.identity).read_text())['stage'], 'cleanup_pending')
        self.assertEqual(self.delete()['stage'], 'completed')

    def test_same_sha_can_be_registered_again_without_retaining_old_curation(self):
        self.delete()
        self.sources.insert1(self.initial)
        self.experiments.insert1({'id': 1, 'h5_uuid': uid(2)})
        self.path.write_bytes(b'clean re-import fixture')
        self.assertFalse(any(row['epoch_uuid'] == uid(10) for row in self.curation.rows))
        self.delete()
        self.assertEqual(sum(row['action'] == 'data_store_deleted' for row in self.events.rows), 2)

    def test_crash_before_sql_commit_restores_quarantine_on_restart(self):
        operation = uid(500)
        quarantine = self.root / '.data-store-deletions' / operation / 'recording.h5'
        quarantine.parent.mkdir(parents=True)
        self.path.rename(quarantine)
        journal = {**self.deletion.describe(self.identity), 'operation_uuid': operation,
            'project_uuid': self.project, 'stage': 'file_quarantined', 'quarantine_path': str(quarantine),
            'removed_cell_uuids': []}
        from recording_workspace import write_json
        write_json(self.deletion._journal(self.identity), journal)
        self.deletion.recover_pending()
        self.assertTrue(self.path.exists())
        self.assertFalse(quarantine.exists())
        self.assertEqual(json.loads(self.deletion._journal(self.identity).read_text())['stage'], 'rolled_back')


import os
@unittest.skipUnless(os.environ.get('RIEKE_TEST_NATIVE_DELETION') == '1', 'opt-in private MySQL acquisition cascade integration')
class NativeDeletionTests(unittest.TestCase):
    def test_real_acquisition_cascade_preserves_other_source_and_allows_same_uuid_reimport(self):
        import datetime as dt
        from recording_workspace import connect, workspace_tables, write_json, digest
        from workspace_projects import create_project_at
        from disco.projects.project_database import ensure_project_database
        from workspace_native_mysql import stop_native_database
        from disco.decisions.curation import CurationStore
        from workspace_service import WorkspaceService
        with tempfile.TemporaryDirectory(prefix='rieke-native-delete-') as temporary:
            root = Path(temporary).resolve() / 'project'
            create_project_at(str(root), 'Disposable deletion verification')
            ensure_project_database(root)
            try:
                provider = json.loads((root/'catalog.json').read_text())['connection']['credential_provider']
                dj = connect(provider, project_dir=root)
                from retinanalysis.config import schema as catalog
                Project, Source, Event, _ = workspace_tables(dj)
                project = json.loads((root/'project.json').read_text())
                Project.insert1({'project_uuid':project['project_uuid'], 'name':project['name'], 'directory':str(root)})
                path = root / 'raw-uploads/source.h5'
                path.write_bytes(b'corrupt managed H5')
                metadata = root / 'imports/source/metadata.catalog.json'
                write_json(metadata, {'uuid':uid(2), 'animals':[]})
                identity = digest(path)
                manifest = {'source_sha256':identity, 'source_path':str(path), 'source_filename':'original.h5', 'source_size':path.stat().st_size,
                    'metadata_path':str(metadata), 'metadata_sha256':digest(metadata), 'counts':{'epochs':1,'cells':1}}
                common = {'label':'fixture','properties':{},'attributes':{}}
                catalog.Experiment.insert1({'id':1, 'h5_uuid':uid(2), 'exp_name':'fixture',
                    'meta_file':str(metadata), 'data_file':str(path), 'tags_file':'', 'is_mea':False,
                    'date_added':dt.datetime.now(), **common})
                catalog.Animal.insert1({'id':1,'h5_uuid':uid(5),'experiment_id':1,'parent_id':1,**common})
                catalog.Preparation.insert1({'id':1,'h5_uuid':uid(6),'experiment_id':1,'parent_id':1,**common})
                catalog.Cell.insert1({'id':1,'h5_uuid':uid(20),'experiment_id':1,'parent_id':1,**common})
                catalog.Protocol.insert1({'protocol_id':1,'name':'Fixture'})
                catalog.EpochGroup.insert1({'id':1,'h5_uuid':uid(7),'experiment_id':1,'parent_id':1,'protocol_id':1,**common})
                catalog.EpochBlock.insert1({'id':1,'h5_uuid':uid(8),'experiment_id':1,'parent_id':1,'protocol_id':1,'data_dir':'',**common})
                catalog.Epoch.insert1({'id':1,'h5_uuid':uid(10),'experiment_id':1,'parent_id':1,**common})
                catalog.Response.insert1({'id':1,'h5_uuid':uid(30),'parent_id':1,'device_name':'Amp1','h5path':'/invalid'})
                Source.insert1({'source_sha256':identity,'project_uuid':project['project_uuid'], 'experiment_uuid':uid(2),'experiment_id':1,'manifest':manifest})
                catalog.Experiment.insert1({'id':2,'h5_uuid':uid(3),'exp_name':'other',
                    'meta_file':str(metadata),'data_file':'/kept/original.h5','tags_file':'','is_mea':False,
                    'date_added':dt.datetime.now(),**common})
                # Opening a corrupt recording exposes manager repair, not stale scientific rows.
                service = WorkspaceService(root)
                self.assertFalse(service._loaded)
                self.assertEqual(service.sources[0]['filename'],'original.h5')
                store = CurationStore(dj, project['project_uuid'])
                history = ExplorerHistory(dj, project['project_uuid'])
                stores = DataStores(service,store,history)
                deletion = DataStoreDeletion(stores,catalog=catalog)
                preview = {'membership':[{'uuid':uid(10),'metadata_hash':'b'*64}],
                    'matched_count':1,'total_source':1,'predicate':{'field':'protocol','operator':'eq','value':'Fixture'},
                    'splits':'cell','tree':{'split_order':['cell']},'metadata_fingerprint_version':2}
                prior = history.create(preview,service.sources,root/'catalog.json','tester',name='Native pinned protocol')
                history.bind(prior['revision_uuid'],uid(4),0,'tester',{},0)
                info = deletion.describe(identity)
                original_insert = stores.Event.insert1
                def fail_audit(row, **options):
                    if row['action'] == 'data_store_deleted':
                        raise RuntimeError('native audit rollback probe')
                    return original_insert(row, **options)
                with patch.object(stores.Event, 'insert1', side_effect=fail_audit), self.assertRaisesRegex(RuntimeError, 'rollback probe'):
                    deletion.delete(identity,info['registration_revision'],confirmed=True)
                self.assertTrue(path.exists())
                self.assertEqual(len(catalog.Experiment()),2)
                self.assertEqual(len(catalog.Response()),1)
                self.assertEqual(history.protocol_binding(uid(4))['version'],1)
                result = deletion.delete(identity,info['registration_revision'],confirmed=True)
                self.assertEqual(result['stage'],'completed')
                self.assertFalse(path.exists())
                self.assertEqual(len(catalog.Experiment()),1)
                self.assertEqual((catalog.Experiment & {'id':2}).fetch1('h5_uuid'),uid(3))
                self.assertEqual(history.protocol_binding(uid(4))['recipe']['epochs'],[])
                self.assertEqual(history.protocol_binding(uid(4))['version'],2)
                self.assertEqual(len(catalog.Response()),0)
                self.assertEqual(len(catalog.Cell()),0)
                self.assertEqual(len(Source()),0)
                service.refresh()
                self.assertTrue(service._loaded)
                self.assertEqual(len(service.rows),0)
                self.assertEqual(service.sources,[])
                # All UUID collision probes are free for the same source acquisition again.
                catalog.Experiment.insert1({'id':1,'h5_uuid':uid(2),'exp_name':'fixture',
                    'meta_file':str(metadata),'data_file':str(path),'tags_file':'','is_mea':False,
                    'date_added':dt.datetime.now(),**common})
                catalog.Animal.insert1({'id':1,'h5_uuid':uid(5),'experiment_id':1,'parent_id':1,**common})
                catalog.Preparation.insert1({'id':1,'h5_uuid':uid(6),'experiment_id':1,'parent_id':1,**common})
                catalog.Cell.insert1({'id':1,'h5_uuid':uid(20),'experiment_id':1,'parent_id':1,**common})
                self.assertEqual(len(catalog.Cell()),1)
            finally:
                stop_native_database(root)
