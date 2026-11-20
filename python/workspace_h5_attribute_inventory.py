"""Source-verified Symphony HDF5 attributes and epoch ownership, without reading datasets."""
from __future__ import annotations

import base64
from collections import defaultdict, deque
from contextlib import closing, contextmanager
import fcntl
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
from urllib.parse import quote_from_bytes


FORMAT_VERSION = 1
_SUMMARY_KEYS = ('version', 'contract', 'source_sha256', 'object_count', 'physical_attribute_count',
                 'attribute_count', 'field_count', 'epoch_count', 'logical_sha256')
_SCHEMA = """
CREATE TABLE path_prefixes(id INTEGER PRIMARY KEY, prefix TEXT NOT NULL, raw_prefix BLOB);
CREATE TABLE physical_objects(address INTEGER PRIMARY KEY, ordinal INTEGER NOT NULL UNIQUE, directory INTEGER NOT NULL, name TEXT NOT NULL, raw_name BLOB, kind TEXT NOT NULL);
CREATE VIEW objects AS SELECT o.address,o.ordinal,p.prefix||o.name AS object_path,
    CAST(coalesce(p.raw_prefix,cast(p.prefix as blob))||coalesce(o.raw_name,cast(o.name as blob)) AS BLOB) AS raw_path,o.kind
    FROM physical_objects o JOIN path_prefixes p ON p.id=o.directory;
CREATE TABLE links(parent INTEGER NOT NULL, name BLOB NOT NULL, target INTEGER NOT NULL, soft_target BLOB, PRIMARY KEY(parent,name)) WITHOUT ROWID;
CREATE TABLE encodings(id INTEGER PRIMARY KEY, dtype TEXT NOT NULL, h5_type_hex TEXT NOT NULL, shape_json TEXT NOT NULL, UNIQUE(dtype,h5_type_hex,shape_json));
CREATE TABLE contents(id INTEGER PRIMARY KEY, value_json TEXT NOT NULL UNIQUE);
CREATE TABLE attribute_names(id INTEGER PRIMARY KEY, name TEXT NOT NULL, raw_name BLOB);
CREATE TABLE physical_attributes(id INTEGER PRIMARY KEY, object INTEGER NOT NULL, name_id INTEGER NOT NULL, encoding INTEGER NOT NULL, content INTEGER NOT NULL, UNIQUE(object,name_id));
CREATE VIEW attributes AS SELECT a.id,a.object,n.name,coalesce(n.raw_name,cast(n.name AS BLOB)) AS raw_name,a.encoding,a.content
    FROM physical_attributes a JOIN attribute_names n ON n.id=a.name_id;
CREATE TABLE fields(id INTEGER PRIMARY KEY, field_id TEXT NOT NULL UNIQUE, label TEXT NOT NULL);
CREATE TABLE field_values(id INTEGER PRIMARY KEY, field INTEGER NOT NULL, content INTEGER NOT NULL, UNIQUE(field,content));
CREATE TABLE assignments(owner INTEGER NOT NULL, attribute INTEGER NOT NULL, field_value INTEGER NOT NULL, PRIMARY KEY(owner,attribute)) WITHOUT ROWID;
CREATE INDEX assignments_attribute ON assignments(attribute,owner);
CREATE TABLE owners(id INTEGER PRIMARY KEY, scope TEXT NOT NULL, qualifier TEXT NOT NULL);
CREATE TABLE epoch_owners(epoch_uuid TEXT NOT NULL, owner INTEGER NOT NULL, PRIMARY KEY(epoch_uuid,owner)) WITHOUT ROWID;
CREATE INDEX owner_epochs ON epoch_owners(owner,epoch_uuid);
CREATE TABLE receipt(json TEXT NOT NULL);
"""


def _json(value):
    return json.dumps(value, allow_nan=False, ensure_ascii=True, sort_keys=True, separators=(',', ':'))


def _sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


@lru_cache(maxsize=1)
def contract_hash():
    return _sha(Path(__file__))


def inventory_path(project_dir, source_sha256):
    if not isinstance(source_sha256, str) or not re.fullmatch('[0-9a-f]{64}', source_sha256):
        raise ValueError('Invalid H5 attribute inventory source identity')
    project = Path(project_dir).resolve(strict=True)
    directory = project / 'imports' / 'h5-attributes'
    if directory.parent.is_symlink() or directory.is_symlink() or directory.resolve() != directory:
        raise ValueError('H5 attribute inventory must stay in its project imports directory')
    return directory / f'{source_sha256}.v{FORMAT_VERSION}-{contract_hash()}.sqlite'


def coverage_summary(descriptor):
    return {key: descriptor[key] for key in _SUMMARY_KEYS}


def _signature(path):
    if path.is_symlink() or not path.is_file():
        if not path.exists() and not path.is_symlink():
            raise FileNotFoundError(path)
        raise ValueError('Unsafe H5 attribute inventory file')
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def _connect(path):
    return sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)


_witness_lock = threading.Lock()
_witnesses = {}


def _admit(path, database_stat, seal_stat):
    # Refresh checks each source twice. Keep one current witness per inspected
    # source asset so large projects do not evict their own proofs mid-refresh.
    with _witness_lock:
        prior = _witnesses.get(path)
        if prior is not None and prior[:2] == (database_stat, seal_stat):
            return prior[2]
    seal_path = path.with_suffix('.seal.json')
    try:
        seal = json.loads(seal_path.read_bytes())
        db_sha = _sha(path)
        if seal.get('sha256') != db_sha:
            raise ValueError('H5 attribute inventory checksum mismatch')
        with closing(_connect(path)) as db:
            summary = json.loads(db.execute('SELECT json FROM receipt').fetchone()[0])
        if (set(summary) != set(_SUMMARY_KEYS) or seal.get('coverage') != summary
                or summary['attribute_count'] != summary['physical_attribute_count']
                or summary['contract'] != contract_hash() or summary['version'] != FORMAT_VERSION):
            raise ValueError('Incomplete or obsolete H5 attribute inventory coverage')
        if database_stat != _signature(path) or seal_stat != _signature(seal_path):
            raise ValueError('H5 attribute inventory changed during verification')
        descriptor = {**summary, 'sha256': db_sha, 'path': str(path)}
        with _witness_lock:
            _witnesses[path] = (database_stat, seal_stat, descriptor)
        return descriptor
    except (sqlite3.DatabaseError, KeyError, TypeError, AttributeError, IndexError) as error:
        raise ValueError('Unreadable H5 attribute inventory proof') from error


def _check_expected(actual, expected):
    if expected is not None and not isinstance(expected, dict):
        raise ValueError('Invalid registered H5 attribute coverage summary')
    if expected and expected.get('source_sha256') != actual['source_sha256']:
        raise ValueError('H5 attribute inventory source identity mismatch')
    if (expected and expected.get('version') == FORMAT_VERSION and expected.get('contract') == contract_hash()
            and any(actual[key] != expected.get(key) for key in _SUMMARY_KEYS)):
        raise ValueError('H5 attribute coverage differs from the registered import')


def verified_inventory(project_dir, source_sha256, *, expected=None):
    path = inventory_path(project_dir, source_sha256)
    descriptor = _admit(path, _signature(path), _signature(path.with_suffix('.seal.json')))
    if descriptor['source_sha256'] != source_sha256:
        raise ValueError('H5 attribute inventory belongs to another recording')
    _check_expected(descriptor, expected)
    return dict(descriptor)


def _bytes(name):
    return name if isinstance(name, bytes) else name.encode('utf-8', 'surrogateescape')


def _display(name):
    return _bytes(name).decode('utf-8', errors='backslashreplace')


def _lossless_name(raw):
    """Store ordinary UTF-8 once; retain original bytes separately only when needed."""
    display = _display(raw)
    return display, None if display.encode('utf-8') == raw else raw


def _component(name):
    return quote_from_bytes(_bytes(name).replace(b'~', b'~0').replace(b'/', b'~1'), safe='~')


def _value(value, h5):
    import h5py
    import numpy as np
    if isinstance(value, h5py.Empty):
        return None
    if isinstance(value, np.ndarray):
        return [_value(part, h5) for part in value] if value.ndim else _value(value[()], h5)
    if isinstance(value, np.void):
        if value.dtype.names:
            return {name: _value(value[name], h5) for name in value.dtype.names}
        return {'$h5_opaque': base64.b64encode(value.tobytes()).decode()}
    if isinstance(value, h5py.Reference):
        if not value:
            return {'$h5_reference': None}
        address = int(h5py.h5o.get_info(h5[value].id).addr)
        encoded = {'$h5_reference': address}
        if isinstance(value, h5py.RegionReference):
            encoded['region'] = base64.b64encode(h5py.h5r.get_region(value, h5.id).encode()).decode()
        return encoded
    if isinstance(value, (bytes, np.bytes_)):
        try:
            return bytes(value).decode('utf-8')
        except UnicodeDecodeError:
            return {'$h5_bytes': base64.b64encode(value).decode()}
    if isinstance(value, str):
        # h5py decodes variable-length string attributes with surrogateescape.
        # SQLite TEXT requires valid UTF-8; restore the original bytes exactly.
        try:
            value.encode('utf-8')
        except UnicodeEncodeError:
            return {'$h5_bytes': base64.b64encode(value.encode('utf-8', 'surrogateescape')).decode()}
        return str(value)
    if isinstance(value, (np.complexfloating, complex)):
        return {'$h5_complex': [_value(value.real, h5), _value(value.imag, h5)]}
    if isinstance(value, (np.floating, float)):
        if not math.isfinite(value) or isinstance(value, np.floating) and value.dtype.itemsize > 8:
            scalar = np.asarray(value)
            return {'$h5_float': scalar.tobytes().hex(), 'dtype': scalar.dtype.str}
        return float(value)
    if isinstance(value, np.generic):
        if value.dtype.kind in ('m', 'M'):
            return {'$h5_time': value.tobytes().hex(), 'dtype': value.dtype.str}
        return value.item()
    return value


def _addr(obj):
    import h5py
    return int(h5py.h5o.get_info(obj.id).addr)


def link_info(group, name):
    """Inspect the link itself, including HDF5 names outside UTF-8."""
    import h5py
    raw = _bytes(name)
    links = group.id.links
    if not links.exists(raw):
        return None, None
    kind = links.get_info(raw).type
    return kind, links.get_val(raw) if kind == h5py.h5l.TYPE_SOFT else None


def _schema_bindings(h5, identity):
    """Pin the canonical hierarchy before traversing hard-linked Symphony backlinks."""
    anchors, epoch_owners = {}, defaultdict(set)
    file_owner = _addr(h5['/'])
    root = next(obj for name, obj in h5.items() if _display(name).startswith('experiment-'))
    experiment = _addr(root)
    anchors[file_owner] = ('file', '')
    anchors[experiment] = ('experiment', '')
    for kind in ('animal', 'preparation', 'cell', 'group', 'block', 'epoch'):
        for node in identity[kind].values():
            anchors[node['address']] = (kind, '')
    devices = root.get('devices', {})
    device_names = defaultdict(list)
    for name, dev in devices.items():
        label = _display(dev.attrs.get('name', name))
        device_names[label].append((name, _addr(dev)))
    for label, group in device_names.items():
        for name, address in group:
            anchors[address] = ('device', label if len(group) == 1 else _display(name))
    for eid, entry in identity['epoch'].items():
        lineage = epoch_owners[eid]
        lineage.update((file_owner, experiment, entry['address']))
        parent = entry['parent']
        for kind in ('block', 'group', 'cell', 'preparation', 'animal'):
            node = identity[kind][parent]
            lineage.add(node['address'])
            parent = node['parent']
        obj = h5[entry['path']]
        for collection, scope in (('responses', 'response'), ('stimuli', 'stimulus'), ('backgrounds', 'background')):
            children = list(obj.get(collection, {}).items())
            labels = defaultdict(list)
            for key, child in children:
                text = _display(key)
                uid = _display(child.attrs.get('uuid', ''))
                label = text[:-len(uid)-1] if uid and text.endswith('-' + uid) else text
                labels[label].append((text, child))
            for label, siblings in labels.items():
                for key, child in siblings:
                    address = _addr(child)
                    qualifier = label if len(siblings) == 1 else key
                    candidate = (scope, qualifier)
                    if address in anchors and anchors[address] != candidate:
                        raise ValueError('Conflicting H5 stream or background owner identity')
                    anchors[address] = candidate
                    lineage.add(address)
                    target = child.get('device')
                    if target is not None and _addr(target) in anchors:
                        lineage.add(_addr(target))
    return anchors, epoch_owners


def _physical_graph(db, h5):
    """Index each physical H5 object once and retain every hard/soft link."""
    import h5py
    edges, paths = defaultdict(list), {}
    directories = {}
    root = h5['/']
    paths[_addr(root)] = root.name
    queue = deque(paths)
    count = 0
    while queue:
        address = queue.popleft()
        obj = h5[paths[address]]
        kind = 'group' if isinstance(obj, h5py.Group) else 'dataset' if isinstance(obj, h5py.Dataset) else 'datatype'
        count += int(h5py.h5o.get_info(obj.id).num_attrs)
        prefix, _, basename = _bytes(paths[address]).rpartition(b'/')
        prefix += b'/'
        if prefix not in directories:
            directories[prefix] = db.execute('INSERT INTO path_prefixes(prefix,raw_prefix) VALUES (?,?)',
                                               _lossless_name(prefix)).lastrowid
        db.execute('INSERT INTO physical_objects VALUES (?,?,?,?,?,?)',
                   (address, len(edges), directories[prefix], *_lossless_name(basename), kind))
        children = edges[address]
        if kind != 'group':
            continue
        for name in obj:
            link, soft_target = link_info(obj,name)
            if link not in (h5py.h5l.TYPE_HARD,h5py.h5l.TYPE_SOFT):
                raise ValueError('External H5 attribute links require a separate source revision')
            # validate_source_identity admitted the sealed link closure before this traversal.
            target = obj[name]
            if target.file.id != h5.id:
                raise ValueError('H5 attribute object escaped the recording')
            child = _addr(target)
            raw_name = _bytes(name)
            children.append((raw_name, child))
            db.execute('INSERT INTO links VALUES (?,?,?,?)',
                       (address, raw_name, child, soft_target))
            if child not in paths:
                paths[child] = target.name
                queue.append(child)
    return edges, paths, count


def _parts_hash(hasher, parts):
    for part in parts:
        data = part if isinstance(part, bytes) else part.encode()
        hasher.update(len(data).to_bytes(8, 'big'))
        hasher.update(data)


def _scan(db, h5, paths):
    """Read attributes independently of the HDF5 object-info counts; never access data[]."""
    @lru_cache(maxsize=2048)
    def encoding(dtype, type_hex, shape):
        db.execute('INSERT OR IGNORE INTO encodings(dtype,h5_type_hex,shape_json) VALUES (?,?,?)', (dtype,type_hex,shape))
        return db.execute('SELECT id FROM encodings WHERE dtype=? AND h5_type_hex=? AND shape_json=?', (dtype,type_hex,shape)).fetchone()[0]

    def content(value):
        db.execute('INSERT OR IGNORE INTO contents(value_json) VALUES (?)', (value,))
        return db.execute('SELECT id FROM contents WHERE value_json=?', (value,)).fetchone()[0]

    small_content = lru_cache(maxsize=2048)(content)
    digest = hashlib.sha256()
    names = {}
    for address, path in paths.items():
        obj = h5[path]
        for name in sorted(obj.attrs, key=_bytes):
            attr = obj.attrs.get_id(name)
            value = _json(_value(obj.attrs[name], h5))
            dtype = str(attr.dtype)
            encoded_type = attr.get_type().encode().hex()
            shape = _json(attr.shape)
            raw_name = _bytes(name)
            if raw_name not in names:
                names[raw_name] = db.execute('INSERT INTO attribute_names(name,raw_name) VALUES (?,?)',
                                              _lossless_name(raw_name)).lastrowid
            _parts_hash(digest, (_bytes(path), raw_name, encoded_type, shape, value))
            value_id = small_content(value) if len(value) <= 4096 else content(value)
            db.execute('INSERT INTO physical_attributes(object,name_id,encoding,content) VALUES (?,?,?,?)',
                       (address, names[raw_name], encoding(dtype,encoded_type,shape), value_id))
    return digest.hexdigest()


def _scope_fields(db, edges, anchors, epoch_owners):
    # Anchored nodes cut cross-links into other scientific owners. Within one
    # owner, the shortest stable path names a field and all aliases remain in links.
    db.executemany('INSERT INTO owners VALUES (?,?,?)', [(a,*v) for a,v in anchors.items()])
    db.executemany('INSERT INTO epoch_owners VALUES (?,?)', ((eid,o) for eid,owners in epoch_owners.items() for o in sorted(owners)))
    db.execute('CREATE TEMP TABLE scoped(owner INTEGER,object INTEGER,prefix TEXT,label TEXT)')
    for owner,(kind, qualifier) in anchors.items():
        components = [kind, *([qualifier] if qualifier else [])]
        queue = deque([(owner, 'h5/' + '/'.join(map(_component,components)), '/'.join(components))])
        seen = {owner}
        while queue:
            address, prefix, label = queue.popleft()
            db.execute('INSERT INTO scoped VALUES (?,?,?,?)', (owner,address,prefix,label))
            for name, child in edges[address]:
                if child not in anchors and child not in seen:
                    seen.add(child)
                    queue.append((child, prefix + '/' + _component(name), label + '/' + _display(name)))
    db.create_function('field_component', 1, _component, deterministic=True)
    db.execute("""CREATE TEMP TABLE bindings AS
        SELECT s.owner, a.id AS attr, a.content, s.prefix || '/@' || field_component(a.raw_name) AS fid,
               'H5 ' || s.label || '/@' || a.name AS label FROM scoped s JOIN attributes a ON a.object=s.object""")
    db.execute('INSERT INTO fields(field_id,label) SELECT fid,min(label) FROM bindings GROUP BY fid')
    db.execute('INSERT INTO field_values(field,content) SELECT DISTINCT f.id,b.content FROM bindings b JOIN fields f ON f.field_id=b.fid')
    db.execute("""INSERT INTO assignments SELECT b.owner,b.attr,v.id FROM bindings b
                  JOIN fields f ON f.field_id=b.fid JOIN field_values v ON v.field=f.id AND v.content=b.content""")
    if db.execute('SELECT 1 FROM attributes a WHERE NOT EXISTS (SELECT 1 FROM assignments s WHERE s.attribute=a.id) LIMIT 1').fetchone():
        raise ValueError('Physical H5 attributes are missing from the scope registry')


def _build(h5, identity, db, source_sha):
    db.executescript(_SCHEMA)
    anchors, epoch_owners = _schema_bindings(h5,identity)
    edges, paths, physical_count = _physical_graph(db,h5)
    source_digest = _scan(db,h5,paths)
    _scope_fields(db,edges,anchors,epoch_owners)
    readback = hashlib.sha256()
    count = 0
    for record in db.execute("""SELECT o.raw_path,a.raw_name,t.h5_type_hex,t.shape_json,c.value_json FROM objects o
        JOIN attributes a ON a.object=o.address JOIN encodings t ON t.id=a.encoding JOIN contents c ON c.id=a.content
        ORDER BY o.ordinal,a.raw_name"""):
        _parts_hash(readback,record)
        count += 1
    if count != physical_count or source_digest != readback.hexdigest():
        raise ValueError('The stored H5 attribute count or logical checksum differs from the recording')
    summary = dict(version=FORMAT_VERSION, contract=contract_hash(), source_sha256=source_sha,
                   object_count=len(paths), physical_attribute_count=physical_count, attribute_count=count,
                   field_count=db.execute('SELECT count(*) FROM fields').fetchone()[0], epoch_count=len(epoch_owners),
                   logical_sha256=source_digest)
    db.execute('INSERT INTO receipt VALUES (?)', (_json(summary),))
    db.commit()
    if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
        raise ValueError('H5 attribute inventory integrity failure')
    return summary


def ensure_inventory(h5, validated_identity, project_dir, source_sha256, *, expected=None, source_signature=None):
    path = inventory_path(project_dir,source_sha256)
    original = Path(h5.filename).resolve(strict=True)
    signature = _signature(original)
    if source_signature is not None and (Path(source_signature[0]).resolve() != original or
                                         tuple(source_signature[1:]) != signature):
        raise ValueError('H5 recording changed before attribute extraction')
    path.parent.mkdir(parents=True,exist_ok=True)
    # A fixed stripe set bounds lock files. Readers open an immutable database;
    # replacement only publishes a complete re-verified inventory.
    lock_path = path.parent / ('.writer-' + source_sha256[:1] + '.lock')
    lock_fd = os.open(lock_path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(lock_fd,'r+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:
            return verified_inventory(project_dir,source_sha256,expected=expected)
        except (FileNotFoundError, ValueError):
            pass
        fd, name = tempfile.mkstemp(dir=path.parent,suffix='.building')
        os.close(fd)
        temp = Path(name)
        seal_tmp = Path(name+'.json')
        try:
            with closing(sqlite3.connect(temp)) as db:
                summary = _build(h5,validated_identity,db,source_sha256)
            _check_expected(summary,expected)
            if _signature(original) != signature:
                raise ValueError('H5 recording changed during attribute extraction')
            with temp.open('rb') as source:
                digest = hashlib.file_digest(source,'sha256').hexdigest()
                os.fsync(source.fileno())
            with seal_tmp.open('x') as seal:
                seal.write(_json({'sha256':digest,'coverage':summary}))
                seal.flush()
                os.fsync(seal.fileno())
            if path.is_symlink() or path.with_suffix('.seal.json').is_symlink():
                raise ValueError('Unsafe H5 attribute inventory publication destination')
            os.replace(temp,path)
            os.replace(seal_tmp,path.with_suffix('.seal.json'))
            directory_fd = os.open(path.parent,os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return verified_inventory(project_dir,source_sha256,expected=expected)
        finally:
            temp.unlink(missing_ok=True)
            seal_tmp.unlink(missing_ok=True)
            Path(name+'-journal').unlink(missing_ok=True)


@contextmanager
def inventory_reader(descriptor):
    path = Path(descriptor['path'])
    signature = _signature(path), _signature(path.with_suffix('.seal.json'))
    verified = _admit(path,*signature)
    if descriptor != verified:
        raise ValueError('H5 attribute descriptor identity mismatch')
    with closing(_connect(path)) as connection:
        yield connection
    if signature != (_signature(path), _signature(path.with_suffix('.seal.json'))):
        raise ValueError('H5 attribute inventory changed during use')
