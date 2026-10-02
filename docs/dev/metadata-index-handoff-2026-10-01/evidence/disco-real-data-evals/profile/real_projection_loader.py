"""Read active real project projections without creating caches or leases.

This helper never opens the mounted project as a WorkspaceService. Output data
stays in memory; callers must keep scientific data in private experiment paths.
"""
from pathlib import Path
import hashlib
import json
import sys
import zlib

PROJECT = Path('/PATH/TO/LOCAL_HOME/Documents/RecordingWorkspace/LOCAL_NATIVE_PROJECT')
REPO = Path('/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI')

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_real_projections(project=PROJECT):
    sys.path.insert(0, str(REPO / 'python'))
    from workspace_projection_cache import _ProjectionDetails
    directory = project / 'cache' / 'source-projections'
    manifest = directory / '.current-generations.json'
    manifest_digest = digest(manifest)
    names = json.loads(manifest.read_bytes())['keep']
    rows, details, cells, sources, evidence = {}, {}, {}, [], []
    for name in names:
        path = directory / name
        blob = path.read_bytes()
        actual = hashlib.sha256(blob).hexdigest()
        seal_path = path.with_suffix('.sha256')
        if actual != seal_path.read_text().strip():
            raise ValueError('Projection seal differs')
        document = json.loads(zlib.decompress(blob))
        projection = document['projection']
        decoded = _ProjectionDetails(projection['rows'], document['details'], document['objects'])
        if rows.keys() & projection['rows'].keys():
            raise ValueError('Active projections duplicate epoch identities')
        rows.update(projection['rows'])
        details.update((identity, decoded[identity]) for identity in decoded)
        cells.update(projection['cells'])
        sources.append(projection['source'])
        evidence.append({'projection': name, 'compressed_bytes': len(blob),
                         'uncompressed_bytes': len(zlib.decompress(blob)),
                         'sha256': actual, 'epochs': len(decoded),
                         'metadata_objects': len(document['objects'])})
    if digest(manifest) != manifest_digest:
        raise ValueError('Active generations changed during extraction')
    for item in evidence:
        if digest(directory / item['projection']) != item['sha256']:
            raise ValueError('Projection changed during extraction')
    return rows, details, cells, sources, {'manifest_sha256': manifest_digest,
                                          'manifest': names, 'sources': evidence}
