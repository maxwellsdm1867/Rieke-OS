"""Disposable, sealed SQLite projection of verified metadata (never acquisition truth).

The caller supplies a generation derived from all verified source/metadata inputs.
Readers pin that generation; no method modifies the published database.
"""
from __future__ import annotations
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import zlib
from collections import OrderedDict
from collections.abc import Mapping
from contextlib import contextmanager
from urllib.parse import unquote

import workspace_tree as tree
import workspace_predicates as predicates

FORMAT = 1
CHUNK_SIZE = 256
CACHE_SIZE = 64


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _signature(path):
    stat = os.stat(path)
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _raw_definition(field):
    key = field['id']
    if key in tree.BASE_FIELDS:
        label, category, path = tree.BASE_FIELDS[key]
        return dict(id=key, label=label, category=category, path=path)
    if key.startswith('joint/'):
        return {name: field[name] for name in ('id','label','category','path','components') if name in field}
    parts = [unquote(part).replace('~1','/').replace('~0','~') for part in key.split('/')]
    names = {'experiment':'Experiment','cell':'Cell','group':'Epoch group','block':'Epoch block','epoch':'Epoch'}
    prefix = names[parts[1]]+' · ' if parts[0]=='metadata' else 'Epoch · ' if parts[0]=='properties' else ''
    return dict(id=key,label=prefix+tree.humanize(parts[-1]),category=field['category'],path='.'.join(parts))


class DiskMetadataIndex:
    @classmethod
    def build(cls, path, rows, details, sources, generation, project_uuid):
        path = Path(path)
        sources = tuple(sources)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=path.name+'.', suffix='.building', dir=path.parent)
        os.close(fd)
        connection = sqlite3.connect(temporary)
        definitions, field_numbers = {}, {}
        try:
            connection.executescript('''
                PRAGMA journal_mode=DELETE; PRAGMA synchronous=FULL;
                CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE epochs(epoch_id INTEGER PRIMARY KEY,epoch_uuid TEXT UNIQUE NOT NULL,
                    source_sha TEXT,cell_uuid TEXT,row_json TEXT NOT NULL,detail_blob BLOB NOT NULL,fingerprint TEXT NOT NULL);
                CREATE INDEX epochs_source ON epochs(source_sha);
                CREATE TABLE fields(field_no INTEGER PRIMARY KEY,field_id TEXT UNIQUE NOT NULL,definition_json TEXT NOT NULL);
                CREATE TABLE field_values(value_id INTEGER PRIMARY KEY,field_no INTEGER NOT NULL,value_json TEXT NOT NULL,
                    UNIQUE(field_no,value_json));
                CREATE TABLE epoch_values(epoch_id INTEGER,field_no INTEGER,value_id INTEGER,
                    PRIMARY KEY(epoch_id,field_no)) WITHOUT ROWID;
                CREATE INDEX values_reverse ON epoch_values(field_no,value_id,epoch_id);
                CREATE TABLE sources(source_sha TEXT PRIMARY KEY,source_json TEXT NOT NULL);
            ''')
            connection.executemany('INSERT INTO sources VALUES(?,?)',[(s['source_sha256'],_json(s)) for s in sources])
            row_list = list(rows.values()) if isinstance(rows, Mapping) else list(rows)
            value_cache = OrderedDict()
            for offset in range(0,len(row_list),CHUNK_SIZE):
                chunk = row_list[offset:offset+CHUNK_SIZE]
                chunk_details = {row['epoch_uuid']:details[row['epoch_uuid']] for row in chunk}
                summary, values = tree.catalog(chunk,chunk_details,sources=sources)
                for field in summary['fields']:
                    key = field['id']
                    if key.startswith('joint/') or key in definitions:
                        continue
                    definition = _raw_definition(field)
                    number = len(field_numbers)+1
                    definitions[key],field_numbers[key] = definition,number
                    connection.execute('INSERT INTO fields VALUES(?,?,?)',(number,key,_json(definition)))
                for row in chunk:
                    identity = row['epoch_uuid']; datum=chunk_details[identity]
                    fingerprint = hashlib.sha256(json.dumps({'epoch':datum,'source_sha256':row.get('source_sha256')},sort_keys=True,allow_nan=False).encode()).hexdigest()
                    cursor=connection.execute('INSERT INTO epochs(epoch_uuid,source_sha,cell_uuid,row_json,detail_blob,fingerprint) VALUES(?,?,?,?,?,?)',
                        (identity,row.get('source_sha256'),row.get('cell_uuid'),_json(row),zlib.compress(_json(datum).encode()),fingerprint))
                    epoch_id=cursor.lastrowid
                    links=[]
                    for key,value in values[identity].items():
                        if key.startswith('joint/'): continue
                        number=field_numbers[key]; encoded=tree.value_key(value); cache_key=(number,encoded)
                        value_id=value_cache.get(cache_key)
                        if value_id is None:
                            connection.execute('INSERT OR IGNORE INTO field_values(field_no,value_json) VALUES(?,?)',cache_key)
                            value_id=connection.execute('SELECT value_id FROM field_values WHERE field_no=? AND value_json=?',cache_key).fetchone()[0]
                            value_cache[cache_key]=value_id
                            if len(value_cache)>8192: value_cache.popitem(last=False)
                        links.append((epoch_id,number,value_id))
                    connection.executemany('INSERT INTO epoch_values VALUES(?,?,?)',links)
            # Empty indexes still expose the stable base schema.
            for key,(label,category,field_path) in tree.BASE_FIELDS.items():
                if key not in definitions:
                    definition=dict(id=key,label=label,category=category,path=field_path)
                    connection.execute('INSERT INTO fields(field_id,definition_json) VALUES(?,?)',(key,_json(definition)))
            connection.executemany('INSERT INTO meta VALUES(?,?)',[(key,_json(value)) for key,value in
                dict(format=FORMAT,generation=generation,project_uuid=project_uuid,complete=True).items()])
            connection.commit()
            if connection.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise ValueError('Metadata index integrity check failed')
            connection.close()
            provisional=cls();provisional.path=Path(temporary).resolve();provisional.generation=generation;provisional.project_uuid=project_uuid
            provisional._signature=_signature(temporary);provisional._definitions=list(definitions.values())
            if not provisional._definitions:
                provisional._definitions=[dict(id=key,label=label,category=category,path=field_path) for key,(label,category,field_path) in tree.BASE_FIELDS.items()]
            provisional._catalog_cache=None;provisional._predicate_cache=None
            catalog=provisional.catalog();predicate_catalog=provisional.predicate_catalog()
            with sqlite3.connect(temporary) as summary_connection:
                summary_connection.executemany('INSERT INTO meta VALUES(?,?)',[('catalog',_json(catalog)),('predicate_catalog',_json(predicate_catalog))])
            seal=dict(format=FORMAT,generation=generation,project_uuid=project_uuid,sha256=_sha(temporary))
            seal_path=temporary+'.json'
            with open(seal_path,'w') as stream:
                stream.write(_json(seal));stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,path)
            os.replace(seal_path,str(path)+'.sha256.json')
            return cls.open(path,generation,project_uuid)
        finally:
            connection.close()
            for leftover in (temporary,temporary+'.json'):
                if os.path.exists(leftover): os.unlink(leftover)

    @classmethod
    def open(cls,path,generation,project_uuid):
        instance=cls();instance.path=Path(path).resolve();instance.generation=generation;instance.project_uuid=project_uuid
        before=_signature(instance.path)
        seal=json.loads(Path(str(instance.path)+'.sha256.json').read_text())
        if any(seal.get(k)!=v for k,v in dict(format=FORMAT,generation=generation,project_uuid=project_uuid).items()):
            raise ValueError('Metadata index generation/project/format mismatch')
        if _sha(instance.path)!=seal.get('sha256') or before!=_signature(instance.path):
            raise ValueError('Metadata index checksum mismatch or changed during verification')
        instance._signature=before;instance._catalog_cache=None;instance._predicate_cache=None
        with instance._connect() as connection:
            metadata={key:json.loads(value) for key,value in connection.execute('SELECT key,value FROM meta')}
            if any(metadata.get(k)!=v for k,v in dict(format=FORMAT,generation=generation,project_uuid=project_uuid,complete=True).items()):
                raise ValueError('Incomplete or incompatible metadata index')
            if connection.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise ValueError('Metadata index integrity check failed')
            instance._definitions=[json.loads(row[0]) for row in connection.execute('SELECT definition_json FROM fields ORDER BY field_no')]
            instance._catalog_cache=metadata.get('catalog');instance._predicate_cache=metadata.get('predicate_catalog')
            instance._epoch_count=connection.execute('SELECT COUNT(*) FROM epochs').fetchone()[0]
        instance.details=_Details(instance)
        return instance

    def _check(self):
        if _signature(self.path)!=self._signature: raise ValueError('Metadata index changed; reopen a verified generation')

    @contextmanager
    def _connect(self,ids=None):
        self._check()
        connection=sqlite3.connect(self.path.as_uri()+'?mode=ro&immutable=1',uri=True)
        try:
            connection.execute('CREATE TEMP TABLE scope(ordinal INTEGER PRIMARY KEY,epoch_id INTEGER UNIQUE)')
            if ids is None:
                connection.execute('INSERT INTO scope SELECT epoch_id,epoch_id FROM epochs')
            else:
                connection.executemany('INSERT OR IGNORE INTO scope SELECT ?,epoch_id FROM epochs WHERE epoch_uuid=?',enumerate(ids))
            yield connection
            self._check()
        finally: connection.close()

    def values(self,ids=None,fields=None):
        return _Values(self,ids,fields)

    def rows(self):
        with self._connect() as connection:
            return {identity:json.loads(raw) for identity,raw in connection.execute('SELECT epoch_uuid,row_json FROM epochs ORDER BY epoch_id')}

    def fingerprints(self,ids=None):
        with self._connect(ids) as connection:
            return dict(connection.execute('SELECT e.epoch_uuid,e.fingerprint FROM scope s JOIN epochs e USING(epoch_id) ORDER BY s.ordinal'))

    def source_projection(self,source_sha,lazy_details=False):
        """Project one source; optionally defer per-epoch metadata decompression.

        Lazy views share the index's bounded detail cache. Cell descriptors read
        only the first epoch of each cell, matching the eager projection's rule.
        """
        with self._connect([]) as connection:
            source=connection.execute('SELECT source_json FROM sources WHERE source_sha=?',(source_sha,)).fetchone()
            if source is None: raise KeyError(source_sha)
            columns='epoch_uuid,row_json,fingerprint' if lazy_details else 'epoch_uuid,row_json,fingerprint,detail_blob'
            records=connection.execute(f'SELECT {columns} FROM epochs WHERE source_sha=? ORDER BY epoch_id',(source_sha,))
            rows,details,fingerprints,cells={},{},{},{}
            for record in records:
                identity,raw,fingerprint=record[:3]
                row=json.loads(raw);rows[identity]=row;fingerprints[identity]=fingerprint
                datum=None
                if not lazy_details:
                    datum=json.loads(zlib.decompress(record[3]));details[identity]=datum
                cell_uuid=row.get('cell_uuid')
                if cell_uuid in cells: continue
                if datum is None: datum=self.details[identity]
                cell=datum.get('metadata',{}).get('cell',{})
                raw_date=str(cell.get('start_time') or row.get('date') or '')[:10]
                for fmt in ('%m/%d/%Y','%Y-%m-%d'):
                    try:
                        raw_date=dt.datetime.strptime(raw_date,fmt).date().isoformat();break
                    except ValueError: pass
                cells[cell_uuid]=dict(cell_uuid=cell_uuid,label=row.get('cell_label'),cell_type=row.get('cell_type'),date=raw_date,start_time=cell.get('start_time'))
            if lazy_details: details=_ScopedDetails(self.details,rows)
            return dict(rows=rows,details=details,cells=cells,source=json.loads(source[0]),fingerprints=fingerprints)

    def catalog(self,ids=None,known_fields=None):
        if ids is None and known_fields is None and self._catalog_cache is not None:
            self._check();return copy.deepcopy(self._catalog_cache)
        with self._connect(ids) as connection:
            rows=[json.loads(raw) for raw, in connection.execute('SELECT row_json FROM scope JOIN epochs USING(epoch_id) ORDER BY ordinal')]
            definitions={field['id']:field for field in self._definitions}
            templates = known_fields if known_fields is not None else self.catalog()['fields'] if ids is not None else []
            for field in templates: definitions[field['id']] = field
            present = {key for key, in connection.execute('SELECT DISTINCT field_id FROM scope JOIN epoch_values USING(epoch_id) JOIN fields USING(field_no)')}
            for field in self._definitions:
                if field['id'] in present: definitions[field['id']] = field
            result,_=tree.catalog([],{},known_fields=list(definitions.values()))
            total=len(rows);family=tree.protocol_family(rows);joint_projections={}
            for field in result['fields']:
                key=field['id']
                if key.startswith('joint/'):
                    projected=dict(self.values(ids=[row['epoch_uuid'] for row in rows],fields=[key]).items())
                    joint_projections[key]=projected
                    field.update(tree._joint_summary(field,projected));continue
                stats=list(connection.execute('SELECT v.value_json,COUNT(*),MIN(s.ordinal) FROM scope s JOIN epoch_values ev USING(epoch_id) JOIN fields f USING(field_no) JOIN field_values v USING(value_id) WHERE f.field_id=? GROUP BY v.value_id ORDER BY MIN(s.ordinal)',(key,)))
                distinct=[json.loads(raw) for raw,_,_ in stats];samples=sorted(distinct,key=tree.value_order)[:5]
                examples=[('null (recorded)' if value is None else tree.value_label(value))[:160] for value in samples]
                if key in {'cell','block','group'}:
                    labels={row.get(tree.BASE_FIELDS[key][2]):f"{row.get('date','')} · {row.get('cell_label','Cell')}" if key=='cell' else row.get('block_start_time') if key=='block' else row.get('group_label') for row in rows}
                    examples=[str(labels.get(value) or value)[:160] for value in samples]
                recorded=sum(value is not None for value in distinct)
                field.update(distinct_count=len(stats),missing_count=total-sum(count for _,count,_ in stats),recorded_distinct_count=recorded,varying=recorded>1,null_count=sum(count for raw,count,_ in stats if raw=='null'),count=total,examples=examples)
            tree.annotate_grouping_fields(result['fields'],{},rows,family)
            for field in result['fields']:
                if field['id'].startswith('joint/'):
                    percell={};varies=False
                    for row in rows:
                        val=joint_projections[field['id']][row['epoch_uuid']][field['id']]
                        bucket=percell.setdefault(row.get('cell_uuid'),set());bucket.add(tree.value_key(val))
                        if len(bucket)>1: varies=True;break
                else:
                    varies=connection.execute('SELECT 1 FROM scope s JOIN epochs e USING(epoch_id) JOIN epoch_values ev USING(epoch_id) JOIN fields f USING(field_no) JOIN field_values v USING(value_id) WHERE f.field_id=? AND v.value_json!=? GROUP BY e.cell_uuid HAVING COUNT(DISTINCT ev.value_id)>1 LIMIT 1',(field['id'],'null')).fetchone() is not None
                field['varies_within_cell']=varies
            scope_ids=[row['epoch_uuid'] for row in rows]
            suggestions=_suggest(result['fields'],self,scope_ids,family)
            layout=tree.protocol_layout(result['fields'],suggestions,family)
            if layout: result['presets'].insert(0,layout)
            result.update(total=total,protocol_family=family,suggestions=suggestions,suggested_layout=layout)
        if ids is None and known_fields is None: self._catalog_cache=copy.deepcopy(result)
        return result

    def predicate_catalog(self,ids=None):
        ids=None if ids is None else tuple(ids)
        if ids is None and self._predicate_cache is not None:
            self._check();return copy.deepcopy(self._predicate_cache)
        result=self.catalog(ids)
        with self._connect(ids) as connection:
            for field in result['fields']:
                buckets=[];indexed={};types=set()
                if field['id'].startswith('joint/'):
                    projected=self.values(ids,fields=[field['id']])
                    summary=predicates.predicate_catalog({'fields':[field]},projected)['fields'][0]
                    field.update({key:summary[key] for key in ('types','choices','choices_truncated')});continue
                for raw,count in connection.execute('SELECT v.value_json,COUNT(*) FROM scope s JOIN epoch_values ev USING(epoch_id) JOIN fields f USING(field_no) JOIN field_values v USING(value_id) WHERE f.field_id=? GROUP BY v.value_id ORDER BY MIN(s.ordinal)',(field['id'],)):
                    value=json.loads(raw);kind=predicates.kind(value);types.add(kind);key=predicates.equality_key(value)
                    if key in indexed: indexed[key]['count']+=count
                    elif len(buckets)<=predicates.MAX_CHOICES:
                        bucket=dict(value=value,type=kind,count=count);buckets.append(bucket);indexed[key]=bucket
                field.update(types=sorted(types),choices=buckets[:predicates.MAX_CHOICES],choices_truncated=len(buckets)>predicates.MAX_CHOICES)
        result.update(operators=list(predicates.OPERATORS),predicate_version=1,limits=dict(max_depth=predicates.MAX_DEPTH,max_nodes=predicates.MAX_NODES,max_choices=predicates.MAX_CHOICES))
        if ids is None: self._predicate_cache=copy.deepcopy(result)
        return result

    def match(self,predicate,ids=None):
        with self._connect(ids) as connection:
            referenced=set();pending=[predicate];visited=0
            while pending and visited <= predicates.MAX_NODES:
                node=pending.pop();visited+=1
                if not isinstance(node,dict): continue
                if isinstance(node.get('field'),str): referenced.add(node['field'])
                if isinstance(node.get('not'),dict): pending.append(node['not'])
                for logic in ('all','any'):
                    if isinstance(node.get(logic),list): pending.extend(node[logic][:predicates.MAX_NODES+1])
            connection.execute('CREATE TEMP TABLE validate_fields(field_id TEXT PRIMARY KEY)')
            connection.executemany('INSERT INTO validate_fields VALUES(?)',[(key,) for key in referenced])
            class Representatives:
                def values(inner):
                    for key,raw in connection.execute('SELECT field_id,value_json FROM validate_fields JOIN fields USING(field_id) JOIN field_values USING(field_no)'):
                        yield {key:json.loads(raw)}
            validated=predicates.validate(predicate,{'fields':self._definitions},Representatives())
            universe={row[0] for row in connection.execute('SELECT epoch_id FROM scope')}
            def walk(node):
                if 'all' in node:
                    result=set(universe)
                    for child in node['all']: result.intersection_update(walk(child))
                    return result
                if 'any' in node:
                    result=set()
                    for child in node['any']: result.update(walk(child))
                    return result
                if 'not' in node: return universe-walk(node['not'])
                key=node['field'];matching=[]
                field_number=connection.execute('SELECT field_no FROM fields WHERE field_id=?',(key,)).fetchone()[0]
                for value_id,raw in connection.execute('SELECT value_id,value_json FROM field_values JOIN fields USING(field_no) WHERE field_id=?',(key,)):
                    if predicates.matches(node,{key:json.loads(raw)}): matching.append((value_id,))
                connection.execute('CREATE TEMP TABLE IF NOT EXISTS matching(value_id INTEGER PRIMARY KEY)');connection.execute('DELETE FROM matching')
                connection.executemany('INSERT INTO matching VALUES(?)',matching)
                result={row[0] for row in connection.execute('SELECT ev.epoch_id FROM epoch_values ev JOIN matching USING(value_id) JOIN scope USING(epoch_id) WHERE ev.field_no=?',(field_number,))}
                if predicates.matches(node,{}):
                    present={row[0] for row in connection.execute('SELECT epoch_id FROM scope JOIN epoch_values USING(epoch_id) JOIN fields USING(field_no) WHERE field_id=?',(key,))}
                    result.update(universe-present)
                return result
            matched=walk(validated)
            return validated,[identity for number,identity in connection.execute('SELECT epoch_id,epoch_uuid FROM scope JOIN epochs USING(epoch_id) ORDER BY ordinal') if number in matched]


class _Values(Mapping):
    def __init__(self,index,ids,fields):
        self.index=index;self.ids=None if ids is None else tuple(ids);self.fields=None if fields is None else tuple(fields);self.idset=None if self.ids is None else frozenset(self.ids);self.cache=OrderedDict();self._length=None
    def __len__(self):
        self.index._check()
        if self._length is None:
            if self.ids is None and hasattr(self.index,'_epoch_count'): self._length=self.index._epoch_count
            else:
                with self.index._connect(self.ids) as connection: self._length=connection.execute('SELECT COUNT(*) FROM scope').fetchone()[0]
        return self._length
    def __iter__(self):
        with self.index._connect(self.ids) as connection:
            for identity, in connection.execute('SELECT epoch_uuid FROM scope JOIN epochs USING(epoch_id) ORDER BY ordinal'): yield identity
    def __getitem__(self,key):
        self.index._check()
        if key not in self.cache:
            if self.idset is not None and key not in self.idset: raise KeyError(key)
            result=dict(_Values(self.index,[key],self.fields).items())
            if key not in result: raise KeyError(key)
            self.cache[key]=result[key]
            if len(self.cache)>CACHE_SIZE: self.cache.popitem(last=False)
        self.cache.move_to_end(key);return copy.deepcopy(self.cache[key])
    def items(self):
        definitions={field['id']:field for field in self.index._definitions}
        joints={}
        if self.fields is None:
            if all(key in definitions for key in tree.HISTORY_COMPONENTS): joints[tree.HISTORY_JOINT]=tree.HISTORY_COMPONENTS
            requested=None
        else:
            requested=set(self.fields)
            for key in self.fields:
                if key.startswith('joint/'): joints[key]=tree.joint_components(key,definitions)
                elif key not in definitions: raise ValueError('Unknown indexed field: '+key)
        required=None if requested is None else requested|{key for components in joints.values() for key in components}
        with self.index._connect(self.ids) as connection:
            connection.execute('CREATE TEMP TABLE wanted(field_no INTEGER PRIMARY KEY)')
            if required is None: connection.execute('INSERT INTO wanted SELECT field_no FROM fields')
            else: connection.executemany('INSERT INTO wanted SELECT field_no FROM fields WHERE field_id=?',[(key,) for key in required])
            current_id=None;current={}
            query='''SELECT e.epoch_uuid,f.field_id,v.value_json FROM scope s JOIN epochs e USING(epoch_id)
                LEFT JOIN epoch_values ev ON ev.epoch_id=e.epoch_id AND ev.field_no IN (SELECT field_no FROM wanted)
                LEFT JOIN fields f ON f.field_no=ev.field_no LEFT JOIN field_values v ON v.value_id=ev.value_id
                ORDER BY s.ordinal,f.field_no'''
            def finish():
                for key,components in joints.items(): current[key]=tree.joint_value(current,components)
                return current if requested is None else {key:value for key,value in current.items() if key in requested}
            for identity,key,raw in connection.execute(query):
                if identity!=current_id:
                    if current_id is not None: yield current_id,finish()
                    current_id=identity;current={}
                if key is not None: current[key]=json.loads(raw)
            if current_id is not None: yield current_id,finish()
    def values(self):
        for _,value in self.items(): yield value


class _Details(Mapping):
    def __init__(self,index): self.index=index;self.cache=OrderedDict();self.lock=threading.RLock()
    def __len__(self):
        self.index._check();return self.index._epoch_count
    def __iter__(self): return iter(self.index.values())
    def __getitem__(self,key):
        with self.lock:
            self.index._check()
            if key not in self.cache:
                with self.index._connect([]) as connection:
                    row=connection.execute('SELECT detail_blob FROM epochs WHERE epoch_uuid=?',(key,)).fetchone()
                    if row is None: raise KeyError(key)
                    self.cache[key]=json.loads(zlib.decompress(row[0]))
                    if len(self.cache)>CACHE_SIZE: self.cache.popitem(last=False)
            self.cache.move_to_end(key);return copy.deepcopy(self.cache[key])

class _ScopedDetails(Mapping):
    def __init__(self,details,rows):
        self.details=details
        # Pin membership independently of the caller's mutable row dictionary.
        self.identities=tuple(rows);self.identity_set=frozenset(self.identities)
    def __len__(self):
        self.details.index._check();return len(self.identities)
    def __iter__(self):
        self.details.index._check();return iter(self.identities)
    def __getitem__(self,key):
        self.details.index._check()
        if key not in self.identity_set: raise KeyError(key)
        return self.details[key]


def _suggest(fields,index,ids,family):
    # Same ranking policy as tree.suggest_fields; fetch one candidate column at
    # a time instead of retaining every epoch's complete metadata projection.
    priority={'protocol':0,'date':1,'cell type':2,'group label':3,'parameters/frequencyCutoff':4,'parameters/currentSD':5,'parameters/currentMean':6,'parameters/currentSpotSize':7,'cell':8,'parameters/useRandomSeed':9}
    if family: priority={key:i for i,key in enumerate(tree.PROTOCOL_AXES[family])}
    candidates=[]
    for field in fields:
        field.update(suggested_rank=None,suggestion_reason='')
        count=field['recorded_distinct_count'];high=count>24 or count>max(5,len(ids)*.25);field['high_cardinality']=high
        if not field['varying'] or high or field.get('grouping_role')=='technical' or field['id'] in {'block','block time','group'}: continue
        if field['id'].rsplit('/',1)[-1].lower() in {'seed','uuid','id'}: continue
        candidates.append(field)
    candidates.sort(key=lambda f:(priority.get(f['id'],20 if f['category']=='Parameters' else 30),not f.get('varies_within_cell',False),f['missing_count'],f['recorded_distinct_count'],f['id']))
    seen=set();suggestions=[]
    for field in candidates:
        key=field['id']
        signature=tuple(tree.value_key(current[key]) if key in current else '__missing__' for current in index.values(ids,fields=[key]).values())
        if signature in seen: continue
        if family and key.startswith('metadata/block/parameters/') and 'parameters/'+key.rsplit('/',1)[-1] in {f['id'] for f in candidates}: continue
        if not family or key not in priority: seen.add(signature)
        field['suggested_rank']=len(suggestions);field['suggestion_reason']=f"{field['recorded_distinct_count']} recorded values across {field['count']} epochs"
        if field.get('varies_within_cell'): field['suggestion_reason']+='; varies within cells'
        if field['missing_count']: field['suggestion_reason']+=f"; {field['missing_count']} missing stay visible"
        suggestions.append(key)
        if len(suggestions)==6: break
    return suggestions
