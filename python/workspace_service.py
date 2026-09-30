"""Read model for the local React workspace, backed by existing RetinAnalysis.

Metadata is checked against the database's recorded source manifest. Waveforms
are read only on request as bounded, full-rate slices from verified H5 sources.
Callers serialize calls because the underlying DataJoint connection is shared.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path
import uuid
from collections.abc import Mapping

from recording_workspace import (connect, digest, epochs, evaluate_protocol_file,
                                 validate_protocol_definition, workspace_tables)
from workspace_recipes import build_tree, parse_splits, checksum
from workspace_tree import catalog as tree_catalog, value_label, humanize as field_label
from workspace_tree_code import matlab_tree_command
from workspace_predicates import validate as validate_predicate, matches as predicate_matches, predicate_catalog

TREE_CACHE_VALUE_BUDGET = 2_000_000
TREE_CACHE_MAX_SCOPES = 8
EPOCH_PAGE_CACHE_BYTES = 64 * 1024 * 1024


class _SourceDetails(Mapping):
    """Dispatch lazy details through the already validated owning source.

    Membership iteration never opens a source or decompresses details. Looking
    up an epoch touches exactly its own source mapping, independent of the
    number of recordings in a project.
    """
    def __init__(self, rows, sources):
        self.rows, self.sources = rows, sources

    def __len__(self):
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def __getitem__(self, identity):
        return self.sources[self.rows[identity]['source_sha256']][identity]


def _date(value):
    raw = str(value or '')[:10]
    for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
        try:
            return dt.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError('Unrecognized source timestamp')


def _text(value):
    return value.decode('utf-8') if isinstance(value, bytes) else str(value)


def _uuid(value):
    return str(uuid.UUID(_text(value)))


def _fingerprint(epoch):
    return hashlib.sha256(json.dumps({k: epoch[k] for k in
        ('parameters', 'properties', 'attributes')}, sort_keys=True,
        allow_nan=False).encode()).hexdigest()


def validate_filters(filters):
    filters = {} if filters is None else filters
    if not isinstance(filters, dict) or set(filters) - {'epoch_uuid', 'cell_uuid', 'cell_type', 'group_label', 'tag', 'tagged', 'tag_predicate'}:
        raise ValueError('Unsupported filter; use epoch_uuid, cell_uuid, cell_type, group_label, tag, tagged, or tag_predicate')
    if any(not isinstance(value, str) for value in filters.values()):
        raise ValueError('Filter values must be text')
    if 'tag' in filters:
        from workspace_annotations import text
        text(filters['tag'])
    if 'tagged' in filters and filters['tagged'] != 'true':
        raise ValueError('The tagged filter must be the text true')
    if 'tag_predicate' in filters:
        predicate = validate_tag_filter_predicate(filters['tag_predicate'])
        filters = {**filters, 'tag_predicate': json.dumps(predicate, sort_keys=True, separators=(',', ':'), allow_nan=False)}
    cleaned = {k: v for k, v in filters.items() if v}
    if 'epoch_uuid' in cleaned:
        cleaned['epoch_uuid'] = _uuid(cleaned['epoch_uuid'])
    if 'cell_uuid' in cleaned:
        cleaned['cell_uuid'] = _uuid(cleaned['cell_uuid'])
    return cleaned


TAG_FILTER_FIELDS = ('annotations/cell/tags', 'annotations/epoch/tags', 'annotations/effective/tags')


def validate_tag_filter_predicate(value):
    """Use the regular bounded predicate grammar, limited to shared tag arrays."""
    if not isinstance(value, str) or len(value) > 65536:
        raise ValueError('Tag predicate must be JSON text up to 65536 characters')
    try:
        predicate = json.loads(value)
    except (ValueError, RecursionError) as error:
        raise ValueError('Malformed tag predicate JSON') from error
    from workspace_predicates import validate
    return validate(predicate, {'fields': [{'id': key} for key in TAG_FILTER_FIELDS]},
                    {'tag_schema': {key: ['example tag'] for key in TAG_FILTER_FIELDS}})


def bounded_window(start, count, total, maximum=100000):
    if isinstance(start, bool) or isinstance(count, bool) or not isinstance(start, int) or not isinstance(count, int):
        raise ValueError('Sample offset and count must be integers')
    if start < 0 or start > total or count < 1 or count > maximum:
        raise ValueError(f'Invalid sample window; count must be 1–{maximum}')
    return start, min(total, start + count)


def _metadata(obj, exclude):
    return {k: v for k, v in obj.items() if k not in exclude}


def number_block_epochs(rows):
    """Readable ordinals within immutable source blocks, independent of filters."""
    blocks = {}
    for row in rows.values():
        blocks.setdefault(row['block_uuid'], []).append(row)
    for items in blocks.values():
        items.sort(key=lambda row: (row['date'], row['start_time'][11:], row['epoch_uuid']))
        for number, row in enumerate(items, 1):
            row['epoch_number'] = number


def read_response_window(path, signature, row, stream, start=0, count=20000):
    """Read bounded samples after the caller verifies the source SHA-256.

    Shared by the live catalog and standalone SQLite handoff consumer. This
    function never opens a database; identity, units and source stat checks are
    identical for both workflows.
    """
    import h5py
    import numpy as np
    from recording_workspace import resolve_sealed_h5_path
    path = Path(path)
    with h5py.File(path, 'r') as h5:
        obj = resolve_sealed_h5_path(h5, stream['h5_path'])
        if _uuid(obj.attrs['uuid']) != stream['uuid'] or _uuid(obj.parent.parent.attrs['uuid']) != row['epoch_uuid']:
            raise ValueError('Trace source identity changed')
        if float(obj.attrs['sampleRate']) != stream['sample_rate']:
            raise ValueError('Trace source sample rate changed')
        data = resolve_sealed_h5_path(h5, stream['h5_path'].rstrip('/') + '/data')
        if not isinstance(data, h5py.Dataset) or not data.dtype.names or not {'quantity', 'units'} <= set(data.dtype.names):
            raise ValueError('Unsupported response representation')
        if len(data) != stream['sample_count']:
            raise ValueError('Trace sample count changed')
        begin, end = bounded_window(start, count, len(data))
        samples = data[begin:end]
        if any(_text(unit) != stream['units'] for unit in np.unique(samples['units'])):
            raise ValueError('Trace sample units are inconsistent')
        values = samples['quantity'].astype(float)
        if not np.isfinite(values).all():
            raise ValueError('Trace contains nonfinite samples; explicit handling required')
    after = path.stat()
    current_signature = ((str(path), after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                         if len(signature) == 6 else (str(path), after.st_size, after.st_mtime_ns, after.st_ctime_ns))
    if signature != current_signature:
        raise ValueError('Source recording changed while reading trace')
    return {'epoch_uuid': row['epoch_uuid'], 'stream_uuid': stream['uuid'],
            'values': values.tolist(), 'sample_rate': stream['sample_rate'], 'units': stream['units'],
            'total_samples': stream['sample_count'], 'start': begin, 'count': end - begin,
            'source_sha256': row['source_sha256'], 'decimated': False}


from workspace_tree import materialize_combinations, predicate_scope, component_display


class WorkspaceService:
    def __init__(self, project_dir, curation_provider=None):
        self.project_dir = Path(project_dir).resolve()
        if (self.project_dir / '.portable-restore.pending').exists():
            raise ValueError('Project transfer restore is incomplete; finish recovery before opening it')
        config = json.loads((self.project_dir / 'catalog.json').read_text())
        if config.get('connection', {}).get('credential_provider', {}).get('kind') == 'native-project':
            from workspace_portability import rebase_project_paths, register_empty_project
            register_empty_project(self.project_dir)
            rebase_project_paths(self.project_dir)
        self.curation_provider = curation_provider
        self._loaded = False
        self._source_signatures = {}
        from workspace_projection_cache import ProjectionCache
        import workspace_projection_cache, workspace_metadata_objects
        self._projection_store = ProjectionCache(self.project_dir / 'cache' / 'source-projections')
        import recording_workspace
        self._projection_contract = checksum([digest(Path(module.__file__)) for module in
            (recording_workspace, workspace_projection_cache, workspace_metadata_objects)] + [digest(Path(__file__))])
        self.refresh()

    def set_curation_provider(self, provider):
        self.curation_provider = provider

    def set_annotation_provider(self, provider):
        """Read protocol-scoped annotations independently of working membership."""
        self.annotation_provider = provider

    def _with_annotation_fields(self, data):
        if not getattr(self, 'annotation_provider', None) and not getattr(self, 'shared_annotations', None):
            return data
        from workspace_tag_predicates import TagPredicates
        fields = TagPredicates(self).catalog_fields([row['epoch_uuid'] for row in self._tree_rows(None)])
        return {**data, 'fields': [*data['fields'], *fields]}

    def _match_metadata_predicate(self, predicate, ids):
        index = getattr(self, 'disk_index', None)
        if index:
            return index.match(predicate, ids=ids)
        catalog, values = predicate_scope(*self._registered_tree_fields())
        validated = validate_predicate(predicate, catalog, values)
        return validated, [identity for identity in ids if predicate_matches(validated, values[identity])]

    def match_predicate(self, predicate, ids=None):
        """Return validated predicate, exact IDs and optional tag provenance."""
        self._ready()
        from workspace_tag_predicates import TagPredicates
        eligible = [row['epoch_uuid'] for row in self._tree_rows(None)] if ids is None else list(ids)
        if set(eligible) - self.rows.keys():
            raise ValueError('Predicate scope contains unavailable epochs')
        return TagPredicates(self).match(predicate, eligible)

    def set_source_state_provider(self, provider):
        self.source_state_provider = provider
        self._predicate_catalog_cache = None
        self._tree_catalog_cache = {}

    def source_scope(self):
        """Eligibility for NEW source queries; frozen working sets stay intact."""
        self._ready()
        provider = getattr(self, 'source_state_provider', None)
        states = provider() if provider else {}
        registrations = []
        for source in self.sources:
            identity = source['source_sha256']
            state = states.get(identity, {})
            archived, version = state.get('archived', False), state.get('version', 0)
            excluded = state.get('query_excluded', archived)
            if type(archived) is not bool or type(excluded) is not bool or type(version) is not int or version < 0:
                raise ValueError('Invalid source registration eligibility state')
            registrations.append({'source_sha256': identity, 'archived': archived, 'query_excluded': excluded, 'version': version})
        registrations.sort(key=lambda item: item['source_sha256'])
        # Freeze/archive change registration state but not query eligibility.
        revision = checksum([{'source_sha256': row['source_sha256'], 'query_excluded': row['query_excluded']}
                             for row in registrations])
        return {'revision': revision, 'registrations': registrations,
                'active_source_revisions': [row['source_sha256'] for row in registrations if not row['query_excluded']],
                'excluded_source_revisions': [row['source_sha256'] for row in registrations if row['query_excluded']],
                'archived_source_revisions': [row['source_sha256'] for row in registrations if row['archived']]}

    def _registered_tree_fields(self):
        """Keep the registered schema even when its last source is query-excluded."""
        self._ready()
        key = (id(self.rows), len(self.rows), id(self.details), len(self.details))
        cached = getattr(self, '_registered_tree_cache', None)
        if cached is None or cached[0] != key:
            index = getattr(self, 'disk_index', None)
            catalog = (index.catalog(), index.values()) if index else tree_catalog(list(self.rows.values()), self.details, sources=self.sources)
            cached = self._registered_tree_cache = (key, catalog)
            self._registered_predicate_cache = None
        return cached[1]

    def _verified_source(self, manifest, signature_cache=None):
        signatures = self._source_signatures if signature_cache is None else signature_cache
        path = Path(manifest['source_path']).resolve()
        stat = path.stat()
        signature = (str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        expected = manifest['source_sha256']
        if stat.st_size != manifest['source_size']:
            raise ValueError('Source recording size changed; import a new revision')
        if signatures.get(expected) != signature:
            if digest(path) != expected:
                raise ValueError('Source recording checksum changed; refusing trace access')
            after = path.stat()
            if signature != (str(path), after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError('Source recording changed during verification')
            signatures[expected] = signature
        return path, signature

    def _read_source_metadata(self, source, document, path, signature):
        """Build one verified source projection without touching published state."""
        import h5py
        manifest = source['manifest']
        rows, details, cells = {}, {}, {}
        source_epoch_count = 0
        source_cells = set()
        from recording_workspace import validate_source_identity, validate_manifest_cell_count
        with h5py.File(path, 'r') as h5:
            validate_source_identity(h5, document)
            for animal in document['animals']:
                for preparation in animal['preparations']:
                    for cell in preparation['cells']:
                        cells[cell['uuid']] = {'cell_uuid': cell['uuid'], 'label': cell['label'],
                            'cell_type': cell.get('type'), 'date': _date(cell['start_time']), 'start_time': cell['start_time']}
            for cell, group, block, epoch in epochs(document):
                identity = _uuid(epoch['uuid'])
                if identity in rows:
                    raise ValueError('Duplicate epoch UUID across source recordings')
                source_epoch_count += 1
                source_cells.add(cell['uuid'])
                streams = []
                for kind in ('responses', 'stimuli'):
                    for device, stream in epoch.get(kind, {}).items():
                        obj = h5[stream['h5path']]
                        if _uuid(obj.attrs['uuid']) != stream['uuid'] or _uuid(obj.parent.parent.attrs['uuid']) != identity:
                            raise ValueError('Stream pointer identity disagrees with source')
                        if _uuid(obj.parent.parent.parent.parent.attrs['uuid']) != block['uuid']:
                            raise ValueError('Stream block pointer disagrees with source')
                        data = obj.get('data')
                        rate = stream.get('sampleRate')
                        units = None
                        if kind == 'responses':
                            if data is None or not data.dtype.names or not {'quantity', 'units'} <= set(data.dtype.names):
                                raise ValueError('Unsupported response representation')
                            if rate != float(obj.attrs['sampleRate']) or stream.get('sampleRateUnits') != 'Hz' or rate <= 0:
                                raise ValueError('Source response sample rate disagrees with metadata')
                            units = _text(data[0]['units']) if len(data) else None
                        streams.append({'uuid': stream['uuid'], 'device': device, 'kind': kind,
                            'sample_rate': rate, 'sample_rate_units': stream.get('sampleRateUnits'),
                            'sample_count': len(data) if data is not None else None,
                            'units': units, 'h5_path': stream['h5path'],
                            'data_path': data.name if data is not None else None})
                durations = [s['sample_count'] / s['sample_rate'] for s in streams
                             if s['kind'] == 'responses' and s['sample_rate'] and s['sample_count'] is not None]
                rows[identity] = {'epoch_uuid': identity, 'cell_uuid': cell['uuid'],
                    'cell_label': cell['label'], 'cell_type': cell.get('type'),
                    'date': _date(epoch['start_time']), 'start_time': epoch['start_time'],
                    'group_uuid': group['uuid'], 'group_label': group.get('label'),
                    'block_uuid': block['uuid'], 'block_start_time': block.get('start_time'),
                    'block_end_time': block.get('end_time'), 'protocol_name': block['protocolID'],
                    'duration_seconds': max(durations, default=0), 'streams': streams,
                    'source_sha256': source['source_sha256'], 'metadata_hash': _fingerprint(epoch)}
                details[identity] = {'parameters': epoch.get('parameters', {}),
                    'properties': epoch.get('properties', {}), 'attributes': epoch.get('attributes', {}),
                    'metadata': {'cell': _metadata(cell, {'epoch_groups'}),
                        'group': _metadata(group, {'epoch_blocks'}),
                        'block': _metadata(block, {'epochs'}), 'epoch': epoch}}
                cells[cell['uuid']] = {'cell_uuid': cell['uuid'], 'label': cell['label'],
                    'cell_type': cell.get('type'), 'date': _date(cell['start_time']), 'start_time': cell['start_time']}
        validate_manifest_cell_count(manifest, cells, source_cells)
        if source_epoch_count != manifest['counts']['epochs']:
            raise ValueError('Source count differs from validated manifest')
        after = path.stat()
        if signature != (str(path), after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('Source recording changed while reading metadata')
        summary = {'source_sha256': source['source_sha256'], 'filename': path.name,
            'source_path': str(path), 'imported_at': manifest.get('imported_at', manifest['validated_at']),
            'counts': manifest['counts'], 'warnings': manifest.get('warnings', []),
            'experiment_uuid': document['uuid'], 'metadata': _metadata(document, {'animals'})}
        fingerprints = {identity: hashlib.sha256(json.dumps({
            'epoch': details[identity], 'source_sha256': row['source_sha256']},
            sort_keys=True, allow_nan=False).encode()).hexdigest()
            for identity, row in rows.items()}
        return {'rows': rows, 'details': details, 'cells': cells,
                'source': summary, 'fingerprints': fingerprints}

    @staticmethod
    def _input_signature(path):
        path = Path(path).resolve(strict=True)
        stat = path.stat()
        if not path.is_file():
            raise ValueError('Recorded input is not a regular file')
        return (str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)

    def refresh(self):
        """Incrementally rebuild verified projections; publish only whole successes."""
        started = time.perf_counter()
        metrics = {'source_cache_hits': 0, 'source_cache_rebuilt': 0,
                   'timing_ms': {'metadata_check': 0., 'source_rebuild': 0., 'sql_queries': 0.}}
        self._loaded = False
        try:
            result = self._refresh_verified_sources(metrics)
        except Exception as error:
            metrics['timing_ms']['total'] = (time.perf_counter() - started) * 1000
            self.last_refresh = {**metrics, 'status': 'failed', 'error_type': type(error).__name__,
                'reused_sources': metrics['source_cache_hits'], 'rebuilt_sources': metrics['source_cache_rebuilt'],
                'elapsed_seconds': metrics['timing_ms']['total']/1000,
                'completed_at': dt.datetime.now(dt.timezone.utc).isoformat()}
            raise
        metrics['timing_ms']['total'] = (time.perf_counter() - started) * 1000
        self.last_refresh = {**result, **metrics, 'status': 'complete',
            'reused_sources': metrics['source_cache_hits'], 'rebuilt_sources': metrics['source_cache_rebuilt'],
            'elapsed_seconds': metrics['timing_ms']['total']/1000,
            'completed_at': dt.datetime.now(dt.timezone.utc).isoformat()}
        self.last_successful_refresh = copy.deepcopy(self.last_refresh)
        return copy.deepcopy(self.last_refresh)

    def _refresh_verified_sources(self, metrics):
        project = json.loads((self.project_dir / 'project.json').read_text())
        config = json.loads((self.project_dir / 'catalog.json').read_text())
        if config.get('adapter') != 'datajoint' or config.get('database') != 'schema':
            raise ValueError('Unsupported main catalog')
        if config['project_uuid'] != project['project_uuid']:
            raise ValueError('Project and catalog identities disagree')
        if hasattr(self, 'project') and self.project['project_uuid'] != project['project_uuid']:
            raise ValueError('Project identity changed; open that project in a separate workspace session')
        provider = config['connection']['credential_provider']
        if provider['kind'] not in {'docker-container-env', 'native-project'}:
            raise ValueError('Unsupported credential provider')
        dj = (connect(provider, project_dir=self.project_dir) if provider['kind'] == 'native-project'
              else connect(provider['container']))
        _, Source, Event, _ = workspace_tables(dj)
        source_records = (Source & {'project_uuid': project['project_uuid']}).to_dicts()
        rows, cells, sources, manifests, fingerprints = {}, {}, [], {}, {}
        detail_maps = {}
        old_cache = getattr(self, '_source_metadata_cache', {})
        projection_store = getattr(self, '_projection_store', None)
        pending_projections = []
        next_cache, final_checks, prepared = {}, [], []
        verified_signatures = dict(getattr(self, '_source_signatures', {}))
        # Establish the entire verified input generation before decoding any
        # source projection. A matching sealed index is already the projection.
        for source in source_records:
            check_started = time.perf_counter()
            manifest = source['manifest']
            identity = source['source_sha256']
            if identity in next_cache:
                raise ValueError('Duplicate source identity in the main catalog')
            if manifest['source_sha256'] != identity:
                raise ValueError('Database source identity and manifest disagree')
            metadata_path = Path(manifest['metadata_path']).resolve()
            if not metadata_path.is_relative_to(self.project_dir / 'imports'):
                raise ValueError('Metadata reference escapes project imports')
            metadata_signature = self._input_signature(metadata_path)
            metadata_sha = digest(metadata_path)
            if metadata_sha != manifest['metadata_sha256']:
                raise ValueError('Imported metadata checksum changed; refusing the read model')
            if metadata_signature != self._input_signature(metadata_path):
                raise ValueError('Imported metadata changed during verification')
            source_path = Path(manifest['source_path']).resolve()
            source_signature = self._input_signature(source_path)
            key = (checksum(source), metadata_signature, metadata_sha, source_signature,
                   getattr(self, '_projection_contract', None))
            next_cache[identity] = {'key':key, 'disk':True}
            prepared.append((source, metadata_path, key))
            final_checks.extend([(metadata_path, metadata_signature), (source_path, source_signature)])
            metrics['timing_ms']['metadata_check'] += (time.perf_counter() - check_started) * 1000
        # Prepared source projections remain leased until this refresh either
        # publishes its complete generation or releases them after failure.
        projection_leases=projection_store.hold(entry['key'] for entry in next_cache.values()) if projection_store else None
        disk_index, previous_index, location, generation = None, getattr(self, 'disk_index', None), None, None
        if projection_store:
            from workspace_disk_index import DiskMetadataIndex
            import workspace_disk_index, workspace_tree, workspace_predicates, workspace_metadata_objects
            import sqlite3
            generation = checksum({'project_uuid':project['project_uuid'],
                'sources':{identity:entry['key'] for identity,entry in next_cache.items()},
                'index_contract':[digest(Path(module.__file__)) for module in
                                  (workspace_disk_index,workspace_tree,workspace_predicates,workspace_metadata_objects)]})
            index_started = time.perf_counter()
            location = self.project_dir / 'cache' / 'metadata' / (generation + '.sqlite')
            if previous_index is not None and previous_index.generation == generation:
                previous_index._check()
                disk_index = previous_index
                metrics['metadata_index'] = 'reused'
            else:
                try:
                    disk_index = DiskMetadataIndex.open(location,generation,project['project_uuid'])
                    metrics['metadata_index'] = 'reopened'
                except (OSError,ValueError,sqlite3.DatabaseError):
                    pass  # An absent/invalid disposable index is rebuilt below.
            metrics['metadata_index_seconds'] = time.perf_counter() - index_started
            metrics['metadata_index_generation'] = generation
        for source, metadata_path, key in prepared:
            manifest, identity = source['manifest'], source['source_sha256']
            cached = old_cache.get(identity)
            # Even when one new source requires a new generation, unchanged
            # sources can retain lazy detail views from the previous index.
            reusable_index = disk_index or (previous_index if projection_store and cached is not None and cached['key'] == key else None)
            if reusable_index is not None:
                projection = reusable_index.source_projection(identity, lazy_details=True)
                metrics['source_cache_hits'] += 1
            else:
                disk_projection = projection_store.read(key) if projection_store else None
                if disk_projection is not None:
                    projection = disk_projection
                    metrics['source_cache_hits'] += 1
                elif not projection_store and cached is not None and cached['key'] == key:
                    projection = cached['projection']
                    metrics['source_cache_hits'] += 1
                else:
                    rebuild_started = time.perf_counter()
                    document = json.loads(metadata_path.read_text())
                    if document['uuid'] != source['experiment_uuid']:
                        raise ValueError('Imported experiment identity disagrees with catalog')
                    path, signature = self._verified_source(manifest, verified_signatures)
                    projection = self._read_source_metadata(source, document, path, signature)
                    if projection_store:
                        pending_projections.append((key, projection))
                    else:
                        projection = copy.deepcopy(projection)
                    metrics['source_cache_rebuilt'] += 1
                    metrics['timing_ms']['source_rebuild'] += (time.perf_counter() - rebuild_started) * 1000
            if rows.keys() & projection['rows'].keys():
                raise ValueError('Duplicate epoch UUID across source recordings')
            snapshot = projection if projection_store else copy.deepcopy(projection)
            rows.update(snapshot['rows'])
            # Retain lazy details and dispatch by the independently validated
            # source owner, without probing every preceding source mapping.
            detail_maps[identity] = snapshot['details']
            cells.update(snapshot['cells'])
            fingerprints.update(snapshot['fingerprints'])
            sources.append(snapshot['source'])
            manifests[identity] = copy.deepcopy(manifest)
            next_cache[identity] = {'key':key,'disk':True} if projection_store else {'key':key,'projection':projection}
        details = _SourceDetails(rows, detail_maps)
        number_block_epochs(rows)
        query_started = time.perf_counter()
        protocols = {}
        for file in sorted((self.project_dir / 'protocols').glob('*.protocol.json')):
            definition = json.loads(file.read_text())
            validate_protocol_definition(definition)
            if definition['project_uuid'] != project['project_uuid']:
                raise ValueError('Protocol points to another project')
            result = evaluate_protocol_file(file)
            result.setdefault('project_uuid', project['project_uuid'])
            result.setdefault('protocol_name', definition['query']['all'][0]['value'])
            result.setdefault('source_revisions', [s['source_sha256'] for s in sources])
            query_ids = [e['uuid'] for e in result['epochs']]
            if len(set(query_ids)) != len(query_ids):
                raise ValueError('Query returned duplicate epoch identities')
            expected_ids = {key for key, row in rows.items() if row['protocol_name'] == result['protocol_name']}
            if set(query_ids) != expected_ids:
                raise ValueError('Main database query disagrees with verified source membership')
            for member in result['epochs']:
                if rows[member['uuid']]['metadata_hash'] != member['metadata_hash']:
                    raise ValueError('Database epoch metadata differs from verified import')
            expected_cells = {rows[key]['cell_uuid'] for key in query_ids}
            if {c['uuid'] for c in result['cells']} != expected_cells:
                raise ValueError('Database query cell identities disagree with source')
            if definition['protocol_uuid'] in protocols:
                raise ValueError('Duplicate protocol workspace identity')
            protocols[definition['protocol_uuid']] = {'definition': definition, 'file': file, 'result': result}
        metrics['timing_ms']['sql_queries'] = (time.perf_counter() - query_started) * 1000
        # SQL validation can take time. Recheck every input before publishing,
        # including warm hits whose files disappeared or changed mid-refresh.
        for path, signature in final_checks:
            if self._input_signature(path) != signature:
                raise ValueError('Recorded input changed before refresh completed')
        preserve_indexes = (hasattr(self, 'rows')
            and {key: entry['key'] for key, entry in old_cache.items()} == {key: entry['key'] for key, entry in next_cache.items()}
            and getattr(self, 'protocols', None) == protocols)
        registered_cache = getattr(self, '_registered_tree_cache', None)
        for key, projection in pending_projections:
            try:
                projection_store.write(key, projection)
            except OSError as error:
                metrics.setdefault('cache_warnings', []).append('Source projection cache could not be saved: ' + str(error))
        if projection_store:
            if disk_index is None:
                self.last_refresh = {'status':'indexing', 'started_at':dt.datetime.now(dt.timezone.utc).isoformat()}
                index_started = time.perf_counter()
                disk_index = DiskMetadataIndex.build(location, rows, details, sources, generation, project['project_uuid'])
                metrics['metadata_index'] = 'built'
                metrics['metadata_index_seconds'] += time.perf_counter() - index_started
            for path, signature in final_checks:
                if self._input_signature(path) != signature:
                    raise ValueError('Recorded input changed while building metadata index')
        metrics['discovery_indexes_preserved'] = preserve_indexes
        self.project, self.config, self.dj, self.Event = project, config, dj, Event
        self.rows, self.details, self.cells, self.sources = rows, disk_index.details if disk_index else details, cells, sources
        self.disk_index = disk_index
        self.manifests, self.protocols = manifests, protocols
        if not preserve_indexes:
            self._tree_catalog_cache = {}
        self._fingerprints = fingerprints
        self._source_metadata_cache = next_cache
        self._source_signatures = verified_signatures
        if not preserve_indexes:
            self._predicate_catalog_cache = None
            self._registered_tree_cache = None
            self._registered_predicate_cache = None
        elif registered_cache is not None:
            self._registered_tree_cache = ((id(rows), len(rows), id(self.details), len(self.details)), registered_cache[1])
        self._loaded = True
        if projection_store and disk_index is not None:
            try:
                metrics['cache_cleanup']={'metadata':disk_index.publish(),
                    'projections':projection_store.publish(entry['key'] for entry in next_cache.values())}
            except (OSError,ValueError) as error:
                metrics.setdefault('cache_warnings',[]).append('Derived cache cleanup was deferred: '+str(error))
        if projection_leases is not None:projection_leases.close()
        return {'sources': len(sources), 'epochs': len(rows), 'protocols': len(protocols)}

    def _ready(self):
        if not self._loaded:
            raise RuntimeError('Workspace validation did not complete; refresh required')

    def _curation(self, protocol_uuid=None):
        if self.curation_provider and protocol_uuid:
            return self.curation_provider(protocol_uuid, self.fingerprints(protocol_uuid))
        return {}

    def fingerprints(self, protocol_uuid):
        result = self.query_result(protocol_uuid)
        return {member['uuid']: self._fingerprints[member['uuid']] for member in result['epochs']}

    @staticmethod
    def _decorate(row, curation):
        state = {'included': True, 'reviewed': False, 'review_state': 'unreviewed',
                 'tags': [], 'revision': 0, **curation.get(row['epoch_uuid'], {})}
        state['reviewed'] = state['review_state'] == 'approved'
        return {**row, 'curation': state}

    def protocol_file(self, protocol_uuid):
        self._ready()
        return self.protocols[_uuid(protocol_uuid)]['file']

    def set_binding_provider(self, provider, *, header_provider=None):
        self.binding_provider = provider
        self.binding_header_provider = header_provider
        self._epoch_page_cache = None

    def binding(self, protocol_uuid):
        provider = getattr(self, 'binding_provider', None)
        return provider(_uuid(protocol_uuid)) if provider else None

    def query_result(self, protocol_uuid):
        self._ready()
        protocol_uuid = _uuid(protocol_uuid)
        original = copy.deepcopy(self.protocols[protocol_uuid]['result'])
        binding = self.binding(protocol_uuid)
        if binding is None:
            if self.protocols[protocol_uuid]['definition'].get('initial_revision_uuid'):
                raise ValueError('Pinned protocol creation was interrupted. Retry creating it from the same saved selection and name.')
            return original
        recipe = binding['recipe']
        identities = [member['uuid'] for member in recipe['epochs']]
        if set(identities) - self.rows.keys():
            raise ValueError('Bound dataset contains unavailable epochs; explicit reconciliation is required')
        cells = {self.rows[key]['cell_uuid'] for key in identities}
        original.update(
            epochs=[{'uuid': key, 'metadata_hash': self.rows[key]['metadata_hash']} for key in identities],
            cells=[{'uuid': key, 'label': self.cells[key]['label'], 'type': self.cells[key]['cell_type']} for key in sorted(cells)],
            source_revisions=recipe['source_revisions'],
            effective_query={'version': 2, 'kind': 'source_predicate', 'predicate': recipe['predicate']},
            effective_view={'group_by': recipe['tree_view']['fields'], 'layout': 'landscape'},
            dataset_binding={'revision_uuid': binding['revision_uuid'], 'version': binding['version'],
                'name': recipe['name'], 'source_revisions': recipe['source_revisions'],
                'predicate': recipe['predicate'], 'splits': recipe['splits'], 'tree_view': recipe['tree_view'],
                **({'annotation_scope': copy.deepcopy(recipe['annotation_scope'])} if recipe.get('annotation_scope') else {}),
                'changed_epoch_uuids': [member['uuid'] for member in recipe['epochs']
                    if self._fingerprints[member['uuid']] != member['metadata_hash']]})
        return original

    def filtered_rows(self, protocol_uuid, filters=None):
        filters = validate_filters(filters)
        result = self.query_result(protocol_uuid)
        curation = self._curation(protocol_uuid)
        rows = [self._decorate(self.rows[member['uuid']], curation) for member in result['epochs']]
        return self._filter_rows(rows, filters)

    def _filter_rows(self, rows, filters):
        """Narrow the current dataset without changing membership or annotations.

        Shared cell tags inherit to epochs. Protocol curation tags are a distinct
        scope and do not satisfy these shared annotation filters.
        """
        ordinary = {key: value for key, value in filters.items() if key not in {'tag', 'tagged', 'tag_predicate'}}
        rows = [row for row in rows if all(row.get(key) == value for key, value in ordinary.items())]
        if any(key in filters for key in ('tag', 'tagged', 'tag_predicate')):
            shared = getattr(self, 'shared_annotations', None)
            indexed=shared.filter_epoch_ids(rows,filters) if hasattr(shared,'filter_epoch_ids') else None
            if indexed is not None:
                selected=set(indexed[0])
                return sorted((row for row in rows if row['epoch_uuid'] in selected),
                    key=lambda row:(row['date'],row['start_time'],row['epoch_uuid']))
            annotations = shared.for_epochs(rows) if shared else {}
            from workspace_predicates import matches
            predicate = validate_tag_filter_predicate(filters['tag_predicate']) if 'tag_predicate' in filters else None
            selected = []
            for row in rows:
                tags = {chip['tag'] for chip in annotations.get(row['epoch_uuid'], {}).get('effective_tags', [])}
                if ('tag' not in filters or filters['tag'] in tags) and ('tagged' not in filters or tags):
                    annotation = annotations.get(row['epoch_uuid'], {})
                    current = {field: sorted({chip['tag'] for chip in annotation.get(scope, [])})
                               for field, scope in zip(TAG_FILTER_FIELDS, ('cell_tags', 'epoch_tags', 'effective_tags'))}
                    if predicate is None or matches(predicate, current):
                        selected.append(row)
            rows = selected
        return sorted(rows, key=lambda row: (row['date'], row['start_time'], row['epoch_uuid']))

    @staticmethod
    def _counts(rows):
        return {'cells': len({r['cell_uuid'] for r in rows}), 'epochs': len(rows),
                'reviewed': sum(bool(r['curation']['reviewed']) for r in rows),
                'included': sum(bool(r['curation']['included']) for r in rows),
                'duration_seconds': sum(r['duration_seconds'] for r in rows)}

    def _cell_summary(self, rows):
        bins = {}
        for row in rows:
            bins.setdefault(row['cell_uuid'], []).append(row)
        result = []
        memberships = {key: {member['uuid'] for member in self.query_result(key)['epochs']} for key in self.protocols}
        for identity, items in bins.items():
            epoch_ids = {row['epoch_uuid'] for row in items}
            result.append({**self.cells[identity], 'epochs': len(items),
                'duration_seconds': sum(r['duration_seconds'] for r in items),
                'reviewed': sum(bool(r['curation']['reviewed']) for r in items),
                'included': sum(bool(r['curation']['included']) for r in items),
                'protocol_uuids': [key for key, membership in memberships.items() if membership & epoch_ids],
                'group_labels': sorted({r['group_label'] for r in items}, key=str)})
        return sorted(result, key=lambda c: (c['cell_type'] or '', c['date'], c['label']))

    def overview(self):
        self._ready()
        curation = self._curation()
        rows = [self._decorate(row, curation) for row in self.rows.values()]
        protocols = []
        for key, value in self.protocols.items():
            definition = value['definition']
            members = self.filtered_rows(key)
            query = self.query_result(key)
            protocols.append({'protocol_uuid': key, 'name': definition['name'],
                'acquisition_protocol': value['result']['protocol_name'], 'counts': self._counts(members),
                'query': query.get('effective_query', definition['query']), 'starter_query': definition['query'],
                'binding': query.get('dataset_binding'), 'view': query.get('effective_view', definition.get('view', {}))})
        active_rows = self._tree_rows(None)
        active_counts = {'cells': len({row['cell_uuid'] for row in active_rows}), 'epochs': len(active_rows),
                         'sources': len(self.source_scope()['active_source_revisions'])}
        return {'active_source_counts': active_counts, 'source_scope': self.source_scope(),
                'project': self.project, 'catalog': {k: v for k, v in self.config.items() if k != 'connection'},
                'counts': {**self._counts(rows), 'protocols': len(protocols), 'sources': len(self.sources)},
                'protocols': protocols, 'cells': self._cell_summary(rows), 'sources': self.sources,
                'events': self.events(25)}

    def protocol(self, protocol_uuid, filters=None):
        rows = self.filtered_rows(protocol_uuid, filters)
        all_rows = self.filtered_rows(protocol_uuid)
        query = self.query_result(protocol_uuid)
        definition = self.protocols[_uuid(protocol_uuid)]['definition']
        return {'definition': definition, 'starter_query': definition['query'],
                'effective_query': query.get('effective_query', definition['query']),
                'binding': query.get('dataset_binding'),
                'counts': self._counts(rows), 'cells': self._cell_summary(rows),
                'groups': sorted({r['group_label'] for r in all_rows}, key=str),
                'filters': validate_filters(filters)}

    def epoch_page(self, protocol_uuid, filters=None, offset=0, limit=100, anchor_uuid=None, *, include_curation=True, include_cells=False):
        if isinstance(offset, bool) or isinstance(limit, bool) or not isinstance(offset, int) or not isinstance(limit, int) or offset < 0 or not 1 <= limit <= 250:
            raise ValueError('Epoch page requires nonnegative offset and limit 1–250')
        if type(include_curation) is not bool or type(include_cells) is not bool:
            raise ValueError('Epoch page projection options must be boolean')
        identities,shared_generation = self._epoch_page_identities(protocol_uuid, filters)
        anchor_index = None
        if anchor_uuid is not None:
            identity = _uuid(anchor_uuid)
            try:
                anchor_index = identities.index(identity)
            except ValueError:
                raise ValueError('Focused epoch is outside this protocol and filter scope')
            offset = anchor_index // limit * limit
        shown = identities[offset:offset + limit]
        provider = self.curation_provider
        curation = provider(_uuid(protocol_uuid), {key:self._fingerprints[key] for key in shown}) if include_curation and provider and shown else {}
        rows = [self._decorate(self.rows[key], curation) for key in shown]
        result={'total': len(identities), 'offset': offset, 'limit': limit, 'epochs': rows,
                **({'_shared_annotation_generation':shared_generation} if shared_generation is not None else {}),
                **({'anchor_index': anchor_index, 'anchor_uuid': identity} if anchor_index is not None else {})}
        if include_cells:
            counts={}
            for identity in identities:
                cell=self.rows[identity]['cell_uuid']
                counts[cell]=counts.get(cell,0)+1
            result['cells']=sorted(({**self.cells[cell],'epochs':count} for cell,count in counts.items()),
                key=lambda row:(row['cell_type'] or '',row['date'],row['label']))
        return result

    def _epoch_page_identities(self, protocol_uuid, filters=None):
        """Order raw membership once; read current curation only after slicing.

        Frozen binding headers are safe cache keys because saved recipes are
        immutable. Unbound/provider-only memberships are compared explicitly to
        detect in-place changes. Shared-tag membership is always read live.
        """
        self._ready()
        protocol_uuid = _uuid(protocol_uuid)
        protocol = self.protocols[protocol_uuid]
        filters = validate_filters(filters)
        tag_filters = {key:value for key,value in filters.items() if key in {'tag','tagged','tag_predicate'}}
        ordinary = {key:value for key,value in filters.items() if key not in tag_filters}
        header_provider = getattr(self, 'binding_header_provider', None)
        binding = None if header_provider else self.binding(protocol_uuid)
        header = header_provider(protocol_uuid) if header_provider else binding
        if header is None and protocol['definition'].get('initial_revision_uuid'):
            raise ValueError('Pinned protocol creation was interrupted. Retry creating it from the same saved selection and name.')
        members = (binding['recipe']['epochs'] if binding else protocol['result']['epochs'])
        signature = None if header_provider and header is not None else tuple(member['uuid'] for member in members)
        key = (protocol_uuid, header and header['version'], header and header.get('revision_uuid'), tuple(sorted(ordinary.items())))
        from workspace_disk_index import DiskMetadataIndex
        index = getattr(self, 'disk_index', None)
        cache = None
        overhead = sys.getsizeof(self._fingerprints) + 16 * 1024
        if isinstance(index, DiskMetadataIndex):
            index._check()
            generation = (id(index),index.generation,id(self.rows),id(self.protocols),id(self._fingerprints))
            previous = getattr(self, '_epoch_page_cache', None)
            if overhead < EPOCH_PAGE_CACHE_BYTES:
                if previous is None or previous[0] != generation or previous[2] != self._fingerprints:
                    previous = self._epoch_page_cache = (generation,{},dict(self._fingerprints))
                cache = previous[1]
            else:
                self._epoch_page_cache = None
        entry = cache.get(key) if cache is not None else None
        if entry is not None and (signature is None or signature == entry[0]):
            cache.pop(key)
            cache[key] = entry
            identities = entry[1]
        else:
            if cache is not None:
                cache.pop(key,None)
            if header_provider and header is not None:
                # Re-read the binding together with its recipe on a cold scope.
                # A concurrent bind may have changed since the header lookup.
                binding = self.binding(protocol_uuid)
                if binding is None and protocol['definition'].get('initial_revision_uuid'):
                    raise ValueError('Pinned protocol creation was interrupted. Retry creating it from the same saved selection and name.')
                members = binding['recipe']['epochs'] if binding else protocol['result']['epochs']
                key = (protocol_uuid, binding and binding['version'], binding and binding.get('revision_uuid'), tuple(sorted(ordinary.items())))
            signature = tuple(member['uuid'] for member in members)
            if binding is not None and set(signature) - self.rows.keys():
                raise ValueError('Bound dataset contains unavailable epochs; explicit reconciliation is required')
            rows = self._filter_rows([self.rows[identity] for identity in signature], ordinary)
            identities = tuple(row['epoch_uuid'] for row in rows)
            if cache is not None:
                # Only UUID tuples are retained. Conservatively count their
                # strings twice even if borrowed/shared, keeping admission cheap.
                size = sum(sys.getsizeof(values) + sum(sys.getsizeof(value) for value in values)
                           for values in (signature,identities))
                if size + overhead <= EPOCH_PAGE_CACHE_BYTES:
                    cache.pop(key,None)
                    cache[key] = (signature,identities,size)
                    while len(cache) > 8 or overhead + sum(item[2] for item in cache.values()) > EPOCH_PAGE_CACHE_BYTES:
                        cache.pop(next(iter(cache)))
        if tag_filters:
            rows = [self.rows[identity] for identity in identities]
            shared = getattr(self, 'shared_annotations', None)
            indexed = shared.filter_epoch_ids(rows,tag_filters) if hasattr(shared,'filter_epoch_ids') else None
            if indexed is not None:
                return indexed
            rows = self._filter_rows(rows, tag_filters)
            identities = tuple(row['epoch_uuid'] for row in rows)
        return identities,None

    def _remember_tree_catalog(self, key, result):
        cache = self._tree_catalog_cache
        cache.pop(key, None)
        cache[key] = result
        registered = getattr(self, '_registered_tree_cache', None)
        shared = registered[1] if registered else None
        def weight(entry):
            return 0 if entry is shared else len(entry[1]) * len(entry[0]['fields'])
        total = sum(weight(entry) for entry in cache.values())
        while len(cache) > TREE_CACHE_MAX_SCOPES or total > TREE_CACHE_VALUE_BUDGET:
            oldest = next((identity for identity in cache if identity != key), None)
            if oldest is None:
                break  # The currently requested single scope may exceed budget.
            total -= weight(cache.pop(oldest))
        return result

    def _tree_fields(self, protocol_uuid, filters=None):
        self._ready()
        protocol_uuid = _uuid(protocol_uuid) if protocol_uuid is not None else None
        filters = validate_filters(filters)
        cache = getattr(self, '_tree_catalog_cache', None)
        if cache is None:
            cache = self._tree_catalog_cache = {}
        binding = self.binding(protocol_uuid) if protocol_uuid else None
        scope = self.source_scope() if protocol_uuid is None else None
        scope_revision = scope['revision'] if scope else None
        shared = getattr(self, 'shared_annotations', None)
        uses_tags=shared and any(key in filters for key in ('tag', 'tagged', 'tag_predicate'))
        tag_generation=shared.generation_token() if uses_tags and hasattr(shared,'generation_token') else None
        tag_revision=tag_generation if tag_generation is not None else shared.snapshot()['revision'] if uses_tags else None
        key = (protocol_uuid, binding['version'] if binding else 0, scope_revision, tuple(sorted(filters.items())), tag_revision)
        if key in cache:
            result = cache.pop(key)
            cache[key] = result  # Most recently used, without recomputation.
            return result
        if protocol_uuid is None and not filters and not scope['excluded_source_revisions']:
            result = self._registered_tree_fields()
        else:
            known = (self._tree_fields(protocol_uuid)[0]['fields'] if filters else
                     self._registered_tree_fields()[0]['fields'] if binding or protocol_uuid is None else None)
            rows = self._tree_rows(protocol_uuid, filters)
            index = getattr(self, 'disk_index', None)
            if index:
                ids = [row['epoch_uuid'] for row in rows]
                result = index.catalog(ids=ids, known_fields=known), index.values(ids=ids)
            else:
                result = tree_catalog(rows, self.details, known, sources=self.sources)
        if tag_generation is not None and shared.generation_token()!=tag_generation:
            from workspace_shared_tag_index import SharedTagsChanged
            raise SharedTagsChanged('Shared tags changed while loading this tree. Refresh and try again.')
        return self._remember_tree_catalog(key, result)

    def tree_fields(self, protocol_uuid, filters=None, *, splits=None):
        catalog, values = self._tree_fields(protocol_uuid, filters)
        if splits is not None:
            order = parse_splits(splits, {field['id'] for field in catalog['fields']})
            catalog, _ = materialize_combinations(catalog, values, order)
        return catalog

    def metadata_fields(self):
        """Registered field definitions for inspecting one epoch's metadata.

        The sealed index stores its complete catalog at publication, so this
        projection never materializes filtered epoch values or saved decisions.
        """
        self._ready()
        index=getattr(self,'disk_index',None)
        if index is not None:
            index._check()
            catalog=index.catalog()
        else:
            catalog=self._registered_tree_fields()[0]
        names=('id','label','category','path','components','grouping_role','grouping_priority','grouping_hint')
        return {'fields':[{key:copy.deepcopy(field[key]) for key in names if key in field}
            for field in catalog['fields']]}

    def _tree_rows(self, protocol_uuid, filters=None):
        if protocol_uuid is not None:
            return self.filtered_rows(protocol_uuid, filters)
        self._ready()
        filters = validate_filters(filters)
        active = set(self.source_scope()['active_source_revisions'])
        return self._filter_rows([row for row in self.rows.values() if row['source_sha256'] in active], filters)

    def validate_tree_splits(self, protocol_uuid, splits):
        fields = self.tree_fields(protocol_uuid)['fields']
        return parse_splits(splits, {field['id'] for field in fields})

    def tree(self, protocol_uuid, filters=None, splits='date, cell, block'):
        rows = self._tree_rows(protocol_uuid, filters)
        catalog, values = self._tree_fields(protocol_uuid, filters)
        return self._render_tree(rows, catalog, values, splits)

    def predicate_fields(self):
        self._ready()
        scope = self.source_scope()
        cached = getattr(self, '_predicate_catalog_cache', None)
        index = getattr(self, 'disk_index', None)
        if index:
            if cached is None or cached[0] != scope['revision']:
                registered = index.predicate_catalog()
                ids = None if not scope['excluded_source_revisions'] else [row['epoch_uuid'] for row in self._tree_rows(None)]
                data = index.predicate_catalog(ids=ids)
                types = {field['id']: field['types'] for field in registered['fields']}
                data['fields'] = [field for field in data['fields'] if not field['id'].startswith('joint/')]
                for field in data['fields']:
                    field['active_types'], field['types'], field['types_scope'] = field['types'], types[field['id']], 'registered_sources'
                cached = self._predicate_catalog_cache = (scope['revision'], data)
            return self._with_annotation_fields({**cached[1], 'source_scope': scope, 'total_catalog': len(self.rows)})
        if cached is None or cached[0] != scope['revision']:
            active = self._tree_fields(None)
            registered = self._registered_tree_fields()
            registered_catalog, registered_values = predicate_scope(*registered)
            if getattr(self, '_registered_predicate_cache', None) is None:
                self._registered_predicate_cache = predicate_catalog(registered_catalog, registered_values)
            schema = {field['id']: field for field in self._registered_predicate_cache['fields']}
            if active is registered:
                data = copy.deepcopy(self._registered_predicate_cache)
            else:
                catalog, values = predicate_scope(*active)
                data = predicate_catalog(catalog, values)
            for field in data['fields']:
                field['active_types'] = field['types']
                field['types'] = schema[field['id']]['types']
                field['types_scope'] = 'registered_sources'
            cached = self._predicate_catalog_cache = (scope['revision'], data)
        return self._with_annotation_fields({**cached[1], 'source_scope': scope, 'total_catalog': len(self.rows)})

    def explore_preview(self, predicate, splits='date,protocol,cell', *, include_tree=True, include_catalog_summary=True):
        if type(include_catalog_summary) is not bool or (include_tree and not include_catalog_summary):
            raise ValueError('A rendered tree requires catalog summaries; include_catalog_summary must be boolean')
        scope = self.source_scope()
        eligible = [row['epoch_uuid'] for row in self._tree_rows(None)]
        validated, identities, annotation_scope = self.match_predicate(predicate, eligible)
        index = getattr(self, 'disk_index', None)
        if not include_catalog_summary:
            # Search-result navigation needs field identities, exact frozen
            # membership and a revision, not every field's scoped statistics.
            # Never label global counts or suggestions as matched-scope data.
            registered = index.catalog() if index else self._registered_tree_fields()[0]
            fields = [{key: field[key] for key in ('id', 'label', 'category', 'path', 'components') if key in field}
                      for field in registered['fields']]
            definitions = {field['id']: field for field in fields}
            order = parse_splits(splits, definitions)
            from workspace_tree import joint_definition
            fields.extend(joint_definition(field, definitions) for field in order if field not in definitions)
            rows = [self.rows[key] for key in identities]
            scoped_catalog = {'fields': fields, 'total': len(rows), 'summary_available': False}
            scoped_values = None
            total_source = len(eligible)
        elif index:
            rows = [self.rows[key] for key in identities]
            scoped_catalog = index.catalog(ids=identities, known_fields=index.catalog()['fields'])
            scoped_values = index.values(ids=identities)
            total_source = len(eligible)
        else:
            catalog, values = self._tree_fields(None)
            rows = [self.rows[key] for key in identities]
            scoped_catalog, scoped_values = tree_catalog(rows, self.details, catalog['fields'], sources=self.sources)
            total_source = len(values)
        order = parse_splits(splits, {field['id'] for field in scoped_catalog['fields']})
        if include_catalog_summary:
            scoped_catalog, scoped_values = materialize_combinations(scoped_catalog, scoped_values, order)
        tree = self._render_tree(rows, scoped_catalog, scoped_values, splits) if include_tree else {
            'count': len(rows), 'split_order': order, 'matlab_command': matlab_tree_command(order)}
        from workspace_tree_pages import selection_revision
        return {'predicate': validated, 'splits': splits, 'tree': tree, 'catalog': scoped_catalog,
                **({'catalog_summary': False} if not include_catalog_summary else {}),
                'tree_revision': selection_revision(self, None, validated, {}, order, rows, annotation_scope=annotation_scope),
                'total_source': total_source, 'total_catalog': len(self.rows), 'matched_count': len(rows),
                'source_scope': scope, 'source_revisions': scope['active_source_revisions'],
                'metadata_fingerprint_version': 2,
                **({'annotation_scope': annotation_scope} if annotation_scope else {}),
                'membership': [{'uuid': key, 'metadata_hash': self._fingerprints[key]} for key in sorted(identities)]}

    def _render_tree(self, rows, catalog, values, splits):
        definitions = {field['id']: field for field in catalog['fields']}
        order = parse_splits(splits, definitions)
        catalog, values = materialize_combinations(catalog, values, order)
        definitions = {field['id']: field for field in catalog['fields']}
        result = build_tree(rows, splits, values, definitions)
        levels = [{'field': field, 'label': definitions[field]['label'], 'groups': 0,
                   'missing_epochs': 0, **({'components': definitions[field]['components']} if 'components' in definitions[field] else {})} for field in order]
        labels = {}
        block_times = {}
        for row in rows:
            cell_date = getattr(self, 'cells', {}).get(row['cell_uuid'], {}).get('date') or row['date']
            labels[row['cell_uuid']] = f"{cell_date} · {row['cell_label']}"
            labels[row['group_uuid']] = row['group_label'] or 'Unlabeled group'
            block_time = row.get('block_start_time')
            block_times[row['block_uuid']] = block_time
            labels[row['block_uuid']] = f"Block · {block_time}" if block_time else 'Block · time not recorded'
        def display_component(field, part):
            value = part.get('value')
            if part['present'] and value is not None:
                if field in {'cell','group','block'}:
                    return labels.get(value,str(value))
                if field in {'date','block time','cell type','group label'}:
                    return str(value)
            return component_display(field,value,not part['present'])

        def annotate(node, depth=0, parent_field=None):
            if 'value' in node:
                value = node['value']
                if parent_field and definitions[parent_field].get('components'):
                    components = definitions[parent_field]['components']
                    node['components'] = [{'field':field, 'label':definitions[field]['label'],
                        'value':part.get('value'), 'missing':not part['present'],
                        'display_value':display_component(field,part)}
                        for field,part in zip(components,value)]
                    node['has_missing_components'] = any(part['missing'] for part in node['components'])
                    node['label'] = ' · '.join(part['label'] + ': ' + part['display_value'] for part in node['components'])
                elif node.get('missing'):
                    node['label'] = 'Not recorded'
                elif parent_field in {'cell', 'group', 'block'}:
                    node['label'] = labels.get(value, value)
                elif catalog.get('protocol_family') == 'history-noise' and parent_field == 'parameters/isControl' and type(value) in (int, float) and value in (0, 1):
                    node['label'] = '1 · Target-only control' if value == 1 else '0 · History sequence'
                elif catalog.get('protocol_family') == 'history-noise' and parent_field in {'parameters/history1', 'parameters/history2', 'parameters/target'} and isinstance(value, list) and len(value) == 2 and all(type(part) in (int, float) for part in value):
                    node['label'] = f'Mean {value_label(value[0])} · SD {value_label(value[1])}'
                elif parent_field == 'protocol' and isinstance(value, str):
                    # Keep the original class identifier as value; the visible
                    # label need not expose its Python/Java package namespace.
                    node['label'] = field_label(value.rsplit('.', 1)[-1]).replace('cur inject', 'current injection')
                elif parent_field in {'date', 'block time', 'cell type', 'group label', 'protocol'}:
                    node['label'] = str(value) if value is not None else 'Not recorded'
                else:
                    node['label'] = 'null (recorded)' if value is None else value_label(value)
                if parent_field == 'block' and value in block_times:
                    node['start_time'] = block_times[node['value']]
            if 'field' in node:
                node['field_label'] = definitions[node['field']]['label']
                levels[depth]['groups'] += len(node.get('children', []))
                levels[depth]['missing_epochs'] += sum(child['count'] for child in node.get('children', []) if child.get('missing') or (definitions[node['field']].get('components') and any(not part['present'] for part in child['value'])))
            for child in node.get('children', []):
                annotate(child, depth + 1, node.get('field'))
            if node.get('field') == 'block':
                node['children'].sort(key=lambda child: (
                    _date(child['start_time']) + child['start_time'][11:] if child.get('start_time') else '',
                    str(child.get('value'))))
            if 'epoch_uuids' in node:
                identities = sorted(node['epoch_uuids'], key=lambda key: (
                    self.rows[key]['date'], self.rows[key]['start_time'][11:], key))
                node['epoch_uuids'] = identities
                node['epochs'] = [{'epoch_uuid': key,
                    'label': f"Epoch {self.rows[key]['epoch_number']} · {self.rows[key]['start_time'][11:]}",
                    'start_time': self.rows[key]['start_time'],
                    'cell_uuid': self.rows[key]['cell_uuid'], 'cell_label': self.rows[key]['cell_label'],
                    'date': self.rows[key]['date'], 'block_uuid': self.rows[key]['block_uuid'],
                    'epoch_number': self.rows[key]['epoch_number']} for key in identities]
        annotate(result)
        result['levels'] = levels
        result['split_order'] = order
        result['matlab_command'] = matlab_tree_command(order)
        return result

    def epoch(self, epoch_uuid, protocol_uuid=None):
        self._ready()
        identity = _uuid(epoch_uuid)
        if protocol_uuid and identity not in {m['uuid'] for m in self.query_result(protocol_uuid)['epochs']}:
            raise ValueError('Epoch is outside this protocol query')
        row = self.rows[identity]
        manifest = self.manifests[row['source_sha256']]
        return {**self._decorate(row, self._curation(protocol_uuid)), **self.details[identity],
                'source_filename': Path(manifest['source_path']).name,
                'source_reference': {'sha256': row['source_sha256'], 'path': manifest['source_path']}}

    def trace(self, epoch_uuid, stream_uuid, start=0, count=20000):
        self._ready()
        row = self.rows[_uuid(epoch_uuid)]
        stream = next((s for s in row['streams'] if s['uuid'] == _uuid(stream_uuid)), None)
        if not stream or stream['kind'] != 'responses':
            raise ValueError('Choose a recorded response stream belonging to this epoch')
        manifest = self.manifests[row['source_sha256']]
        path, signature = self._verified_source(manifest)
        return read_response_window(path, signature, row, stream, start, count)

    def events(self, limit=100):
        self._ready()
        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError('Event limit must be 1–1000')
        rows = (self.Event & {'project_uuid': self.project['project_uuid']}).proj(
            'project_uuid', 'occurred_at', 'actor', 'action').fetch(
            as_dict=True, order_by='occurred_at DESC, event_uuid DESC', limit=limit)
        return [{**row, 'occurred_at': row['occurred_at'].replace(tzinfo=dt.timezone.utc).isoformat()} for row in rows]

    def event_page(self, limit=50, offset=0, action=None):
        self._ready()
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
            raise ValueError('Event page requires limit 1–100 and a nonnegative offset')
        restriction = {'project_uuid': self.project['project_uuid']}
        if action is not None:
            if not isinstance(action, str) or not action or len(action) > 63:
                raise ValueError('Invalid action filter')
            restriction['action'] = action
        relation = self.Event & restriction
        summaries = relation.proj('project_uuid', 'occurred_at', 'actor', 'action').fetch(as_dict=True,
            order_by='occurred_at DESC, event_uuid DESC', limit=limit + 1, offset=offset)
        page = summaries[:limit]
        details = ((relation & [{'event_uuid': row['event_uuid']} for row in page]).fetch(as_dict=True)
                   if page else [])
        by_identity = {row['event_uuid']: row for row in details}
        rows = [by_identity[row['event_uuid']] for row in page]
        return {'events': [{**row, 'occurred_at': row['occurred_at'].replace(
            tzinfo=dt.timezone.utc).isoformat()} for row in rows],
            'offset': offset, 'limit': limit, 'has_more': len(summaries) > limit}

    def event_detail(self, event_uuid):
        self._ready()
        rows = (self.Event & {'project_uuid': self.project['project_uuid'],
                             'event_uuid': _uuid(event_uuid)}).fetch(as_dict=True)
        if not rows:
            raise KeyError('Event not found in this project')
        row = rows[0]
        return {**row, 'occurred_at': row['occurred_at'].replace(tzinfo=dt.timezone.utc).isoformat()}
