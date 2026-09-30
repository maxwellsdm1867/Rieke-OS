import json
from pathlib import Path
import tempfile
import unittest
from flask import Flask
from workspace_frontend import project_frontend_response


class FrontendProjectBootstrapTests(unittest.TestCase):
    def test_sidebar_is_seeded_before_scripts_without_injecting_project_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_text('<html><head></head><body></body></html>')
            (root / 'asset.js').write_text('asset')
            app = Flask(__name__)
            data = {'projects': [{'name': '</script><script>alert(1)</script>', 'path': '/a', 'uuid': 'a'}], 'launcher': False}
            with app.test_request_context('/'):
                response = project_frontend_response(root, 'index.html', lambda: data)
                html = response.get_data(as_text=True)
                payload = html.split('id="rieke-projects-bootstrap">')[1].split('</script>')[0]
                self.assertEqual(json.loads(payload), data)
                self.assertEqual(html.count('</script>'), 1)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertNotIn('ETag', response.headers)
            with app.test_request_context('/asset.js'):
                response = project_frontend_response(root, 'asset.js', lambda: self.fail('asset requested inventory'))
                response.direct_passthrough = False
                self.assertEqual(response.get_data(as_text=True), 'asset')
                response.close()
