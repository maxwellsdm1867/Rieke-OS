"""Prepared, immutable tree projection over caller-owned canonical metadata.

This module grants no membership or revision authority. The caller supplies a
validated scope, immutable rows/values and stable scope ranks. Preparation is
allowed to enumerate and sort the complete scope; reads never do so. Membership deltas build
an atomic persistent snapshot and invalidate affected canonical duration sums.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from contextvars import ContextVar
import copy
import sys
from datetime import datetime
from types import MappingProxyType

from disco.workbench.recipes import SPLIT_FIELDS, checksum
from disco.navigation.tree import field_value_order, joint_value, value_key


class _Chronology:
    """Compact comparison key borrowing a row, without retained time substrings."""
    __slots__ = ('row',)

    def __init__(self, row):
        self.row = row

    def _key(self):
        row = self.row
        return row['date'], row['start_time'][11:], row['epoch_uuid']

    def __lt__(self, other):
        return self._key() < other._key()

    def __eq__(self, other):
        return isinstance(other, _Chronology) and self._key() == other._key()

    def __gt__(self, other):
        return self._key() > other._key()


@dataclass(frozen=True, slots=True)
class _Entry:
    row: object
    values: object
    rank: object
    buckets: tuple

    @property
    def scope_key(self):
        row = self.row
        return (row['date'], row['start_time'], row['epoch_uuid']) if self.rank is None else self.rank

    @property
    def chronology(self):
        return _Chronology(self.row)

    @property
    def representative(self):
        return self


@dataclass(frozen=True, slots=True)
class _Map:
    key: object
    value: object
    left: object
    right: object
    height: int
    size: int
    representative: object


def _size(node):
    return node.size if node else 0


def _height(node):
    return node.height if node else 0


_ALLOCATION = ContextVar("prepared_tree_allocations", default=None)


def _make(key, value, left=None, right=None):
    allocation = _ALLOCATION.get()
    if allocation is not None:
        allocation[0] += 256  # Node plus conservative newly retained ordering-key allowance.
    candidates = (getattr(value, 'representative', None),
                  left.representative if left else None, right.representative if right else None)
    representative = min((item for item in candidates if item is not None),
                         key=lambda item: item.scope_key, default=None)
    return _Map(key, value, left, right, 1 + max(_height(left), _height(right)),
                1 + _size(left) + _size(right), representative)


def _balance(node):
    delta = _height(node.left) - _height(node.right)
    if delta > 1:
        child = node.left
        if _height(child.left) < _height(child.right):
            pivot = child.right
            child = _make(pivot.key, pivot.value,
                          _make(child.key, child.value, child.left, pivot.left), pivot.right)
        return _make(child.key, child.value, child.left,
                     _make(node.key, node.value, child.right, node.right))
    if delta < -1:
        child = node.right
        if _height(child.right) < _height(child.left):
            pivot = child.left
            child = _make(pivot.key, pivot.value, pivot.left,
                          _make(child.key, child.value, pivot.right, child.right))
        return _make(child.key, child.value,
                     _make(node.key, node.value, node.left, child.left), child.right)
    return node


def _get(node, key, default=None):
    while node:
        if key == node.key:
            return node.value
        node = node.left if key < node.key else node.right
    return default


def _set(node, key, value):
    if node is None:
        return _make(key, value)
    if key == node.key:
        return _make(key, value, node.left, node.right)
    if key < node.key:
        return _balance(_make(node.key, node.value, _set(node.left, key, value), node.right))
    return _balance(_make(node.key, node.value, node.left, _set(node.right, key, value)))


def _delete(node, key):
    if node is None:
        raise KeyError(key)
    if key < node.key:
        return _balance(_make(node.key, node.value, _delete(node.left, key), node.right))
    if key > node.key:
        return _balance(_make(node.key, node.value, node.left, _delete(node.right, key)))
    if node.left is None:
        return node.right
    if node.right is None:
        return node.left
    successor = node.right
    while successor.left:
        successor = successor.left
    return _balance(_make(successor.key, successor.value, node.left,
                          _delete(node.right, successor.key)))


def _rank(node, key):
    result = 0
    while node:
        if key == node.key:
            return result + _size(node.left)
        if key < node.key:
            node = node.left
        else:
            result += 1 + _size(node.left)
            node = node.right
    raise KeyError(key)


def _window(node, offset, limit):
    """In-order range, pruning whole subtrees: O(log N + returned values)."""
    if node is None or limit <= 0 or offset >= node.size:
        return
    left = _size(node.left)
    if offset < left:
        amount = min(limit, left - offset)
        yield from _window(node.left, offset, amount)
        limit -= amount
        offset = left
    if offset == left and limit:
        yield node.value
        limit -= 1
        offset += 1
    if limit:
        yield from _window(node.right, max(0, offset - left - 1), limit)


def _bulk(items):
    """Build a balanced map from sorted unique (key, value) pairs without slices."""
    def build(first, last):
        if first == last:
            return None
        middle = (first + last) // 2
        key, value = items[middle]
        return _make(key, value, build(first, middle), build(middle + 1, last))
    return build(0, len(items))


_ABSENT = object()


class _Entries:
    """Immutable base UUID map plus persistent bounded-update overlay."""
    __slots__ = ('base', 'changes', 'count', 'base_bytes')

    def __init__(self, base, changes=None, count=None, base_bytes=None):
        self.base = MappingProxyType(base) if isinstance(base, dict) else base
        self.changes = changes
        self.count = len(base) if count is None else count
        self.base_bytes = sys.getsizeof(base) if base_bytes is None else base_bytes

    def get(self, identity):
        changed = _get(self.changes, identity, _ABSENT)
        return self.base.get(identity) if changed is _ABSENT else changed

    def change(self, identity, entry):
        before = self.get(identity)
        return _Entries(self.base, _set(self.changes, identity, entry),
                        self.count + int(entry is not None) - int(before is not None), self.base_bytes)

    def values(self):
        for identity, entry in self.base.items():
            if _get(self.changes, identity, _ABSENT) is _ABSENT:
                yield entry
        for entry in _window(self.changes, 0, _size(self.changes)):
            if entry is not None:
                yield entry


@dataclass(frozen=True, slots=True)
class _Group:
    depth: int
    key: str | None = None
    value: object = None
    missing: bool = False
    children: object = None
    lookup: object = None
    leaves: object = None
    cells: object = None
    count: int = 0
    duration: object = 0
    pending: bool = False

    @property
    def representative(self):
        contents = self.children if self.children else self.leaves
        return contents.representative if contents else None


def _order(group, field):
    if group.missing:
        primary = (1,)
    elif field == 'block':
        stamp = group.representative.row.get('block_start_time')
        date = ''
        if stamp:
            for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
                try:
                    date = datetime.strptime(str(stamp)[:10], fmt).date().isoformat()
                    break
                except ValueError:
                    pass
            else:
                raise ValueError('Unrecognized source timestamp')
        primary = (0, date + stamp[11:] if stamp else '', str(group.value))
    else:
        primary = (0, field_value_order(field, group.value, canonical=value_key(group.value)))
    # Python's legacy stable sort breaks equal ordering keys by first occurrence.
    return primary, group.representative.scope_key


def _summary(group, counts_only):
    result = {'count': group.count}
    if not counts_only:
        result.update(cells=_size(group.cells), duration_seconds=None if group.pending else group.duration,
                      duration_status='pending' if group.pending else 'ready')
    return result


def _estimate(*roots):
    """Conservative retained Python structure bytes; borrowed rows are excluded."""
    seen, pending, total = set(), list(roots), 0
    while pending:
        value = pending.pop()
        if value is None or id(value) in seen:
            continue
        seen.add(id(value))
        total += sys.getsizeof(value)
        if isinstance(value, _Map):
            pending.extend((value.key, value.value, value.left, value.right))
        elif isinstance(value, _Group):
            pending.extend((value.key, value.value, value.children, value.lookup, value.leaves, value.cells))
        elif isinstance(value, _Entry):
            pending.extend((value.rank, value.buckets, value.values))
        elif isinstance(value, _Entries):
            total += value.base_bytes
            pending.extend(value.base.values())
            pending.append(value.changes)
        elif isinstance(value, MappingProxyType):
            # Owned minimal projected dictionaries, shared by typed bucket path.
            total += sys.getsizeof(dict(value))
            pending.extend(value.keys())
            pending.extend(value.values())
        elif isinstance(value, (tuple, list)):
            pending.extend(value)
        elif isinstance(value, dict):
            pending.extend(value.keys())
            pending.extend(value.values())
    return total


class PreparedTree:
    """A publication-local read projection, never a scientific membership owner.

    Rows and projected values must remain immutable for the snapshot's lifetime.
    Supplied scope keys must follow the input scope order and remain comparable
    across deltas; a metadata/source publication replacement requires rebuilding.
    The caller owns labels, annotations, freshness fences and explicit lifecycle.
    ``estimated_bytes`` accounts owned retained structures and projected values,
    excluding the caller's borrowed base rows. It is not a process RSS ceiling:
    preparation has transient arrays and Python's allocator may retain arenas.
    Delta admission conservatively charges every allocated persistent path without
    subtracting released nodes; explicit rebuilding compacts the UUID overlay.
    """
    __slots__ = ('_root', '_entries', 'definitions', 'split_order', 'estimated_bytes')

    def __setattr__(self, name, value):
        raise AttributeError('PreparedTree snapshots are immutable')

    def __init__(self, root, entries, definitions, split_order, estimated_bytes=0):
        for name, value in (('_root', root), ('_entries', entries), ('definitions', definitions),
                            ('split_order', tuple(split_order)), ('estimated_bytes', estimated_bytes)):
            object.__setattr__(self, name, value)

    @classmethod
    def build(cls, rows, values, definitions, split_order, *, scope_keys=None):
        order = tuple(split_order)
        if len(order) > 8 or len(set(order)) != len(order):
            raise ValueError('Tree splits require at most eight distinct fields')
        for field in order:
            if field not in definitions:
                raise ValueError('Unknown tree grouping field')
            parts = definitions[field].get('components')
            if parts and (not isinstance(parts, (list, tuple)) or any(part not in definitions for part in parts)):
                raise ValueError('Unknown joint grouping component')
        tree = cls(None, None, MappingProxyType({field: MappingProxyType({
            key: tuple(value) if key == 'components' else copy.deepcopy(value)
            for key, value in definitions[field].items()})
            for field in set(order).union(*(set(definitions[field].get('components', ())) for field in order))}), order)
        def staging(depth, bucket=None):
            return {'depth': depth, 'bucket': bucket, 'children': {}, 'leaves': [],
                    'cells': {}, 'count': 0, 'durations': []}
        root, entries, previous = staging(0), {}, None
        bucket_cache, projection_cache = {}, {}
        for position, row in enumerate(rows):
            identity = row['epoch_uuid']
            if identity in entries:
                raise ValueError('Duplicate epoch in prepared scope')
            rank = position if scope_keys is None else scope_keys[identity]
            if position and not previous < rank:
                raise ValueError('Scope ranks must follow canonical input order')
            previous = rank
            entry = tree._entry(row, values[identity] if order else {}, rank, bucket_cache, projection_cache)
            entries[identity] = entry
            current = root
            for depth in range(len(order) + 1):
                current['count'] += 1
                cell = row['cell_uuid']
                current['cells'][cell] = current['cells'].get(cell, 0) + 1
                duration = row.get('duration_seconds')
                current['durations'].append(duration)
                if depth == len(order):
                    current['leaves'].append(entry)
                else:
                    bucket = entry.buckets[depth]
                    child = current['children'].get(bucket[0])
                    if child is None:
                        child = current['children'][bucket[0]] = staging(depth + 1, bucket)
                    current = child
        def finish(current):
            depth, bucket = current['depth'], current['bucket']
            children = [finish(child) for child in current['children'].values()]
            ordered = sorted((_order(child, order[depth]), child) for child in children)
            return _Group(depth, *(bucket or (None, None, False)),
                          children=_bulk(ordered),
                          lookup=_bulk(sorted((child.key, key) for key, child in ordered)),
                          leaves=_bulk(sorted((entry.chronology, entry) for entry in current['leaves'])),
                          cells=_bulk(sorted(current['cells'].items())), count=current['count'],
                          duration=(sum(current['durations']) if all(value is not None for value in current['durations']) else None))
        root, entries = finish(root), _Entries(entries)
        return cls(root, entries, tree.definitions, order, _estimate(root, entries))

    def _entry(self, row, values, scope_key, bucket_cache=None, projection_cache=None):
        buckets = []
        for field in self.split_order:
            components = self.definitions[field].get('components')
            if components:
                present, value = True, joint_value(values, components)
            else:
                value = values.get(field)
                present = field in values and (field not in SPLIT_FIELDS or value is not None)
            identity = (field, present, value_key(value) if present else None)
            bucket = bucket_cache.get(identity) if bucket_cache is not None else None
            if bucket is None:
                key = checksum({'field': field, 'present': present, **({'value': value} if present else {})})
                bucket = key, value, not present
                if bucket_cache is not None:
                    bucket_cache[identity] = bucket
            buckets.append(bucket)
        projection_key = tuple(bucket[0] for bucket in buckets)
        projection = projection_cache.get(projection_key) if projection_cache is not None else None
        if projection is None and self._root is not None:
            # Reuse immutable existing branch projections during a bounded delta.
            try:
                existing, _ = self._resolve(projection_key)
            except KeyError:
                existing = None
            if existing is not None and existing.representative is not None:
                representative = existing.representative
                projection = representative.buckets, representative.values
        if projection is None:
            projected = {}
            for field, (_, value, missing) in zip(self.split_order, buckets):
                components = self.definitions[field].get('components')
                if components:
                    for component, part in zip(components, value):
                        if part['present']:
                            projected[component] = part['value']
                elif not missing:
                    projected[field] = value
            projection = tuple(buckets), MappingProxyType(projected)
        if projection_cache is not None:
            projection_cache[projection_key] = projection
        canonical_rank = (row['date'], row['start_time'], row['epoch_uuid'])
        return _Entry(row, projection[1], None if scope_key == canonical_rank else scope_key, projection[0])

    def _resolve(self, path):
        if len(path) > len(self.split_order):
            raise ValueError('Path exceeds grouping depth')
        node = self._root
        ancestors = []
        for key in path:
            ordering = _get(node.lookup, key)
            if ordering is None:
                raise KeyError('Tree branch is outside this selection')
            child = _get(node.children, ordering)
            ancestors.append((child, _rank(node.children, ordering)))
            node = child
        return node, ancestors

    def _branch(self, node, path, counts_only):
        entry = node.representative
        return {'key': node.key, 'value': copy.deepcopy(node.value), 'missing': node.missing,
                'path': list(path), 'has_children': node.depth < len(self.split_order),
                'representative': entry.row, 'values': copy.deepcopy(dict(entry.values)), **_summary(node, counts_only)}

    def page(self, path=(), offset=0, limit=80, *, anchor_uuid=None, counts_only=False):
        if (type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100
                or type(counts_only) is not bool):
            raise ValueError('Invalid prepared tree page window')
        if anchor_uuid is not None:
            if path or offset:
                raise ValueError('Anchor cannot also specify path or offset')
            entry = self._entries.get(anchor_uuid)
            if entry is None:
                raise KeyError('Epoch is outside this tree selection')
            path = tuple(bucket[0] for bucket in entry.buckets)
        node, ancestors = self._resolve(path)
        payload = {'path': list(path), 'depth': len(path), 'offset': offset, 'limit': limit,
                   'total_epochs': self._root.count, **_summary(self._root, counts_only),
                   'selection': _summary(node, counts_only), 'branches': [], 'epochs': [],
                   'ancestors': [{**self._branch(parent, path[:depth + 1], counts_only),
                                  'parent_index': index, 'parent_offset': index // limit * limit}
                                 for depth, (parent, index) in enumerate(ancestors)]}
        if len(path) < len(self.split_order):
            payload.update(kind='branches', total=_size(node.children),
                           branches=[self._branch(child, (*path, child.key), counts_only)
                                     for child in _window(node.children, offset, limit)])
        else:
            if anchor_uuid is not None:
                index = _rank(node.leaves, entry.chronology)
                offset = index // limit * limit
                payload.update(offset=offset, anchor={'epoch_uuid': anchor_uuid, 'path': list(path),
                                                     'index': index, 'offset': offset})
            payload.update(kind='epochs', total=node.count,
                           epochs=[entry.row for entry in _window(node.leaves, offset, limit)])
        payload['has_more'] = offset + limit < payload['total']
        return payload

    def select(self, path=(), *, max_count=1000):
        node, _ = self._resolve(path)
        if type(max_count) is not int or not 0 <= max_count <= 1000 or node.count > max_count:
            raise ValueError('Prepared selection exceeds 1,000 epochs')
        def visit(current):
            if current.depth == len(self.split_order):
                yield from (entry.row['epoch_uuid'] for entry in _window(current.leaves, 0, current.count))
            else:
                for child in _window(current.children, 0, _size(current.children)):
                    yield from visit(child)
        return tuple(visit(node))

    def apply(self, *, additions=(), removals=(), values=None, scope_keys=None):
        """Return a new snapshot; invalid deltas leave this snapshot untouched."""
        allocation = [0]
        token = _ALLOCATION.set(allocation)
        try:
            updated = self._apply(additions=additions, removals=removals, values=values, scope_keys=scope_keys)
            return PreparedTree(updated._root, updated._entries, self.definitions, self.split_order,
                                self.estimated_bytes + allocation[0])
        finally:
            _ALLOCATION.reset(token)

    def _apply(self, *, additions, removals, values, scope_keys):
        root, entries = self._root, self._entries
        bucket_cache, projection_cache = {}, {}
        def change(node, entry, delta):
            _ALLOCATION.get()[0] += 512  # Group, entry/path and ordering-key overhead.
            row, depth = entry.row, node.depth
            cell = row['cell_uuid']
            amount = _get(node.cells, cell, 0) + delta
            if amount < 0:
                raise ValueError('Invalid prepared cell count')
            cell_counts = _set(node.cells, cell, amount) if amount else _delete(node.cells, cell)
            if depth == len(self.split_order):
                leaves = (_set(node.leaves, entry.chronology, entry) if delta > 0
                          else _delete(node.leaves, entry.chronology))
                return replace(node, leaves=leaves, cells=cell_counts, count=node.count + delta,
                               duration=None, pending=True)
            key, value, missing = entry.buckets[depth]
            ordering = _get(node.lookup, key)
            child = _get(node.children, ordering) if ordering is not None else _Group(depth + 1, key, value, missing)
            child = change(child, entry, delta)
            children = _delete(node.children, ordering) if ordering is not None else node.children
            lookup = _delete(node.lookup, key) if ordering is not None else node.lookup
            if child.count:
                ordering = _order(child, self.split_order[depth])
                children = _set(children, ordering, child)
                lookup = _set(lookup, key, ordering)
            return replace(node, children=children, lookup=lookup, cells=cell_counts,
                           count=node.count + delta, duration=None, pending=True)
        seen = set()
        for identity in removals:
            if identity in seen:
                raise ValueError('Duplicate removed epoch')
            seen.add(identity)
            entry = entries.get(identity)
            if entry is None:
                raise KeyError('Removed epoch is outside this selection')
            root, entries = change(root, entry, -1), entries.change(identity, None)
        seen = set()
        for row in additions:
            identity = row['epoch_uuid']
            if identity in seen or entries.get(identity) is not None:
                raise ValueError('Duplicate added epoch')
            seen.add(identity)
            if values is None or scope_keys is None:
                raise ValueError('Additions require projected values and stable scope ranks')
            entry = self._entry(row, values[identity] if self.split_order else {}, scope_keys[identity], bucket_cache, projection_cache)
            root, entries = change(root, entry, 1), entries.change(identity, entry)
        return PreparedTree(root, entries, self.definitions, self.split_order)

    def finish_durations(self):
        """Explicit/background canonical summation, never part of a page read.

        Only pending nodes receive new sums. The fold follows initial scope order
        exactly (not AVL association or subtract/add arithmetic), preserving float
        rounding and missing duration semantics. The old snapshot stays pending.
        """
        if not self._root.pending:
            return self
        totals = {}
        ordered = sorted(self._entries.values(), key=lambda entry: entry.scope_key)
        for entry in ordered:
            current = self._root
            for depth in range(len(self.split_order) + 1):
                if not current.pending:
                    break
                totals.setdefault(id(current), []).append(entry.row.get('duration_seconds'))
                if depth < len(self.split_order):
                    ordering = _get(current.lookup, entry.buckets[depth][0])
                    current = _get(current.children, ordering)
        def finish(group):
            if not group.pending:
                return group
            def children(node):
                if node is None:
                    return None
                return _make(node.key, finish(node.value), children(node.left), children(node.right))
            durations = totals.get(id(group), ())
            duration = sum(durations) if all(value is not None for value in durations) else None
            return replace(group, children=children(group.children), duration=duration, pending=False)
        root = finish(self._root)
        return PreparedTree(root, self._entries, self.definitions, self.split_order,
                            _estimate(root, self._entries))
