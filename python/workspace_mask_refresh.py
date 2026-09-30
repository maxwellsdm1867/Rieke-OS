"""Discover updated UGM sidecars during metadata refresh; apply only on request."""
import hashlib
import tempfile
import zipfile
from pathlib import Path

from workspace_matlab_masks import read_ugm

MAX_BYTES = 32 * 1024 * 1024
LOCATIONS = {'matlab': 'matlab/selection.ugm', 'export': 'selection.ugm'}


class MaskRefresh:
    def __init__(self, service, store, state, importer):
        self.service, self.store, self.state, self.importer = service, store, state, importer
        self.latest = None

    def read(self, dataset_uuid, location):
        from workspace_matlab_routes import _identity
        dataset_uuid = _identity(dataset_uuid)
        if location not in LOCATIONS: raise ValueError('Unknown mask location')
        path = self.service.project_dir.resolve() / 'exports' / dataset_uuid / LOCATIONS[location]
        if path.resolve() != path: raise ValueError('Mask path must remain inside its registered export folder')
        with path.open('rb') as handle: raw = handle.read(MAX_BYTES + 1)
        if not raw or len(raw) > MAX_BYTES: raise ValueError('Mask must contain 1 byte to 32 MiB')
        # Parse the same bytes that were hashed, even if MATLAB saves again concurrently.
        with tempfile.TemporaryDirectory(prefix='rieke-mask-check-') as folder:
            copy = Path(folder) / 'selection.ugm'; copy.write_bytes(raw)
            parsed = read_ugm(copy)
        return path, hashlib.sha256(raw).hexdigest(), parsed

    def scan(self):
        candidates, errors = [], []
        events = (self.store.Event & {'project_uuid':self.service.project['project_uuid'], 'action':'curation_updated'}).to_dicts()
        applied = {(e['payload'].get('query_context',{}).get('dataset_uuid'),
                    e['payload'].get('query_context',{}).get('input_sha256')) for e in events}
        for export in self.store.list_dataset_revisions():
            if export.get('format') != 'epictree-mat': continue
            dataset, protocol = export['dataset_uuid'], export['protocol_uuid']
            if protocol not in self.service.protocols: continue
            original_hash = None
            try:
                with zipfile.ZipFile(export['artifact_path']) as archive:
                    if 'selection.ugm' in archive.namelist():
                        if archive.getinfo('selection.ugm').file_size > MAX_BYTES: raise ValueError('Archived mask exceeds 32 MiB')
                        original_hash = hashlib.sha256(archive.read('selection.ugm')).hexdigest()
            except (OSError, ValueError, zipfile.BadZipFile) as error:
                errors.append({'dataset_uuid':dataset,'error':str(error)}); continue
            for location, relative in LOCATIONS.items():
                path = self.service.project_dir / 'exports' / dataset / relative
                if not path.exists() and not path.is_symlink(): continue
                try:
                    path, sha, parsed = self.read(dataset, location)
                    if sha == original_hash or (dataset,sha) in applied: continue
                    revision = self.state(protocol)[2]
                    preview = self.importer(parsed,sha,path.name,protocol,revision,dataset,
                                            preview_only=True,refresh_service=False)
                    if preview['changed_count']:
                        candidates.append(dict(dataset_uuid=dataset, protocol_uuid=protocol, location=location,
                            name=export.get('name',dataset), path=str(path), input_sha256=sha, **preview))
                except (OSError, ValueError, KeyError, TypeError) as error:
                    errors.append({'dataset_uuid':dataset,'path':str(path),'error':str(error)})
        self.latest = dict(candidates=candidates, errors=errors, checked=True)
        return self.latest

    def apply(self, body):
        record = self.store.get_dataset_revision(body['dataset_uuid'])
        path, sha, parsed = self.read(body['dataset_uuid'], body['location'])
        if sha != body['input_sha256']:
            raise ValueError('MATLAB mask changed since refresh. Refresh metadata and review it again.')
        response = self.importer(parsed,sha,path.name,record['protocol_uuid'],body['query_revision'],body['dataset_uuid'])
        self.latest = None
        return response
