"""Execute publisher workflow code with owned bytes and inert command ports."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCE = 'a' * 40
PUBLISHER = 'b' * 40


class TestingPromoteWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        workflow = yaml.safe_load((ROOT / '.github/workflows/desktop-testing-promote.yml').read_text())
        cls.steps = workflow['jobs']['publish']['steps']
        step = next(step for step in cls.steps if step.get('name') == 'Verify and publish the exact testing archive')
        lines = step['run'].splitlines()
        if lines[0] != "python3 - <<'PY'" or lines[-1] != 'PY':
            raise AssertionError('Expected the actual publisher Python step')
        cls.code = compile('\n'.join(lines[1:-1]), 'desktop-testing-promote.yml:publisher', 'exec')

    def exercise(self, *, fail=None, symbol=True, source_match=True, archive_match=True):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            notes = root / 'release-evidence/notes.md'; notes.parent.mkdir()
            notes.write_text('Owned release notes')
            directory = root / 'runner/testing-candidate'; directory.mkdir(parents=True)
            archive = directory / 'Disco-0.1.15-arm64.zip'
            archive.write_bytes(b'Owned inert archive fixture')
            archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
            (directory / 'desktop-release.json').write_text(json.dumps({
                'source_commit': SOURCE, 'archive': {'filename': archive.name,
                    'sha256': archive_hash if archive_match else '0' * 64}}))
            template = root / 'template/Disco.app'
            runtime = template / 'Contents/Resources/runtime'
            (runtime / 'native').mkdir(parents=True)
            (runtime / 'runtime-manifest.json').write_text(json.dumps({
                'source_commit': SOURCE, 'source_dirty': False}))
            native_source = b'Owned native source fixture'
            source_hash = hashlib.sha256(native_source).hexdigest()
            (runtime / 'native/trace-inflate-build.json').write_text(json.dumps({
                'source_sha256': source_hash if source_match else '0' * 64}))
            (runtime / 'native/libdisco_trace_inflate.dylib').write_bytes(b'Owned inert helper')
            (template / 'Contents/Resources/app.asar').write_bytes(b'Owned inert ASAR')
            commands = []
            def run(command, **options):
                if command[0] == 'ditto':
                    self.assertEqual(command[1:4], ['-x', '-k', str(archive)])
                    shutil.copytree(template, Path(command[4]) / 'Disco.app')
                    commands.append('extract')
                    return subprocess.CompletedProcess(command, 0)
                if command[0] == '/usr/bin/codesign': label = 'signature'
                elif 'desktop_runtime_manifest.py' in command[2]: label = 'runtime'
                elif 'desktop_native_compatibility.py' in command[2]: label = 'native'
                elif command[0] == '/usr/bin/nm': label = 'trace-symbols'
                else: self.fail('Unexpected command port: ' + repr(command))
                commands.append(label)
                output = 'verified ' + label
                if label == 'trace-symbols':
                    output = '000000 T _disco_trace_extract_foreground_v1\n' if symbol else '000000 T _disco_trace_extract_v1\n'
                return subprocess.CompletedProcess(command, int(fail == label), output, 'injected failure' if fail == label else '')
            def check_output(command, **options):
                if command == ['git', 'show', SOURCE + ':desktop/native/trace_inflate.c']:
                    return native_source
                self.assertEqual(command, ['git', 'rev-parse', 'HEAD'])
                self.assertTrue(options.get('text'))
                return PUBLISHER + '\n'
            def publish(*arguments, **options):
                commands.append('publish')
                self.assertEqual(commands[:-1], ['extract', 'signature', 'runtime', 'native', 'trace-symbols'])
                self.assertTrue((directory / 'publication-audit/identity.json').is_file())
                self.assertEqual(arguments, (directory / 'extracted/Disco.app', archive,
                    directory / 'desktop-release.json', notes, '42'))
                self.assertEqual(options, {'verification_run_id': '43'})
                return {'source_commit': SOURCE, 'candidate_run': 42}
            publisher = Mock(side_effect=publish)
            module = types.ModuleType('desktop_test_release'); module.publish = publisher
            previous = Path.cwd()
            error = None
            try:
                os.chdir(root)
                with patch.dict(os.environ, {'SOURCE_COMMIT': SOURCE, 'CANDIDATE_RUN_ID': '42', 'VERIFICATION_RUN_ID': '43',
                        'NOTES_PATH': 'release-evidence/notes.md', 'RUNNER_TEMP': str(root / 'runner')}), \
                     patch.dict(sys.modules, {'desktop_test_release': module}), \
                     patch.object(sys, 'path', list(sys.path)), \
                     patch.object(subprocess, 'run', side_effect=run), \
                     patch.object(subprocess, 'check_output', side_effect=check_output):
                    try: exec(self.code, {'__name__': '__main__'})
                    except SystemExit as caught: error = str(caught)
            finally:
                os.chdir(previous)
            files = {str(path.relative_to(directory)): path.read_bytes()
                     for path in directory.rglob('*') if path.is_file()}
            return commands, publisher.call_count, error, files, archive_hash, source_hash

    def test_success_records_distinct_application_and_publisher_identity_before_publish(self):
        commands, count, error, files, archive_hash, source_hash = self.exercise()
        self.assertIsNone(error); self.assertEqual(count, 1)
        identity = json.loads(files['publication-audit/identity.json'])
        self.assertEqual(identity['source_commit'], SOURCE)
        self.assertEqual(identity['publisher_commit'], PUBLISHER)
        self.assertEqual(identity['candidate_run_id'], '42')
        self.assertEqual(identity['verification_run_id'], '43')
        self.assertEqual(identity['archive_sha256'], archive_hash)
        self.assertEqual(identity['native_source_sha256'], source_hash)
        self.assertEqual(identity['read_only_artifact_checks'], commands[1:-1])
        self.assertEqual(json.loads(files['publication.json'])['source_commit'], SOURCE)

    def test_failed_signature_runtime_or_native_audit_never_publishes(self):
        for label in ('signature', 'runtime', 'native', 'trace-symbols'):
            with self.subTest(label=label):
                commands, count, error, files, *_ = self.exercise(fail=label)
                self.assertEqual(count, 0)
                self.assertIn(label + ' verification', error)
                self.assertEqual(commands[-1], label)
                self.assertIn(b'injected failure', files['publication-audit/' + label + '.log'])
                self.assertNotIn('publication.json', files)

    def test_successful_nm_without_foreground_symbol_never_publishes(self):
        commands, count, error, files, *_ = self.exercise(symbol=False)
        self.assertEqual(count, 0)
        self.assertIn('foreground trace entry is missing', error)
        self.assertIn('publication-audit/trace-symbols.log', files)
        self.assertNotIn('publication.json', files)

    def test_native_source_mismatch_never_reaches_audit_or_publication(self):
        commands, count, error, _, *_ = self.exercise(source_match=False)
        self.assertEqual(commands, ['extract']); self.assertEqual(count, 0)
        self.assertIn('Native trace helper build source differs', error)

    def test_archive_mismatch_never_extracts_or_publishes(self):
        commands, count, error, _, *_ = self.exercise(archive_match=False)
        self.assertEqual(commands, []); self.assertEqual(count, 0)
        self.assertIn('archive hash differs', error)

    def test_exact_source_gate_precedes_download_and_audit_upload_survives_failure(self):
        gate = next(index for index, step in enumerate(self.steps)
                    if step.get('name') == 'Require successful exact-source checks before downloading app bytes')
        download = next(index for index, step in enumerate(self.steps)
                        if step.get('uses') == 'actions/download-artifact@v4')
        self.assertLess(gate, download)
        self.assertNotIn('continue-on-error', self.steps[gate])
        self.assertEqual(self.steps[download]['with']['run-id'], '${{ inputs.candidate_run_id }}')
        upload = next(step for step in self.steps if step.get('uses') == 'actions/upload-artifact@v4')
        self.assertEqual(upload['if'], 'always()')
        self.assertIn('publication-audit/', upload['with']['path'])
        self.assertEqual(upload['with']['if-no-files-found'], 'error')


if __name__ == '__main__': unittest.main()
