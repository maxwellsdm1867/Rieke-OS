"""Disposable, incremental shared-tag membership index with exact text semantics.

Canonical annotations remain in SQL. This index stores no waveform or acquisition
metadata and never substitutes its records for the visible provenance response.
A transactional source token fences every rebuild/delta; a caller must also fence
that token across membership and its later visible annotation/revision reads.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import sys
import zlib
import hashlib
import threading
from functools import wraps
from collections import OrderedDict
from pathlib import Path


FIELDS={'annotations/cell/tags':('cell',),
        'annotations/epoch/tags':('epoch',),
        'annotations/effective/tags':('cell','epoch')}
SCOPE_CACHE_ROWS=200000
MATCH_CACHE_BYTES=64*1024*1024
MATCH_DELTA_MAX_RECORDS=1000
CATALOG_FIELDS=(*FIELDS,'annotations/authors','annotations/author_uuids')


class SharedTagsChanged(ValueError):
    pass


def _serialized(operation):
    """One owner at a time for SQLite, its temp scopes and derived caches."""
    @wraps(operation)
    def guarded(self, *args, **kwargs):
        with self._lock:
            return operation(self, *args, **kwargs)
    return guarded


class SharedTagIndex:
    """One derived on-disk index with bounded browse and aggregate scopes.

    generation() returns a verified immutable authority token, or None when its
    contract is unavailable. changes(old) returns (target keys, current token),
    or None when a full rebuild is required. records(keys) yields canonical rows;
    keys=None requests a bounded streaming full scan. validate(row) returns its
    exact validated tag strings and must check target/profile/author/revision.
    """
    def __init__(self,*,generation,changes,records,validate):
        self._lock=threading.RLock()
        self.generation,self.changes,self.records,self.validate=generation,changes,records,validate
        self.token=None;self.folder=None;self.connection=None
        self.scopes={kind:None for kind in ('filter','summary','catalog')};self.scope_revisions=dict.fromkeys(self.scopes,0)
        self.summary_cache=None;self.catalog_cache={}
        self.shared_vocabulary=None
        self.tag_ids=OrderedDict()
        self.match_cache=OrderedDict();self.match_cache_bytes=0
        self.stats={'full_builds':0,'delta_updates':0,'rows_loaded':0,'rows_indexed':0}

    def _open(self):
        if self.connection is not None:return self.connection
        self.folder=tempfile.TemporaryDirectory(prefix='rieke-shared-tag-index-')
        # Waitress hands successive requests to different threads. Every public
        # operation below holds _lock for its full cursor/transaction lifetime;
        # this flag permits ownership transfer, never concurrent SQLite access.
        self.connection=sqlite3.connect(Path(self.folder.name)/'membership.sqlite',check_same_thread=False)
        self.connection.create_collation('TAG_ORDER',lambda left,right:
            ((left.casefold(),left)>(right.casefold(),right))-((left.casefold(),left)<(right.casefold(),right)))
        self.connection.create_function('pack_array',1,lambda value:zlib.compress(value.encode('utf-8'),1),deterministic=True)
        self.connection.create_function('array_prefix',1,lambda value:zlib.decompress(value).decode('utf-8')[:160],deterministic=True)
        self.connection.create_function('array_hash',1,lambda value:hashlib.sha256(value).digest(),deterministic=True)
        # This private working database is disposable after a crash. Keep
        # transactional rollback, but reserve disk durability barriers for the
        # canonical SQL commit and explicitly sealed reusable checkpoints.
        self.connection.executescript('''
            PRAGMA cache_size=-8192;
            PRAGMA temp_store=FILE;
            PRAGMA auto_vacuum=INCREMENTAL;
            PRAGMA journal_mode=DELETE;
            PRAGMA synchronous=OFF;
            PRAGMA foreign_keys=ON;
            CREATE TABLE records(record_id INTEGER PRIMARY KEY,kind TEXT COLLATE BINARY,target TEXT COLLATE BINARY,
                profile TEXT COLLATE BINARY,author TEXT,revision INTEGER,
                UNIQUE(kind,target,profile));
            CREATE TABLE tag_values(tag_id INTEGER PRIMARY KEY,tag TEXT COLLATE BINARY UNIQUE);
            CREATE TABLE tag_memberships(record_id INTEGER REFERENCES records(record_id) ON DELETE CASCADE,
                tag_id INTEGER REFERENCES tag_values(tag_id),PRIMARY KEY(record_id,tag_id)) WITHOUT ROWID;
            CREATE INDEX memberships_by_tag ON tag_memberships(tag_id,record_id);
            CREATE VIEW tags AS SELECT r.kind,r.target,r.profile,v.tag FROM tag_memberships m
                JOIN records r ON r.record_id=m.record_id JOIN tag_values v ON v.tag_id=m.tag_id;
            CREATE TEMP TABLE changed_tag_values(tag_id INTEGER PRIMARY KEY);
            CREATE TABLE filter_scope(position INTEGER PRIMARY KEY,epoch_uuid TEXT COLLATE BINARY UNIQUE,cell_uuid TEXT COLLATE BINARY);
            CREATE INDEX filter_scope_cell ON filter_scope(cell_uuid);
            CREATE TABLE summary_scope(position INTEGER PRIMARY KEY,epoch_uuid TEXT COLLATE BINARY UNIQUE,cell_uuid TEXT COLLATE BINARY);
            CREATE INDEX summary_scope_cell ON summary_scope(cell_uuid);
            CREATE TABLE catalog_scope(position INTEGER PRIMARY KEY,epoch_uuid TEXT COLLATE BINARY UNIQUE,cell_uuid TEXT COLLATE BINARY);
            CREATE INDEX catalog_scope_cell ON catalog_scope(cell_uuid);
            CREATE TEMP TABLE predicate_values(literal_id INTEGER,tag TEXT COLLATE BINARY,
                PRIMARY KEY(literal_id,tag)) WITHOUT ROWID;
            CREATE TEMP TABLE affected_positions(position INTEGER PRIMARY KEY);
            CREATE TEMP TABLE catalog_values(field INTEGER,position INTEGER,bucket_id INTEGER,
                PRIMARY KEY(field,position)) WITHOUT ROWID;
            CREATE INDEX catalog_values_by_bucket ON catalog_values(bucket_id,position);
            CREATE TEMP TABLE catalog_examples(example_id INTEGER PRIMARY KEY,prefix TEXT COLLATE BINARY UNIQUE);
            CREATE TEMP TABLE changed_examples(example_id INTEGER PRIMARY KEY);
            CREATE TEMP TABLE catalog_buckets(bucket_id INTEGER PRIMARY KEY,field INTEGER,value BLOB,value_hash BLOB,
                amount INTEGER,first_position INTEGER,example_id INTEGER);
            CREATE INDEX catalog_bucket_lookup ON catalog_buckets(field,value_hash);
            CREATE INDEX catalog_choices ON catalog_buckets(field,first_position);
            CREATE INDEX catalog_examples_by_bucket ON catalog_buckets(example_id,field);
            CREATE TEMP TABLE catalog_fields(field INTEGER PRIMARY KEY,amount INTEGER,distinct_count INTEGER);
            CREATE TEMP TABLE catalog_changes(position INTEGER PRIMARY KEY,old_bucket INTEGER,new_value BLOB,old_value BLOB,old_example INTEGER);
            CREATE TEMP TABLE affected_cells(cell_uuid TEXT PRIMARY KEY) WITHOUT ROWID;
            CREATE TEMP TABLE summary_cells(cell_uuid TEXT PRIMARY KEY,tagged_cell INTEGER,tagged_epochs INTEGER) WITHOUT ROWID;
            CREATE TEMP TABLE summary_cell_tags(cell_uuid TEXT,tag TEXT COLLATE BINARY,epoch_count INTEGER,
                PRIMARY KEY(cell_uuid,tag)) WITHOUT ROWID;
            CREATE TEMP TABLE summary_tags(tag TEXT COLLATE BINARY PRIMARY KEY,epoch_count INTEGER,cell_count INTEGER) WITHOUT ROWID;
            CREATE INDEX summary_rank ON summary_tags(epoch_count DESC,tag COLLATE TAG_ORDER);
            CREATE TEMP TABLE summary_totals(id INTEGER PRIMARY KEY,tagged_cells INTEGER,tagged_epochs INTEGER,total_tags INTEGER);
            CREATE TEMP TABLE summary_changes(tag TEXT COLLATE BINARY PRIMARY KEY,amount INTEGER) WITHOUT ROWID;
        ''')
        return self.connection

    @_serialized
    def refresh(self):
        current=self.generation()
        if current is None:return False
        if current==self.token:return True
        change=self.changes(self.token) if self.token is not None else None
        keys=None
        if change is not None:
            keys,current=change
            if current is None:return False
            # Profile display metadata is separate from the author_name saved
            # with each annotation. It changes freshness, not historical text.
            keys=[key for key in keys if key['target_kind'] in ('cell','epoch')]
        if keys is None and self.connection is not None:
            # A lost authority/changefeed already makes the old index unusable.
            # Drop that disposable projection before rebuilding so a complete
            # old database and a full rollback journal never coexist on disk.
            self.close()
        db=self._open();loaded=0;removed=0;self.tag_ids.clear()
        previous_tags={}
        # Large external batches conservatively drop matches rather than keep
        # another unbounded copy of every changed record's tag strings.
        changed_tags=set() if keys is not None and len(keys)<=MATCH_DELTA_MAX_RECORDS and self.match_cache else None
        reset_vocabulary=keys is not None and len(keys)>MATCH_DELTA_MAX_RECORDS and self.shared_vocabulary is not None
        try:
            with db:
                if reset_vocabulary:
                    # sqlite3's context manager does not begin a transaction
                    # for DDL alone. Include the lazy reset in rollback too.
                    if not db.in_transaction:db.execute('BEGIN')
                    self.shared_vocabulary.discard()
                vocabulary_before=self.shared_vocabulary.before(keys) if self.shared_vocabulary is not None and keys is not None and not reset_vocabulary else None
                if changed_tags is not None:
                    for key in keys:
                        identity=(key['target_kind'],key['target_uuid'],key['profile_uuid'])
                        previous_tags[identity]={row[0] for row in db.execute('SELECT v.tag FROM records r '
                            'JOIN tag_memberships m ON m.record_id=r.record_id JOIN tag_values v ON v.tag_id=m.tag_id '
                            'WHERE r.kind=? AND r.target=? AND r.profile=?',identity)}
                if keys is None:
                    db.execute('DELETE FROM tag_memberships');db.execute('DELETE FROM records');db.execute('DELETE FROM tag_values')
                else:
                    params=[(key['target_kind'],key['target_uuid'],key['profile_uuid']) for key in keys]
                    db.execute('DELETE FROM changed_tag_values')
                    db.executemany('INSERT OR IGNORE INTO changed_tag_values SELECT m.tag_id FROM records r JOIN tag_memberships m ON m.record_id=r.record_id WHERE r.kind=? AND r.target=? AND r.profile=?',params)
                    removed=db.executemany('DELETE FROM records WHERE kind=? AND target=? AND profile=?',params).rowcount
                for row in self.records(keys):
                    values=self.validate(row)
                    key=(row['target_kind'],row['target_uuid'],row['profile_uuid'])
                    if changed_tags is not None:
                        changed_tags.update(previous_tags.pop(key,set()) ^ set(values))
                    record_id=db.execute('INSERT INTO records(kind,target,profile,author,revision) VALUES (?,?,?,?,?)',(*key,row['author_name'],row['revision'])).lastrowid
                    ids=[]
                    for tag in values:
                        tag_id=self.tag_ids.get(tag)
                        if tag_id is None:
                            found=db.execute('SELECT tag_id FROM tag_values WHERE tag=?',(tag,)).fetchone()
                            tag_id=found[0] if found else db.execute('INSERT INTO tag_values(tag) VALUES (?)',(tag,)).lastrowid
                            self.tag_ids[tag]=tag_id
                            if len(self.tag_ids)>8192:self.tag_ids.popitem(last=False)
                        else:self.tag_ids.move_to_end(tag)
                        ids.append(tag_id)
                    db.executemany('INSERT INTO tag_memberships VALUES (?,?)',((record_id,tag_id) for tag_id in ids))
                    loaded+=1
                if keys is not None:
                    db.execute('DELETE FROM tag_values WHERE tag_id IN (SELECT c.tag_id FROM changed_tag_values c WHERE NOT EXISTS (SELECT 1 FROM tag_memberships m WHERE m.tag_id=c.tag_id))')
                if changed_tags is not None:
                    for values in previous_tags.values():changed_tags.update(values)
                self._update_catalog(keys)
                self._update_summary(keys)
                if vocabulary_before is not None:self.shared_vocabulary.after(keys,vocabulary_before)
                if self.generation()!=current:
                    raise SharedTagsChanged('Shared tags changed while loading this selection. Refresh and try again.')
            self.token=copy.deepcopy(current)
            if reset_vocabulary:self.shared_vocabulary=None
            self._invalidate_matches(changed_tags)
            self.stats['full_builds' if keys is None else 'delta_updates']+=1
            self.stats['rows_loaded']+=loaded
            self.stats['rows_indexed']=loaded if keys is None else self.stats['rows_indexed']-removed+loaded
            # Reclaim bounded batches of free pages after large removals. Only
            # this derived database is touched; its page cache is capped at8MiB.
            db.execute('PRAGMA incremental_vacuum(256)')
            return True
        except Exception:
            # No invalid or mixed-generation membership is published. SQLite's
            # transaction retains the previous complete index after a failure.
            self.tag_ids.clear();raise

    def _scope(self,rows,kind='filter'):
        identities=tuple((row['epoch_uuid'],row['cell_uuid']) for row in rows)
        if identities==self.scopes[kind]:return
        if len({key for key,_ in identities})!=len(identities):
            raise ValueError('Expected unique epoch identities in the tag-filter scope')
        db=self._open();table=kind+'_scope'
        with db:
            db.execute('DELETE FROM '+table)
            db.executemany('INSERT INTO '+table+' VALUES (?,?,?)',((position,*pair) for position,pair in enumerate(identities)))
            if kind=='catalog':self._clear_catalog()
            if kind=='summary':self._clear_summary()
        # Scopes retain only already-owned UUID strings; they never retain tag
        # provenance. Separate scopes keep pagination from discarding aggregate
        # work for the overview or project field catalog.
        self.scopes[kind]=identities if len(identities)<=SCOPE_CACHE_ROWS else None
        self.scope_revisions[kind]+=1
        if kind=='summary':self.summary_cache=None
        if kind=='catalog':self.catalog_cache={}
        if kind=='filter':self.match_cache.clear();self.match_cache_bytes=0

    def _check_generation(self):
        if self.generation()!=self.token:
            raise SharedTagsChanged('Shared tags changed while loading this selection. Refresh and try again.')

    @staticmethod
    def _tag_dependencies(filters,predicate):
        """Exact literals sufficient for contains/boolean queries; None is broad.

        Array equality and tagged/empty-state tests depend on the whole tag set,
        so any changed tag conservatively invalidates those cached results.
        """
        if 'tagged' in filters:return None
        dependencies={filters['tag']} if 'tag' in filters else set()
        def walk(node):
            if 'not' in node:return walk(node['not'])
            for logic in ('all','any'):
                if logic in node:
                    result=set()
                    for child in node[logic]:
                        current=walk(child)
                        if current is None:return None
                        result.update(current)
                    return result
            if node['operator']=='contains' and node['field'] in FIELDS:
                return {node['value']} if isinstance(node['value'],str) else set()
            if node['operator'] in ('exists','missing','is_null'):return set()
            return None
        if predicate is not None:
            current=walk(predicate)
            if current is None:return None
            dependencies.update(current)
        return dependencies

    def _invalidate_matches(self,changed_tags):
        if changed_tags is None:
            self.match_cache.clear();self.match_cache_bytes=0
            return
        if not changed_tags:return
        for key,(_,size) in list(self.match_cache.items()):
            dependencies=self._tag_dependencies(*json.loads(key))
            if dependencies is None or not dependencies.isdisjoint(changed_tags):
                del self.match_cache[key];self.match_cache_bytes-=size

    @_serialized
    def summary(self,rows):
        """Exact overview counts/top vocabulary, with no per-epoch chip copies."""
        self._scope(rows,'summary');key=(self.token,self.scope_revisions['summary'])
        if self.summary_cache is not None and self.summary_cache[0]==key:
            self._check_generation();return copy.deepcopy(self.summary_cache[1])
        db=self.connection
        stored=db.execute('SELECT tagged_cells,tagged_epochs,total_tags FROM summary_totals WHERE id=1').fetchone()
        if stored is None:
            with db:
                db.execute('INSERT INTO summary_totals VALUES (1,0,0,0)')
                for (cell,) in db.execute('SELECT DISTINCT cell_uuid FROM summary_scope'):
                    self._replace_summary_cell(cell)
            stored=db.execute('SELECT tagged_cells,tagged_epochs,total_tags FROM summary_totals WHERE id=1').fetchone()
        tagged_cells,tagged_epochs,total=stored
        counts=db.execute('SELECT tag,epoch_count,cell_count FROM summary_tags ORDER BY epoch_count DESC,tag COLLATE TAG_ORDER LIMIT 12').fetchall()
        result={'shared_tagged_cells':tagged_cells,'shared_tagged_epochs':tagged_epochs,
            'tags':[{'tag':tag,'epoch_count':epochs,'cell_count':cells} for tag,epochs,cells in counts],
            'total_tags':total,'truncated':total>12}
        self._check_generation();self.summary_cache=(key,copy.deepcopy(result))
        return result

    def _clear_summary(self):
        for table in ('summary_cells','summary_cell_tags','summary_tags','summary_totals','summary_changes'):
            self.connection.execute('DELETE FROM '+table)

    def _replace_summary_cell(self,cell):
        """Reconcile one exact eligible cell, retaining profile/inheritance unions."""
        db=self.connection;difference=0
        previous=db.execute('SELECT tagged_cell,tagged_epochs FROM summary_cells WHERE cell_uuid=?',(cell,)).fetchone() or (0,0)
        for tag,amount in db.execute('SELECT tag,epoch_count FROM summary_cell_tags WHERE cell_uuid=?',(cell,)):
            db.execute('UPDATE summary_tags SET epoch_count=epoch_count-?,cell_count=cell_count-1 WHERE tag=?',(amount,tag))
            difference-=db.execute('DELETE FROM summary_tags WHERE tag=? AND cell_count=0',(tag,)).rowcount
        db.execute('DELETE FROM summary_cell_tags WHERE cell_uuid=?',(cell,))
        db.execute('DELETE FROM summary_changes')
        db.execute("INSERT INTO summary_changes SELECT v.tag,COUNT(DISTINCT s.epoch_uuid) FROM summary_scope s CROSS JOIN records r ON r.kind='epoch' AND r.target=s.epoch_uuid JOIN tag_memberships m ON m.record_id=r.record_id JOIN tag_values v ON v.tag_id=m.tag_id WHERE s.cell_uuid=? GROUP BY v.tag",(cell,))
        size=db.execute('SELECT COUNT(*) FROM summary_scope WHERE cell_uuid=?',(cell,)).fetchone()[0]
        db.execute("INSERT OR REPLACE INTO summary_changes SELECT tag,? FROM tags WHERE kind='cell' AND target=? GROUP BY tag",(size,cell))
        tagged_cell=db.execute("SELECT EXISTS (SELECT 1 FROM tags WHERE kind='cell' AND target=?)",(cell,)).fetchone()[0]
        tagged_epochs=size if tagged_cell else db.execute("SELECT COUNT(*) FROM summary_scope s WHERE s.cell_uuid=? AND EXISTS (SELECT 1 FROM tags WHERE kind='epoch' AND target=s.epoch_uuid)",(cell,)).fetchone()[0]
        for tag,amount in db.execute('SELECT tag,amount FROM summary_changes'):
            db.execute('INSERT INTO summary_cell_tags VALUES (?,?,?)',(cell,tag,amount))
            difference+=db.execute('INSERT OR IGNORE INTO summary_tags VALUES (?,0,0)',(tag,)).rowcount
            db.execute('UPDATE summary_tags SET epoch_count=epoch_count+?,cell_count=cell_count+1 WHERE tag=?',(amount,tag))
        db.execute('INSERT OR REPLACE INTO summary_cells VALUES (?,?,?)',(cell,tagged_cell,tagged_epochs))
        db.execute('UPDATE summary_totals SET tagged_cells=tagged_cells+?,tagged_epochs=tagged_epochs+?,total_tags=total_tags+? WHERE id=1',
            (tagged_cell-previous[0],tagged_epochs-previous[1],difference))

    def _update_summary(self,keys):
        if keys is None:self._clear_summary();return
        db=self.connection
        if not keys or db.execute('SELECT 1 FROM summary_totals WHERE id=1').fetchone() is None:return
        db.execute('DELETE FROM affected_cells')
        for key in keys:
            column='cell_uuid' if key['target_kind']=='cell' else 'epoch_uuid'
            db.execute('INSERT OR IGNORE INTO affected_cells SELECT DISTINCT cell_uuid FROM summary_scope WHERE '+column+'=?',(key['target_uuid'],))
        for (cell,) in db.execute('SELECT cell_uuid FROM affected_cells'):
            self._replace_summary_cell(cell)

    @staticmethod
    def _array_sql(field):
        """Sorted exact union; the scalar JSON result exists only for one row."""
        if field in FIELDS:
            scopes=[f"(kind='{kind}' AND target=s.{'cell_uuid' if kind=='cell' else 'epoch_uuid'})"
                    for kind in FIELDS[field]]
            source='SELECT DISTINCT tag AS value FROM tags WHERE '+' OR '.join(scopes)+' ORDER BY value'
        elif field in ('annotations/authors','annotations/author_uuids'):
            column='author' if field=='annotations/authors' else 'profile'
            source=f'''SELECT DISTINCT r.{column} AS value FROM records r WHERE
                ((r.kind='cell' AND r.target=s.cell_uuid) OR (r.kind='epoch' AND r.target=s.epoch_uuid))
                AND EXISTS (SELECT 1 FROM tags t WHERE t.kind=r.kind AND t.target=r.target AND t.profile=r.profile)
                ORDER BY value'''
        else:raise ValueError('Unsupported shared annotation catalog field')
        return '(SELECT json_group_array(value) FROM ('+source+'))'

    def _clear_catalog(self):
        for table in ('catalog_values','catalog_buckets','catalog_fields','catalog_changes','catalog_examples','changed_examples'):
            self.connection.execute('DELETE FROM '+table)

    def _update_catalog(self,keys):
        """Update only changed members of any materialized active-scope catalog."""
        if keys is None:self._clear_catalog();return
        db=self.connection
        fields=[row[0] for row in db.execute('SELECT field FROM catalog_fields')]
        if not fields or not keys:return
        db.execute('DELETE FROM affected_positions')
        for key in keys:
            column='cell_uuid' if key['target_kind']=='cell' else 'epoch_uuid'
            db.execute('INSERT OR IGNORE INTO affected_positions SELECT position FROM catalog_scope WHERE '+column+'=?',(key['target_uuid'],))
        db.execute('DELETE FROM changed_examples')
        for field in fields:
            db.execute('DELETE FROM catalog_changes')
            db.execute('INSERT INTO catalog_changes SELECT s.position,c.bucket_id,pack_array('+self._array_sql(CATALOG_FIELDS[field])+'),b.value,b.example_id'+
                ' FROM affected_positions a JOIN catalog_scope s ON s.position=a.position JOIN catalog_values c ON c.field=? AND c.position=s.position JOIN catalog_buckets b ON b.bucket_id=c.bucket_id',(field,))
            difference=0
            for position,old,new,old_example in db.execute('SELECT position,old_bucket,new_value,old_example FROM catalog_changes WHERE old_value!=new_value'):
                db.execute('DELETE FROM catalog_values WHERE field=? AND position=?',(field,position))
                db.execute('UPDATE catalog_buckets SET amount=amount-1 WHERE bucket_id=?',(old,))
                removed=db.execute('DELETE FROM catalog_buckets WHERE bucket_id=? AND amount=0',(old,)).rowcount
                difference-=removed
                if removed:db.execute('INSERT OR IGNORE INTO changed_examples VALUES (?)',(old_example,))
                db.execute('UPDATE catalog_buckets SET first_position=(SELECT MIN(position) FROM catalog_values WHERE bucket_id=?) WHERE bucket_id=? AND first_position=?',
                    (old,old,position))
                found=db.execute('SELECT bucket_id FROM catalog_buckets WHERE field=? AND value_hash=array_hash(?) AND value=?',(field,new,new)).fetchone()
                if found:bucket=found[0]
                else:
                    prefix=zlib.decompress(new).decode('utf-8')[:160]
                    db.execute('INSERT OR IGNORE INTO catalog_examples(prefix) VALUES (?)',(prefix,))
                    example=db.execute('SELECT example_id FROM catalog_examples WHERE prefix=?',(prefix,)).fetchone()[0]
                    bucket=db.execute('INSERT INTO catalog_buckets(field,value,value_hash,amount,first_position,example_id) VALUES (?,?,array_hash(?),0,?,?)',(field,new,new,position,example)).lastrowid
                    difference+=1
                db.execute('INSERT INTO catalog_values VALUES (?,?,?)',(field,position,bucket))
                db.execute('UPDATE catalog_buckets SET amount=amount+1,first_position=MIN(first_position,?) WHERE bucket_id=?',(position,bucket))
            db.execute('UPDATE catalog_fields SET distinct_count=distinct_count+? WHERE field=?',(difference,field))
        db.execute('DELETE FROM catalog_changes')
        db.execute('DELETE FROM catalog_examples WHERE example_id IN (SELECT c.example_id FROM changed_examples c WHERE NOT EXISTS (SELECT 1 FROM catalog_buckets b WHERE b.example_id=c.example_id))')

    @_serialized
    def catalog(self,rows,fields):
        """Exact metrics over lossless compressed arrays and integer buckets.

        The digest is only a small lookup index. Every lookup also compares the
        complete compressed bytes, so collisions cannot merge distinct arrays.
        The displayed examples are truncated to160 characters. Sorting those
        prefixes gives exactly the same displayed examples as sorting complete
        JSON arrays first; equal prefixes remain equal after truncation.
        """
        self._scope(rows,'catalog');key=(self.token,self.scope_revisions['catalog']);result={};db=self.connection
        for field in fields:
            field_id=CATALOG_FIELDS.index(field)
            cached=self.catalog_cache.get(field)
            if cached is not None and cached[0]==key:
                result[field]=copy.deepcopy(cached[1]);continue
            stored=db.execute('SELECT amount,distinct_count FROM catalog_fields WHERE field=?',(field_id,)).fetchone()
            if stored is None:
                with db:
                    db.execute('DELETE FROM catalog_changes')
                    db.execute('INSERT INTO catalog_changes SELECT s.position,NULL,pack_array('+self._array_sql(field)+'),NULL,NULL FROM catalog_scope s')
                    db.execute('INSERT OR IGNORE INTO catalog_examples(prefix) SELECT DISTINCT array_prefix(new_value) FROM catalog_changes')
                    db.execute('INSERT INTO catalog_buckets(field,value,value_hash,amount,first_position,example_id) SELECT ?,c.new_value,array_hash(c.new_value),COUNT(*),MIN(c.position),e.example_id FROM catalog_changes c JOIN catalog_examples e ON e.prefix=array_prefix(c.new_value) GROUP BY c.new_value',(field_id,))
                    db.execute('INSERT INTO catalog_values SELECT ?,c.position,b.bucket_id FROM catalog_changes c CROSS JOIN catalog_buckets b ON b.field=? AND b.value_hash=array_hash(c.new_value) AND b.value=c.new_value',(field_id,field_id))
                    count=db.execute('SELECT COUNT(*) FROM catalog_scope').fetchone()[0]
                    distinct=db.execute('SELECT COUNT(*) FROM catalog_buckets WHERE field=?',(field_id,)).fetchone()[0]
                    db.execute('INSERT INTO catalog_fields VALUES (?,?,?)',(field_id,count,distinct))
                    db.execute('DELETE FROM catalog_changes')
            else:count,distinct=stored
            examples=[row[0] for row in db.execute('SELECT e.prefix FROM catalog_examples e CROSS JOIN catalog_buckets b ON b.example_id=e.example_id WHERE b.field=? ORDER BY e.prefix LIMIT 5',(field_id,))]
            choices=[{'value':json.loads(zlib.decompress(value)),'type':'array','count':amount} for value,amount in db.execute(
                'SELECT value,amount FROM catalog_buckets WHERE field=? ORDER BY first_position LIMIT 50',(field_id,))]
            current={'count':count,'distinct_count':distinct,'recorded_distinct_count':distinct,
                'missing_count':0,'null_count':0,'varying':distinct>1,'examples':examples,
                'grouping_role':'annotation','grouping_priority':100,'varies_within_cell':False,
                'suggested_rank':None,'suggestion_reason':'','high_cardinality':distinct>24,
                'active_types':['array'] if count else [],'types':['array'],'types_scope':'project_annotations',
                'element_types':['string'],'choices':choices,'choices_truncated':distinct>50}
            self.catalog_cache[field]=(key,copy.deepcopy(current));result[field]=current
        self._check_generation()
        return result

    @staticmethod
    def _contains(field,value,params):
        if not isinstance(value,str):return '0'
        parts=[]
        for kind in FIELDS[field]:
            column='cell_uuid' if kind=='cell' else 'epoch_uuid'
            source=("SELECT r.target FROM records r CROSS JOIN tag_memberships m ON m.record_id=r.record_id WHERE r.kind='cell' AND m.tag_id=(SELECT tag_id FROM tag_values WHERE tag=?)" if kind=='cell' else
                "SELECT r.target FROM tag_values v JOIN tag_memberships m ON m.tag_id=v.tag_id JOIN records r ON r.record_id=m.record_id WHERE v.tag=? AND r.kind='epoch'")
            parts.append(f"s.{column} IN ({source})")
            params.append(value)
        return '('+' OR '.join(parts)+')'

    def _equal(self,field,value,params):
        # Display/filter arrays are exact sorted unions across profiles. Typed
        # scalars, repeated values and differently ordered arrays cannot equal.
        if (not isinstance(value,list) or any(not isinstance(tag,str) for tag in value)
                or value!=sorted(set(value))):return '0'
        # Store array literals once instead of expanding one SQL parameter and
        # subquery per tag per scope. The public grammar permits enough literals
        # to exceed SQLite's platform-dependent variable limit if expanded.
        literal_id=self._literal_id;self._literal_id+=1
        if value:
            self.connection.executemany('INSERT INTO predicate_values VALUES (?,?)',
                ((literal_id,tag) for tag in value))
        parts=[];scopes=[]
        if value:
            def rarity(tag):
                key=(field,tag)
                if key not in self._rarity:
                    amount=0
                    for kind in FIELDS[field]:
                        # Bounded probes select an effective seed without a
                        # vocabulary-wide count. A cell match can inherit to
                        # many epochs, so conservatively saturate its estimate.
                        limit=1 if kind=='cell' else 32
                        if kind=='cell':
                            count=self.connection.execute("SELECT COUNT(*) FROM (SELECT 1 FROM records r CROSS JOIN tag_memberships m ON m.record_id=r.record_id WHERE r.kind='cell' AND m.tag_id=(SELECT tag_id FROM tag_values WHERE tag=?) LIMIT 1)",(tag,)).fetchone()[0]
                        else:
                            count=self.connection.execute("SELECT COUNT(*) FROM (SELECT 1 FROM tag_values v JOIN tag_memberships m ON m.tag_id=v.tag_id JOIN records r ON r.record_id=m.record_id WHERE v.tag=? AND r.kind='epoch' LIMIT 32)",(tag,)).fetchone()[0]
                        amount+=32 if kind=='cell' and count else count
                    self._rarity[key]=amount
                return self._rarity[key]
            seed=min(value,key=rarity)
            parts.append(self._contains(field,seed,params))
        for kind in FIELDS[field]:
            column='cell_uuid' if kind=='cell' else 'epoch_uuid'
            outside=f' AND tag NOT IN (SELECT tag FROM predicate_values WHERE literal_id={literal_id})' if value else ''
            parts.append(f"NOT EXISTS (SELECT 1 FROM tags WHERE kind='{kind}' AND target=s.{column}{outside})")
            scopes.append(f"(kind='{kind}' AND target=s.{column})")
        if value:
            parts.append('(SELECT COUNT(DISTINCT tag) FROM tags WHERE '+' OR '.join(scopes)+f')={len(value)}')
        return '('+' AND '.join(parts)+')'

    def _predicate(self,node,params):
        if 'all' in node:return '('+(' AND '.join(self._predicate(child,params) for child in node['all']) or '1')+')'
        if 'any' in node:return '('+(' OR '.join(self._predicate(child,params) for child in node['any']) or '0')+')'
        if 'not' in node:return '(NOT '+self._predicate(node['not'],params)+')'
        field,operator=node['field'],node['operator']
        if field not in FIELDS:raise ValueError('Only shared tag arrays are available in this index')
        if operator=='exists':return '1'
        if operator in ('missing','is_null'):return '0'
        value=node['value']
        if operator=='contains':return self._contains(field,value,params)
        if operator in ('eq','ne'):
            equal=self._equal(field,value,params)
            return '(NOT '+equal+')' if operator=='ne' else equal
        if operator in ('in','not_in'):
            branches=['SELECT s.epoch_uuid FROM filter_scope s WHERE '+self._equal(field,item,params) for item in value]
            any_equal='s.epoch_uuid IN ('+' UNION '.join(branches)+')' if branches else '0'
            return '(NOT '+any_equal+')' if operator=='not_in' else any_equal
        # Validated tag arrays never satisfy numeric ordering predicates.
        return '0'

    @_serialized
    def matching(self,rows,filters,predicate=None):
        """Return ordered UUID membership and its verified source token.

        The caller validates predicate shape/typed limits before passing it here.
        The SQLite scope makes NOT/empty arrays relative to exact eligible rows,
        including rows with no direct or inherited annotations.
        """
        if self.token is None:raise RuntimeError('Refresh the shared-tag index before querying it')
        self._scope(rows)
        cache_key=json.dumps([filters,predicate],sort_keys=True,ensure_ascii=False,separators=(',',':'))
        cached=self.match_cache.get(cache_key)
        if cached is not None:
            self._check_generation();self.match_cache.move_to_end(cache_key)
            return cached[0],copy.deepcopy(self.token)
        params=[];parts=[];self._literal_id=0;self._rarity={}
        self.connection.execute('DELETE FROM predicate_values')
        if 'tag' in filters:parts.append(self._contains('annotations/effective/tags',filters['tag'],params))
        if 'tagged' in filters:parts.append('(NOT '+self._equal('annotations/effective/tags',[],params)+')')
        if predicate is not None:parts.append(self._predicate(predicate,params))
        sql='SELECT s.epoch_uuid FROM filter_scope AS s WHERE '+(' AND '.join(parts) or '1')+' ORDER BY s.position'
        result=tuple(row[0] for row in self.connection.execute(sql,params))
        self.connection.commit()
        if self.generation()!=self.token:
            raise SharedTagsChanged('Shared tags changed while loading this selection. Refresh and try again.')
        size=sys.getsizeof(cache_key)+sys.getsizeof(result)+sum(sys.getsizeof(value) for value in result)
        if size<=MATCH_CACHE_BYTES:
            self.match_cache[cache_key]=(result,size);self.match_cache_bytes+=size
            while len(self.match_cache)>8 or self.match_cache_bytes>MATCH_CACHE_BYTES:
                _,(_,removed)=self.match_cache.popitem(last=False);self.match_cache_bytes-=removed
        return result,copy.deepcopy(self.token)

    @_serialized
    def suggestions(self,query,limit):
        if not self.refresh():return None
        if self.shared_vocabulary is None:
            from workspace_shared_vocabulary import SharedVocabulary
            try:self.shared_vocabulary=SharedVocabulary(self)
            except Exception:
                # A partially-created disposable schema must never be reused.
                self.close()
                raise
        return self.shared_vocabulary.suggestions(query,limit)

    @_serialized
    def storage_stats(self):
        """Account for SQLite's live temp database as well as the named file."""
        if self.connection is None:return {'sqlite_allocated_bytes':0,'sqlite_used_bytes':0,'match_cache_bytes':0}
        result={}
        for schema in ('main','temp'):
            size=self.connection.execute(f'PRAGMA {schema}.page_size').fetchone()[0]
            pages=self.connection.execute(f'PRAGMA {schema}.page_count').fetchone()[0]
            free=self.connection.execute(f'PRAGMA {schema}.freelist_count').fetchone()[0]
            result[schema+'_allocated_bytes']=size*pages
            result[schema+'_used_bytes']=size*(pages-free)
        result['sqlite_allocated_bytes']=result['main_allocated_bytes']+result['temp_allocated_bytes']
        result['sqlite_used_bytes']=result['main_used_bytes']+result['temp_used_bytes']
        result['match_cache_bytes']=self.match_cache_bytes
        return result

    @_serialized
    def close(self):
        if self.connection is not None:self.connection.close();self.connection=None
        if self.folder is not None:self.folder.cleanup();self.folder=None
        self.token=None;self.scopes=dict.fromkeys(self.scopes);self.tag_ids.clear();self.match_cache.clear();self.match_cache_bytes=0
        self.summary_cache=None;self.catalog_cache={}
        self.shared_vocabulary=None
