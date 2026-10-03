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

    def test_production_move_into_documentation_cannot_transfer_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            def git(*args):
                return native.git(repo, *args)
            git('init', '-q')
            git('config', 'diff.renames', 'true')
            (repo / 'app.js').write_text('unchanged production content\n')
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'Measured production')
            measured = git('rev-parse', 'HEAD')
            (repo / 'docs').mkdir()
            git('mv', 'app.js', 'docs/app.js')
            git('-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'Move production into allowed directory')
            candidate = git('rev-parse', 'HEAD')
            # Prove this fixture exercises Git's destination-only rename output.
            self.assertEqual(git('diff', '--name-only', measured, candidate), 'docs/app.js')
            evidence = repo / 'evidence'; evidence.mkdir()
            (evidence / 'source.json').write_text(json.dumps({'commit': measured}))
            (evidence / 'report.md').write_text('Measured production report')
            with self.assertRaisesRegex(ValueError, 'Production differs'):
                native.attach(repo, evidence, measured, candidate, 'source.json', ['report.md'])
