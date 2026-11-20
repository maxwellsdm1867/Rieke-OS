"""Inspect and search a verified Symphony HDF5 attribute inventory.

The writer's format and implementation identify each immutable inventory.
Presentation and lookup changes in this module reuse its exact recorded data.
"""
import json

from workspace_h5_attribute_inventory import (
    FORMAT_VERSION, contract_hash, coverage_summary, ensure_inventory, inventory_path,
    inventory_reader, verified_inventory,
)


def field_definitions(descriptor):
    with inventory_reader(descriptor) as db:
        for fid,label in db.execute('SELECT field_id,label FROM fields ORDER BY field_id'):
            yield {'id':fid,'path':fid,'label':label,'category':'H5 attributes'}


def field_value_rows(descriptor):
    with inventory_reader(descriptor) as db:
        yield from db.execute('SELECT v.id,f.field_id,c.value_json FROM field_values v JOIN fields f ON f.id=v.field JOIN contents c ON c.id=v.content ORDER BY v.id')


def epoch_value_ids(descriptor):
    with inventory_reader(descriptor) as db:
        yield from db.execute('SELECT DISTINCT e.epoch_uuid,a.field_value FROM epoch_owners e JOIN assignments a ON a.owner=e.owner')


_VALUES = """SELECT DISTINCT e.epoch_uuid,f.field_id,c.value_json FROM epoch_owners e JOIN assignments a ON a.owner=e.owner
              JOIN field_values v ON v.id=a.field_value JOIN fields f ON f.id=v.field JOIN contents c ON c.id=v.content"""


def epoch_value_rows(descriptor):
    with inventory_reader(descriptor) as db:
        yield from db.execute(_VALUES)


def epoch_values(descriptor, epoch_ids):
    with inventory_reader(descriptor) as db:
        db.execute('CREATE TEMP TABLE requested(epoch_uuid TEXT PRIMARY KEY)')
        db.executemany('INSERT OR IGNORE INTO requested VALUES (?)', ((eid,) for eid in epoch_ids))
        for eid,fid,encoded in db.execute(_VALUES+' JOIN requested r ON r.epoch_uuid=e.epoch_uuid'):
            yield eid,fid,json.loads(encoded)


def _records(db, epoch_uuid, query, record_id=None):
    where, args = [], []
    scope_join = ''
    if epoch_uuid is not None:
        scope_join = ' JOIN epoch_owners e ON e.owner=sa.owner'
        where.append('e.epoch_uuid=?')
        args.append(epoch_uuid)
    if query:
        term = query.casefold()
        def value_matches(encoded):
            # Decode escaped Unicode only once per distinct value, independently
            # of how many epochs share an ancestor or repeat the same attribute.
            if term in encoded.casefold():
                return True
            return ('\\u' in encoded and term in json.dumps(json.loads(encoded), ensure_ascii=False,
                                                            separators=(',', ':')).casefold())
        db.create_function('value_matches', 1, value_matches, deterministic=True)
        db.execute('CREATE TEMP TABLE matching_values(id INTEGER PRIMARY KEY)')
        db.execute('INSERT INTO matching_values SELECT id FROM contents WHERE value_matches(value_json)')
        db.create_function('name_matches', 1, lambda text: term in text.casefold(), deterministic=True)
        where.append("(name_matches(f.field_id) OR name_matches(o.object_path) OR name_matches(f.label) OR a.content IN matching_values)")
    if record_id is not None:
        where.append('a.id=?')
        args.append(record_id)
    matches = ("""SELECT sa.attribute, min(f.field_id) AS field_id FROM assignments sa
        JOIN attributes a ON a.id=sa.attribute JOIN objects o ON o.address=a.object
        JOIN field_values v ON v.id=sa.field_value JOIN fields f ON f.id=v.field""" + scope_join +
        (' WHERE '+' AND '.join(where) if where else '')+' GROUP BY sa.attribute')
    return matches,args


def _record_rows(db,matches,args,full,limit,offset,*,source_order=False):
    from sqlite3 import Row
    db.row_factory = Row
    value = 'c.value_json, t.h5_type_hex, hex(o.raw_path) AS path_bytes_hex, hex(a.raw_name) AS name_bytes_hex' if full else 'substr(c.value_json,1,240) AS value_preview, length(c.value_json)>240 AS value_truncated'
    order = 'a.id' if source_order else 'f.field_id,o.object_path,a.id'
    sql = f"""WITH matched AS ({matches}) SELECT a.id AS record_id,f.field_id,f.label,o.object_path,a.name AS attribute_name,
            t.dtype,t.shape_json,{value} FROM matched m JOIN attributes a ON a.id=m.attribute
            JOIN fields f ON f.field_id=m.field_id JOIN objects o ON o.address=a.object
            JOIN encodings t ON t.id=a.encoding JOIN contents c ON c.id=a.content
            ORDER BY {order} LIMIT ? OFFSET ?"""
    results = []
    for data in db.execute(sql,[*args,limit,offset]):
        row = dict(data)
        row['shape'] = json.loads(row.pop('shape_json'))
        if not full:
            row['value_truncated'] = bool(row['value_truncated'])
        results.append(row)
    return results


def attribute_page(descriptor, *, epoch_uuid=None, q='', offset=0, limit=40):
    if not isinstance(q,str) or len(q)>512 or type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:
        raise ValueError('Invalid H5 attribute page or search')
    with inventory_reader(descriptor) as db:
        if epoch_uuid is None and not q:
            # A physical inventory has one record per attribute. Its verified
            # count and stable record order need no whole-source grouping.
            matches = """SELECT a.id AS attribute,(SELECT min(f.field_id) FROM assignments s
                JOIN field_values v ON v.id=s.field_value JOIN fields f ON f.id=v.field
                WHERE s.attribute=a.id) AS field_id FROM physical_attributes a ORDER BY a.id LIMIT ? OFFSET ?"""
            records = _record_rows(db,matches,[limit,offset],False,limit,0,source_order=True)
            total = descriptor['attribute_count']
            return dict(records=records,total=total,has_more=offset+len(records)<total)
        matches,args = _records(db,epoch_uuid,q)
        total = db.execute('SELECT count(*) FROM ('+matches+')',args).fetchone()[0]
        records = _record_rows(db,matches,args,False,limit,offset)
        return dict(records=records,total=total,has_more=offset+len(records)<total)


def attribute_record(descriptor, record_id, *, epoch_uuid=None):
    if type(record_id) is not int or record_id<1:
        raise ValueError('Invalid H5 attribute record ID')
    with inventory_reader(descriptor) as db:
        matches,args = _records(db,epoch_uuid,'',record_id)
        result = _record_rows(db,matches,args,True,1,0)
        if not result:
            raise KeyError('H5 attribute is outside this scope')
        return {**result[0],'source_sha256':descriptor['source_sha256']}
