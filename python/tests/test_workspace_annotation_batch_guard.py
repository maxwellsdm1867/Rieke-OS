"""Outer-transaction annotation/ledger coupling, using owned SQL doubles only."""
import contextlib
import copy
import threading
import unittest
from unittest.mock import Mock, patch

import test_workspace_annotations as fixtures
from test_workspace_curation import Table
from workspace_curation import RevisionConflict


class TrackedConnection:
    def __init__(self, delegate):
        self.delegate=delegate
        self.in_transaction=False
        self._conn=object()
        self.begins=0
        self.order=[]

    def query(self, sql):
        self.order.append(sql)
        return self.delegate.query(sql)

    @property
    @contextlib.contextmanager
    def transaction(self):
        if self.in_transaction:
            raise AssertionError('No nested annotation transaction')
        self.begins+=1
        self.order.append('BEGIN')
        self.in_transaction=True
        try:
            with self.delegate.transaction:
                yield
            self.order.append('COMMIT')
        except Exception:
            self.order.append('ROLLBACK')
            raise
        finally:
            self.in_transaction=False


class GuardedBatchTests(unittest.TestCase):
    def setUp(self):
        self.case=fixtures.SharedAnnotationTests()
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.store=self.case.store
        self.connection=TrackedConnection(self.case.case.connection)
        self.case.service.dj.conn=lambda:self.connection
        self.ledger=Table(('step',))
        self.connection.delegate.tables.append(self.ledger)
        self.store.on_commit=Mock()
        self.cached=object()
        self.store._vocabulary=self.cached

    def operation(self,target=None,revision=0,tag='group tag'):
        return dict(target_kind='epoch',target_uuid=target or self.case.first,
                    profile_uuid=self.case.author,expected_revision=revision,tags_add=[tag])

    def test_private_primitive_requires_live_guard_and_native_transaction(self):
        with self.assertRaisesRegex(RuntimeError,'guard'):
            self.store._apply_batch_locked([self.operation()],'actor')
        with self.store.lock():
            with self.assertRaisesRegex(RuntimeError,'active native transaction'):
                self.store._apply_batch_locked([self.operation()],'actor')
        with self.connection.transaction:
            with self.assertRaisesRegex(RuntimeError,'guard'):
                self.store._apply_batch_locked([self.operation()],'actor')
        self.assertEqual(self.case.records.rows,[])
        self.store.on_commit.assert_not_called()

    def test_annotation_audit_and_ledger_share_one_outer_transaction(self):
        with self.store.lock(),self.connection.transaction:
            result=self.store._apply_batch_locked([self.operation()],'OS actor',include_undo=True)
            self.ledger.insert1({'step':0,'changed':result['changed']})
            self.assertEqual(result['changed'],1)
            self.assertEqual(len(self.case.case.events.rows),1)
            self.store.on_commit.assert_not_called()
            self.assertIs(self.store._vocabulary,self.cached)
        self.assertEqual(self.connection.begins,1)
        self.assertEqual(self.ledger.rows,[{'step':0,'changed':1}])
        self.assertEqual(result['undo']['target_kind'],'epoch')
        self.store._after_batch_commit(result)
        self.store.on_commit.assert_called_once_with()
        self.assertIsNone(self.store._vocabulary)
        self.assertIn('GET_LOCK',self.connection.order[0])
        self.assertEqual(self.connection.order[1],'BEGIN')
        self.assertIn('RELEASE_LOCK',self.connection.order[-1])

    def test_ledger_failure_rolls_back_annotations_profiles_audit_without_hooks(self):
        before=copy.deepcopy((self.case.records.rows,self.case.profiles.rows,self.case.case.events.rows))
        with self.assertRaisesRegex(RuntimeError,'ledger failed'):
            with self.store.lock(),self.connection.transaction:
                self.store._apply_batch_locked([self.operation()],'actor')
                self.ledger.insert1({'step':0})
                raise RuntimeError('ledger failed')
        self.assertEqual((self.case.records.rows,self.case.profiles.rows,self.case.case.events.rows),before)
        self.assertEqual(self.ledger.rows,[])
        self.assertIs(self.store._vocabulary,self.cached)
        self.store.on_commit.assert_not_called()

    def test_last_target_conflict_is_checked_before_first_write(self):
        self.case.edit('epoch',self.case.second,['existing'])
        self.store.on_commit.reset_mock()
        with patch.object(self.case.records,'insert1',wraps=self.case.records.insert1) as insert:
            with self.assertRaises(RevisionConflict):
                with self.store.lock(),self.connection.transaction:
                    self.store._apply_batch_locked([
                        self.operation(),self.operation(self.case.second)],'actor')
            insert.assert_not_called()
        self.store.on_commit.assert_not_called()

    def test_last_target_tag_limit_is_checked_before_first_write(self):
        self.case.edit('epoch',self.case.second,[str(index) for index in range(100)])
        self.store.on_commit.reset_mock()
        with patch.object(self.case.records,'insert1',wraps=self.case.records.insert1) as insert:
            with self.assertRaisesRegex(ValueError,'100 current tags'):
                with self.store.lock(),self.connection.transaction:
                    self.store._apply_batch_locked([
                        self.operation(),self.operation(self.case.second,1)],'actor')
            insert.assert_not_called()
        self.store.on_commit.assert_not_called()

    def test_noop_external_receipt_commits_without_change_notification(self):
        self.case.edit('epoch',self.case.first,['group tag'])
        self.store.on_commit.reset_mock()
        event_count=len(self.case.case.events.rows)
        with self.store.lock(),self.connection.transaction:
            result=self.store._apply_batch_locked([self.operation(revision=1)],'actor',
                external_receipt={'message_sha256':'a'*64})
            self.ledger.insert1({'step':0,'changed':0})
        self.store._after_batch_commit(result)
        self.assertEqual(result['changed'],0)
        self.assertEqual(len(self.case.case.events.rows),event_count+1)
        self.assertEqual(self.case.case.events.rows[-1]['action'],'external_annotation_received')
        self.store.on_commit.assert_not_called()

    def test_hook_refuses_running_transaction_and_rollback_emits_nothing(self):
        with self.store.lock(),self.connection.transaction:
            with self.assertRaisesRegex(RuntimeError,'committed transaction'):
                self.store._after_batch_commit({'changed':1})
        with patch.object(self.case.case.events,'insert1',side_effect=RuntimeError('audit failed')):
            with self.assertRaisesRegex(RuntimeError,'audit failed'):
                self.store.apply_batch([self.operation()],'actor')
        self.assertEqual(self.case.records.rows,[])
        self.store.on_commit.assert_not_called()
        self.assertIs(self.store._vocabulary,self.cached)

    def test_guard_refuses_reconnection_other_thread_and_expired_lease(self):
        errors=[]
        with self.store.lock(),self.connection.transaction:
            native=self.connection._conn
            self.connection._conn=object()
            with self.assertRaisesRegex(RuntimeError,'guard'):
                self.store._apply_batch_locked([self.operation()],'actor')
            self.connection._conn=native
            context=__import__('contextvars').copy_context()
            def invoke():
                try:self.store._apply_batch_locked([self.operation()],'actor')
                except RuntimeError as error:errors.append(str(error))
            thread=threading.Thread(target=lambda:context.run(invoke))
            thread.start();thread.join()
        self.assertEqual(len(errors),1)
        with self.assertRaisesRegex(RuntimeError,'guard'):
            context.run(self.store._apply_batch_locked,[self.operation()],'actor')
        self.assertEqual(self.case.records.rows,[])


if __name__=='__main__':unittest.main()
