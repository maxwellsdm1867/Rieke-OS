import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch
from workspace_state_snapshot import compact_queries, expand_queries, serialized, load, save, restore


class StateSnapshotTests(unittest.TestCase):
    def fixture(self):
        project,revision,protocol=[str(uuid.uuid4()) for _ in range(3)]
        members=[{'uuid':str(uuid.uuid4()),'metadata_hash':'b'*64} for _ in range(1000)]
        members.sort(key=lambda row:row['uuid'])
        service=SimpleNamespace(rows={row['uuid']:{'source_sha256':'a'*64} for row in members},
            _fingerprints={row['uuid']:row['metadata_hash'] for row in members},
            match_predicate=lambda predicate,eligible:(predicate,eligible,None))
        recipe={'revision_uuid':revision,'epochs':members,'predicate':{'all':[]},'source_revisions':['a'*64],
                'diff':{'added':[row['uuid'] for row in members]},'content_sha256':'c'*64,
                'provenance':{'application':{'version':'test'},'code':{'large':'unnecessary'}}}
        row={'project_uuid':project,'revision_uuid':revision,'parent_revision_uuid':None,'summary':{},'recipe':recipe}
        state={'tables':{'explorer_revision':[row],'protocol_binding':[{'revision_uuid':revision}]},
               'protocols':{protocol+'.json':{'initial_revision_uuid':revision}}}
        return state,service,members

    def test_thousand_epoch_pin_recovers_from_small_query_without_uuid_list(self):
        state,service,members=self.fixture()
        compact_queries(state,service)
        text=serialized(state)
        self.assertLess(len(text),2000)
        self.assertNotIn(members[0]['uuid'],text)
        self.assertNotIn('code',state['tables']['explorer_revision'][0]['recipe']['provenance'])
        expand_queries(state,service)
        self.assertEqual(state['tables']['explorer_revision'][0]['recipe']['epochs'],members)
        self.assertEqual(state['tables']['protocol_binding'][0]['revision_uuid'],
                         state['tables']['explorer_revision'][0]['revision_uuid'])

    def test_different_metadata_refuses_recovery_instead_of_changing_pin(self):
        state,service,members=self.fixture();compact_queries(state,service)
        service._fingerprints[members[0]['uuid']]='d'*64
        with self.assertRaisesRegex(ValueError,'no longer reproduces'):
            expand_queries(state,service)

    def test_explicit_subset_keeps_only_required_existing_frozen_membership(self):
        state,service,members=self.fixture()
        state['tables']['explorer_revision'][0]['recipe']['epochs']=members[:2]
        compact_queries(state,service)
        self.assertNotIn('requery',state['tables']['explorer_revision'][0]['recipe'])
        self.assertEqual(len(state['tables']['explorer_revision'][0]['recipe']['epochs']),2)

    def test_daily_sqlite_checksum_rejects_tampered_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'snapshot.sqlite'
            with sqlite3.connect(path) as connection:
                connection.execute('CREATE TABLE snapshot (format,version,sha256,document)')
                connection.execute('INSERT INTO snapshot VALUES (?,?,?,?)',('rieke-app-state',1,'0'*64,'{}'))
            with self.assertRaisesRegex(ValueError,'checksum'):
                load(path)

    def test_restore_refuses_open_app_before_reading_or_writing_state(self):
        import fcntl
        with tempfile.TemporaryDirectory() as folder:
            with (Path(folder)/'.app-state-session.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_SH)
                with self.assertRaisesRegex(ValueError,'Stop the project app'):
                    restore(folder,None,Path(folder)/'unused.sqlite')
