"""Retire derived generations only after publication and the last live reader."""
import gc
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from workspace_cache_lifecycle import CacheNamespace
from workspace_disk_index import DiskMetadataIndex
from workspace_projection_cache import ProjectionCache
from test_workspace_disk_index import fixture


READER=r'''
import json,sys
from pathlib import Path
from workspace_disk_index import DiskMetadataIndex
index=DiskMetadataIndex.open(sys.argv[1],sys.argv[2],'project')
Path(sys.argv[3]).write_text('ready')
sys.stdin.readline()
Path(sys.argv[4]).write_text(json.dumps(sorted(index.rows())))
index.close()
'''


class CacheLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='rieke-cache-lifecycle-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.rows,self.details,self.sources=fixture(9)

    def build(self,number):
        generation=f'{number:064x}'
        index=DiskMetadataIndex.build(self.root/'metadata'/(generation+'.sqlite'),
            self.rows,self.details,self.sources,generation,'project')
        return index

    def test_lazy_views_pin_old_generation_until_last_reference_is_dropped(self):
        old=self.build(1);old.publish();path=old.path
        details=old.details;values=old.values(['epoch-1'])
        current=self.build(2);self.addCleanup(current.close)
        result=current.publish()
        self.assertIn(path.name,result['leased_generations'])
        del old;gc.collect()
        self.assertTrue(path.exists())
        self.assertEqual(details['epoch-1'],self.details['epoch-1'])
        self.assertEqual(list(values),['epoch-1'])
        del details,values;gc.collect()
        self.assertFalse(path.exists())
        self.assertFalse(Path(str(path)+'.sha256.json').exists())
        self.assertEqual(len(current.rows()),9)

    def test_repeated_successful_refreshes_are_bounded_and_unchanged_reopen_reuses(self):
        current=None
        for number in range(1,9):
            current=self.build(number);current.publish()
            self.assertEqual(list(current.path.parent.glob('*.sqlite')),[current.path])
        path=current.path;generation=current.generation;before=path.stat().st_mtime_ns
        current.close()
        reopened=DiskMetadataIndex.open(path,generation,'project')
        self.addCleanup(reopened.close)
        self.assertEqual(path.stat().st_mtime_ns,before)
        self.assertEqual(len(reopened.details),9)
        self.assertEqual(len(list((path.parent/'.reader-leases').glob('*.lock'))),1)

    def test_failed_build_keeps_last_published_generation_and_ignores_unknown_files(self):
        old=self.build(1);old.publish();self.addCleanup(old.close)
        before=(old.path.read_bytes(),Path(str(old.path)+'.sha256.json').read_bytes())
        unknown=old.path.parent/'scientist-notes.txt';unknown.write_text('keep this')
        outside=self.root/'outside.txt';outside.write_text('outside scientific data')
        link=old.path.parent/(f'{3:064x}'+'.sqlite');link.symlink_to(outside)
        class FailedDetails(dict):
            def __getitem__(self,key):raise RuntimeError('Failed verification')
        with self.assertRaisesRegex(RuntimeError,'Failed verification'):
            DiskMetadataIndex.build(old.path.parent/(f'{2:064x}'+'.sqlite'),self.rows,
                FailedDetails(self.details),self.sources,f'{2:064x}','project')
        CacheNamespace(old.path.parent,'metadata','project').collect()
        self.assertEqual((old.path.read_bytes(),Path(str(old.path)+'.sha256.json').read_bytes()),before)
        self.assertEqual(len(old.rows()),9)
        self.assertEqual(unknown.read_text(),'keep this')
        self.assertTrue(link.is_symlink());self.assertEqual(outside.read_text(),'outside scientific data')
        self.assertFalse(list(old.path.parent.glob('*.building*')))

    def test_other_process_can_read_retired_generation_and_exit_releases_lease(self):
        for killed in (False,True):
            with self.subTest(killed=killed):
                old=self.build(10 if killed else 1);old.publish();path=old.path;generation=old.generation
                old.close()
                marker=self.root/('ready-kill' if killed else 'ready-read')
                result=self.root/('result-kill' if killed else 'result-read')
                environment={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])}
                child=subprocess.Popen([sys.executable,'-c',READER,str(path),generation,str(marker),str(result)],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=environment)
                try:
                    deadline=time.monotonic()+10
                    while not marker.exists() and child.poll() is None and time.monotonic()<deadline:time.sleep(.01)
                    self.assertTrue(marker.exists(),'Child did not acquire its reader lease')
                    current=self.build(11 if killed else 2);current.publish()
                    self.assertTrue(path.exists())
                    if killed:child.kill();child.communicate(timeout=10)
                    else:
                        output,error=child.communicate('\n',timeout=10)
                        self.assertEqual(child.returncode,0,error)
                        self.assertEqual(json.loads(result.read_text()),sorted(row['epoch_uuid'] for row in self.rows))
                    CacheNamespace(path.parent,'metadata','project').collect()
                    self.assertFalse(path.exists());self.assertTrue(current.path.exists())
                    current.close()
                finally:
                    if child.poll() is None:child.kill();child.communicate(timeout=10)

    def test_projection_publication_retains_prepared_reader_then_reclaims_old_key(self):
        cache=ProjectionCache(self.root/'projections')
        projection=dict(rows={},details={},cells={},source={},fingerprints={})
        old=('source','old');new=('source','new')
        old_path=Path(cache.write(old,projection));cache.publish([old])
        held=cache.hold([old])
        new_path=Path(cache.write(new,projection));cache.publish([new])
        self.assertTrue(old_path.exists());self.assertEqual(cache.read(old),projection)
        held.close()
        self.assertFalse(old_path.exists());self.assertTrue(new_path.exists())
        self.assertEqual(cache.read(new),projection)
        cache.publish([new])
        self.assertEqual(list(cache.directory.glob('*.json.zlib')),[new_path])

    @unittest.skipUnless(hasattr(os,'fork'),'Requires inherited POSIX reader descriptors')
    def test_parent_close_does_not_unlock_a_forked_reader(self):
        old=self.build(1);old.publish();path=old.path
        ready_read,ready_write=os.pipe();release_read,release_write=os.pipe()
        child=os.fork()
        if child==0:
            try:
                os.close(ready_read);os.close(release_write)
                os.write(ready_write,b'r');os.read(release_read,1)
                os._exit(0 if len(old.rows())==9 else 2)
            except BaseException:os._exit(3)
        os.close(ready_write);os.close(release_read)
        try:
            self.assertEqual(os.read(ready_read,1),b'r')
            old.close()
            current=self.build(2);current.publish();self.addCleanup(current.close)
            self.assertTrue(path.exists())
            os.write(release_write,b'g')
            _,status=os.waitpid(child,0);child=None
            self.assertEqual(os.waitstatus_to_exitcode(status),0)
            CacheNamespace(path.parent,'metadata','project').collect()
            self.assertFalse(path.exists())
        finally:
            os.close(ready_read);os.close(release_write)
            if child is not None:
                try:os.kill(child,signal.SIGKILL)
                except ProcessLookupError:pass
                os.waitpid(child,0)

    def test_active_builder_staging_is_protected_and_orphan_staging_is_collected(self):
        current=self.build(1);current.publish();self.addCleanup(current.close)
        namespace=CacheNamespace(current.path.parent,'metadata','project')
        key=f'{2:064x}'+'.sqlite'
        lease=namespace.lease(key)
        stage=current.path.parent/(key+'.temporary.building');stage.write_bytes(b'partial derived data')
        namespace.collect();self.assertTrue(stage.exists())
        lease.close();self.assertFalse(stage.exists())
        self.assertTrue(current.path.exists())


if __name__=='__main__':unittest.main()
