"""Approved async HTTP seam checks; accepts an isolated Flask test client.

Caller controls the worker deterministically (no sleeps). These checks never
connect an application to native SQL. Do not use a live client.
"""
from truth import canonical

GENERATION_KEYS = {'metadata', 'typed', 'source', 'publication'}


def assert_generation_compatible(admitted, contextual):
    """Context may add protocol/annotation witnesses, while admitted base stays equal."""
    for key in GENERATION_KEYS:
        if key not in admitted:raise AssertionError('Missing admitted base witness')
        value=admitted[key]
        if key not in contextual or canonical(value)!=canonical(contextual[key]):
            raise AssertionError('Admitted generation changed or lost a witness')


def assert_registry(payload, expected_fields):
    if not GENERATION_KEYS <= set(payload['generation']): raise AssertionError('Incomplete generation token')
    if payload['summary_available'] is not False: raise AssertionError('Registry must not claim summaries')
    if set(expected_fields)-{f['id'] for f in payload['fields']}: raise AssertionError('Missing registry fields')
    for field in payload['fields']:
        if 'types' not in field or 'operators' not in field: raise AssertionError('Missing field semantics')
        if set(field) & {'choices','missing_count','present_count','values','distinct_count'}:
            raise AssertionError('Registry computed distributions')
    if 'source_scope' not in payload or 'operators' not in payload: raise AssertionError('Missing registry context')


def assert_summary_state(payload, request_id, generation, expected_status, expected=None):
    if payload['request_id'] != request_id: raise AssertionError('Wrong request identity')
    if canonical(payload['generation']) != canonical(generation): raise AssertionError('Wrong generation')
    if payload['status'] != expected_status: raise AssertionError('Wrong summary status')
    if expected_status != 'ready':
        if 'result' in payload: raise AssertionError('Unready state leaked result')
        return
    result = payload['result']
    if result['matched_count'] != expected['count']: raise AssertionError('Wrong matched count')
    if canonical(result['summaries']) != canonical(expected['facets']):
        raise AssertionError('Wrong facets; missing summary must be unavailable, never zero')


def summary_roundtrip(client, request, expected, drive_worker, headers):
    """drive_worker(request_id) completes fixture work before deterministic polling."""
    response = client.post('/api/explore/summaries', json=request, headers=headers)
    if response.status_code != 202: raise AssertionError(f'Expected async acceptance: {response.status_code}')
    pending = response.get_json(); identity, generation = pending['request_id'], pending['generation']
    if 'generation' in request:assert_generation_compatible(request['generation'], generation)
    assert_summary_state(pending, identity, generation, 'pending')
    drive_worker(identity)
    ready = client.get('/api/explore/summaries/'+identity).get_json()
    assert_summary_state(ready, identity, generation, 'ready', expected)
    return ready


def fault_roundtrip(client, request, expected_status, inject_fault, drive_worker, headers):
    response = client.post('/api/explore/summaries', json=request, headers=headers)
    if response.status_code != 202: raise AssertionError('Fault setup did not accept request')
    pending = response.get_json(); identity, generation = pending['request_id'], pending['generation']
    if 'generation' in request:assert_generation_compatible(request['generation'], generation)
    inject_fault(identity)
    drive_worker(identity)
    payload = client.get('/api/explore/summaries/'+identity).get_json()
    assert_summary_state(payload, identity, generation, expected_status)
    return payload


def cursor_refusal(service, predicate, inject_fault, **kwargs):
    """Metadata/source/annotation/publication or query change must refuse stale cursor."""
    page = service.explore_page(predicate, limit=1, **kwargs)
    if page['cursor'] is None: raise AssertionError('Fixture needs at least two matching epochs')
    inject_fault()
    try: service.explore_page(predicate, limit=1, cursor=page['cursor'], **kwargs)
    except ValueError: return
    raise AssertionError('Stale cursor accepted')


def assert_empty_branches(actual, frozen_branches):
    # Complete recorded identity, parent, ordering and parameters; labels alone are insufficient.
    if canonical(actual) != canonical(frozen_branches): raise AssertionError('Empty acquisition branches lost')
