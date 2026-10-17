"""Per-tag added times for shared annotations.

The ``shared_annotation.tags`` JSON list stays the scientific contract read by
exports, MATLAB exchange and native lookups. ``shared_annotation_tag`` adds one
row per current (target, author, tag) with the time and author revision at
which that tag was added. ``SharedAnnotations._apply_batch_locked`` writes it in
the same transaction as the tags JSON (every writer: single edits, undo, group
commands, external receipts and tag exchange share that primitive). Removing a
tag deletes its row; re-adding records the new commit time.

Readers never trust a time row blindly: a row counts only when its tag is still
present and its ``added_revision`` does not exceed the author's current
revision. Anything else falls back to the annotation row's ``updated_at`` and is
reported as ``approximate``. Raw recordings and acquisition rows are untouched.

``reconcile`` runs once at app bootstrap when a project has annotations but no
time rows (first migration, or after an offline app-state restore cleared them).
It replays ``shared_annotations_updated`` audit events, whose before/after tag
lists and ``occurred_at`` give exact historical times when the per-target
revision chain is contiguous up to the current revision. Underivable times use
the row's ``updated_at`` with ``time_source='approximate'``.
"""
from __future__ import annotations

import datetime as dt
import hashlib

TIME_SOURCES = ('recorded', 'audit_event', 'approximate')
_BATCH = 250


def tag_digest(tag):
    return hashlib.sha256(tag.encode('utf-8')).hexdigest()


def iso_utc(value):
    """Naive UTC datetime -> ISO 8601 text with an explicit Z."""
    if not isinstance(value, dt.datetime):
        return None
    if value.tzinfo is not None:
        value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return value.isoformat() + 'Z'


def _key(row):
    return (row['target_kind'], row['target_uuid'], row['profile_uuid'])


def read_times(store, rows):
    """Valid time rows for the given annotation rows, keyed by (kind,target,profile,tag)."""
    table = getattr(store, 'TagTime', None)
    if table is None or not rows:
        return {}
    wanted = {}
    for row in rows:
        if row.get('tags'):
            wanted.setdefault(row['target_kind'], set()).add(row['target_uuid'])
    result = {}
    base = table & {'project_uuid': store.project_uuid}
    for kind, targets in wanted.items():
        targets = sorted(targets)
        for offset in range(0, len(targets), _BATCH):
            batch = [{'target_uuid': key} for key in targets[offset:offset + _BATCH]]
            for time in (base & {'target_kind': kind} & batch).to_dicts():
                result[(time['target_kind'], time['target_uuid'], time['profile_uuid'], time['tag'])] = time
    return result


def _valid(time, row, tag):
    if time is None:
        return False
    revision = time.get('added_revision')
    return (time.get('tag') == tag and time.get('tag_sha256') == tag_digest(tag)
            and type(revision) is int and 1 <= revision <= row['revision']
            and isinstance(time.get('added_at'), dt.datetime)
            and time.get('time_source') in TIME_SOURCES)


def chip_time(row, tag, times):
    """Chip fields: ``added_at`` (ISO UTC) and ``time_source``."""
    time = (times or {}).get((row['target_kind'], row['target_uuid'], row['profile_uuid'], tag))
    if time is not None and _valid(time, row, tag):
        return {'added_at': iso_utc(time['added_at']), 'time_source': time['time_source']}
    return {'added_at': iso_utc(row.get('updated_at')), 'time_source': 'approximate'}


def time_changes(project_uuid, row, previous, removed, added):
    """Collect the time-row delta for one changed target/author."""
    key = {'project_uuid': project_uuid, 'target_kind': row['target_kind'],
           'target_uuid': row['target_uuid'], 'profile_uuid': row['profile_uuid']}
    old, new = set(previous), set(row['tags'])
    for tag in sorted(old - new):
        removed.append({**key, 'tag_sha256': tag_digest(tag)})
    for tag in sorted(new - old):
        added.append({**key, 'tag_sha256': tag_digest(tag), 'tag': tag, 'added_at': row['updated_at'],
                      'added_revision': row['revision'], 'time_source': 'recorded'})


def write_changes(table, removed, added):
    for offset in range(0, len(removed), _BATCH):
        (table & removed[offset:offset + _BATCH]).delete_quick()
    if added:
        # Replace any stale row left by an out-of-band restore of older tags.
        table.insert(added, replace=True)


def delete_targets(store, targets):
    """Remove time rows for deleted annotation targets (data-store deletion)."""
    table = getattr(store, 'TagTime', None)
    if table is not None and targets:
        for offset in range(0, len(targets), _BATCH):
            (table & targets[offset:offset + _BATCH]).delete_quick()


def _audit_chains(store, wanted):
    """Per-key ordered audit transitions from shared_annotations_updated events."""
    relation = store.Event & {'project_uuid': store.project_uuid, 'action': 'shared_annotations_updated'}
    chains = {}
    offset = 0
    while True:
        page = relation.fetch(as_dict=True, order_by='occurred_at ASC, event_uuid ASC', limit=200, offset=offset)
        if not page:
            break
        offset += len(page)
        for event in page:
            payload = event.get('payload') or {}
            occurred = event.get('occurred_at')
            before = payload.get('before') if isinstance(payload, dict) else None
            after = payload.get('after') if isinstance(payload, dict) else None
            if not isinstance(before, list) or not isinstance(after, list) or len(before) != len(after):
                continue
            if not isinstance(occurred, dt.datetime):
                continue
            for prior, current in zip(before, after):
                try:
                    key = _key(current)
                    if key != _key(prior) or key not in wanted:
                        continue
                    transition = (int(prior['revision']), int(current['revision']),
                                  frozenset(prior['tags']), frozenset(current['tags']), occurred)
                except (KeyError, TypeError, ValueError):
                    continue
                chains.setdefault(key, {})[transition[1]] = transition
    return chains


def derive(row, transitions):
    """Exact add times for current tags along a contiguous revision chain.

    Walk back from the current revision; the newest transition must end in the
    current tag set. A tag added within the contiguous suffix has an exact time;
    a tag already present at the oldest reachable transition has none.
    """
    current = set(row['tags'])
    revision = row['revision']
    chain = []
    while revision > 0:
        step = (transitions or {}).get(revision)
        if step is None or step[0] >= step[1]:
            break
        if not chain and set(step[3]) != current:
            return {}
        chain.append(step)
        revision = step[0]
    result = {}
    for before_revision, after_revision, before, after, occurred in reversed(chain):
        for tag in after - before:
            result[tag] = (occurred, after_revision)
        for tag in before - after:
            result.pop(tag, None)
    return {tag: value for tag, value in result.items() if tag in current}


def reconcile(store, *, force=False):
    """Idempotent bootstrap backfill. Returns counts; never edits tags JSON."""
    from disco.decisions.annotations import tags as validated_tags
    table = getattr(store, 'TagTime', None)
    if table is None:
        return {'status': 'unavailable'}
    project = {'project_uuid': store.project_uuid}
    if not force and (table & project).fetch(as_dict=True, limit=1):
        return {'status': 'current'}
    if not (store.Annotation & project).fetch(as_dict=True, limit=1):
        return {'status': 'empty'}
    with store.lock(), store.dj.conn().transaction:
        rows = (store.Annotation & project).to_dicts()
        existing = {(time['target_kind'], time['target_uuid'], time['profile_uuid'], time['tag']): time
                    for time in (table & project).to_dicts()}
        current, stale, missing = {}, [], []
        for row in rows:
            for tag in validated_tags(row['tags']):
                current[_key(row) + (tag,)] = row
        for key, time in existing.items():
            row = current.get(key)
            if row is None or not _valid(time, row, key[3]):
                stale.append({name: time[name] for name in ('project_uuid', 'target_kind', 'target_uuid',
                                                             'profile_uuid', 'tag_sha256')})
        valid = {key for key, time in existing.items() if key in current and _valid(time, current[key], key[3])}
        missing = [key for key in current if key not in valid]
        counts = {'status': 'reconciled', 'audit_event': 0, 'approximate': 0, 'stale_removed': len(stale)}
        if not missing and not stale:
            return {**counts, 'status': 'current'}
        chains = _audit_chains(store, {key[:3] for key in missing}) if missing else {}
        derived = {}
        inserts = []
        for key in missing:
            row = current[key]
            if key[:3] not in derived:
                derived[key[:3]] = derive(row, chains.get(key[:3]))
            exact = derived[key[:3]].get(key[3])
            updated = row.get('updated_at')
            if exact is not None and (not isinstance(updated, dt.datetime) or exact[0] <= updated + dt.timedelta(seconds=1)):
                added_at, revision, source = exact[0], exact[1], 'audit_event'
            else:
                added_at, revision, source = updated, row['revision'], 'approximate'
            if not isinstance(added_at, dt.datetime):
                raise ValueError('Shared annotation lacks a saved time; tag times cannot be backfilled')
            counts[source] += 1
            inserts.append({**project, 'target_kind': key[0], 'target_uuid': key[1], 'profile_uuid': key[2],
                            'tag_sha256': tag_digest(key[3]), 'tag': key[3],
                            'added_at': added_at.replace(microsecond=0) if added_at.tzinfo is None
                            else added_at.astimezone(dt.timezone.utc).replace(tzinfo=None, microsecond=0),
                            'added_revision': revision, 'time_source': source})
        write_changes(table, stale, inserts)
    return counts


def tag_time_targets(store, tag):
    """Validated (kind, target, added_at) for every current chip with this tag.

    Cached per verified shared-tag generation token; without a token the read
    is always fresh. Rows are checked against the current tags JSON/revision.
    """
    table = getattr(store, 'TagTime', None)
    if table is None:
        return None
    token = store.generation_token()
    cache = getattr(store, '_tag_time_cache', None)
    if token is not None and cache is not None and cache[0] == token and tag in cache[1]:
        return cache[1][tag]
    project = {'project_uuid': store.project_uuid}
    times = (table & project & {'tag_sha256': tag_digest(tag)}).to_dicts()
    keys = sorted({_key(time) for time in times})
    rows = {}
    relation = store.Annotation & project
    for offset in range(0, len(keys), _BATCH):
        batch = [{'target_kind': k, 'target_uuid': t, 'profile_uuid': p} for k, t, p in keys[offset:offset + _BATCH]]
        for row in (relation & batch).to_dicts():
            rows[_key(row)] = row
    result = []
    for time in times:
        row = rows.get(_key(time))
        if row is not None and tag in row['tags'] and _valid(time, row, tag):
            result.append((time['target_kind'], time['target_uuid'], time['added_at']))
    result.sort(key=lambda item: (item[0], item[1], item[2]))
    if token is not None:
        if cache is None or cache[0] != token:
            cache = store._tag_time_cache = (token, {})
        if len(cache[1]) >= 32:
            cache[1].pop(next(iter(cache[1])))
        cache[1][tag] = result
    return result


def filter_with_times(store, rows, filters, predicate):
    """Tag filter whose predicate contains tag-time leaves.

    Ordinary leaves use the existing indexed membership readers; tag-time
    leaves read validated time rows. Opening and closing generation tokens
    must agree, else SharedTagsChanged. Without a verified token (or time
    table) return None so the canonical chip-based reader decides.
    """
    from disco.navigation.tag_time_filter import TIME_FIELDS, condition, in_window, evaluate
    from disco.decisions.shared_tag_index import SharedTagsChanged
    before = store.generation_token()
    if before is None or getattr(store, 'TagTime', None) is None:
        return None
    order = [row['epoch_uuid'] for row in rows]
    universe = set(order)
    if len(universe) != len(order):
        raise ValueError('Expected unique epoch identities in the tag-filter scope')
    cells = {}
    for row in rows:
        saved = store.service.rows.get(row['epoch_uuid'])
        if saved is None or saved['cell_uuid'] != row['cell_uuid']:
            raise ValueError('Epoch/cell identity linkage does not match this project')
        cells.setdefault(row['cell_uuid'], set()).add(row['epoch_uuid'])

    class Fallback(Exception):
        pass

    def plain(extra, node):
        result = store._filter_plain(rows, extra, node)
        if result is None:
            raise Fallback()
        return set(result[0])

    def leaf(node):
        field = node['field']
        if field not in TIME_FIELDS:
            return plain({}, node)
        value = condition(node['value'])
        found = tag_time_targets(store, value['tag'])
        if found is None:
            raise Fallback()
        kinds = TIME_FIELDS[field]
        matched = set()
        for kind, target, added_at in found:
            if kind not in kinds or not in_window(added_at, value):
                continue
            if kind == 'epoch':
                if target in universe:
                    matched.add(target)
            else:
                matched.update(cells.get(target, ()))
        return matched

    try:
        matched = evaluate(predicate, universe, leaf)
        extra = {key: filters[key] for key in ('tag', 'tagged') if key in filters}
        if extra:
            matched &= plain(extra, None)
    except Fallback:
        return None
    if store.generation_token() != before:
        raise SharedTagsChanged('Shared tags changed while filtering; refresh and retry')
    return tuple(key for key in order if key in matched), before
