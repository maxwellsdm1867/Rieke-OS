"""Immutable source-only oracle. Never imports application or optimized code.

Values are frozen in native-truth.json, not decoded from a candidate index.
This bounded development oracle must not materialize the million replay.
"""
import copy
import hashlib
import json
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def kind(value):
    if value is None: return 'null'
    if type(value) is bool: return 'boolean'
    if type(value) in (int, float): return 'number'
    if isinstance(value, str): return 'string'
    if isinstance(value, list): return 'array'
    if isinstance(value, dict): return 'object'
    raise ValueError('Non-JSON native truth')


def equal(left, right):
    if kind(left) != kind(right): return False
    if isinstance(left, list):
        return len(left) == len(right) and all(equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(equal(left[k], right[k]) for k in left)
    return left == right


def matches(node, values):
    """Native semantics, independently implemented; input validation is separate."""
    if node is None: return True
    if 'all' in node: return all(matches(n, values) for n in node['all'])
    if 'any' in node: return any(matches(n, values) for n in node['any'])
    if 'not' in node: return not matches(node['not'], values)
    field, op = node['field'], node['operator']
    present = field in values
    if op == 'exists': return present
    if op == 'missing': return not present
    if op == 'is_null': return present and values[field] is None
    if not present: return False
    value, target = values[field], node['value']
    if op == 'eq': return equal(value, target)
    if op == 'ne': return not equal(value, target)
    if op in ('in', 'not_in'):
        found = any(equal(value, choice) for choice in target)
        return found if op == 'in' else not found
    if op == 'contains':
        if isinstance(value, str): return isinstance(target, str) and target in value
        return isinstance(value, list) and any(equal(item, target) for item in value)
    if kind(value) != 'number': return False
    if op == 'gt': return value > target
    if op == 'gte': return value >= target
    if op == 'lt': return value < target
    if op == 'lte': return value <= target
    raise ValueError('Unsupported oracle operator')


def browser_literal(value):
    if type(value) is int: return abs(value)<=2**53-1
    if isinstance(value, list): return all(browser_literal(v) for v in value)
    if isinstance(value, dict): return all(browser_literal(v) for v in value.values())
    return True


class Truth:
    def __init__(self, path=None):
        path = path or Path(__file__).with_name('native-truth.json')
        raw = Path(path).read_bytes()
        seal = json.loads(Path(path).with_suffix('.seal.json').read_bytes())
        if hashlib.sha256(raw).hexdigest() != seal['sha256']:
            raise ValueError('Frozen truth seal mismatch')
        self._raw = raw
        self.sha256 = seal['sha256']
        data = json.loads(raw)
        if len(data['rows']) > 10000:
            raise ValueError('Use lineage streaming oracle for real-million qualification')
        self._data = data
        self.rows = {r['epoch_uuid']: r for r in data['rows']}
        self.values = data['values']
        self.ids = sorted(self.rows, key=lambda i: (self.rows[i]['date'], self.rows[i]['start_time'], i))
        self.rank = {i: r for r, i in enumerate(self.ids, 1)}

    def fixture(self): return json.loads(self._raw)

    @property
    def fields(self): return sorted({f for v in self.values.values() for f in v})

    def membership(self, predicate=None, scope=None, eligible_sources=None):
        if isinstance(scope, list):
            allowed = set(scope)
            scoped = lambda i: i in allowed
        elif isinstance(scope, dict):
            def scoped(i):
                for field,value in scope.items():
                    if field=='sources':
                        if self.rows[i]['source_sha256'] not in value:return False
                    elif field=='epoch_ids':
                        if i not in value:return False
                    elif field not in self.values[i] or not equal(self.values[i][field],value):return False
                return True
        else: scoped = lambda i: True
        return [i for i in self.ids if scoped(i) and matches(predicate, self.values[i]) and
                (eligible_sources is None or self.rows[i]['source_sha256'] in eligible_sources)]

    def facets(self, ids, fields):
        result = {}
        for field in fields:
            buckets, present = [], 0
            for identity in ids:
                if field not in self.values[identity]: continue
                present += 1
                value = self.values[identity][field]
                bucket = next((b for b in buckets if equal(b['value'], value)), None)
                if bucket is None:
                    bucket = dict(value=copy.deepcopy(value), type=kind(value), count=0)
                    buckets.append(bucket)
                bucket['count'] += 1
            result[field] = dict(values=buckets[:60], missing_count=len(ids)-present,
                                 present_count=present, values_truncated=len(buckets)>60)
        return result

    def preview(self, predicate=None, scope=None, facet_fields=(), limit=60, cursor=None):
        ids = self.membership(predicate, scope)
        remaining = [i for i in ids if self.rank[i] > (cursor or 0)]
        page = remaining[:limit]
        return dict(count=len(ids), rows=copy.deepcopy([self.rows[i] for i in page]),
                    cursor=self.rank[page[-1]] if len(remaining)>limit else None,
                    facets=self.facets(ids, facet_fields))

    def scenarios(self):
        unary = [dict(field=f, operator=op) for f in self.fields
                 for op in ('exists', 'missing', 'is_null')]
        leaves = []
        for field in self.fields:
            examples = []
            for v in self.values.values():
                if field in v and not any(equal(v[field], old) for old in examples):
                    examples.append(v[field])
            for value in examples:
                # Native JS/API literals cannot represent integers outside this range.
                if not browser_literal(value): continue
                leaves.extend(dict(field=field, operator=op, value=value) for op in ('eq', 'ne'))
                leaves.extend(dict(field=field, operator=op, value=[value]) for op in ('in', 'not_in'))
                if kind(value) == 'number':
                    leaves.extend(dict(field=field, operator=op, value=value) for op in ('gt','gte','lt','lte'))
                if isinstance(value, str): leaves.append(dict(field=field, operator='contains', value=value[:1]))
                if isinstance(value, list):
                    leaves.extend(dict(field=field, operator='contains', value=item) for item in value if browser_literal(item))
        a = dict(field='parameters/mixed', operator='eq', value=True)
        b = dict(field='parameters/optional', operator='missing')
        return [None, {'all':[]}, {'any':[]}, {'not':{'any':[]}},
                {'all':[a,b]}, {'any':[a,b]}, {'not':{'all':[a,b]}}] + unary + leaves


def validation_rejections():
    return [({'field':'foreign','operator':'eq','value':1},'Choose a recorded field from the predicate catalog'),
            ({'field':'parameters/futureBoolean','operator':'eq','value':1},'Comparison value type does not match the recorded field'),
            ({'field':'parameters/a~1b~0','operator':'eq','value':'1'},'Comparison value type does not match the recorded field'),
            ({'field':'parameters/a~1b~0','operator':'is_null','value':None},'Exists/missing/is_null do not accept a comparison value'),
            ({'field':'parameters/a~1b~0','operator':'gte','value':True},'Ordered comparisons require a numeric field and numeric value'),
            ({'field':'epoch','operator':'eq','value':'x'*4097},'Predicate literal exceeds 4096 characters'),
            ({'field':'parameters/exactBigInteger','operator':'eq','value':639258608779858225},'Predicate integer literals must fit the exact browser JSON range'),
            ({'all':'bad'},'All/any predicate groups require an array')]
