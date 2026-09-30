"""Private MySQL provisioning trust boundaries, independent of installed services."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import workspace_mysql_runtime as runtime


class NativeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'python').mkdir()
        (self.root / runtime.LOCK).write_bytes((runtime.ROOT / runtime.LOCK).read_bytes())

    def test_no_mysql_path_search_or_system_service_fallback(self):
        with patch.object(runtime.platform, 'machine', return_value='arm64'), patch.object(runtime.sys, 'platform', 'darwin'), \
                patch.object(runtime.subprocess, 'run') as command:
            with self.assertRaisesRegex(ValueError, 'not installed'):
                runtime.mysql_runtime(self.root)
        command.assert_not_called()

    def test_unsupported_platform_does_not_download(self):
        with patch.object(runtime.platform, 'machine', return_value='x86_64'), patch.object(runtime.sys, 'platform', 'linux'), \
                patch.object(runtime, 'urlopen') as network:
            with self.assertRaisesRegex(ValueError, 'not yet validated'):
                runtime.install_mysql_runtime(self.root)
        network.assert_not_called()

    def test_partial_and_linked_prefixes_are_never_adopted(self):
        prefix = self.root / '.rieke-runtime/mysql'
        prefix.mkdir(parents=True)
        with patch.object(runtime.platform, 'machine', return_value='arm64'), patch.object(runtime.sys, 'platform', 'darwin'):
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                runtime.mysql_runtime(self.root)
            prefix.rmdir()
            prefix.symlink_to(self.root / 'external')
            with self.assertRaisesRegex(ValueError, 'symbolic link'):
                runtime.install_mysql_runtime(self.root)

    def test_cached_archive_hash_verified_before_reuse(self):
        data = b'package content'
        archive = self.root / 'p.conda'
        archive.write_bytes(data)
        package = {'url': 'https://conda.anaconda.org/conda-forge/osx-arm64/p.conda',
                   'sha256': hashlib.sha256(data).hexdigest()}
        with patch.object(runtime, 'urlopen') as network:
            self.assertEqual(runtime._verified_package(package, self.root), archive)
            archive.write_bytes(b'corrupted')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                runtime._verified_package(package, self.root)
        network.assert_not_called()

    def test_bad_download_never_promoted_to_cache(self):
        source = io.BytesIO(b'bad payload')
        source.url = 'https://conda.anaconda.org/conda-forge/osx-arm64/p.conda'
        package = {'url': source.url, 'sha256': '0' * 64}
        with patch.object(runtime, 'urlopen', return_value=source):
            with self.assertRaisesRegex(ValueError, 'checksum'):
                runtime._verified_package(package, self.root)
        self.assertFalse((self.root / 'p.conda').exists())

    def test_runtime_receipt_must_match_this_release_lock(self):
        prefix = self.root / '.rieke-runtime/mysql'
        prefix.mkdir(parents=True)
        (prefix / '.rieke-mysql-runtime.json').write_text(json.dumps({'lock_sha256': '0' * 64}))
        with patch.object(runtime.platform, 'machine', return_value='arm64'), patch.object(runtime.sys, 'platform', 'darwin'), \
                patch.object(runtime, '_probe') as probe:
            with self.assertRaisesRegex(ValueError, 'differs from the release lock'):
                runtime.mysql_runtime(self.root)
        probe.assert_not_called()


if __name__ == '__main__':
    unittest.main()
