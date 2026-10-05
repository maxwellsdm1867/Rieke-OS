"""Shared local HTTP admission for project compositions.

Desktop capability/process admission remains in DesktopBoundary. This module
retains the existing host, mutation-header and origin checks for local routes.
"""
import json

from flask import jsonify, request
from flask.json.provider import DefaultJSONProvider


def browser_safe_metadata(value):
    """Preserve the existing exact-integer boundary for detached JSON values."""
    if type(value) is int and abs(value) > 2**53 - 1:
        return str(value)
    if isinstance(value, dict):
        return {key: browser_safe_metadata(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [browser_safe_metadata(item) for item in value]
    return value


class ExactMetadataJSON(DefaultJSONProvider):
    """Keep exact imported tick integers outside JavaScript's Number range."""
    def dumps(self, obj, **kwargs):
        return super().dumps(browser_safe_metadata(obj), **kwargs)


def encode_exact_response(value, *, ensure_ascii=True, sort_keys=True, compact=True):
    """The exact provider's response encoding, without a Flask request/app owner."""
    options = {'separators': (',', ':')} if compact else {'indent': 2}
    body = json.dumps(browser_safe_metadata(value), default=DefaultJSONProvider.default,
                      ensure_ascii=ensure_ascii, sort_keys=sort_keys, **options)
    return (body + '\n').encode('utf-8')


def register_local_boundary(app):
    @app.before_request
    def local_boundary():
        if request.host.split(':')[0] not in {'127.0.0.1', 'localhost'}:
            return jsonify(error='This workspace accepts local connections only.'), 403
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            if request.headers.get('X-Workspace-Request') != '1':
                return jsonify(error='Missing workspace request header.'), 403
            origin = request.headers.get('Origin')
            if origin and origin not in {'http://127.0.0.1:5173', 'http://localhost:5173',
                    'http://127.0.0.1:8766', 'http://localhost:8766', request.host_url.rstrip('/')}:
                return jsonify(error='Unrecognized request origin.'), 403
