"""Exact, reviewed compatibility for disposable source projection witnesses.

Unknown source bytes keep a distinct identity, including this resolver's bytes.
A review can select an existing legacy identity; it never edits a cache or seal.
"""
import ast
import hashlib
import json
from pathlib import Path


OWNER_PATHS = (
    'recording_workspace.py',
    'disco/metadata/projection_cache.py',
    'disco/metadata/metadata_objects.py',
    'workspace_service.py',
)
_REVIEW_FIELDS = frozenset((
    'id', 'decision', 'reviewed_build', 'legacy_owners', 'legacy_contract',
    'rationale', 'evidence',
))


def _checksum(values):
    # Same canonicalization as the historical recipes.checksum witness.
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _digests(values, count):
    if (type(values) not in (list, tuple) or len(values) != count or
            any(type(value) is not str or len(value) != 64 or
                any(character not in '0123456789abcdef' for character in value)
                for value in values)):
        raise ValueError('Projection contract requires complete ordered SHA256 witnesses')
    return tuple(values)


def _reviews(path):
    # Do not import/execute this data file. Its own hash is deliberately outside
    # the reviewed vector to avoid a self-referential receipt. Packaging includes
    # it in the same application-integrity manifest as every other Python file.
    if path.is_symlink() or not path.is_file():
        raise ValueError('Projection contract review must be a regular data file')
    with path.open('rb') as stream:
        content = stream.read(131073)
    if len(content) > 131072:
        raise ValueError('Projection contract review exceeds its bound')
    body = ast.parse(content.decode('utf-8'), filename=str(path)).body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and type(body[0].value.value) is str:
        body = body[1:]
    if (len(body) != 1 or not isinstance(body[0], ast.Assign) or
            len(body[0].targets) != 1 or not isinstance(body[0].targets[0], ast.Name) or
            body[0].targets[0].id != 'COMPATIBILITY_RECEIPTS'):
        raise ValueError('Projection contract review must contain one literal assignment')
    data = ast.literal_eval(body[0].value)
    if (type(data) is not dict or set(data) != {'version', 'owners', 'reviews'} or
            type(data['version']) is not int or data['version'] != 1 or
            type(data['owners']) not in (list, tuple) or tuple(data['owners']) != OWNER_PATHS or
            type(data['reviews']) not in (list, tuple) or not 1 <= len(data['reviews']) <= 128):
        raise ValueError('Unsupported projection contract review schema')
    seen, ids = set(), set()
    for review in data['reviews']:
        if type(review) is not dict or set(review) != _REVIEW_FIELDS:
            raise ValueError('Invalid projection contract review fields')
        build = _digests(review['reviewed_build'], 5)
        if build in seen or type(review['id']) is not str or not review['id'].strip() or review['id'] in ids:
            raise ValueError('Duplicate or missing projection contract review identity')
        seen.add(build)
        ids.add(review['id'])
        if (type(review['rationale']) is not str or not review['rationale'].strip() or
                type(review['evidence']) not in (list, tuple) or not review['evidence'] or
                any(type(item) is not str or not item.strip() for item in review['evidence'])):
            raise ValueError('Projection contract review requires rationale and evidence')
        if review['decision'] == 'compatible':
            legacy = _digests(review['legacy_owners'], 4)
            if review['legacy_contract'] != _checksum(list(legacy)):
                raise ValueError('Legacy projection contract checksum disagrees with its owners')
        elif review['decision'] == 'breaking':
            if review['legacy_owners'] is not None or review['legacy_contract'] is not None:
                raise ValueError('Breaking projection contract cannot select a legacy identity')
        else:
            raise ValueError('Unknown projection contract review decision')
    return data['reviews']


def resolve_projection_contract(owner_digests):
    """Return a legacy witness only for one reviewed complete implementation.

    The four owners retain their historical order. All other builds, including
    resolver changes or invalid/missing review data, use the full five witnesses.
    Recording, metadata, SQL, index and lease admission remain caller-owned.
    """
    owners = _digests(owner_digests, 4)
    source = Path(__file__)
    build = owners + (hashlib.sha256(source.read_bytes()).hexdigest(),)
    fallback = _checksum(list(build))
    try:
        reviews = _reviews(source.with_name('projection_contract_receipts.py'))
    except (OSError, ValueError, SyntaxError, UnicodeError, RecursionError):
        return fallback
    for review in reviews:
        if tuple(review['reviewed_build']) == build:
            return review['legacy_contract'] if review['decision'] == 'compatible' else fallback
    return fallback
