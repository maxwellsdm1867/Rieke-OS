"""Updater safety contracts; no remote release, database or user project touched."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import workspace_updates as updates


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'app'
        self.root.mkdir()
        self.metadata = {'format': 'rieke-application-release', 'version': '0.1.0',
                         'repository': updates.REPOSITORY, 'updater_protocol': 1, 'database_compatibility': 1}
        self.write(self.root / 'rieke-release.json', self.metadata)
        self.installation = Path(self.temp.name) / 'installation'
        self.installation.mkdir()
        self.write(self.installation / 'installation.json', {'format': 'rieke-installation', 'version': 1, 'repository': updates.REPOSITORY})
        updates._cache.clear()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def release(self, version='0.2.0'):
        return {'tag_name': 'v' + version, 'html_url': f'https://github.com/{updates.REPOSITORY}/releases/tag/v{version}',
                'draft': False, 'prerelease': False, 'body': 'Release notes'}

    def ready(self, version, compatibility=1):
        path = self.installation / 'releases' / version
        self.write(path / '.release-ready.json', {'version': version, 'database_compatibility': compatibility})
        self.write(path / 'rieke-release.json', {**self.metadata, 'version': version})
        return path

    def test_status_is_offline_and_does_not_offer_install_without_trust(self):
        with patch.object(updates, '_download') as download:
            result = updates.installation_status(self.root)
        download.assert_not_called()
        self.assertEqual(result['installed'], '0.1.0')
        self.assertFalse(result['can_install'])
        self.assertFalse(result['can_stage'])

    def test_404_is_unavailable_not_up_to_date(self):
        with patch.object(updates, '_download', side_effect=HTTPError(updates.API, 404, '', {}, None)):
            self.assertEqual(updates.check_for_updates(self.root)['state'], 'unavailable')

    def test_update_check_is_cached_and_manual_force_rechecks(self):
        with patch.object(updates, '_download', return_value=json.dumps(self.release()).encode()) as download:
            result = updates.check_for_updates(self.root)
            self.assertEqual(result['state'], 'update_available')
            self.assertEqual(result['available'], '0.2.0')
            updates.check_for_updates(self.root)
            self.assertEqual(download.call_count, 1)
            updates.check_for_updates(self.root, force=True)
            self.assertEqual(download.call_count, 2)

    def test_offline_malformed_and_prerelease_checks_fail_without_mutation(self):
        for response in (b'bad json', b'[]', json.dumps({**self.release(), 'prerelease': True}).encode()):
            with self.subTest(response=response), patch.object(updates, '_download', return_value=response):
                self.assertEqual(updates.check_for_updates(self.root, force=True)['state'], 'error')
        with patch.object(updates, '_download', side_effect=OSError('offline')):
            self.assertEqual(updates.check_for_updates(self.root, force=True)['state'], 'error')
        self.assertFalse((self.installation / 'active.json').exists())

    def test_known_update_survives_failed_refresh_but_not_release_withdrawal(self):
        with patch.object(updates, '_download', return_value=json.dumps(self.release()).encode()):
            available = updates.check_for_updates(self.root)
        for failure in (OSError('offline'), HTTPError(updates.API, 503, '', {}, None)):
            with patch.object(updates, '_download', side_effect=failure):
                result = updates.check_for_updates(self.root, force=True)
                self.assertEqual(result['state'], 'update_available')
                self.assertEqual(result['available'], '0.2.0')
                self.assertEqual(result['release_url'], available['release_url'])
                self.assertEqual(result['checked_at'], available['checked_at'])
                self.assertIn('check_error', result)
                self.assertEqual(updates.check_for_updates(self.root), result)
        with patch.object(updates, '_download', return_value=json.dumps(self.release('0.1.0')).encode()):
            result = updates.check_for_updates(self.root, force=True)
            self.assertEqual(result['state'], 'up_to_date')
            self.assertNotIn('check_error', result)
        with patch.object(updates, '_download', return_value=json.dumps(self.release()).encode()):
            updates.check_for_updates(self.root, force=True)
        with patch.object(updates, '_download', side_effect=HTTPError(updates.API, 404, '', {}, None)):
            self.assertEqual(updates.check_for_updates(self.root, force=True)['state'], 'unavailable')

    def test_managed_status_requires_ready_release_inside_managed_installation(self):
        release = self.ready('0.1.0')
        (release / updates.TRUST_KEY).write_text('trusted public key')
        with patch.dict(os.environ, RIEKE_INSTALLATION_ROOT=str(self.installation)), patch.object(updates.shutil, 'which', return_value='/usr/bin/openssl'):
            self.assertFalse(updates.installation_status(self.root)['can_stage'])
            self.assertTrue(updates.installation_status(release)['can_stage'])

    def archive(self, entries):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode='w:gz') as tar:
            for name, value in entries:
                info = tarfile.TarInfo(name)
                if value is None:
                    info.type = tarfile.SYMTYPE
                    info.linkname = '/tmp/outside'
                    tar.addfile(info)
                else:
                    info.size = len(value)
                    tar.addfile(info, io.BytesIO(value))
        return data.getvalue()

    def test_archive_traversal_links_and_duplicates_are_rejected(self):
        for entries in ([('../escape', b'x')], [('/absolute', b'x')], [('link', None)], [('same', b'x'), ('same', b'y')]):
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as folder:
                with self.assertRaises((ValueError, FileExistsError)):
                    updates._extract(self.archive(entries), Path(folder))

    def test_activate_refuses_running_services_and_schema_change(self):
        self.ready('0.1.0')
        self.ready('0.2.0')
        self.write(self.installation / 'active.json', {'version': '0.1.0'})
        self.write(self.installation / 'staged.json', {'version': '0.2.0'})
        with updates.installation_lock(self.installation):
            with self.assertRaisesRegex(ValueError, 'Close all'):
                updates.activate_staged(self.installation)
        self.ready('0.2.0', compatibility=2)
        with self.assertRaisesRegex(ValueError, 'migration'):
            updates.activate_staged(self.installation)
        self.assertEqual(updates._read(self.installation / 'active.json')['version'], '0.1.0')

    def test_activation_switches_atomically_and_keeps_previous_release(self):
        self.ready('0.1.0')
        self.ready('0.2.0')
        self.write(self.installation / 'active.json', {'version': '0.1.0'})
        self.write(self.installation / 'staged.json', {'version': '0.2.0'})
        updates.activate_staged(self.installation)
        self.assertEqual(updates._read(self.installation / 'active.json'), {'version': '0.2.0', 'previous': '0.1.0'})
        self.assertTrue((self.installation / 'releases/0.1.0').exists())
        self.assertFalse((self.installation / 'staged.json').exists())

    def test_real_manager_launch_applies_prepared_update_and_preserves_preferences(self):
        for version in ('0.1.0', '0.2.0'):
            release = self.ready(version)
            (release / 'rieke.py').write_text(f'import sys, json; print(json.dumps({{"version":{version!r},"args":sys.argv[1:]}}))')
        self.write(self.installation / 'active.json', {'version': '0.1.0'})
        self.write(self.installation / 'staged.json', {'version': '0.2.0'})
        self.write(self.installation / 'preferences/workspace-selection.json', {'managed_root': '/research'})
        command = [updates.sys.executable, str(Path(updates.__file__)), '--installation',
                   str(self.installation), 'launch', '--', '--port', '8910']
        # Another open project defers activation and still launches the old app.
        with updates.installation_lock(self.installation):
            held = subprocess.run(command, check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(held.stdout)['version'], '0.1.0')
        self.assertIn('Update deferred', held.stderr)
        launched = subprocess.run(command, check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(launched.stdout), {'version': '0.2.0', 'args': ['launch', '--port', '8910']})
        self.assertEqual(updates._read(self.installation / 'active.json'), {'version': '0.2.0', 'previous': '0.1.0'})
        self.assertEqual(updates._read(self.installation / 'preferences/workspace-selection.json'), {'managed_root': '/research'})
        self.assertTrue((self.installation / 'releases/0.1.0').exists())
        # Subsequent launches use the new release without reapplying its receipt.
        self.assertEqual(json.loads(subprocess.check_output(command, text=True))['version'], '0.2.0')

    def test_manager_defers_incompatible_update_and_refuses_stale_staged_version(self):
        self.ready('0.1.0')
        self.ready('0.2.0', compatibility=2)
        self.write(self.installation / 'active.json', {'version': '0.1.0'})
        self.write(self.installation / 'staged.json', {'version': '0.2.0'})
        with patch.object(updates.subprocess, 'call', return_value=0) as launch:
            self.assertEqual(updates.main(['--installation', str(self.installation), 'launch']), 0)
        self.assertIn('0.1.0/rieke.py', launch.call_args.args[0][1])
        self.write(self.installation / 'staged.json', {'version': '0.1.0'})
        with self.assertRaisesRegex(ValueError, 'newer'):
            updates.activate_staged(self.installation)

    @unittest.skipUnless(shutil.which('openssl'), 'OpenSSL signature verification unavailable')
    def test_real_signature_accepts_trusted_payload_rejects_tampering(self):
        private = Path(self.temp.name) / 'private.pem'
        public = Path(self.temp.name) / 'public.pem'
        subprocess.run(['openssl', 'genrsa', '-out', str(private), '2048'], check=True, capture_output=True)
        subprocess.run(['openssl', 'rsa', '-in', str(private), '-pubout', '-out', str(public)], check=True, capture_output=True)
        payload = json.dumps({'format': 'rieke-release-manifest', 'updater_protocol': 1,
                              'repository': updates.REPOSITORY, 'version': '0.2.0', 'commit': 'a' * 40}).encode()
        data = Path(self.temp.name) / 'payload'
        data.write_bytes(payload)
        signature = subprocess.check_output(['openssl', 'dgst', '-sha256', '-sign', str(private), str(data)])
        envelope = {'algorithm': 'rsa-sha256', 'payload': base64.b64encode(payload).decode(), 'signature': base64.b64encode(signature).decode()}
        self.assertEqual(updates.verify_manifest(json.dumps(envelope).encode(), public)['version'], '0.2.0')
        envelope['payload'] = base64.b64encode(payload.replace(b'0.2.0', b'9.9.9')).decode()
        with self.assertRaisesRegex(ValueError, 'signature'):
            updates.verify_manifest(json.dumps(envelope).encode(), public)

    def test_stage_can_run_while_app_open_and_failure_keeps_active(self):
        self.ready('0.1.0')
        self.write(self.installation / 'active.json', {'version': '0.1.0'})
        archive = self.archive([('rieke-release.json', json.dumps({**self.metadata, 'version': '0.2.0'}).encode())])
        prefix = f'https://github.com/{updates.REPOSITORY}/releases/download/v0.2.0/'
        release = {**self.release(), 'assets': [{'name': updates.MANIFEST_ASSET, 'browser_download_url': prefix + updates.MANIFEST_ASSET}]}
        manifest = {'version': '0.2.0', 'commit': 'a' * 40, 'database_compatibility': 1,
                    'artifacts': [{'platform': f'{updates.sys.platform}-{updates.platform.machine().lower()}',
                                   'url': prefix + 'app.tar.gz', 'size': len(archive), 'sha256': hashlib.sha256(archive).hexdigest()}]}
        (self.installation / updates.TRUST_KEY).write_text('installed key')
        with updates.installation_lock(self.installation), patch.object(updates, '_download', side_effect=[json.dumps(release).encode(), b'envelope', archive]), \
                patch.object(updates, 'verify_manifest', return_value=manifest), \
                patch.object(updates.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['setup'])):
            with self.assertRaises(subprocess.CalledProcessError):
                updates.stage_release(self.installation, root=self.root)
        self.assertEqual(updates._read(self.installation / 'active.json')['version'], '0.1.0')
        self.assertFalse((self.installation / 'staged.json').exists())
        self.assertTrue((self.installation / 'releases/0.2.0/.stage-failed.json').exists())

    def test_bounded_restart_never_kills_active_writer(self):
        with patch.object(updates, 'activate_staged', side_effect=ValueError('Close all Rieke OS launchers')) as activate, \
                patch.object(updates, 'main') as launch:
            with self.assertRaises(ValueError):
                updates.activate_and_launch(self.installation, wait_seconds=0)
        self.assertEqual(activate.call_count, 1)
        launch.assert_not_called()

    def test_wrong_checksum_cannot_execute_setup_or_create_release(self):
        prefix = f'https://github.com/{updates.REPOSITORY}/releases/download/v0.2.0/'
        release = {**self.release(), 'assets': [{'name': updates.MANIFEST_ASSET, 'browser_download_url': prefix + updates.MANIFEST_ASSET}]}
        manifest = {'version': '0.2.0', 'commit': 'a' * 40, 'database_compatibility': 1,
                    'artifacts': [{'platform': f'{updates.sys.platform}-{updates.platform.machine().lower()}',
                                   'url': prefix + 'app.tar.gz', 'size': 3, 'sha256': '0' * 64}]}
        with patch.object(updates, '_download', side_effect=[json.dumps(release).encode(), b'envelope', b'bad']), \
                patch.object(updates, 'verify_manifest', return_value=manifest), patch.object(updates.subprocess, 'run') as execute:
            with self.assertRaisesRegex(ValueError, 'checksum'):
                updates.stage_release(self.installation)
        execute.assert_not_called()
        self.assertFalse((self.installation / 'releases').exists())

    def test_multiple_services_reuse_only_matching_verified_staged_release(self):
        release_dir = self.ready('0.2.0')
        prefix = f'https://github.com/{updates.REPOSITORY}/releases/download/v0.2.0/'
        release = {**self.release(), 'assets': [{'name': updates.MANIFEST_ASSET, 'browser_download_url': prefix + updates.MANIFEST_ASSET}]}
        artifact = {'platform': f'{updates.sys.platform}-{updates.platform.machine().lower()}',
                    'url': prefix + 'app.tar.gz', 'size': 3, 'sha256': 'a' * 64}
        manifest = {'version': '0.2.0', 'commit': 'b' * 40, 'database_compatibility': 1, 'artifacts': [artifact]}
        self.write(release_dir / '.release-ready.json', {'version': '0.2.0', 'commit': 'b' * 40,
                                                      'database_compatibility': 1, 'sha256': 'a' * 64})
        with patch.object(updates, '_download', side_effect=[json.dumps(release).encode(), b'envelope']) as download, \
                patch.object(updates, 'verify_manifest', return_value=manifest), patch.object(updates.subprocess, 'run') as setup:
            self.assertEqual(updates.stage_release(self.installation)['version'], '0.2.0')
            self.assertEqual(download.call_count, 2)
            setup.assert_not_called()
        self.write(release_dir / '.release-ready.json', {'version': '0.2.0'})
        with patch.object(updates, '_download', side_effect=[json.dumps(release).encode(), b'envelope']), \
                patch.object(updates, 'verify_manifest', return_value=manifest):
            with self.assertRaisesRegex(ValueError, 'inspect'):
                updates.stage_release(self.installation)

    def test_incompatible_signed_release_is_rejected_before_artifact_download(self):
        self.ready('0.1.0')
        self.write(self.installation / 'active.json', {'version': '0.1.0'})
        prefix = f'https://github.com/{updates.REPOSITORY}/releases/download/v0.2.0/'
        release = {**self.release(), 'assets': [{'name': updates.MANIFEST_ASSET, 'browser_download_url': prefix + updates.MANIFEST_ASSET}]}
        manifest = {'version': '0.2.0', 'database_compatibility': 2,
                    'artifacts': [{'platform': f'{updates.sys.platform}-{updates.platform.machine().lower()}',
                                   'url': prefix + 'app.tar.gz', 'size': 3}]}
        with patch.object(updates, '_download', side_effect=[json.dumps(release).encode(), b'envelope']) as download, \
                patch.object(updates, 'verify_manifest', return_value=manifest), patch.object(updates.subprocess, 'run') as setup:
            with self.assertRaisesRegex(ValueError, 'migration'):
                updates.stage_release(self.installation)
            self.assertEqual(download.call_count, 2)
            setup.assert_not_called()

    def test_managed_server_rejects_old_release_even_with_same_project_uuid(self):
        from workspace_project_servers import write_server_record, ready_url
        project = Path(self.temp.name) / 'project'
        project.mkdir()
        write_server_record(project, 'project-id', 8877)
        with patch.dict(os.environ, RIEKE_INSTALLATION_ROOT=str(self.installation)), \
                patch('workspace_project_servers.urlopen', return_value=io.StringIO(json.dumps(
                    {'status': 'ready', 'project_uuid': 'project-id', 'app_release': '0.0.1',
                     'project_path': str(project.resolve())}))):
            with self.assertRaisesRegex(RuntimeError, 'different release'):
                ready_url(project, 'project-id')


if __name__ == '__main__':
    unittest.main()
