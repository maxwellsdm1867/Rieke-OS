"""Independent scientific and crash oracles for the current-state mirror.

Expected values come from this fixture and explicit operations, never from the
production encoder, row-key helper, or recovery loader.
"""
import copy
import errno
import json
import os
from pathlib import Path
import select
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

import workspace_recovery_store as recovery
from workspace_state_snapshot import TABLES


def identity(number):
    return str(uuid.UUID(int=number))


def scientific_fixture():
    project=identity(1);protocols=[identity(10),identity(11)];epochs=[identity(20),identity(21)];cell=identity(30)
    profiles=[identity(40+i) for i in range(3)];revision=identity(50)
    tables={name:[] for name in TABLES}
    keys={
        'annotation_profile':['project_uuid','profile_uuid'],
        'shared_annotation':['project_uuid','target_kind','target_uuid','profile_uuid'],
        'curation':['project_uuid','protocol_uuid','epoch_uuid'],
        'explorer_revision':['project_uuid','revision_uuid'],
        'protocol_binding':['project_uuid','protocol_uuid'],
    }
    for p,profile in enumerate(profiles):
        author='Same display name' if p<2 else 'Third author'
        tables['annotation_profile'].append(dict(project_uuid=project,profile_uuid=profile,display_name=author,
            created_at='2026-09-29T10:11:12',created_by='fixture'))
        for kind,target in [('cell',cell),*[('epoch',epoch) for epoch in epochs]]:
            tables['shared_annotation'].append(dict(project_uuid=project,target_kind=kind,target_uuid=target,
                profile_uuid=profile,tags=['QC','qc','é','e\u0301',f'{kind}-{p}'],author_name=author,
                revision=1,updated_at='2026-09-29T10:11:12'))
    for n,protocol in enumerate(protocols):
        for epoch in epochs:
            tables['curation'].append(dict(project_uuid=project,protocol_uuid=protocol,epoch_uuid=epoch,
                included=1,tags=['QC',f'protocol-{n}'],review_state='unreviewed',revision=1,
                metadata_fingerprint='b'*64))
    members=[{'uuid':epoch,'metadata_hash':'b'*64} for epoch in epochs]
    recipe={'revision_uuid':revision,'epochs':members,'predicate':{'field':'annotations/effective/tags','operator':'contains','value':'QC'},
        'source_revisions':['a'*64],'typed':{'boolean':True,'integer':1,'float':1.0,'none':None,'empty':[]},
        'provenance':{'author':'Same display name'}}
    tables['explorer_revision']=[dict(project_uuid=project,revision_uuid=revision,parent_revision_uuid=None,
        recipe=recipe,summary={'epoch_count':2})]
    tables['protocol_binding']=[dict(project_uuid=project,protocol_uuid=protocols[0],revision_uuid=revision,version=1)]
    state={'format':'rieke-app-state','version':1,'project':{'project_uuid':project,'name':'Independent fixture'},
        'source_sha256s':['a'*64],'source_references':[{'source_sha256':'a'*64,'metadata_sha256':'b'*64,'source_path':'/recordings/source.h5'}],
        'protocols':{protocols[0]+'.json':{'protocol_uuid':protocols[0],'initial_revision_uuid':revision}},'tables':tables}
    return state,keys


def canonical(state):
    result=copy.deepcopy(state)
    for rows in result['tables'].values():
        rows.sort(key=lambda row:json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    return json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


class RecoveryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name).resolve();self.state,self.keys=scientific_fixture()
        self.watermark={'authority':'fixture-authority','epoch':identity(99),'generation':0}

    def write_baseline(self,*,day='2026-09-29'):
        return recovery.write(self.root,state=copy.deepcopy(self.state),keys=self.keys,watermark=self.watermark,day=day)

    def inspect(self):return recovery.inspect(self.root)

    def load(self):
        item=self.inspect();return recovery.load_database(item['path'],expected=item['pointer'])

    def delta(self,changes=None,deleted=None,*,day='2026-09-29',generation=1):
        header=copy.deepcopy(self.state);header['tables']={table:[] for table in TABLES}
        return recovery.write(self.root,state=header,keys=self.keys,watermark={**self.watermark,'generation':generation},
                              changes=changes or {},deleted=deleted,day=day)

    def assert_scientific_state(self,wanted):
        self.assertEqual(canonical(self.load()),canonical(wanted))

    def test_content_seals_track_only_changed_tables_and_match_complete_rebuild(self):
        self.write_baseline()
        original=copy.deepcopy(self.inspect()['header']['table_seals'])
        row={**self.state['tables']['shared_annotation'][0],'tags':['new exact é'],'revision':2}
        self.delta({'shared_annotation':[row]})
        changed=self.inspect()['header']['table_seals']
        self.assertNotEqual(changed['shared_annotation'],original['shared_annotation'])
        for table in TABLES:
            if table!='shared_annotation':self.assertEqual(changed[table],original[table])
        wanted=self.load()
        recovery.write(self.root,state=wanted,keys=self.keys,watermark=self.watermark,day='2026-09-29')
        self.assertEqual(self.inspect()['header']['table_seals'],changed)
        self.delta(deleted={'shared_annotation':[[row[name] for name in self.keys['shared_annotation']]]})
        self.assertEqual(self.inspect()['header']['table_seals']['shared_annotation']['count'],8)
        self.load()

    def test_verified_content_requires_fresh_unchanged_matching_authority(self):
        from unittest.mock import Mock
        self.watermark['project_uuid']=self.state['project']['project_uuid']
        self.write_baseline()
        tracker=Mock();tracker.token.return_value=self.watermark
        proof=recovery.verified_table_content(self.root,tracker)
        self.assertEqual(proof['project_uuid'],self.state['project']['project_uuid'])
        self.assertEqual(set(proof['tables']),{'shared_annotation','annotation_profile'})
        tracker.token.side_effect=[self.watermark,{**self.watermark,'generation':1}]
        self.assertIsNone(recovery.verified_table_content(self.root,tracker))
        tracker.token.side_effect=None;tracker.token.return_value=None
        self.assertIsNone(recovery.verified_table_content(self.root,tracker))

    def test_legacy_header_restores_but_requires_full_capture_before_content_proof(self):
        from unittest.mock import Mock
        import hashlib
        self.watermark['project_uuid']=self.state['project']['project_uuid']
        self.write_baseline();current=self.inspect();header=current['header'];header.pop('table_seals')
        blob=recovery._pack(header)
        with sqlite3.connect(current['path']) as db:
            db.execute('UPDATE recovery_header SET payload=?,sha256=?',(blob,hashlib.sha256(blob).digest()))
        self.assert_scientific_state(self.state)
        tracker=Mock();tracker.token.return_value=self.watermark
        self.assertIsNone(recovery.verified_table_content(self.root,tracker))
        with self.assertRaisesRegex(ValueError,'content-sealed baseline'):self.delta()
        self.write_baseline()
        self.assertIsNotNone(recovery.verified_table_content(self.root,tracker))

    def test_baseline_round_trip_preserves_exact_types_tags_profiles_and_frozen_members(self):
        result=self.write_baseline();self.assert_scientific_state(self.state)
        self.assertFalse(result['incremental']);self.assertEqual(self.inspect()['header']['watermark'],self.watermark)
        typed=self.load()['tables']['explorer_revision'][0]['recipe']['typed']
        self.assertIs(type(typed['boolean']),bool);self.assertIs(type(typed['integer']),int);self.assertIs(type(typed['float']),float)
        self.assertEqual({row['author_name'] for row in self.load()['tables']['shared_annotation']},{'Same display name','Third author'})

    def test_after_images_empty_tags_and_key_moves_preserve_unaffected_protocols_and_pin(self):
        self.write_baseline();wanted=copy.deepcopy(self.state)
        old=wanted['tables']['shared_annotation'][0];old_key=[old[name] for name in self.keys['shared_annotation']]
        moved={**old,'target_uuid':identity(31),'profile_uuid':identity(43),'tags':[],'revision':2}
        wanted['tables']['shared_annotation'][0]=moved
        decision={**wanted['tables']['curation'][0],'tags':['qc','new'],'revision':2};wanted['tables']['curation'][0]=decision
        self.delta({'shared_annotation':[moved],'curation':[decision]}, {'shared_annotation':[old_key]})
        self.assert_scientific_state(wanted)
        self.assertEqual(self.inspect()['header']['watermark']['generation'],1)
        self.assertEqual(self.load()['tables']['explorer_revision'],self.state['tables']['explorer_revision'])

    def test_deleting_all_rows_then_reinserting_does_not_resurrect_old_rows(self):
        self.write_baseline();wanted=copy.deepcopy(self.state)
        deleted={table:[[row[name] for name in self.keys[table]] for row in rows]
                 for table,rows in wanted['tables'].items() if rows}
        self.delta(deleted=deleted);wanted['tables']={table:[] for table in TABLES};self.assert_scientific_state(wanted)
        row={**self.state['tables']['shared_annotation'][1],'tags':['returned'],'revision':7}
        self.delta({'shared_annotation':[row]},generation=2);wanted['tables']['shared_annotation']=[row];self.assert_scientific_state(wanted)

    def test_repeated_after_image_is_idempotent_and_zero_change_advances_only_watermark(self):
        self.write_baseline();row={**self.state['tables']['shared_annotation'][0],'tags':['new'],'revision':2}
        wanted=copy.deepcopy(self.state);wanted['tables']['shared_annotation'][0]=row
        self.delta({'shared_annotation':[row]});self.delta({'shared_annotation':[row]},generation=2);self.delta(generation=3)
        self.assert_scientific_state(wanted);self.assertEqual(self.inspect()['header']['watermark']['generation'],3)

    def test_duplicate_primary_key_in_complete_capture_preserves_previous_mirror(self):
        self.write_baseline();invalid=copy.deepcopy(self.state)
        invalid['tables']['shared_annotation'][0]['tags']=['first duplicate']
        invalid['tables']['shared_annotation'].append({**invalid['tables']['shared_annotation'][0],
                                                       'tags':['conflicting duplicate']})
        with self.assertRaises(sqlite3.IntegrityError):
            recovery.write(self.root,state=invalid,keys=self.keys,
                           watermark={**self.watermark,'generation':1},day='2026-09-29')
        self.assert_scientific_state(self.state)
        self.assertEqual(self.inspect()['header']['watermark'],self.watermark)

    def test_duplicate_primary_key_in_delta_rolls_back_deletions_and_after_images(self):
        self.write_baseline();first={**self.state['tables']['shared_annotation'][0],'tags':['first duplicate']}
        second={**first,'tags':['conflicting duplicate']}
        deleted=self.state['tables']['curation'][0]
        deleted_key=[deleted[name] for name in self.keys['curation']]
        with self.assertRaisesRegex(ValueError,'Duplicate primary key'):
            self.delta({'shared_annotation':[first,second]}, {'curation':[deleted_key]})
        self.assert_scientific_state(self.state)
        self.assertEqual(self.inspect()['header']['watermark'],self.watermark)

    def test_incremental_requires_baseline_and_exact_project_key_contract(self):
        with self.assertRaisesRegex(ValueError,'baseline'):self.delta()
        self.write_baseline();before=canonical(self.load())
        foreign={**self.state['tables']['shared_annotation'][0],'project_uuid':identity(999)}
        with self.assertRaisesRegex(ValueError,'foreign'):self.delta({'shared_annotation':[foreign]})
        key=[foreign[name] for name in self.keys['shared_annotation']]
        with self.assertRaisesRegex(ValueError,'different project'):self.delta(deleted={'shared_annotation':[key]})
        self.assertEqual(canonical(self.load()),before);self.assertEqual(self.inspect()['header']['watermark'],self.watermark)

    def test_checkpoint_is_immutable_and_retention_preserves_unmanaged_backups(self):
        result=self.write_baseline();daily=Path(result['daily_backup']);original=daily.read_bytes()
        row={**self.state['tables']['shared_annotation'][0],'tags':['later'],'revision':2}
        self.delta({'shared_annotation':[row]});self.assertEqual(daily.read_bytes(),original)
        folder=daily.parent;legacy=folder/'2025-01-01.sqlite';legacy.write_bytes(b'legacy backup')
        explicit=folder/'before_restore.sqlite';explicit.write_bytes(b'user restore backup')
        self.delta(day='2026-09-30',generation=2);self.delta(day='2026-10-01',generation=3)
        managed=sorted(folder.glob('checkpoint-v2-*.sqlite'))
        self.assertLessEqual(len(managed),recovery.CHECKPOINT_COUNT);self.assertEqual(managed[-1].name,'checkpoint-v2-2026-10-01.sqlite')
        self.assertEqual(legacy.read_bytes(),b'legacy backup');self.assertEqual(explicit.read_bytes(),b'user restore backup')
        with patch.object(recovery,'CHECKPOINT_BYTES',1):
            self.delta(day='2026-10-02',generation=4)
            self.assertTrue(recovery.storage(self.root)['checkpoint_budget_exceeded'])
        self.assertEqual(len(list(folder.glob('checkpoint-v2-*.sqlite'))),1)

    def test_pointer_scope_and_path_validation_precedes_loading(self):
        self.write_baseline();item=self.inspect();pointer=item['pointer'];path=self.root/'app-state.json'
        for changes in ({'project_uuid':identity(999)},{'store':'../../outside.sqlite'},{'version':999}):
            with self.subTest(changes=changes):
                path.write_text(json.dumps({**pointer,**changes}))
                with self.assertRaises(ValueError):recovery.inspect(self.root)
        path.write_text(json.dumps(pointer));self.assert_scientific_state(self.state)

    def test_pointer_store_uuid_must_match_database_identity(self):
        self.write_baseline();item=self.inspect();new_id=identity(900)
        copied=item['path'].with_name('current-'+uuid.UUID(new_id).hex+'.sqlite');shutil.copy2(item['path'],copied)
        pointer={**item['pointer'],'store_uuid':new_id,'store':'backups/app-state/'+copied.name}
        (self.root/'app-state.json').write_text(json.dumps(pointer))
        with self.assertRaisesRegex(ValueError,'identity'):recovery.inspect(self.root)

    def test_symlinked_directories_and_current_files_are_rejected(self):
        external=self.root/'external';external.mkdir();(self.root/'backups').symlink_to(external,target_is_directory=True)
        with self.assertRaises(ValueError):self.write_baseline()
        self.assertEqual(list(external.iterdir()),[]);(self.root/'backups').unlink();self.write_baseline()
        item=self.inspect();moved=external/'copied.sqlite';shutil.move(item['path'],moved);item['path'].symlink_to(moved)
        before=moved.read_bytes()
        with self.assertRaises(ValueError):recovery.inspect(self.root)
        self.assertEqual(moved.read_bytes(),before)

    def test_complete_row_corruption_is_detected_before_restore_input(self):
        self.write_baseline();item=self.inspect()
        with sqlite3.connect(item['path']) as db:
            key=db.execute('SELECT table_name,row_key FROM recovery_rows LIMIT 1').fetchone()
            db.execute('UPDATE recovery_rows SET payload=? WHERE table_name=? AND row_key=?',(b'not the original content',*key))
        with self.assertRaisesRegex(ValueError,'checksum'):recovery.load_database(item['path'])

    def test_missing_row_is_detected_even_when_sqlite_structure_is_valid(self):
        self.write_baseline();item=self.inspect()
        with sqlite3.connect(item['path']) as db:
            key=db.execute('SELECT table_name,row_key FROM recovery_rows LIMIT 1').fetchone()
            db.execute('DELETE FROM recovery_rows WHERE table_name=? AND row_key=?',key)
            self.assertEqual(db.execute('PRAGMA quick_check').fetchall(),[('ok',)])
        with self.assertRaises(ValueError):recovery.load_database(item['path'])

    def test_failure_after_row_updates_rolls_back_rows_and_watermark(self):
        self.write_baseline();row={**self.state['tables']['shared_annotation'][0],'tags':['must roll back'],'revision':2}
        original=recovery._write_rows
        def failed(*args,**kwargs):
            original(*args,**kwargs);raise OSError(errno.ENOSPC,'injected disk full after rows')
        with patch.object(recovery,'_write_rows',side_effect=failed):
            with self.assertRaises(OSError):self.delta({'shared_annotation':[row]})
        self.assert_scientific_state(self.state);self.assertEqual(self.inspect()['header']['watermark'],self.watermark)

    def test_fsync_failure_after_sqlite_commit_is_reported_without_repeating_mutation(self):
        self.write_baseline();row={**self.state['tables']['shared_annotation'][0],'tags':['committed before error'],'revision':2}
        wanted=copy.deepcopy(self.state);wanted['tables']['shared_annotation'][0]=row
        with patch.object(recovery.os,'fsync',side_effect=OSError(errno.EIO,'injected synchronization failure')):
            with self.assertRaises(OSError):self.delta({'shared_annotation':[row]})
        self.assert_scientific_state(wanted);self.assertEqual(self.inspect()['header']['watermark']['generation'],1)
        self.delta({'shared_annotation':[row]});self.assert_scientific_state(wanted)

    def test_failed_pointer_publication_keeps_older_v1_snapshot_readable(self):
        legacy=json.dumps(self.state).encode();(self.root/'app-state.json').write_bytes(legacy)
        with patch('workspace_state_snapshot.atomic_write',side_effect=OSError(errno.EIO,'pointer publication failed')):
            with self.assertRaises(OSError):self.write_baseline()
        self.assertEqual((self.root/'app-state.json').read_bytes(),legacy);self.assertIsNone(recovery.inspect(self.root))
        self.write_baseline();self.assert_scientific_state(self.state)

    def test_failed_baseline_publications_do_not_accumulate_full_current_images(self):
        legacy=json.dumps(self.state).encode();(self.root/'app-state.json').write_bytes(legacy)
        for _ in range(3):
            with patch('workspace_state_snapshot.atomic_write',side_effect=OSError(errno.EIO,'pointer publication failed')):
                with self.assertRaises(OSError):self.write_baseline()
        self.write_baseline();item=self.inspect();self.assert_scientific_state(self.state)
        self.assertEqual(list(item['path'].parent.glob('current-*.sqlite')),[item['path']])

    def test_error_after_pointer_publication_keeps_the_referenced_database(self):
        from workspace_state_snapshot import atomic_write
        def published_then_error(*args,**kwargs):
            atomic_write(*args,**kwargs);raise OSError(errno.EIO,'error after pointer publication')
        with patch('workspace_state_snapshot.atomic_write',side_effect=published_then_error):
            with self.assertRaises(OSError):self.write_baseline()
        self.assert_scientific_state(self.state)

    def test_daily_checkpoint_failure_preserves_the_committed_current_mirror(self):
        self.write_baseline();row={**self.state['tables']['shared_annotation'][0],'tags':['current survives'],'revision':2}
        wanted=copy.deepcopy(self.state);wanted['tables']['shared_annotation'][0]=row
        with patch.object(recovery,'checkpoint',side_effect=OSError(errno.ENOSPC,'daily checkpoint full')):
            with self.assertRaises(OSError):self.delta({'shared_annotation':[row]},day='2026-09-30')
        self.assert_scientific_state(wanted);self.assertEqual(self.inspect()['header']['watermark']['generation'],1)

    def _kill_at(self,phase):
        row={**self.state['tables']['shared_annotation'][0],'tags':['crash boundary'],'revision':2}
        header=copy.deepcopy(self.state);header['tables']={table:[] for table in TABLES}
        request={'root':str(self.root),'state':header,'keys':self.keys,'watermark':{**self.watermark,'generation':1},
                 'changes':{'shared_annotation':[row]},'day':'2026-09-29'}
        if phase=='rows':
            request['changes']['shared_annotation']=[{**original,'tags':['crash boundary',*[identity(100000+i*20+j) for j in range(20)]],'revision':2}
                for i,original in enumerate(self.state['tables']['shared_annotation'])]
        request_path=self.root/'child-request.json';request_path.write_text(json.dumps(request))
        script='''import json,os,sys,time
from contextlib import contextmanager
import workspace_recovery_store as recovery
request=json.load(open(sys.argv[1]));phase=sys.argv[2]
def stop():
 os.write(1,b'READY\\n');time.sleep(30)
if phase=='rows':
 connect=recovery._connect
 @contextmanager
 def tiny_cache(*args,**kwargs):
  with connect(*args,**kwargs) as database:
   if not kwargs.get('readonly'):
    database.execute('PRAGMA cache_size=1');database.execute('PRAGMA cache_spill=ON')
   yield database
 recovery._connect=tiny_cache
 original=recovery._write_rows
 def write_rows(*args,**kwargs):
  original(*args,**kwargs);stop()
 recovery._write_rows=write_rows
else:
 recovery.os.fsync=lambda descriptor:stop()
recovery.write(**request)
'''
        process=subprocess.Popen([sys.executable,'-c',script,str(request_path),phase],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                 env={**os.environ,'PYTHONPATH':str(Path(recovery.__file__).parent)})
        try:
            ready,_,_=select.select([process.stdout],[],[],10)
            self.assertTrue(ready,'Recovery subprocess did not reach its crash cut')
            line=process.stdout.readline()
            if line!=b'READY\n':self.fail('Recovery subprocess failed: '+process.stderr.read().decode())
            process.kill();process.wait(timeout=10)
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=10)
            process.stdout.close();process.stderr.close()
        return row

    def test_actual_process_kill_before_commit_recovers_complete_old_state(self):
        original=self.state['tables']['shared_annotation'][0]
        self.state['tables']['shared_annotation']=[{**original,'target_kind':'epoch','target_uuid':identity(1000+i)} for i in range(500)]
        self.write_baseline();self._kill_at('rows');self.assert_scientific_state(self.state)
        self.assertEqual(self.inspect()['header']['watermark'],self.watermark)

    def test_actual_process_kill_after_commit_recovers_complete_new_state(self):
        self.write_baseline();row=self._kill_at('fsync');wanted=copy.deepcopy(self.state);wanted['tables']['shared_annotation'][0]=row
        self.assert_scientific_state(wanted);self.assertEqual(self.inspect()['header']['watermark']['generation'],1)


if __name__=='__main__':unittest.main()
