"""Exercise real loopback responses, without any user catalog or service."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from workspace_project_unmount import require_ready_launcher, _desktop_chooser_headers


class ChooserReadinessTests(unittest.TestCase):
    def setUp(self):
        self.health = {'status': 'ready', 'launcher': True, 'project_uuid': None}
        self.page = b'<html><div id="root"></div><script src="/app.js"></script></html>'
        self.status = 200
        self.headers = []
        fixture = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                fixture.headers.append(dict(self.headers))
                self.send_response(fixture.status)
                self.send_header('Content-Type', 'application/json' if self.path == '/api/health' else 'text/html')
                self.send_header('Location', 'http://example.invalid/')
                self.end_headers()
                self.wfile.write(json.dumps(fixture.health).encode() if self.path == '/api/health' else fixture.page)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.env = patch.dict(os.environ, {'RIEKE_LAUNCHER_PORT': str(self.server.server_port), 'RIEKE_DESKTOP_MODE': '0'})
        self.env.start()
        os.environ.pop('RIEKE_DESKTOP_LAUNCHER_PORT', None)
        self.addCleanup(self.env.stop)
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(3)

    def test_real_ready_chooser_and_stopped_listener(self):
        self.assertEqual(require_ready_launcher(), f'http://127.0.0.1:{self.server.server_port}/')
        self.stop()
        with self.assertRaisesRegex(ValueError, 'chooser is unavailable'):
            require_ready_launcher()

    def test_other_project_or_missing_frontend_or_redirect_is_not_ready(self):
        for health, page, status in [
            ({'status': 'ready', 'project_uuid': 'other'}, self.page, 200),
            (self.health, b'Build workspace-app first', 200),
            (self.health, self.page, 503),
            (self.health, self.page, 302),
        ]:
            self.health, self.page, self.status = health, page, status
            with self.assertRaisesRegex(ValueError, 'Nothing was detached'):
                require_ready_launcher()

    def test_desktop_uses_private_capability_on_fixed_loopback_only(self):
        with patch.dict(os.environ, {'RIEKE_DESKTOP_MODE': '1', 'RIEKE_DESKTOP_LAUNCHER_PORT': str(self.server.server_port)}):
            with patch('workspace_project_unmount._desktop_chooser_headers', side_effect=ValueError('wrong owner')):
                with self.assertRaises(ValueError):require_ready_launcher()
            self.assertEqual(self.headers, [])
            with patch('workspace_project_unmount._desktop_chooser_headers', return_value={'X-Rieke-Desktop-Capability': 'fixture-capability'}):
                require_ready_launcher()
        self.assertEqual(len(self.headers), 2)
        self.assertTrue(all(row['X-Rieke-Desktop-Capability'] == 'fixture-capability' for row in self.headers))

    def test_desktop_requires_exact_parent_entry_session_profile_and_listener(self):
        entry = str(Path(__file__).resolve().parents[1] / 'workspace_desktop.py')
        child, owner = Mock(), Mock()
        child.parent.return_value = owner; owner.pid = 1234
        owner.exe.return_value = sys.executable; owner.uids.return_value = SimpleNamespace(real=os.getuid())
        child.cmdline.return_value = [sys.executable, entry, '--session-id', 'test-session', '--project-dir', '/fixture']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'profile').mkdir(); (root / 'alias').symlink_to(root / 'profile')
            command = [sys.executable, '-B', entry, '--port', '9997', '--user-state', str(root / 'alias'), '--session-id', 'test-session']
            owner.cmdline.return_value = command
            listener = SimpleNamespace(status='LISTEN', laddr=SimpleNamespace(ip='127.0.0.1', port=9997))
            owner.net_connections.return_value = [listener]
            with patch('psutil.Process', return_value=child), patch.dict(os.environ, {'RIEKE_DESKTOP_USER_STATE': str((root / 'profile').resolve()), 'RIEKE_DESKTOP_CAPABILITY': 'owned-only'}):
                self.assertEqual(_desktop_chooser_headers(9997), {'X-Rieke-Desktop-Capability': 'owned-only'})
                for bad in ([sys.executable, '-c', entry, *command[3:]], [*command, '--project-dir', '/other'], [part.replace('test-session', 'foreign-session') for part in command]):
                    owner.cmdline.return_value = bad
                    with self.assertRaises(ValueError):_desktop_chooser_headers(9997)
                owner.cmdline.return_value = command
                owner.net_connections.return_value = []
                with self.assertRaises(ValueError):_desktop_chooser_headers(9997)


if __name__ == '__main__': unittest.main()
