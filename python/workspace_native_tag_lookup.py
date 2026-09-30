"""Persistent exact tag lookup maintained transactionally by native SQL triggers.

Canonical JSON remains the annotation record. This table is rebuildable and has
no application write path. The caller supplies a fresh recovery content proof at
open/checkpoint and fences queries with the existing native generation authority.
Ordinary writes to canonical shared_annotation are supported through the SQL
triggers. Privileged direct rewrites of this app-owned derived table or its proof
marker are outside the authority contract, as are rewrites of generation rows.
"""
from __future__ import annotations

import contextlib
import json
import uuid

SCHEMA='recording_workspace'
TABLE='app_shared_tag_lookup'
MARKER='app_shared_tag_lookup_checkpoint'
VERSION=1
PREFIX='rieke_tag_lookup_v1_'
INDEX='by_tag'
COLUMNS=('project_uuid','target_kind','target_uuid','profile_uuid','tag')


def _tag(alias):
    return f"JSON_UNQUOTE(JSON_EXTRACT({alias}.tags,CONCAT('$[',j.ordinal-1,']')))"


def _valid(alias):
    # JSON_TABLE extracts each tag once. The wider staging column cannot trim a
    # legal 255-character tag; any longer value still fails the explicit bound.
    tag='j.tag'
    whitespace=[chr(n).encode('utf-8').hex() for n in range(0x3001) if chr(n).isspace()]
    ends=','.join('0x'+value for value in whitespace)
    invalid=(f"JSON_TYPE(JSON_EXTRACT({alias}.tags,CONCAT('$[',j.ordinal-1,']')))!='STRING' "
        f'OR CHAR_LENGTH({tag}) NOT BETWEEN 1 AND 255 OR BINARY LEFT({tag},1) IN ({ends}) '
        f'OR BINARY RIGHT({tag},1) IN ({ends}) '
        # UTF-8 pattern bytes are [U+0000-U+001F]. DEL remains legal.
        f"OR REGEXP_LIKE({tag},CONVERT(0x5b002d1f5d USING utf8mb4),'c')")
    return (f"IF JSON_TYPE({alias}.tags)!='ARRAY' OR JSON_LENGTH({alias}.tags)>100 OR EXISTS ("
        f"SELECT 1 FROM JSON_TABLE({alias}.tags,'$[*]' COLUMNS(ordinal FOR ORDINALITY,"
        f"tag VARCHAR(1020) CHARACTER SET utf8mb4 PATH '$' ERROR ON ERROR)) j WHERE {invalid}) "
        "THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid canonical shared annotation tags'; END IF;")


def _insert(alias):
    return (_valid(alias)+f' INSERT INTO `{SCHEMA}`.`{TABLE}` ({",".join(COLUMNS)}) '
        f'SELECT {alias}.project_uuid,{alias}.target_kind,{alias}.target_uuid,{alias}.profile_uuid,'
        f"CAST(j.tag AS BINARY) FROM JSON_TABLE({alias}.tags,'$[*]' "
        "COLUMNS(tag VARCHAR(1020) CHARACTER SET utf8mb4 PATH '$' ERROR ON ERROR)) j;")


def _delete(alias):
    # Canonical DataJoint UUID columns are UTF-8. Coerce the source values,
    # otherwise MySQL converts our ASCII indexed columns and scans the table.
    comparisons=[f'{field}=CONVERT({alias}.{field} USING ascii) COLLATE ascii_bin'
        for field in ('project_uuid','target_kind','target_uuid','profile_uuid')]
    return f'DELETE FROM `{SCHEMA}`.`{TABLE}` WHERE '+ ' AND '.join(comparisons)+';'


def _dirty(alias):
    return (f'UPDATE `{SCHEMA}`.`{MARKER}` SET dirty=1 '
        f'WHERE project_uuid=CONVERT({alias}.project_uuid USING ascii) COLLATE ascii_bin;')


TRIGGER_MANIFEST={PREFIX+suffix:{'table':'shared_annotation','event':event,'timing':'AFTER',
    'body':'BEGIN '+body+' END'} for suffix,event,body in (
        ('ai','INSERT',_insert('NEW')+' '+_dirty('NEW')),
        ('au','UPDATE',_delete('OLD')+' '+_insert('NEW')+' '+_dirty('OLD')+' '+_dirty('NEW')),
        ('ad','DELETE',_delete('OLD')+' '+_dirty('OLD')))}


def _normal(value):return ' '.join(str(value).split())


def _proof(value,project):
    if not isinstance(value,dict) or value.get('project_uuid')!=project:
        raise ValueError('A fresh project annotation content proof is required')
    tables=value.get('tables');seal=tables.get('shared_annotation') if isinstance(tables,dict) else None
    if (not isinstance(seal,dict) or set(seal)!={'count','xor'} or type(seal['count']) is not int
            or seal['count']<0 or not isinstance(seal['xor'],str) or len(seal['xor'])!=64
            or any(char not in '0123456789abcdef' for char in seal['xor'])):
        raise ValueError('Invalid annotation content seal')
    return {'project_uuid':project,'tables':{'shared_annotation':dict(seal)}}


class NativeTagLookup:
    def __init__(self,connection,project_uuid):
        self.connection=connection;self.project_uuid=str(uuid.UUID(str(project_uuid)))
        self.ready=False;self.reason='not prepared';self.reused=False
        self.incarnation=None

    def _rows(self,sql,args=()):
        return list(self.connection.query(sql,args,as_dict=True,reconnect=False).fetchall())

    def _execute(self,sql,args=()):return self.connection.query(sql,args,reconnect=False)

    def _validate_schema(self):
        expected={TABLE:[('project_uuid','varchar',36,'ascii_bin'),('target_kind','varchar',8,'ascii_bin'),
            ('target_uuid','varchar',36,'ascii_bin'),('profile_uuid','varchar',36,'ascii_bin'),('tag','varbinary',1020,None)],
            MARKER:[('project_uuid','varchar',36,'ascii_bin'),('version','int',None,None),('proof','json',None,None),('dirty','tinyint',None,None)]}
        for table,columns in expected.items():
            engine=self._rows('SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s',(SCHEMA,table))
            if len(engine)!=1 or engine[0]['ENGINE']!='InnoDB':raise ValueError('Tag lookup requires its expected InnoDB tables')
            rows=self._rows('SELECT COLUMN_NAME,DATA_TYPE,CHARACTER_MAXIMUM_LENGTH,COLLATION_NAME,IS_NULLABLE '
                'FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION',(SCHEMA,table))
            actual=[(row['COLUMN_NAME'],row['DATA_TYPE'],row['CHARACTER_MAXIMUM_LENGTH'],row['COLLATION_NAME']) for row in rows]
            if actual!=columns or any(row['IS_NULLABLE']!='NO' for row in rows):raise ValueError('Existing tag lookup schema is incompatible')
            indexes=self._rows('SELECT INDEX_NAME,SEQ_IN_INDEX,COLUMN_NAME,SUB_PART,NON_UNIQUE,EXPRESSION FROM information_schema.STATISTICS '
                'WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY INDEX_NAME,SEQ_IN_INDEX',(SCHEMA,table))
            for name,keys in ({'PRIMARY':COLUMNS,INDEX:('project_uuid','tag','target_kind','target_uuid')} if table==TABLE else {'PRIMARY':('project_uuid',)}).items():
                selected=[row for row in indexes if row['INDEX_NAME']==name]
                if (tuple(row['COLUMN_NAME'] for row in selected)!=keys or any(row['SUB_PART'] is not None or row['EXPRESSION'] is not None
                        or row['NON_UNIQUE']!=int(name!='PRIMARY') for row in selected)):
                    raise ValueError('Existing tag lookup index is incompatible')

    def _triggers(self):
        rows=self._rows('SELECT TRIGGER_NAME,EVENT_OBJECT_TABLE,EVENT_MANIPULATION,ACTION_TIMING,ACTION_STATEMENT '
            'FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s',(SCHEMA,))
        present={row['TRIGGER_NAME']:row for row in rows if row['TRIGGER_NAME'].startswith(PREFIX)}
        if set(present)-set(TRIGGER_MANIFEST):raise ValueError('Unknown managed tag lookup trigger')
        for name,row in present.items():
            spec=TRIGGER_MANIFEST[name]
            if any(_normal(row[field])!=_normal(spec[key]) for field,key in
                (('EVENT_OBJECT_TABLE','table'),('EVENT_MANIPULATION','event'),('ACTION_TIMING','timing'),('ACTION_STATEMENT','body'))):
                raise ValueError('Existing tag lookup trigger is incompatible')
        return present

    def _lock_source(self):
        self._execute(f'SELECT 1 FROM `{SCHEMA}`.`shared_annotation` LIMIT 0')
        self._execute(f'SELECT 1 FROM `{SCHEMA}`.`{TABLE}` LIMIT 0')
        self._execute(f'SELECT 1 FROM `{SCHEMA}`.`{MARKER}` LIMIT 0')
        rows=self._rows(f'SELECT generation FROM `{SCHEMA}`.`app_state_generation` WHERE project_uuid=%s '
            "AND scope_kind='shared_annotations' AND scope_uuid=%s FOR UPDATE",(self.project_uuid,self.project_uuid))
        if len(rows)!=1:raise ValueError('Native annotation generation scope must exist before lookup preparation')

    def _validate_source(self):
        from workspace_annotations import tags
        after=None
        while True:
            where='project_uuid=%s';args=[self.project_uuid]
            if after is not None:
                kind,target,profile=after
                where+=' AND (target_kind>%s OR (target_kind=%s AND target_uuid>%s) OR (target_kind=%s AND target_uuid=%s AND profile_uuid>%s))'
                args.extend((kind,kind,target,kind,target,profile))
            rows=self._rows(f'SELECT target_kind,target_uuid,profile_uuid,tags FROM `{SCHEMA}`.`shared_annotation` '
                f'WHERE {where} ORDER BY target_kind,target_uuid,profile_uuid LIMIT 250',tuple(args))
            if not rows:break
            for row in rows:
                value=row['tags']
                tags(json.loads(value) if isinstance(value,(str,bytes)) else value)
            last=rows[-1];after=tuple(last[key] for key in ('target_kind','target_uuid','profile_uuid'))

    def _save_proof(self,proof):
        proof={'content':proof,'lookup_table_id':self._incarnation()}
        self._execute(f'INSERT INTO `{SCHEMA}`.`{MARKER}` (project_uuid,version,proof,dirty) VALUES (%s,%s,%s,0) '
            'ON DUPLICATE KEY UPDATE version=VALUES(version),proof=VALUES(proof),dirty=0',
            (self.project_uuid,VERSION,json.dumps(proof,sort_keys=True,separators=(',',':'))))

    def _incarnation(self):
        rows=self._rows('SELECT TABLE_ID FROM information_schema.INNODB_TABLES WHERE NAME=%s',(SCHEMA+'/'+TABLE,))
        if len(rows)!=1:raise ValueError('Native tag lookup table incarnation is unavailable')
        return int(rows[0]['TABLE_ID'])

    def validate_current(self):
        self._validate_schema()
        if len(self._triggers())!=len(TRIGGER_MANIFEST):
            raise ValueError('Native tag lookup trigger coverage is incomplete')
        if self.incarnation is None or self._incarnation()!=self.incarnation:
            raise ValueError('Native tag lookup table incarnation changed')
        return True

    def checkpoint(self,proof,*,guard=None):
        """Caller must verify unchanged lookup authority and fresh source proof."""
        if not self.ready:raise ValueError('Tag lookup is not prepared')
        proof=_proof(proof,self.project_uuid)
        if getattr(self.connection,'in_transaction',True):raise ValueError('Tag checkpoint cannot nest a transaction')
        with self.connection.transaction:
            self._lock_source();self.validate_current()
            if guard is not None and not guard():raise ValueError('Native tag lookup authority changed before checkpoint publication')
            self._save_proof(proof)

    def prepare(self,proof,*,force=False,guard=None,proof_provider=None):
        """Install once or rebuild a project after an unmatched content receipt."""
        locked=False
        try:
            proof=_proof(proof,self.project_uuid)
            if getattr(self.connection,'in_transaction',True):raise ValueError('Tag preparation cannot nest a transaction')
            lock=self._rows("SELECT GET_LOCK('rieke_native_tag_lookup_v1',10) AS acquired")
            if len(lock)!=1 or lock[0]['acquired']!=1:raise ValueError('Tag lookup preparation is already running')
            locked=True
            existing={row['TABLE_NAME'] for row in self._rows('SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN (%s,%s)',(SCHEMA,TABLE,MARKER))}
            if TABLE not in existing:self._execute(f'''CREATE TABLE IF NOT EXISTS `{SCHEMA}`.`{TABLE}` (
                project_uuid varchar(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                target_kind varchar(8) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                target_uuid varchar(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                profile_uuid varchar(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                tag varbinary(1020) NOT NULL,PRIMARY KEY(project_uuid,target_kind,target_uuid,profile_uuid,tag),
                KEY {INDEX}(project_uuid,tag,target_kind,target_uuid)) ENGINE=InnoDB''')
            if MARKER not in existing:self._execute(f'''CREATE TABLE IF NOT EXISTS `{SCHEMA}`.`{MARKER}` (
                project_uuid varchar(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                version int NOT NULL,proof json NOT NULL,dirty tinyint unsigned NOT NULL,PRIMARY KEY(project_uuid)) ENGINE=InnoDB''')
            self._validate_schema();present=self._triggers();complete=len(present)==len(TRIGGER_MANIFEST)
            for name,spec in TRIGGER_MANIFEST.items():
                if name not in present:
                    self._execute(f'CREATE TRIGGER `{SCHEMA}`.`{name}` AFTER {spec["event"]} ON '
                        f'`{SCHEMA}`.`shared_annotation` FOR EACH ROW {spec["body"]}')
            if proof_provider is not None:proof=_proof(proof_provider(),self.project_uuid)
            with self.connection.transaction:
                self._lock_source()
                self._validate_schema()
                if len(self._triggers())!=len(TRIGGER_MANIFEST):
                    raise ValueError('Native tag lookup trigger coverage changed during preparation')
                if guard is not None and not guard():
                    raise ValueError('Native source proof changed before lookup preparation')
                saved=self._rows(f'SELECT version,proof,dirty FROM `{SCHEMA}`.`{MARKER}` WHERE project_uuid=%s FOR UPDATE',(self.project_uuid,))
                stored=saved[0]['proof'] if saved else None
                if isinstance(stored,(str,bytes)):stored=json.loads(stored)
                expected={'content':proof,'lookup_table_id':self._incarnation()}
                self.incarnation=expected['lookup_table_id']
                self.reused=bool(not force and complete and saved and saved[0]['version']==VERSION and saved[0]['dirty']==0 and stored==expected)
                if not self.reused:
                    self._validate_source()
                    self._execute(f'DELETE FROM `{SCHEMA}`.`{TABLE}` WHERE project_uuid=%s',(self.project_uuid,))
                    self._execute(f'INSERT INTO `{SCHEMA}`.`{TABLE}` ({",".join(COLUMNS)}) '
                        f'SELECT a.project_uuid,a.target_kind,a.target_uuid,a.profile_uuid,CAST({_tag("a")} AS BINARY) '
                        f'FROM `{SCHEMA}`.`shared_annotation` a JOIN JSON_TABLE(a.tags,\'$[*]\' '
                        "COLUMNS(ordinal FOR ORDINALITY)) j "
                        'WHERE a.project_uuid=%s',(self.project_uuid,))
                    self._save_proof(proof)
            self.ready=True;self.reason=None
        except Exception as error:
            self.ready=False;self.reason=str(error)
        finally:
            if locked:
                with contextlib.suppress(Exception):self._execute("SELECT RELEASE_LOCK('rieke_native_tag_lookup_v1')")
        return self

    def _target_query(self,tag,kinds):
        if not self.ready:raise ValueError('Native tag lookup is unavailable: '+str(self.reason))
        kinds=tuple(kinds)
        if not kinds or any(kind not in ('cell','epoch') for kind in kinds):raise ValueError('Invalid annotation target kinds')
        args=[self.project_uuid,*kinds]
        where='project_uuid=%s AND target_kind IN ('+','.join('%s' for _ in kinds)+')'
        hint=''
        if tag is not None:
            if not isinstance(tag,str) or not 1<=len(tag)<=255:raise ValueError('Invalid exact tag')
            where+=' AND tag=%s';args.append(tag.encode('utf-8'));hint=f' FORCE INDEX ({INDEX})'
        return f'SELECT DISTINCT target_kind,target_uuid FROM `{SCHEMA}`.`{TABLE}`{hint} WHERE {where}',tuple(args)

    def targets(self,tag,kinds=('cell','epoch')):
        if tag is None:raise ValueError('An exact tag is required')
        sql,args=self._target_query(tag,kinds)
        return {(row['target_kind'],row['target_uuid']) for row in self._rows(sql,args)}

    def tagged_targets(self,kinds=('cell','epoch')):
        sql,args=self._target_query(None,kinds)
        return {(row['target_kind'],row['target_uuid']) for row in self._rows(sql,args)}

    def targets_outside(self,tags,kinds=('cell','epoch')):
        values=tuple(tags)
        if any(not isinstance(tag,str) or not 1<=len(tag)<=255 for tag in values):
            raise ValueError('Invalid exact tags')
        sql,args=self._target_query(None,kinds)
        if values:
            sql+=' AND tag NOT IN ('+','.join('%s' for _ in values)+')'
            args+=tuple(tag.encode('utf-8') for tag in values)
        return {(row['target_kind'],row['target_uuid']) for row in self._rows(sql,args)}


def bootstrap(connection,project_uuid,proof,*,force=False,guard=None,proof_provider=None):
    return NativeTagLookup(connection,project_uuid).prepare(proof,force=force,guard=guard,proof_provider=proof_provider)
