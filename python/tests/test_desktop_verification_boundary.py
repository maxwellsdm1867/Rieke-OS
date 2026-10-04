"""Install/explicit byte auditing and ordinary launch have different contracts."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from workspace_bootstrap import validate_desktop_runtime


class VerificationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        files = {'python/bin/python3.11': 'python', 'mysql/bin/mysqld': 'mysql',
                 'application/python/workspace_desktop.py': 'entry', 'frontend/index.html': 'html',
                 'unused.txt': 'original',
                 'application/rieke-release.json': json.dumps(dict(version='1.0.0', workspace_formats=[1], database_compatibility=1)),
                 'application/python/workspace-source.json': json.dumps(dict(commit='a'*40, python='3.11.13'))}
        resources = {}
        for name, text in files.items():
            file = self.root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(text)
            resources[name] = dict(size=len(text.encode()), sha256=hashlib.sha256(text.encode()).hexdigest())
        self.manifest = dict(format='rieke-desktop-runtime', version=1, platform=sys.platform,
                             architecture=os.uname().machine, application_version='1.0.0', workspace_formats=[1],
                             database_compatibility=1, parser_commit='a'*40, python_version='3.11.13', resources=resources)
        self.write_manifest()

    def write_manifest(self):
        (self.root / 'runtime-manifest.json').write_text(json.dumps(self.manifest))

    def test_normal_launch_does_not_walk_or_hash_and_explicit_audit_detects_unused_corruption(self):
        (self.root / 'unused.txt').write_text('modified')  # same size, unused at launch
        with patch.object(Path, 'rglob', side_effect=AssertionError('no recursive launch scan')), \
                patch('hashlib.file_digest', side_effect=AssertionError('no launch hash')):
            validate_desktop_runtime(self.root)
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            validate_desktop_runtime(self.root, verify_hashes=True)

    def test_missing_required_runtime_never_passes_launch(self):
        (self.root / 'mysql/bin/mysqld').unlink()
        with self.assertRaisesRegex(ValueError, 'Required packaged resource is absent'):
            validate_desktop_runtime(self.root)

    def test_launch_rejects_required_path_escape(self):
        file = self.root / 'frontend/index.html'
        file.unlink()
        file.symlink_to('/etc/hosts')
        with self.assertRaisesRegex(ValueError, 'escapes'):
            validate_desktop_runtime(self.root)

    def test_mixed_version_and_wrong_architecture_fail_lightweight_checks(self):
        for field, value in [('application_version', '2.0.0'), ('architecture', 'wrong')]:
            original = self.manifest[field]
            self.manifest[field] = value
            self.write_manifest()
            with self.assertRaises(ValueError):
                validate_desktop_runtime(self.root)
            self.manifest[field] = original

    def test_full_audit_rejects_added_and_missing_unused_files(self):
        extra = self.root / 'unexpected'
        extra.write_text('extra')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            validate_desktop_runtime(self.root, verify_hashes=True)
        extra.unlink()
        (self.root / 'unused.txt').unlink()
        with self.assertRaisesRegex(ValueError, 'inventory'):
            validate_desktop_runtime(self.root, verify_hashes=True)
