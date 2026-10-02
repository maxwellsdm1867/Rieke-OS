"""Seed project navigation before React paints on each local project address."""
import json
from html.parser import HTMLParser
from http.client import HTTPConnection, HTTPException
from pathlib import Path
from urllib.parse import urlsplit
from flask import Response, send_from_directory


class ProjectHandoffUnavailable(ValueError):
    """A running API is not proof that its project window can load."""


def require_project_page(port, project_dir, identity):
    """Preflight a source/browser handoff without leaving the current window.

    In particular, an older running process can answer health while rejecting a
    newer shared project-index format. Never spawn over, stop, or rewrite that
    service/catalog as a side effect of this read-only compatibility check.
    """
    def read(path, limit):
        connection = HTTPConnection('127.0.0.1', port, timeout=2)
        try:
            connection.request('GET', path)
            response = connection.getresponse()
            payload = response.read(limit + 1)
            if response.status != 200 or len(payload) > limit:
                raise ValueError('Project page or catalog did not load')
            return response.getheader('Content-Type', ''), payload
        finally:
            connection.close()

    class Page(HTMLParser):
        def __init__(self):
            super().__init__(); self.root = False; self.entry = False; self.assets = []
        def handle_starttag(self, tag, attributes):
            attrs = dict(attributes)
            self.root |= attrs.get('id') == 'root'
            if tag == 'script' and attrs.get('src'):
                self.entry = attrs.get('type', '') in {'', 'module', 'text/javascript', 'application/javascript'} or self.entry
                self.assets.append((attrs['src'], 'javascript'))
            if tag == 'link' and attrs.get('rel') in {'stylesheet', 'modulepreload'}:
                self.assets.append((attrs.get('href', ''), 'css' if attrs['rel'] == 'stylesheet' else 'javascript'))

    try:
        content_type, page = read('/', 1024 * 1024)
        if 'text/html' not in content_type:
            raise ValueError('Project app page is unavailable')
        parsed = Page(); parsed.feed(page.decode('utf-8'))
        if not parsed.root or not parsed.entry or len(parsed.assets) > 32:
            raise ValueError('Project app page is incomplete')
        _, payload = read('/api/projects', 8 * 1024 * 1024)
        inventory = json.loads(payload)
        current = [row for row in inventory.get('projects', []) if row.get('current') is True]
        if (inventory.get('launcher') is True or inventory.get('current_project_uuid') != identity
                or len(current) != 1 or current[0].get('uuid') != identity
                or current[0].get('path') != str(Path(project_dir).resolve())):
            raise ValueError('Project catalog does not match the selected folder')
        for asset, kind in dict(parsed.assets).items():
            target = urlsplit(asset)
            if (target.scheme or target.netloc or not target.path.startswith('/')
                    or target.path.startswith('//') or target.fragment):
                raise ValueError('Project app asset is not on its own local service')
            content_type, payload = read(asset, 16 * 1024 * 1024)
            if not payload or (kind not in content_type and not (kind == 'javascript' and 'ecmascript' in content_type)):
                raise ValueError('Project app asset is unavailable')
    except (OSError, HTTPException, ValueError, AttributeError, TypeError) as error:
        raise ProjectHandoffUnavailable(
            'The selected project service cannot load its project list or app page. '
            'Your current project remains open. Close the selected project normally and '
            'reopen it with this app, then retry. Its files and database are retained.') from error


def project_frontend_response(frontend, path, inventory):
    if path != 'index.html':
        return send_from_directory(frontend, path)
    response = send_from_directory(frontend, path, conditional=False)
    response.direct_passthrough = False
    data = json.dumps(inventory(), ensure_ascii=True).replace('<', '\\u003c')
    bootstrap = '<script type="application/json" id="rieke-projects-bootstrap">' + data + '</script>'
    try:
        html = response.get_data(as_text=True).replace('</head>', bootstrap + '</head>', 1)
    finally:
        response.close()
    return Response(html, mimetype='text/html', headers={'Cache-Control': 'no-store'})
