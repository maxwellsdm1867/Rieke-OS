"""Generation-fenced requested aggregates over immutable metadata readers.

One worker and bounded retained responses keep broad aggregates off the native
connection and ordinary navigation lock. No request accepts epoch ID lists.
"""
from __future__ import annotations
import copy
import json
import threading
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass

from workspace_predicates import OPERATORS, equality_key, kind
from workspace_recipes import checksum
from workspace_service import validate_filters
from workspace_tag_predicates import TagPredicates, referenced_fields, annotation_locks
from workspace_tree import predicate_scope

MAX_JOBS = 8
MAX_RESULT_BYTES = 2 * 1024 * 1024


class StaleQuery(ValueError):
    pass


class SummaryCapacity(RuntimeError):
    pass


def query_context(service, body):
    scope = body.get('scope', {})
    if not isinstance(scope, dict) or set(scope) - {'cell_uuid', 'block_uuid', 'group_uuid'}:
        raise ValueError('Scope requires recorded cell_uuid, block_uuid or group_uuid')
    scope = {key: str(uuid.UUID(value)) for key, value in scope.items() if isinstance(value, str)}
    if len(scope) != len(body.get('scope', {})):
        raise ValueError('Scope identities must be UUID strings')
    protocol = body.get('protocol_uuid')
    if protocol is not None:
        if not isinstance(protocol, str):
            raise ValueError('protocol_uuid must be a UUID string')
        protocol = str(uuid.UUID(protocol))
        if protocol not in service.protocols:
            raise ValueError('Protocol workspace is unavailable')
    filters = validate_filters(body.get('filters'))
    return {'predicate': copy.deepcopy(body['predicate']), 'scope': scope,
            'protocol_uuid': protocol, 'filters': filters}


def generation(service, context=None):
    service._ready()
    index = getattr(service, 'disk_index', None)
    if index is not None:
        index._check()
    typed = getattr(service, 'typed_index', None)
    if typed is not None:
        typed._check()
    context = context or {}
    annotation_fields = referenced_fields(context.get('predicate', {}))
    annotation_fields.update(field for field in context.get('summary_fields', [])
                             if field.startswith(('annotations/', 'curation/')))
    tracker = getattr(service, '_explore_state_generation', None)
    if tracker is not None:
        protocols = {field.split('/')[1] for field in annotation_fields if field.startswith('curation/')}
        if context.get('protocol_uuid'):
            protocols.add(context['protocol_uuid'])
        tokens = []
        for protocol in [None, *sorted(protocols)]:
            token = tracker.token(protocol)
            if token is None:
                raise StaleQuery('Annotation generation is unavailable; retry after recovery')
            tokens.append(asdict(token) if is_dataclass(token) else token)
        annotation = checksum(tokens)
    else:
        shared = getattr(service, 'shared_annotations', None)
        shared_revision = shared.change_revision() if shared and hasattr(shared, 'change_revision') else (
            shared.snapshot()['revision'] if shared else None)
        annotation = checksum({'shared': shared_revision,
            'protocols': TagPredicates(service).snapshot(annotation_fields)[1]['revision'] if annotation_fields else None})
    publication = getattr(service, '_explore_publication', None)
    if publication is None:
        publication = service._explore_publication = str(uuid.uuid4())
    header_provider = getattr(service, 'binding_header_provider', None)
    binding_header = (header_provider(context['protocol_uuid']) if header_provider else
                      service.binding(context['protocol_uuid'])) if context.get('protocol_uuid') else None
    return {'metadata': index.generation if index else checksum(service._fingerprints),
            'typed': typed.generation_token if typed else None,
            'source': service.source_scope()['revision'], 'annotation': annotation,
            'publication': publication,
            'binding': checksum(binding_header) if context.get('protocol_uuid') else None}


def typed_policy(service):
    # Share the native reader/binding proof used by structural navigation.
    from workspace_tree_pages import _structural_contract
    return _structural_contract(service)


def field_operators(types):
    observed = set(types) - {'null'}
    return [operator for operator in OPERATORS if
            (operator not in {'gt', 'gte', 'lt', 'lte', 'contains'} or
             operator == 'contains' and (not observed or bool(observed & {'array', 'string'})) or
             operator in {'gt', 'gte', 'lt', 'lte'} and (not observed or 'number' in observed))]


def field_registry(service):
    before = generation(service)
    index = getattr(service, 'disk_index', None)
    typed = getattr(service, 'typed_index', None)
    if typed is not None:
        data = typed.field_registry()
        catalog = index.catalog()
    elif index is not None:
        # Publication already stored the complete native schema/type proof.
        # Reading it never requests scoped distributions.
        data, catalog = index.predicate_catalog(), index.catalog()
    else:
        catalog, values = predicate_scope(*service._registered_tree_fields())
        observed = {field['id']: set() for field in catalog['fields']}
        for current in values.values():
            for key, value in current.items():
                if key in observed:
                    observed[key].add(kind(value))
        data = {'fields': [{**field, 'types': sorted(observed[field['id']])} for field in catalog['fields']]}
    names = ('id', 'label', 'category', 'path', 'components', 'grouping_role',
             'grouping_priority', 'grouping_hint', 'description', 'annotation_scope')
    tree_fields = [{key: copy.deepcopy(field[key]) for key in names if key in field}
                   for field in catalog['fields']]
    hints = {field['id']: field for field in tree_fields}
    fields = []
    for field in data['fields']:
        if field['id'].startswith('joint/'):
            continue
        definition = {**hints.get(field['id'], {}),
            **{key: copy.deepcopy(field[key]) for key in names if key in field},
            'types': list(field.get('types', [])), 'types_scope': 'registered_sources',
            'operators': field_operators(field.get('types', []))}
        fields.append(definition)
    for field in TagPredicates(service).definitions():
        fields.append({**field, 'types': ['array'], 'element_types': ['string'],
                       'types_scope': 'project_annotations', 'operators': field_operators(['array'])})
    if before != generation(service):
        raise StaleQuery('Metadata generation changed while reading field definitions')
    return {'fields': fields, 'tree_fields': tree_fields, 'operators': list(OPERATORS),
            'predicate_version': 1, 'generation': before, 'source_scope': service.source_scope(),
            'summary_available': False}


def _native_rows(service, context):
    rows = service._tree_rows(context['protocol_uuid'], context['filters'])
    return [row for row in rows if all(row.get(key) == value for key, value in context['scope'].items())]


def _native_summaries(service, context, cancelled):
    rows = _native_rows(service, context)
    _, identities, _ = service.match_predicate(context['predicate'], (row['epoch_uuid'] for row in rows))
    catalog, values = predicate_scope(*service._registered_tree_fields())
    definitions = {field['id'] for field in catalog['fields']}
    annotation_fields = {field for field in context['summary_fields'] if field.startswith(('annotations/', 'curation/'))}
    annotations = TagPredicates(service).snapshot(annotation_fields)[0] if annotation_fields else {}
    summaries = {}
    for field in context['summary_fields']:
        if field not in definitions and field not in annotations:
            raise ValueError('Unknown native summary field')
        buckets, present, seen, truncated = [], 0, {}, False
        for identity in identities:
            if cancelled():
                raise InterruptedError('Summary cancelled')
            current = {field: annotations[field].get(identity, [])} if field in annotations else values[identity]
            if field not in current:
                continue
            value = current[field]
            present += 1
            key = equality_key(value)
            bucket = seen.get(key)
            if bucket is None:
                if len(buckets) >= 60:
                    truncated = True
                    continue
                bucket = {'value': copy.deepcopy(value), 'type': kind(value), 'count': 0}
                seen[key] = bucket
                buckets.append(bucket)
            bucket['count'] += 1
        summaries[field] = {'values': buckets[:60], 'present_count': present,
            'missing_count': len(identities) - present, 'values_truncated': truncated}
    return {'matched_count': len(identities), 'summaries': summaries}


@contextmanager
def typed_reader(service):
    owner = getattr(service, 'typed_index', None)
    if owner is None:
        yield None
        return
    # Retaining the published owner pins both derived and native generations.
    reader = owner.clone()
    try:
        yield reader
    finally:
        reader.close()


def typed_scope(service, context):
    scope = {key.removesuffix('_uuid'): value for key, value in context['scope'].items()}
    scope['sources'] = ([source['source_sha256'] for source in service.sources]
                        if context['protocol_uuid'] else service.source_scope()['active_source_revisions'])
    filters = context['filters']
    field_map = {'epoch_uuid': 'epoch', 'cell_uuid': 'cell', 'cell_type': 'cell type', 'group_label': 'group label'}
    predicates = [context['predicate']]
    predicates.extend({'field': field_map[key], 'operator': 'eq', 'value': value}
                      for key, value in filters.items() if key in field_map)
    if context['protocol_uuid'] is not None:
        binding = service.binding(context['protocol_uuid'])
        members = binding['recipe']['epochs'] if binding else service.protocols[context['protocol_uuid']]['result']['epochs']
        scope['epoch_ids'] = (member['uuid'] for member in members)
    return {'all': predicates}, scope


class SummaryJobs:
    def __init__(self, service, db_lock, registration_locks):
        self.service, self.db_lock, self.registration_locks = service, db_lock, registration_locks
        self.lock = threading.RLock()
        self.jobs = OrderedDict()
        self.worker = None
        self.autostart = True

    def drive_worker(self):
        # Deterministic isolated-test seam; no second worker may run concurrently.
        with self.lock:
            if self.worker is not None and self.worker.is_alive():
                raise RuntimeError('A summary worker is already running')
        self._run()

    def _calculate(self, job, reader, predicate, scope, native):
        context = job['context']
        if reader is not None and not native:
            reader.set_cancel_callback(job['cancel'].is_set)
            result = reader.summaries(predicate, scope, facet_fields=context['summary_fields'])
            return {'matched_count': result['count'], 'summaries': result['facets']}
        # Authoritative fallback retains annotation and custom-policy behavior.
        with self.db_lock, self.registration_locks(), annotation_locks(self.service, context['predicate']):
            return _native_summaries(self.service, context, job['cancel'].is_set)

    def submit(self, body):
        context = query_context(self.service, body)
        fields = body['summary_fields']
        if (not isinstance(fields, list) or any(not isinstance(field, str) for field in fields)
                or len(set(fields)) != len(fields)):
            raise ValueError('summary_fields must be an array of unique field IDs')
        context['summary_fields'] = list(fields)
        catalog = field_registry(self.service)
        if set(fields) - {field['id'] for field in catalog['fields']}:
            raise ValueError('Unknown native summary field')
        current = generation(self.service, context)
        # Registry tokens describe metadata/shared annotations. Protocol/tag
        # scope obtains its own full fence here; compare the common witnesses.
        expected = body.get('generation')
        if expected is not None and expected != generation(self.service):
            raise StaleQuery('Metadata generation changed; refresh field definitions')
        with self.lock:
            if sum(job['status'] == 'pending' for job in self.jobs.values()) >= MAX_JOBS:
                raise SummaryCapacity('Too many pending summaries; cancel one before retrying')
            while len(self.jobs) >= MAX_JOBS:
                terminal = next((key for key, job in self.jobs.items() if job['status'] != 'pending' and not job.get('running')), None)
                if terminal is None:
                    raise SummaryCapacity('Too many pending summaries; cancel one before retrying')
                del self.jobs[terminal]
            request_id = str(uuid.uuid4())
            job = {'request_id': request_id, 'status': 'pending', 'generation': current,
                   'summary_fields': fields, 'context': context, 'cancel': threading.Event(), 'running': False}
            self.jobs[request_id] = job
            # Capture the acknowledgement before starting the worker.
            acknowledgement = self._payload(job)
            if self.autostart and (self.worker is None or not self.worker.is_alive()):
                self.worker = threading.Thread(target=self._run, daemon=True, name='metadata-summaries')
                self.worker.start()
            return acknowledgement

    def _fence(self, job):
        with self.db_lock, self.registration_locks():
            try:
                current = generation(self.service, job['context'])
            except Exception as error:
                raise StaleQuery('Published metadata or annotation validation is unavailable: ' + str(error)) from error
            if job['generation'] != current:
                raise StaleQuery('Metadata or annotation generation changed')

    def _run(self):
        while True:
            with self.lock:
                job = next((item for item in self.jobs.values() if item['status'] == 'pending' and not item['running']), None)
                if job is None:
                    self.worker = None
                    return
                job['running'] = True
            try:
                self._fence(job)
                context = job['context']
                native = (not typed_policy(self.service) or referenced_fields(context['predicate']) or
                    any(field.startswith(('annotations/', 'curation/')) for field in context['summary_fields']) or
                    any(key in context['filters'] for key in ('tag', 'tagged', 'tag_predicate')))
                with self.db_lock, self.registration_locks():
                    if job['generation'] != generation(self.service, context):
                        raise StaleQuery('Metadata or annotation generation changed')
                    reader_context = typed_reader(self.service)
                    reader = reader_context.__enter__()
                    predicate, scope = typed_scope(self.service, context) if reader else (None, None)
                try:
                    result = self._calculate(job, reader, predicate, scope, native)
                finally:
                    reader_context.__exit__(None, None, None)
                self._fence(job)
                if len(json.dumps(result, ensure_ascii=False)) > MAX_RESULT_BYTES:
                    raise ValueError('Requested summaries exceed the response budget; request fewer fields')
                with self.lock:
                    if job['status'] == 'pending':
                        job.update(status='ready', result=result)
            except Exception as error:
                with self.lock:
                    if job['status'] == 'pending':
                        job.update(status='cancelled' if job['cancel'].is_set() else
                                   'stale' if isinstance(error, StaleQuery) else 'failed', error=str(error))
            finally:
                with self.lock:
                    job['running'] = False

    @staticmethod
    def _payload(job):
        return copy.deepcopy({key: job[key] for key in
            ('request_id', 'status', 'generation', 'summary_fields', 'result', 'error') if key in job})

    def poll(self, request_id):
        with self.lock:
            job = self.jobs[str(uuid.UUID(request_id))]
        if job['status'] in ('pending', 'ready'):
            try:
                self._fence(job)
            except Exception as error:
                with self.lock:
                    job['cancel'].set()
                    job.pop('result', None)
                    job.update(status='stale', error=str(error))
        with self.lock:
            return self._payload(job)

    def cancel(self, request_id):
        with self.lock:
            job = self.jobs[str(uuid.UUID(request_id))]
            job['cancel'].set()
            job.pop('result', None)
            job.update(status='cancelled')
            return self._payload(job)


def explore_page(service, predicate, *, scope=None, protocol_uuid=None, filters=None, limit=60, cursor=None):
    """Bounded native row DTOs; the public continuation binds query and generation."""
    import base64
    import hashlib
    import hmac
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Page limit must be 1–100')
    context = query_context(service, {'predicate': predicate, 'scope': {} if scope is None else scope,
                                     'protocol_uuid': protocol_uuid, 'filters': filters})
    before = generation(service, context)
    query = checksum(context)
    secret = getattr(service, '_explore_cursor_secret', None)
    if secret is None:
        secret = service._explore_cursor_secret = uuid.uuid4().bytes
    rank, token, membership = None, None, None
    if cursor is not None:
        if not isinstance(cursor, str) or len(cursor) > 4096:
            raise ValueError('Cursor must be a bounded opaque continuation')
        try:
            encoded, signature = cursor.split('.')
            if not hmac.compare_digest(signature, hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()):
                raise ValueError('Cursor signature mismatch')
            token = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
            if token['generation'] != before or token['query'] != query:
                raise StaleQuery('Cursor belongs to a different metadata generation or query')
            rank = token['rank']
            if type(rank) is not int or rank < 1:
                raise ValueError('Invalid cursor rank')
        except StaleQuery:
            raise
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError('Malformed metadata cursor') from error
    native = (not typed_policy(service) or referenced_fields(predicate) or
              any(key in context['filters'] for key in ('tag', 'tagged', 'tag_predicate')))
    with typed_reader(service) as reader:
        if reader is not None and not native:
            combined, typed = typed_scope(service, context)
            result = reader.page(combined, typed, limit=limit, cursor=rank)
        else:
            rows = _native_rows(service, context)
            _, identities, _ = service.match_predicate(predicate, (row['epoch_uuid'] for row in rows))
            members = set(identities)
            rows = sorted((row for row in rows if row['epoch_uuid'] in members),
                          key=lambda row: (row['date'], row['start_time'][11:], row['epoch_uuid']))
            membership = checksum(rows)
            if token is not None and token.get('membership') != membership:
                raise StaleQuery('Authoritative filtered membership changed during paging')
            offset = rank or 0
            result = {'rows': copy.deepcopy(rows[offset:offset+limit]),
                      'cursor': offset+limit if offset+limit < len(rows) else None}
    if before != generation(service, context):
        raise StaleQuery('Metadata or annotation generation changed during the page')
    if result['cursor'] is not None:
        token = {'rank': result['cursor'], 'generation': before, 'query': query, 'membership': membership}
        encoded = base64.urlsafe_b64encode(json.dumps(token, separators=(',', ':')).encode()).decode().rstrip('=')
        result['cursor'] = encoded + '.' + hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()
    return {**result, 'generation': before, 'limit': limit}


def register_explore_query_routes(app, service, db_lock, registration_locks, read_request):
    from flask import jsonify, request
    jobs = SummaryJobs(service, db_lock, registration_locks)
    app.extensions['metadata_summary_jobs'] = jobs

    @app.get('/api/explore/field-registry')
    def explorer_field_registry():
        if request.args:
            raise ValueError('Field registry describes the registered catalog')
        with db_lock, registration_locks():
            return jsonify(field_registry(service))

    @app.post('/api/explore/page')
    def explorer_query_page():
        body = read_request({'predicate', 'protocol_uuid', 'filters', 'scope', 'limit', 'cursor'}, {'predicate'})
        with db_lock, registration_locks(), annotation_locks(service, body['predicate']):
            try:
                return jsonify(explore_page(service, **body))
            except StaleQuery as error:
                return jsonify(status='stale', error=str(error), generation=generation(service)), 409

    @app.post('/api/explore/summaries')
    def explorer_summaries():
        body = read_request({'predicate', 'summary_fields', 'protocol_uuid', 'filters', 'scope', 'generation'}, {'predicate', 'summary_fields'})
        if 'generation' in body and not isinstance(body['generation'], dict):
            raise ValueError('generation must be the field registry token')
        with db_lock, registration_locks():
            try:
                return jsonify(jobs.submit(body)), 202
            except StaleQuery as error:
                return jsonify(status='stale', error=str(error), generation=generation(service)), 409
            except SummaryCapacity as error:
                return jsonify(error=str(error)), 429

    @app.get('/api/explore/summaries/<request_id>')
    def explorer_summary_poll(request_id):
        if request.args:
            raise ValueError('Summary polls do not accept filters')
        return jsonify(jobs.poll(request_id))

    @app.post('/api/explore/summaries/<request_id>/cancel')
    def explorer_summary_cancel(request_id):
        read_request(set(), set())
        return jsonify(jobs.cancel(request_id))
