"""Explicit .ugm import into a current protocol's saved MATLAB-export subset."""
from __future__ import annotations

import contextlib
import hashlib
import os
from pathlib import Path
import tempfile
import uuid

from flask import jsonify, request

from recording_workspace import digest
from workspace_curation import RevisionConflict
from workspace_matlab_masks import read_ugm
from workspace_recipes import checksum, member_map, verify

MAX_MASK_BYTES = 32 * 1024 * 1024


class MatlabMaskConflict(RevisionConflict):
    def __init__(self, message):
        ValueError.__init__(self, message)
        self.current = {}


def _identity(value):
    if not isinstance(value, str):
        raise ValueError('Dataset identity must be a UUID')
    return str(uuid.UUID(value))


def _mat_record(store, identity, project_uuid, protocol_uuid):
    record = store.get_dataset_revision(identity)
    recipe = verify(record['recipe'])
    snapshot = verify(recipe['query_snapshot'])
    if (recipe.get('format') != 'recording-export-recipe' or recipe.get('destination') != 'epictree-mat'
            or recipe.get('export_uuid') != identity or record.get('dataset_uuid') != identity
            or record.get('project_uuid') != project_uuid or recipe.get('project_uuid') != project_uuid
            or record.get('protocol_uuid') != protocol_uuid or recipe.get('protocol_uuid') != protocol_uuid):
        raise ValueError('Mask must identify a completed MATLAB export from this project and protocol')
    for key in ('project_uuid', 'protocol_uuid', 'query_sha256', 'catalog_ref'):
        if snapshot.get(key) != recipe.get(key):
            raise ValueError('Saved MATLAB recipe and query snapshot disagree')
    if recipe.get('query_sha256') != checksum(recipe.get('query')) or snapshot.get('query') != recipe.get('query'):
        raise ValueError('Saved MATLAB query hash disagrees with its predicate')
    members, all_members = member_map(recipe), member_map(snapshot)
    if (not members or len(members) != record.get('epoch_count')
            or any(key not in all_members or value != all_members[key] for key, value in members.items())):
        raise ValueError('Saved MATLAB export membership is inconsistent')
    if snapshot.get('metadata_fingerprint_version') != 2:
        raise ValueError('MATLAB export lacks current source-metadata fingerprints; create a new export')
    return record, recipe, snapshot, members


def register_matlab_mask_routes(app, service, store, state, db_lock):
    """Register one manual import; no mask discovery, auto-load or tag rewrites.

    ``state(protocol_uuid)`` returns current result, curation mapping and revision.
    The existing CurationStore applies only exported UUID pairs transactionally,
    preserving nonexported decisions and checking the binding/curation revisions.
    """
    @app.post('/api/protocols/<protocol_uuid>/masks/import-matlab')
    def import_matlab_mask(protocol_uuid):
        protocol_uuid = _identity(protocol_uuid)
        if (request.args or set(request.files) != {'file'} or len(request.files.getlist('file')) != 1
                or set(request.form) - {'query_revision', 'dataset_uuid'}
                or 'query_revision' not in request.form
                or any(len(request.form.getlist(key)) != 1 for key in request.form)):
            raise ValueError('MATLAB mask import requires one file, query_revision and optional dataset_uuid')
        query_revision = request.form['query_revision']
        if not query_revision:
            raise ValueError('Current query revision is required')
        upload = request.files['file']
        filename = Path(upload.filename or '').name
        if Path(filename).suffix.lower() != '.ugm':
            raise ValueError('Choose an EpicTree .ugm selection mask')
        requested = request.form.get('dataset_uuid')
        requested = _identity(requested) if requested else None
        with tempfile.TemporaryDirectory(prefix='rieke-ugm-') as directory:
            path = Path(directory) / 'selection.ugm'
            size, input_digest = 0, hashlib.sha256()
            with path.open('wb') as handle:
                while chunk := upload.stream.read(64 * 1024):
                    size += len(chunk)
                    if size > MAX_MASK_BYTES:
                        return jsonify(error='UGM upload exceeds the 32 MiB limit'), 413
                    input_digest.update(chunk)
                    handle.write(chunk)
            parsed = read_ugm(path)
        identities = set(parsed['epoch_uuids'])
        metadata = parsed['metadata']
        embedded = {metadata[key] for key in ('dataset_uuid', 'export_uuid') if key in metadata}
        if len(embedded) > 1 or requested and embedded and requested not in embedded:
            raise ValueError('Requested dataset identity and mask provenance disagree')
        selected = requested or next(iter(embedded), None)
        project_uuid = service.project['project_uuid']
        source_manager = app.extensions.get('data_stores')
        guard = source_manager.registration_locks() if source_manager else contextlib.nullcontext()
        with db_lock, guard:
            service.refresh()
            result, current, revision = state(protocol_uuid)
            if query_revision != revision:
                raise MatlabMaskConflict('Query, source metadata or curation changed. Refresh before importing the MATLAB mask.')
            if selected is None:
                # One exported UUID narrows the immutable index; do not inspect
                # unrelated exports or guess from filenames and created dates.
                links = store.epoch_exports(parsed['epoch_uuids'][0])
                candidates = []
                for identity in sorted({link['dataset_uuid'] for link in links if link['protocol_uuid'] == protocol_uuid}):
                    candidate = store.get_dataset_revision(identity)
                    if candidate['recipe'].get('destination') != 'epictree-mat':
                        continue
                    record, recipe, snapshot, members = _mat_record(store, identity, project_uuid, protocol_uuid)
                    if set(members) == identities:
                        candidates.append({'dataset_uuid': identity, 'name': recipe.get('options', {}).get('name', identity)})
                if not candidates:
                    raise ValueError('No completed MATLAB export matches this exact UUID set; no mask decisions were applied')
                if len(candidates) > 1:
                    return jsonify(error='Several completed MATLAB exports have this UUID set. Choose an explicit dataset UUID.',
                                   code='ambiguous_export', matching_exports=candidates), 409
                selected = candidates[0]['dataset_uuid']
            record, recipe, snapshot, members = _mat_record(store, selected, project_uuid, protocol_uuid)
            if set(members) != identities:
                raise ValueError('Mask UUID set must exactly match the completed MATLAB export; positional or partial matching is not accepted')
            expected = {'project_uuid': project_uuid, 'protocol_uuid': protocol_uuid,
                        'dataset_uuid': selected, 'export_uuid': selected,
                        'query_sha256': recipe['query_sha256'], 'recipe_sha256': recipe['content_sha256']}
            scope = snapshot.get('source_scope') or recipe.get('source_scope') or {}
            for key in ('source_scope_revision', 'source_scope_sha256'):
                if key in metadata:
                    if not scope.get('revision') or metadata[key] != scope['revision']:
                        raise ValueError('Mask source-scope hash disagrees with the frozen MATLAB export')
            if any(key in metadata and metadata[key] != value for key, value in expected.items()):
                raise ValueError('Mask identity/query provenance disagrees with the frozen MATLAB export')
            if identities - current.keys():
                raise MatlabMaskConflict('Some exported epochs are outside the current protocol dataset; reconcile the dataset before importing this mask.')
            fingerprints = {row['uuid']: row['metadata_hash'] for row in result['epochs']}
            if any(members[key]['metadata_hash'] != fingerprints.get(key) for key in identities):
                raise MatlabMaskConflict('Exported source metadata changed. This MATLAB mask cannot be applied to changed recordings.')
            if any(service.rows[key]['source_sha256'] not in recipe['source_revisions'] for key in identities):
                raise ValueError('Exported epoch source identity disagrees with its frozen source revisions')
            artifact = Path(record['artifact_path']).resolve()
            if not artifact.is_relative_to((service.project_dir / 'exports').resolve()) or digest(artifact) != record['artifact_sha256']:
                raise ValueError('Completed MATLAB export artifact is missing, changed, or outside this project')
            inclusion = dict(zip(parsed['epoch_uuids'], parsed['mask']))
            changed = store.update(protocol_uuid, sorted(identities), {},
                {key: current[key]['revision'] for key in identities},
                {key: fingerprints[key] for key in identities}, os.environ.get('USER', 'local-user'),
                inclusion_by_epoch=inclusion,
                audit_context={'query_revision': revision, 'source_revisions': recipe['source_revisions'],
                    'input_format': 'epictree-ugm', 'input_version': metadata['version'],
                    'input_sha256': input_digest.hexdigest(), 'input_filename': filename,
                    'dataset_uuid': selected, 'recipe_sha256': recipe['content_sha256'],
                    'artifact_sha256': record['artifact_sha256'], 'matched_by': 'exact_export_epoch_uuid_set',
                    'nonexported_epochs_preserved': True},
                expected_binding_version=result.get('dataset_binding', {}).get('version', 0))
            _, _, after_revision = state(protocol_uuid)
            return jsonify(**changed, imported_count=len(identities), included_count=sum(inclusion.values()),
                query_revision=after_revision, dataset_uuid=selected,
                message=f'Imported {len(identities)} exported epoch decisions by UUID; other working-epoch decisions are unchanged.')
