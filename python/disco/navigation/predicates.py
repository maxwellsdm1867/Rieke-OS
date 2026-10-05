"""Bounded typed predicates over verified metadata; no SQL or expression eval.

Missing keys never match leaf comparisons, including ne/not_in. ``exists``
includes recorded null; ``is_null`` matches only a present null. Unary ``not``
inverts its entire child expression. Numeric values compare numerically, while
booleans, strings and arrays retain distinct types. Ordering is numeric only.
"""
from __future__ import annotations

import copy
import json
import math

OPERATORS = ('eq', 'ne', 'in', 'not_in', 'contains', 'gt', 'gte', 'lt', 'lte', 'exists', 'missing', 'is_null')
UNARY = {'exists', 'missing', 'is_null'}
MAX_DEPTH, MAX_NODES, MAX_CHOICES = 8, 128, 50


def kind(value):
    if value is None:
        return 'null'
    if type(value) is bool:
        return 'boolean'
    if type(value) in (int, float):
        if (type(value) is int and value.bit_length() > 256) or (type(value) is float and not math.isfinite(value)):
            raise ValueError('Predicate numbers must be finite and fit within 256 bits')
        return 'number'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, list):
        return 'array'
    if isinstance(value, dict):
        return 'object'
    raise ValueError('Predicate values must be JSON data')


def literal(value, depth=0):
    if depth > 6:
        raise ValueError('Predicate literal exceeds nesting limit')
    value_type = kind(value)
    if type(value) is int and abs(value) > 2**53 - 1:
        raise ValueError('Predicate integer literals must fit the exact browser JSON range')
    if value_type == 'array':
        if len(value) > 100:
            raise ValueError('Predicate arrays are limited to 100 values')
        for item in value:
            literal(item, depth + 1)
    if value_type == 'object':
        if any(not isinstance(key, str) for key in value):
            raise ValueError('Predicate object keys must be strings')
        for item in value.values():
            literal(item, depth + 1)
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False)) > 4096:
        raise ValueError('Predicate literal exceeds 4096 characters')
    return value_type


def equal(left, right):
    if kind(left) != kind(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(equal(left[key], right[key]) for key in left)
    return left == right


def equality_key(value):
    """Hash key matching equal(): numeric 1/1.0 merge, bool stays distinct.

    Python's numeric hash obeys exact numeric equality, including large ints;
    no float conversion or JSON string formatting is used for numeric identity.
    """
    value_type = kind(value)
    if value_type == 'array':
        return value_type, tuple(equality_key(item) for item in value)
    if value_type == 'object':
        return value_type, frozenset((key, equality_key(item)) for key, item in value.items())
    return value_type, value


def predicate_catalog(catalog, values):
    result = copy.deepcopy(catalog)
    for field in result['fields']:
        buckets, types, indexed = [], set(), {}
        for current in values.values():
            if field['id'] not in current:
                continue
            value = current[field['id']]
            value_type = kind(value)
            types.add(value_type)
            key = equality_key(value)
            found = indexed.get(key)
            if found is not None:
                found['count'] += 1
            elif len(buckets) <= MAX_CHOICES:
                bucket = {'value': copy.deepcopy(value), 'type': value_type, 'count': 1}
                buckets.append(bucket)
                indexed[key] = bucket
        field['types'] = sorted(types)
        field['choices'] = buckets[:MAX_CHOICES]
        field['choices_truncated'] = len(buckets) > MAX_CHOICES
    result['operators'] = list(OPERATORS)
    result['predicate_version'] = 1
    result['limits'] = {'max_depth': MAX_DEPTH, 'max_nodes': MAX_NODES, 'max_choices': MAX_CHOICES}
    return result


def validate(predicate, catalog, values):
    fields = {field['id'] for field in catalog['fields']}
    types = {key: set() for key in fields}
    array_types = {key: set() for key in fields}
    for current in values.values():
        for key, value in current.items():
            if key not in fields:
                continue
            types[key].add(kind(value))
            if isinstance(value, list):
                array_types[key].update(kind(item) for item in value)
    nodes = 0

    def walk(node, depth):
        nonlocal nodes
        nodes += 1
        if depth > MAX_DEPTH or nodes > MAX_NODES:
            raise ValueError('Predicate exceeds the nesting or node limit')
        if not isinstance(node, dict):
            raise ValueError('Each predicate node must be an object')
        if set(node) in ({'all'}, {'any'}):
            key = next(iter(node))
            if not isinstance(node[key], list):
                raise ValueError('All/any predicate groups require an array')
            return {key: [walk(child, depth + 1) for child in node[key]]}
        if set(node) == {'not'}:
            return {'not': walk(node['not'], depth + 1)}
        if set(node) not in ({'field', 'operator'}, {'field', 'operator', 'value'}):
            raise ValueError('Unknown predicate shape or extra fields')
        field, operator = node['field'], node['operator']
        if not isinstance(field, str) or field not in fields:
            raise ValueError('Choose a recorded field from the predicate catalog')
        if not isinstance(operator, str) or operator not in OPERATORS:
            raise ValueError('Unknown predicate operator')
        if operator in UNARY:
            if 'value' in node:
                raise ValueError('Exists/missing/is_null do not accept a comparison value')
            return {'field': field, 'operator': operator}
        if 'value' not in node:
            raise ValueError('This predicate operator requires a value')
        value = node['value']
        value_type = literal(value)
        observed = types[field] - {'null'}
        def compatible(item):
            item_type = kind(item)
            if item_type != 'null' and observed and item_type not in observed:
                raise ValueError('Comparison value type does not match the recorded field')
        if operator in {'in', 'not_in'}:
            if not isinstance(value, list):
                raise ValueError('In/not_in require an array of typed comparison values')
            for item in value:
                compatible(item)
        elif operator in {'gt', 'gte', 'lt', 'lte'}:
            if value_type != 'number' or (observed and 'number' not in observed):
                raise ValueError('Ordered comparisons require a numeric field and numeric value')
        elif operator == 'contains':
            allowed = array_types[field] | ({'string'} if 'string' in observed else set())
            if observed and not observed & {'array', 'string'}:
                raise ValueError('Contains requires a recorded string or array field')
            if allowed and value_type not in allowed:
                raise ValueError('Contains value type does not match recorded text/array elements')
        else:
            compatible(value)
        return {'field': field, 'operator': operator, 'value': copy.deepcopy(value)}

    return walk(predicate, 0)


def matches(predicate, current):
    if 'all' in predicate:
        return all(matches(child, current) for child in predicate['all'])
    if 'any' in predicate:
        return any(matches(child, current) for child in predicate['any'])
    if 'not' in predicate:
        return not matches(predicate['not'], current)
    field, operator = predicate['field'], predicate['operator']
    present = field in current
    if operator == 'exists':
        return present
    if operator == 'missing':
        return not present
    if operator == 'is_null':
        return present and current[field] is None
    if not present:
        return False
    value, target = current[field], predicate['value']
    if operator == 'eq':
        return equal(value, target)
    if operator == 'ne':
        return not equal(value, target)
    if operator in {'in', 'not_in'}:
        included = any(equal(value, item) for item in target)
        return included if operator == 'in' else not included
    if operator == 'contains':
        return (target in value if isinstance(value, str) and isinstance(target, str) else
                any(equal(item, target) for item in value) if isinstance(value, list) else False)
    if kind(value) != 'number':
        return False
    return {'gt': lambda: value > target, 'gte': lambda: value >= target,
            'lt': lambda: value < target, 'lte': lambda: value <= target}[operator]()


def evaluate(predicate, catalog, values):
    validated = validate(predicate, catalog, values)
    return validated, [identity for identity, current in values.items() if matches(validated, current)]
