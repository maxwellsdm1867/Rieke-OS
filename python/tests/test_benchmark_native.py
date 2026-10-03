"""Native evidence is an integrity attachment, never release qualification."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('native', ROOT / 'tools/benchmark_native.py')
native = importlib.util.module_from_spec(spec); spec.loader.exec_module(native)
class NativeTests(unittest.TestCase):
    def test_attachment_preserves_measured_commit_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); repo = root/'repo'; repo.mkdir()
            def git(*args):
                return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
            git('init','-q'); (repo/'app.js').write_text('production')
            git('add','.'); git('-c','user.name=Fixture','-c','user.email=test@example.invalid','commit','-qm','base')
            measured = git('rev-parse','HEAD')
            (repo/'benchmarks').mkdir(); (repo/'benchmarks/note.md').write_text('infra')
            git('add','.'); git('-c','user.name=Fixture','-c','user.email=test@example.invalid','commit','-qm','infra')
            candidate = git('rev-parse','HEAD')
            evidence = root/'evidence'; evidence.mkdir()
            (evidence/'source.json').write_text(json.dumps({'commit':measured}))
            (evidence/'report.md').write_text('Observed scoped tree return results')
            attachment = native.attach(repo, evidence, measured, candidate, 'source.json', ['report.md'])
            self.assertEqual(attachment['measured_commit'], measured)
            self.assertEqual(attachment['candidate_commit'], candidate)
            self.assertFalse(attachment['release_qualified'])
            native.verify(attachment, repo, evidence)
            for field, value in [('release_qualified', True), ('candidate_commit', measured)]:
                with self.assertRaises(ValueError): native.verify({**attachment, field:value}, repo, evidence)
            (evidence/'linked.md').symlink_to(evidence/'report.md')
            with self.assertRaises(ValueError): native.attach(repo,evidence,measured,candidate,'source.json',['linked.md'])
            with self.assertRaises(ValueError): native.attach(repo,evidence,candidate,candidate,'source.json',['report.md'])
            (evidence/'report.md').write_text('tampered')
            with self.assertRaises(ValueError): native.verify(attachment, repo, evidence)
            with self.assertRaises(ValueError): native.attach(repo,evidence,measured,candidate,'source.json',['../repo/app.js'])
            (repo/'app.js').write_text('changed production'); git('add','.')
            git('-c','user.name=Fixture','-c','user.email=test@example.invalid','commit','-qm','production')
            with self.assertRaises(ValueError): native.attach(repo,evidence,measured,git('rev-parse','HEAD'),'source.json',['report.md'])
