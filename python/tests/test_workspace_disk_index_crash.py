"""Real process termination at derived-index construction/publication boundaries.

Only disposable SQLite indexes are touched. This verifies reader fail-closed
behavior and preservation of a separately named previous generation; it is not
a MySQL, application restore, filesystem power-loss, or lab-data experiment.
"""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from workspace_disk_index import DiskMetadataIndex
from test_workspace_disk_index import fixture


WORKER = r'''
import os,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1]);sys.path.insert(0,sys.argv[2])
from workspace_disk_index import DiskMetadataIndex
from test_workspace_disk_index import fixture
target,marker,stage=Path(sys.argv[3]),Path(sys.argv[4]),sys.argv[5]
rows,details,sources=fixture(512)
def checkpoint():
    with marker.open('w') as stream:
        stream.write(stage);stream.flush();os.fsync(stream.fileno())
    while True:time.sleep(1)
class InterruptedDetails(dict):
    def __getitem__(self,key):
        if stage=='during_build' and key=='epoch-8':checkpoint()
        return super().__getitem__(key)
replace=os.replace
def interrupted_replace(source,destination):
    if str(destination)==str(target) and stage=='before_database_publish':checkpoint()
    replace(source,destination)
    if str(destination)==str(target) and stage=='after_database_publish':checkpoint()
    if str(destination)==str(target)+'.sha256.json' and stage=='after_seal_publish':checkpoint()
os.replace=interrupted_replace
DiskMetadataIndex.build(target,rows,InterruptedDetails(details),sources,'next','project')
raise RuntimeError('Worker did not reach the requested checkpoint')
'''


@unittest.skipUnless(hasattr(signal,'SIGKILL'),'Requires abrupt process termination')
class IndexProcessKillTests(unittest.TestCase):
    def test_reader_refuses_torn_generation_and_keeps_previous_generation(self):
        python_dir=Path(__file__).resolve().parents[1]
        for stage in ('during_build','before_database_publish','after_database_publish','after_seal_publish'):
            with self.subTest(stage=stage),tempfile.TemporaryDirectory(prefix='rieke-index-kill-') as folder:
                directory=Path(folder);old=directory/'old.sqlite';target=directory/'next.sqlite';marker=directory/'checkpoint'
                rows,details,sources=fixture(31)
                original=DiskMetadataIndex.build(old,rows,details,sources,'old','project')
                before=old.read_bytes();seal=Path(str(old)+'.sha256.json').read_bytes()
                log=directory/'worker.log'
                with log.open('w') as output:
                    child=subprocess.Popen([sys.executable,'-c',WORKER,str(python_dir),str(python_dir/'tests'),
                        str(target),str(marker),stage],stdout=output,stderr=subprocess.STDOUT)
                    try:
                        deadline=time.monotonic()+20
                        while not marker.exists() and child.poll() is None and time.monotonic()<deadline:
                            time.sleep(.01)
                        self.assertTrue(marker.exists(),'Missing checkpoint: '+log.read_text())
                        child.kill();child.wait(timeout=10)
                        self.assertEqual(child.returncode,-signal.SIGKILL)
                    finally:
                        if child.poll() is None:child.kill();child.wait(timeout=10)
                self.assertEqual(old.read_bytes(),before)
                self.assertEqual(Path(str(old)+'.sha256.json').read_bytes(),seal)
                self.assertEqual(original.rows(),{row['epoch_uuid']:row for row in rows})
                restored=DiskMetadataIndex.open(old,'old','project')
                self.assertEqual(len(restored.details),31)
                if stage=='after_seal_publish':
                    complete=DiskMetadataIndex.open(target,'next','project')
                    self.assertEqual(len(complete.details),512)
                else:
                    with self.assertRaises((OSError,ValueError)):
                        DiskMetadataIndex.open(target,'next','project')


if __name__=='__main__':unittest.main()
