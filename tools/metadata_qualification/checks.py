"""Reusable source-truth DTO/facet/cursor checks for a baseline or candidate adapter."""
from truth import canonical, digest, validation_rejections


def qualify(adapter, truth):
    missing = set(truth.fields)-set(adapter.fields)
    if missing: raise AssertionError(f'Incomplete field registry: {sorted(missing)}')
    if set(adapter.fields)!=set(truth.fields):raise AssertionError('Unexpected fields changed native eligibility')
    receipt = dict(status='passed', corpus='small hand-authored native fixture',
                   truth_sha256=truth.sha256, fields=len(truth.fields), checks=0, page_walks=[],
                   integrated_service=False, real_million=False, timings_certify_ui_slo=False)
    scenarios = truth.scenarios()
    scopes = [None, {'cell':truth.values[truth.ids[0]]['cell']},
              {'block':truth.values[truth.ids[0]]['block']},
              {'group':truth.values[truth.ids[0]]['group']},
              [], [truth.ids[2], truth.ids[0], truth.ids[2], 'foreign'], {'block':'empty-block'},
              {'sources':['source-A']}, {'sources':[]},
              {'cell':truth.values[truth.ids[0]]['cell'],'sources':['source-B']},
              {'epoch_ids':[truth.ids[2],truth.ids[0],truth.ids[2],'foreign'],'sources':['source-A']}]
    for scope in scopes:
        for predicate in scenarios:
            expected = truth.membership(predicate, scope)
            if adapter.membership(predicate, scope) != expected:
                raise AssertionError(f'Membership mismatch: {predicate!r}, {scope!r}')
            receipt['checks'] += 1
        # All native fields, a selected subset, and no facets are distinct requested work.
        for fields in (truth.fields, ['parameters/mixed', 'parameters/optional'], []):
            request = dict(scope=scope, facet_fields=fields, limit=3)
            expected = truth.preview(**request)
            actual = adapter.preview(**request)
            if canonical(actual) != canonical(expected):
                raise AssertionError(f'DTO/cursor/facet mismatch: {scope!r}, {fields!r}')
            cursor, seen, pages = None, [], 0
            while True:
                expected = truth.preview(**request, cursor=cursor)
                actual = adapter.preview(**request, cursor=cursor)
                if canonical(actual) != canonical(expected): raise AssertionError('Pagination mismatch')
                seen.extend(r['epoch_uuid'] for r in actual['rows']); pages += 1
                cursor = actual['cursor']
                if cursor is None: break
                if pages > len(truth.ids)+1: raise AssertionError('Cursor failed to advance')
            if seen != truth.membership(scope=scope): raise AssertionError('Lost or repeated page rows')
            receipt['page_walks'].append(dict(scope=scope, fields=len(fields), pages=pages,
                                               ordered_ids_sha256=digest(seen)))
    for identity, detail in truth.fixture()['details'].items():
        if canonical(adapter.detail(identity)) != canonical(detail): raise AssertionError('Full detail mismatch')
        modified = adapter.detail(identity); modified.clear()
        if canonical(adapter.detail(identity)) != canonical(detail): raise AssertionError('Mutable detail cache')
    for predicate,error in validation_rejections():
        for scope in (None, [], {'sources':[]}):
            try:adapter.membership(predicate,scope)
            except ValueError as caught:
                if str(caught)!=error:raise AssertionError(f'Validation error changed: {caught!s}')
            else:raise AssertionError('Invalid predicate accepted')
    receipt['validation_rejections']=len(validation_rejections())*3
    receipt['dto_detail_and_cursor_checked'] = True
    receipt['predicate_scenarios'] = len(scenarios)
    receipt['membership_sha256'] = digest(truth.ids)
    return receipt
