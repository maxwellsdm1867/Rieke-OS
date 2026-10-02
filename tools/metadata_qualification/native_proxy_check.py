"""Real dev-proxy/native preference boundary regression; no mocked HTTP routes.

Run only against the owned isolated server, using its private preference path.
The successful write resaves the existing theme. SQL/scientific data are unused.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def check(origin, preferences):
    url = urlsplit(origin)
    preferences = preferences.resolve(strict=True)
    if (url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost'}
            or url.path not in ('', '/') or url.query or url.fragment
            or not preferences.is_relative_to(Path('/tmp').resolve())):
        raise ValueError('Require local HTTP origin and existing private /tmp preferences')
    endpoint = origin.rstrip('/') + '/api/app/appearance'
    original = Path.home() / '.rieke-os'
    guarded = [preferences/'annotation-author.json', original/'annotation-author.json', original/'appearance.json']
    before = [fingerprint(path) for path in guarded]
    with urlopen(endpoint, timeout=10) as response:
        current = json.load(response)
    saved = json.loads((preferences/'appearance.json').read_bytes())
    if (saved.get('theme'), saved.get('icon')) != (current['theme'], current['icon']):
        raise ValueError('Native preference response does not match owned private file')
    cases = []
    for identity, headers, expected in [
        ('valid_same_origin', {'Origin': origin, 'X-Workspace-Request': '1'}, 200),
        ('foreign_origin', {'Origin': 'http://example.invalid', 'X-Workspace-Request': '1'}, 403),
        ('missing_workspace_header', {'Origin': origin}, 403),
    ]:
        appearance_before = fingerprint(preferences/'appearance.json')
        request = Request(endpoint, data=json.dumps({'theme': current['theme']}).encode(),
            headers={'Content-Type': 'application/json', **headers}, method='POST')
        try:
            with urlopen(request, timeout=10) as response:
                status, body = response.status, json.load(response)
        except HTTPError as response:
            status, body = response.code, json.load(response)
        if status != expected:
            raise AssertionError(f'{identity}: expected {expected}, received {status}')
        if status == 200 and body != current:
            raise AssertionError('Idempotent native theme save changed appearance')
        if status == 403 and fingerprint(preferences/'appearance.json') != appearance_before:
            raise AssertionError('Rejected request changed private preference file')
        cases.append(dict(id=identity, status=status, passed=True))
    if before != [fingerprint(path) for path in guarded]:
        raise AssertionError('Author or original user preference bytes changed')
    return dict(status='passed', cases=cases, native_backend=True, mocked_routes=False,
                host_preserved=True, origin_rewritten=False, workspace_header_rewritten=False,
                original_preferences_unchanged=True, private_author_unchanged=True,
                scientific_sql_writes=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--origin', required=True)
    parser.add_argument('--preferences', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    receipt = check(args.origin, args.preferences)
    args.receipt.write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
