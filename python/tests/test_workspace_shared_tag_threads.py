"""Transfer actual SQLite ownership safely across scientific HTTP threads."""
import concurrent.futures
import copy
import threading
import unittest

from workspace_shared_tag_index import SharedTagIndex


class SharedTagThreadTests(unittest.TestCase):
    def setUp(self):
        self.version=1
        self.rows=[{'epoch_uuid':'epoch-1','cell_uuid':'cell-1'}, {'epoch_uuid':'epoch-2','cell_uuid':'cell-1'}]
        self.saved=[{'target_kind':'epoch','target_uuid':'epoch-1','profile_uuid':'profile-1',
                     'author_name':'Author','revision':1,'tags':['exact','é']}]
        self.index=SharedTagIndex(generation=lambda:self.version,changes=lambda token:None,
                                 records=lambda keys:iter(copy.deepcopy(self.saved)),validate=lambda row:row['tags'])
        self.addCleanup(self.index.close)

    def test_connection_built_in_one_thread_can_rebuild_query_and_close_in_another(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as first, \
                concurrent.futures.ThreadPoolExecutor(max_workers=1) as second:
            first_id=first.submit(threading.get_ident).result(timeout=5)
            self.assertTrue(first.submit(self.index.refresh).result(timeout=5))
            self.assertEqual(first.submit(self.index.matching,self.rows,{'tag':'exact'}).result(timeout=5)[0],('epoch-1',))
            # Keep the first worker alive so SQLite cannot mistake a recycled
            # thread identifier for ownership transfer.
            self.assertNotEqual(first_id,second.submit(threading.get_ident).result(timeout=5))
            # Force the production full-rebuild path that closes the previous
            # connection before creating its replacement on a Waitress worker.
            self.version=2
            self.saved[0]['revision']=2;self.saved[0]['tags']=['changed']
            self.assertTrue(second.submit(self.index.refresh).result(timeout=5))
            self.assertEqual(second.submit(self.index.matching,self.rows,{'tag':'changed'}).result(timeout=5)[0],('epoch-1',))
            self.assertEqual(second.submit(self.index.summary,self.rows).result(timeout=5)['shared_tagged_epochs'],1)
            second.submit(self.index.close).result(timeout=5)
        self.assertIsNone(self.index.connection)

    def test_overlapping_queries_have_independent_exact_temp_scopes(self):
        self.index.refresh()
        barrier=threading.Barrier(6)
        def query(number):
            barrier.wait(timeout=5)
            rows=self.rows if number%2==0 else list(reversed(self.rows))
            for _ in range(12):
                actual,token=self.index.matching(rows,{}, {'not':{'field':'annotations/epoch/tags','operator':'contains','value':'absent'}})
                if actual!=tuple(row['epoch_uuid'] for row in rows) or token!=1:
                    raise AssertionError('Another request replaced this query scope')
                catalog=self.index.catalog(rows,['annotations/epoch/tags'])
                if catalog['annotations/epoch/tags']['count']!=2:
                    raise AssertionError('Another request replaced this catalog scope')
                if self.index.summary(rows)['shared_tagged_epochs']!=1:
                    raise AssertionError('Another request replaced this summary scope')
            return True
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            self.assertTrue(all(result.result(timeout=15) for result in [pool.submit(query,i) for i in range(6)]))

    def test_close_waits_for_full_refresh_transaction_and_allows_later_reopen(self):
        entered,release,closed=threading.Event(),threading.Event(),threading.Event()
        def records(keys):
            entered.set()
            if not release.wait(timeout=5):raise AssertionError('Test did not release paused canonical read')
            yield from copy.deepcopy(self.saved)
        self.index.records=records
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            refreshing=pool.submit(self.index.refresh)
            self.assertTrue(entered.wait(timeout=5))
            closing=pool.submit(lambda:(self.index.close(),closed.set()))
            try:self.assertFalse(closed.wait(timeout=.05),'Close raced an active SQLite transaction')
            finally:release.set()
            self.assertTrue(refreshing.result(timeout=5))
            closing.result(timeout=5)
        self.assertIsNone(self.index.connection)
        self.index.records=lambda keys:iter(copy.deepcopy(self.saved))
        self.assertTrue(self.index.refresh())
        self.assertEqual(self.index.matching(self.rows,{'tag':'exact'})[0],('epoch-1',))


if __name__=='__main__':unittest.main()
