"""Real loopback preflight of the app that will receive a project switch."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from workspace_frontend import ProjectHandoffUnavailable, require_project_page


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name).resolve()
        self.inventory = {'launcher': False, 'current_project_uuid': 'same', 'projects': [
            {'uuid': 'same', 'path': str(self.path), 'current': True},
            {'uuid': 'same', 'path': str(self.path / 'other'), 'current': False}]}
        self.page = b'<html><div id="root"></div><script type="module" src="/assets/app.js"></script><link rel="stylesheet" href="/assets/app.css"></html>'
        self.failed = None; self.requests = []; fixture = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                fixture.requests.append(self.path)
                status = 400 if self.path == fixture.failed else 200
                content_type, body = {'/': ('text/html', fixture.page),
                    '/api/projects': ('application/json', json.dumps(fixture.inventory).encode()),
                    '/assets/app.js': ('text/javascript', b'// actual entry'),
                    '/assets/app.css': ('text/css', b'body{}')}[self.path]
                self.send_response(status); self.send_header('Content-Type', content_type); self.end_headers(); self.wfile.write(body)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(3)

    def check(self):require_project_page(self.server.server_port, self.path, 'same')

    def test_ready_page_catalog_and_compiled_entry_assets(self):
        self.check()
        self.assertEqual(self.requests, ['/', '/api/projects', '/assets/app.js', '/assets/app.css'])

    def test_root_catalog_or_entry_asset_failure_keeps_handoff_unavailable(self):
        for path in ('/', '/api/projects', '/assets/app.js', '/assets/app.css'):
            self.failed = path
            with self.assertRaisesRegex(ProjectHandoffUnavailable, 'current project remains open'):self.check()

    def test_duplicate_uuid_still_requires_exact_current_folder(self):
        self.inventory['projects'][0]['current'] = False
        self.inventory['projects'][1]['current'] = True
        with self.assertRaises(ProjectHandoffUnavailable):self.check()

    def test_assets_cannot_probe_another_origin(self):
        self.page = self.page.replace(b'/assets/app.js', b'http://example.invalid/app.js')
        with self.assertRaises(ProjectHandoffUnavailable):self.check()
        self.assertEqual(self.requests, ['/', '/api/projects'])

    def test_stylesheet_or_preload_without_executable_entry_is_not_an_app(self):
        for tag in (b'<link rel="stylesheet" href="/assets/app.css">', b'<link rel="modulepreload" href="/assets/app.js">'):
            self.page = b'<div id="root"></div>' + tag
            with self.assertRaises(ProjectHandoffUnavailable):self.check()


if __name__ == '__main__':unittest.main()
