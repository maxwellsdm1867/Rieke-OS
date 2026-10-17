"""Tag-time leaves inside the bounded shared-tag predicate grammar.

A tag-time leaf is an ordinary ``contains`` node on one of three fields whose
value names one exact tag and a half-open UTC window::

    {"field": "annotations/effective/tag_times", "operator": "contains",
     "value": {"tag": "good", "after": "2026-10-01T00:00:00Z"}}

It matches an epoch when some chip in that scope (cell chips inherit) carries
exactly that tag with ``after <= added_at < before``. ``not``/``all``/``any``
compose as usual. Any other operator, unknown key, malformed instant or empty
window is refused. Times compare the stored per-tag added time, including
approximate backfilled times (see disco.decisions.tag_times).
"""
from __future__ import annotations

import datetime as dt

TIME_FIELDS = {
    'annotations/cell/tag_times': ('cell',),
    'annotations/epoch/tag_times': ('epoch',),
    'annotations/effective/tag_times': ('cell', 'epoch'),
}
TIME_LABELS = {
    'annotations/cell/tag_times': 'Cell tag added time',
    'annotations/epoch/tag_times': 'Epoch tag added time',
    'annotations/effective/tag_times': 'Shared tag added time',
}
SCOPES = {'annotations/cell/tag_times': ('cell_tags',), 'annotations/epoch/tag_times': ('epoch_tags',),
          'annotations/effective/tag_times': ('cell_tags', 'epoch_tags')}
# Sample values let the generic validator admit an object ``contains`` value.
SAMPLE = [{'tag': 'example tag', 'added_at': '2026-01-01T00:00:00Z'}]


def parse_instant(value):
    """ISO 8601 text with an explicit UTC offset -> naive UTC datetime."""
    if not isinstance(value, str) or not 10 <= len(value) <= 40:
        raise ValueError('Tag times must be ISO 8601 text with a UTC offset, such as 2026-10-01T00:00:00Z')
    text = value[:-1] + '+00:00' if value.endswith(('Z', 'z')) else value
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as error:
        raise ValueError('Tag times must be ISO 8601 text with a UTC offset, such as 2026-10-01T00:00:00Z') from error
    if parsed.tzinfo is None:
        raise ValueError('Tag times need an explicit UTC offset (for example a trailing Z)')
    return parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)


def condition(value):
    if not isinstance(value, dict) or 'tag' not in value or set(value) - {'tag', 'after', 'before'}:
        raise ValueError('A tag-time rule needs a tag and an after and/or before time')
    from disco.decisions.annotations import text
    result = {'tag': text(value['tag'])}
    for key in ('after', 'before'):
        if key in value:
            result[key] = parse_instant(value[key])
    if 'after' not in result and 'before' not in result:
        raise ValueError('A tag-time rule needs an after and/or before time')
    if 'after' in result and 'before' in result and result['after'] >= result['before']:
        raise ValueError('The tag-time window is empty; choose an after time earlier than the before time')
    return result


def in_window(added_at, value):
    if isinstance(added_at, str):
        try:
            added_at = parse_instant(added_at)
        except ValueError:
            return False
    if not isinstance(added_at, dt.datetime):
        return False
    if added_at.tzinfo is not None:
        added_at = added_at.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return ('after' not in value or added_at >= value['after']) and ('before' not in value or added_at < value['before'])


def _nodes(predicate):
    pending = [predicate]
    while pending:
        node = pending.pop()
        if not isinstance(node, dict):
            continue
        if 'not' in node:
            pending.append(node['not'])
        for logic in ('all', 'any'):
            if isinstance(node.get(logic), list):
                pending.extend(node[logic])
        if 'field' in node:
            yield node


def has_time_fields(predicate):
    return any(node.get('field') in TIME_FIELDS for node in _nodes(predicate))


def check_time_nodes(predicate):
    """Refuse every tag-time node except a well-formed ``contains`` rule."""
    for node in _nodes(predicate):
        if node.get('field') in TIME_FIELDS:
            if node.get('operator') != 'contains':
                raise ValueError('Tag-time fields support only a contains rule with a tag and time window')
            condition(node.get('value'))
    return predicate


def samples(field_ids, default):
    """Generic-validator sample values: object arrays for tag-time fields."""
    return {key: {key: SAMPLE if key in TIME_FIELDS else default} for key in field_ids}


def evaluate(predicate, universe, leaf):
    """Set semantics for all/any/not over a fixed epoch universe."""
    if 'all' in predicate:
        result = set(universe)
        for child in predicate['all']:
            result &= evaluate(child, universe, leaf)
            if not result:
                break
        return result
    if 'any' in predicate:
        result = set()
        for child in predicate['any']:
            result |= evaluate(child, universe, leaf)
        return result
    if 'not' in predicate:
        return set(universe) - evaluate(predicate['not'], universe, leaf)
    return set(leaf(predicate)) & set(universe)


def chip_matches(node, annotation):
    """One tag-time leaf against one epoch's hydrated chips."""
    value = condition(node['value'])
    for scope in SCOPES[node['field']]:
        for chip in (annotation or {}).get(scope, []):
            if chip.get('tag') == value['tag'] and in_window(chip.get('added_at'), value):
                return True
    return False


def matches_with_chips(predicate, current, annotation):
    """Canonical per-epoch evaluation: tag arrays plus hydrated chip times."""
    from disco.navigation.predicates import matches
    if 'all' in predicate:
        return all(matches_with_chips(child, current, annotation) for child in predicate['all'])
    if 'any' in predicate:
        return any(matches_with_chips(child, current, annotation) for child in predicate['any'])
    if 'not' in predicate:
        return not matches_with_chips(predicate['not'], current, annotation)
    if predicate['field'] in TIME_FIELDS:
        return chip_matches(predicate, annotation)
    return matches(predicate, current)
