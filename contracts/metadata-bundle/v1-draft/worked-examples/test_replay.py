import hashlib
import pathlib
import shutil
import tempfile
import unittest
import replay
ROOT=pathlib.Path(__file__).parent

def hashes(root):return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}

class ReplayTests(unittest.TestCase):
    def test_golden_unchanged(self):
        before=hashes(ROOT);result=replay.check(ROOT)
        self.assertTrue(result['valid'],result)
        self.assertEqual(before,hashes(ROOT))
    def test_drift_missing_extra_fail_without_repair(self):
        for change in ('drift','missing','extra'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temp:
                root=pathlib.Path(temp)/'fixture';shutil.copytree(ROOT,root)
                target=root/'expected/mapping-report.json'
                if change=='drift':target.write_text('{}\n')
                elif change=='missing':target.unlink()
                else:(root/'expected/unexpected.json').write_text('{}\n')
                before=hashes(root);result=replay.check(root)
                self.assertFalse(result['valid']);self.assertEqual(before,hashes(root))
if __name__=='__main__':unittest.main()
