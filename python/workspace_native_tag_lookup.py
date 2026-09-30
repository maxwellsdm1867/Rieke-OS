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
import unicodedata

SCHEMA='recording_workspace'
TABLE='app_shared_tag_lookup'
MARKER='app_shared_tag_lookup_checkpoint'
DICTIONARY='app_shared_tag_dictionary'
AUTHORS='app_shared_tag_authors'
VERSION=2
FOLD_VERSION='python-casefold-'+unicodedata.unidata_version
FOLD_BYTES=1530
PREFIX='rieke_tag_lookup_v1_'
INDEX='by_tag'
COLUMNS=('project_uuid','target_kind','target_uuid','profile_uuid','tag')


def _tag(alias):
    return f"JSON_UNQUOTE(JSON_EXTRACT({alias}.tags,CONCAT('$[',j.ordinal-1,']')))"


def _valid(alias,*,duplicates=True):
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
    duplicate_check=(f" OR EXISTS (SELECT 1 FROM JSON_TABLE({alias}.tags,'$[*]' COLUMNS(tag VARCHAR(1020) CHARACTER SET utf8mb4 PATH '$' ERROR ON ERROR)) d GROUP BY CAST(d.tag AS BINARY) HAVING COUNT(*)>1)" if duplicates else '')
    return (f"IF JSON_TYPE({alias}.tags)!='ARRAY' OR JSON_LENGTH({alias}.tags)>100 OR EXISTS ("
        f"SELECT 1 FROM JSON_TABLE({alias}.tags,'$[*]' COLUMNS(ordinal FOR ORDINALITY,"
        f"tag VARCHAR(1020) CHARACTER SET utf8mb4 PATH '$' ERROR ON ERROR)) j WHERE {invalid}){duplicate_check} "
        "THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid canonical shared annotation tags'; END IF;")


def _insert(alias):
    return (_valid(alias,duplicates=False)+f' INSERT INTO `{SCHEMA}`.`{TABLE}` ({",".join(COLUMNS)}) '
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


LEGACY_TRIGGER_MANIFEST={PREFIX+suffix:{'table':'shared_annotation','event':event,'timing':'AFTER',
    'body':'BEGIN '+body+' END'} for suffix,event,body in (
        ('ai','INSERT',_insert('NEW')+' '+_dirty('NEW')),
        ('au','UPDATE',_delete('OLD')+' '+_insert('NEW')+' '+_dirty('OLD')+' '+_dirty('NEW')),
        ('ad','DELETE',_delete('OLD')+' '+_dirty('OLD')))}


def _identity(alias,field):
    return f'CONVERT({alias}.{field} USING ascii) COLLATE ascii_bin'


def _scope_lock(alias):
    project=f'{alias}.project_uuid'  # The existing authority uses canonical UTF-8 UUID columns.
    return (f'SET v_generation=NULL; SELECT generation INTO v_generation FROM `{SCHEMA}`.`app_state_generation` '
        f"WHERE project_uuid={project} AND scope_kind='shared_annotations' AND scope_uuid={project} FOR UPDATE; "
        "IF v_generation IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Annotation generation scope is unavailable'; END IF;")


def _tag_loop(alias,adding,other=None):
    project,kind,target,profile=(_identity(alias,field) for field in ('project_uuid','target_kind','target_uuid','profile_uuid'))
    path=f"JSON_EXTRACT({alias}.tags,CONCAT('$[',v_i,']'))"
    check=f'NOT v_same OR NOT JSON_CONTAINS({other}.tags,{path})' if other else 'TRUE'
    local=f'project_uuid={project} AND target_kind={kind} AND target_uuid={target} AND tag=v_tag'
    member=f'{local} AND profile_uuid={profile}'
    # Current locking reads are essential: a transaction may have established a
    # repeatable-read snapshot before waiting for the project scope lock.
    probe=(f'SET v_other=NULL; SELECT profile_uuid INTO v_other FROM `{SCHEMA}`.`{TABLE}` FORCE INDEX (PRIMARY) '
        f'WHERE {local} LIMIT 1 FOR UPDATE; ')
    if adding:
        change=(probe+f'INSERT INTO `{SCHEMA}`.`{TABLE}` ({",".join(COLUMNS)}) VALUES ({project},{kind},{target},{profile},v_tag); '
            f'INSERT INTO `{SCHEMA}`.`{DICTIONARY}` (project_uuid,tag,target_count,fold_key) '
            f'VALUES ({project},v_tag,IF(v_other IS NULL,1,0),NULL) ON DUPLICATE KEY UPDATE target_count=target_count+VALUES(target_count); '
            f'INSERT INTO `{SCHEMA}`.`{AUTHORS}` (project_uuid,tag,profile_uuid,membership_count) '
            f'VALUES ({project},v_tag,{profile},1) ON DUPLICATE KEY UPDATE membership_count=membership_count+1; ')
    else:
        change=(f'DELETE FROM `{SCHEMA}`.`{TABLE}` WHERE {member}; '+probe+
            f'IF v_other IS NULL THEN UPDATE `{SCHEMA}`.`{DICTIONARY}` SET target_count=target_count-1 WHERE project_uuid={project} AND tag=v_tag; END IF; '
            f'UPDATE `{SCHEMA}`.`{AUTHORS}` SET membership_count=membership_count-1 WHERE project_uuid={project} AND tag=v_tag AND profile_uuid={profile}; ')
    return (f'SET v_i=0; WHILE v_i<JSON_LENGTH({alias}.tags) DO IF {check} THEN '
        f'SET v_tag=CAST(JSON_UNQUOTE({path}) AS BINARY); '+change+'END IF; SET v_i=v_i+1; END WHILE; ')


def _cleanup(alias):
    project,profile=_identity(alias,'project_uuid'),_identity(alias,'profile_uuid')
    return (f'SET v_i=0; WHILE v_i<JSON_LENGTH({alias}.tags) DO '
        f"SET v_tag=CAST(JSON_UNQUOTE(JSON_EXTRACT({alias}.tags,CONCAT('$[',v_i,']'))) AS BINARY); "
        f'DELETE FROM `{SCHEMA}`.`{AUTHORS}` WHERE project_uuid={project} AND tag=v_tag AND profile_uuid={profile} AND membership_count=0; '
        f'DELETE FROM `{SCHEMA}`.`{DICTIONARY}` WHERE project_uuid={project} AND tag=v_tag AND target_count=0; '
        'SET v_i=v_i+1; END WHILE; ')


def _manifest():
    result={}
    declarations=('DECLARE v_i INT DEFAULT 0; DECLARE v_tag VARBINARY(1020); DECLARE v_other VARCHAR(36); '
        'DECLARE v_generation BIGINT UNSIGNED DEFAULT NULL; DECLARE v_same BOOL DEFAULT FALSE; '
        'DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_other=NULL; ')
    same=' AND '.join(f'BINARY OLD.{field}=BINARY NEW.{field}' for field in ('project_uuid','target_kind','target_uuid','profile_uuid'))
    for suffix,event in (('ai','INSERT'),('au','UPDATE'),('ad','DELETE')):
        old=event!='INSERT';new=event!='DELETE'
        body=declarations+(_scope_lock('OLD') if old else '')+(_scope_lock('NEW') if new else '')
        if new:body+=_valid('NEW')
        if old and new:body+=' SET v_same=('+same+'); '
        if old:body+=_tag_loop('OLD',False,'NEW' if new else None)
        if new:body+=_tag_loop('NEW',True,'OLD' if old else None)
        if old:body+=_cleanup('OLD')+_dirty('OLD')
        if new:body+=_dirty('NEW')
        result[PREFIX+suffix]={'table':'shared_annotation','event':event,'timing':'AFTER','body':'BEGIN '+body+' END'}
    return result


TRIGGER_MANIFEST=_manifest()


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

    def _validate_schema(self,*,legacy_index=False):
        expected={TABLE:[('project_uuid','varchar',36,'ascii_bin'),('target_kind','varchar',8,'ascii_bin'),
            ('target_uuid','varchar',36,'ascii_bin'),('profile_uuid','varchar',36,'ascii_bin'),('tag','varbinary',1020,None)],
            MARKER:[('project_uuid','varchar',36,'ascii_bin'),('version','int',None,None),('proof','json',None,None),('dirty','tinyint',None,None)],
            DICTIONARY:[('project_uuid','varchar',36,'ascii_bin'),('tag','varbinary',1020,None),('target_count','bigint',None,None),('fold_key','varbinary',FOLD_BYTES,None)],
            AUTHORS:[('project_uuid','varchar',36,'ascii_bin'),('tag','varbinary',1020,None),('profile_uuid','varchar',36,'ascii_bin'),('membership_count','bigint',None,None)]}
        for table,columns in expected.items():
            engine=self._rows('SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s',(SCHEMA,table))
            if len(engine)!=1 or engine[0]['ENGINE']!='InnoDB':raise ValueError('Tag lookup requires its expected InnoDB tables')
            rows=self._rows('SELECT COLUMN_NAME,DATA_TYPE,CHARACTER_MAXIMUM_LENGTH,COLLATION_NAME,IS_NULLABLE '
                'FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION',(SCHEMA,table))
            actual=[(row['COLUMN_NAME'],row['DATA_TYPE'],row['CHARACTER_MAXIMUM_LENGTH'],row['COLLATION_NAME']) for row in rows]
            if actual!=columns or any(row['IS_NULLABLE']!=('YES' if table==DICTIONARY and row['COLUMN_NAME']=='fold_key' else 'NO') for row in rows):raise ValueError('Existing tag lookup schema is incompatible')
            indexes=self._rows('SELECT INDEX_NAME,SEQ_IN_INDEX,COLUMN_NAME,SUB_PART,NON_UNIQUE,EXPRESSION,COLLATION FROM information_schema.STATISTICS '
                'WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY INDEX_NAME,SEQ_IN_INDEX',(SCHEMA,table))
            expected_indexes={TABLE:{'PRIMARY':COLUMNS,INDEX:('project_uuid','tag','profile_uuid','target_kind','target_uuid')},
                MARKER:{'PRIMARY':('project_uuid',)},
                DICTIONARY:{'PRIMARY':('project_uuid','tag'),'by_prefix':('project_uuid','fold_key','tag'),'by_rank':('project_uuid','target_count','fold_key','tag')},
                AUTHORS:{'PRIMARY':('project_uuid','tag','profile_uuid')}}
            if legacy_index:expected_indexes[TABLE][INDEX]=('project_uuid','tag','target_kind','target_uuid')
            for name,keys in expected_indexes[table].items():
                selected=[row for row in indexes if row['INDEX_NAME']==name]
                if (tuple(row['COLUMN_NAME'] for row in selected)!=keys or any(row['SUB_PART'] is not None or row['EXPRESSION'] is not None
                        or row['NON_UNIQUE']!=int(name!='PRIMARY') or row['COLLATION']!=('D' if name=='by_rank' and row['COLUMN_NAME']=='target_count' else 'A') for row in selected)):
                    raise ValueError('Existing tag lookup index is incompatible')

    def _migrate_legacy(self):
        rows=self._rows('SELECT TRIGGER_NAME,EVENT_OBJECT_TABLE,EVENT_MANIPULATION,ACTION_TIMING,ACTION_STATEMENT '
            'FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s',(SCHEMA,))
        legacy=set()
        for row in rows:
            name=row['TRIGGER_NAME']
            if not name.startswith(PREFIX):continue
            def matches(spec):
                return spec is not None and all(_normal(row[field])==_normal(spec[key]) for field,key in
                    (('EVENT_OBJECT_TABLE','table'),('EVENT_MANIPULATION','event'),('ACTION_TIMING','timing'),('ACTION_STATEMENT','body')))
            if matches(LEGACY_TRIGGER_MANIFEST.get(name)):legacy.add(name)
            elif not matches(TRIGGER_MANIFEST.get(name)):raise ValueError('Existing tag lookup trigger is incompatible')
        indexes=self._rows('SELECT COLUMN_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s ORDER BY SEQ_IN_INDEX',(SCHEMA,TABLE,INDEX))
        if tuple(row['COLUMN_NAME'] for row in indexes)==('project_uuid','tag','target_kind','target_uuid'):
            self._validate_schema(legacy_index=True)
            self._execute(f'ALTER TABLE `{SCHEMA}`.`{TABLE}` DROP INDEX {INDEX},ADD INDEX {INDEX}(project_uuid,tag,profile_uuid,target_kind,target_uuid)')
        for name in legacy:self._execute(f'DROP TRIGGER `{SCHEMA}`.`{name}`')

    def fill_fold_keys(self):
        """Persist exact Python folds only for newly observed distinct tags."""
        while True:
            rows=self._rows(f'SELECT tag FROM `{SCHEMA}`.`{DICTIONARY}` FORCE INDEX (by_prefix) '
                'WHERE project_uuid=%s AND fold_key IS NULL LIMIT 200',(self.project_uuid,))
            if not rows:return
            for row in rows:
                tag=bytes(row['tag']);fold=tag.decode('utf-8').casefold().encode('utf-8')
                if len(fold)>FOLD_BYTES:raise ValueError('Unicode casefold exceeds the verified dictionary key bound')
                self._execute(f'UPDATE `{SCHEMA}`.`{DICTIONARY}` SET fold_key=%s WHERE project_uuid=%s AND tag=%s AND fold_key IS NULL',
                    (fold,self.project_uuid,tag))

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
        for table in (DICTIONARY,AUTHORS):self._execute(f'SELECT 1 FROM `{SCHEMA}`.`{table}` LIMIT 0')
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
        proof={'content':proof,'table_ids':self._incarnation(),'fold_version':FOLD_VERSION}
        self._execute(f'INSERT INTO `{SCHEMA}`.`{MARKER}` (project_uuid,version,proof,dirty) VALUES (%s,%s,%s,0) '
            'ON DUPLICATE KEY UPDATE version=VALUES(version),proof=VALUES(proof),dirty=0',
            (self.project_uuid,VERSION,json.dumps(proof,sort_keys=True,separators=(',',':'))))

    def _incarnation(self):
        names=tuple(SCHEMA+'/'+table for table in (TABLE,DICTIONARY,AUTHORS))
        rows=self._rows('SELECT NAME,TABLE_ID FROM information_schema.INNODB_TABLES WHERE NAME IN (%s,%s,%s)',names)
        result={row['NAME'].split('/')[-1]:int(row['TABLE_ID']) for row in rows}
        if set(result)!={TABLE,DICTIONARY,AUTHORS}:raise ValueError('Native tag lookup table incarnation is unavailable')
        return result

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
            existing={row['TABLE_NAME'] for row in self._rows('SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN (%s,%s,%s,%s)',(SCHEMA,TABLE,MARKER,DICTIONARY,AUTHORS))}
            if TABLE not in existing:self._execute(f'''CREATE TABLE IF NOT EXISTS `{SCHEMA}`.`{TABLE}` (
                project_uuid varchar(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                target_kind varchar(8) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                target_uuid varchar(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                profile_uuid varchar(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                tag varbinary(1020) NOT NULL,PRIMARY KEY(project_uuid,target_kind,target_uuid,profile_uuid,tag),
                KEY {INDEX}(project_uuid,tag,profile_uuid,target_kind,target_uuid)) ENGINE=InnoDB''')
            if MARKER not in existing:self._execute(f'''CREATE TABLE IF NOT EXISTS `{SCHEMA}`.`{MARKER}` (
                project_uuid varchar(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                version int NOT NULL,proof json NOT NULL,dirty tinyint unsigned NOT NULL,PRIMARY KEY(project_uuid)) ENGINE=InnoDB''')
            if DICTIONARY not in existing:self._execute(f'''CREATE TABLE `{SCHEMA}`.`{DICTIONARY}` (
                project_uuid varchar(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                tag varbinary(1020) NOT NULL,target_count bigint unsigned NOT NULL,fold_key varbinary({FOLD_BYTES}) NULL,
                PRIMARY KEY(project_uuid,tag),KEY by_prefix(project_uuid,fold_key,tag),
                KEY by_rank(project_uuid,target_count DESC,fold_key,tag)) ENGINE=InnoDB''')
            if AUTHORS not in existing:self._execute(f'''CREATE TABLE `{SCHEMA}`.`{AUTHORS}` (
                project_uuid varchar(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                tag varbinary(1020) NOT NULL,profile_uuid varchar(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
                membership_count bigint unsigned NOT NULL,PRIMARY KEY(project_uuid,tag,profile_uuid)) ENGINE=InnoDB''')
            self._migrate_legacy()
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
                expected={'content':proof,'table_ids':self._incarnation(),'fold_version':FOLD_VERSION}
                self.incarnation=expected['table_ids']
                self.reused=bool(not force and complete and saved and saved[0]['version']==VERSION and saved[0]['dirty']==0 and stored==expected)
                if not self.reused:
                    self._validate_source()
                    self._execute(f'DELETE FROM `{SCHEMA}`.`{TABLE}` WHERE project_uuid=%s',(self.project_uuid,))
                    self._execute(f'INSERT INTO `{SCHEMA}`.`{TABLE}` ({",".join(COLUMNS)}) '
                        f'SELECT a.project_uuid,a.target_kind,a.target_uuid,a.profile_uuid,CAST({_tag("a")} AS BINARY) '
                        f'FROM `{SCHEMA}`.`shared_annotation` a JOIN JSON_TABLE(a.tags,\'$[*]\' '
                        "COLUMNS(ordinal FOR ORDINALITY)) j "
                        'WHERE a.project_uuid=%s',(self.project_uuid,))
                    for table in (AUTHORS,DICTIONARY):self._execute(f'DELETE FROM `{SCHEMA}`.`{table}` WHERE project_uuid=%s',(self.project_uuid,))
                    self._execute(f'INSERT INTO `{SCHEMA}`.`{DICTIONARY}` (project_uuid,tag,target_count,fold_key) '
                        f'SELECT project_uuid,tag,COUNT(DISTINCT target_kind,target_uuid),NULL FROM `{SCHEMA}`.`{TABLE}` WHERE project_uuid=%s GROUP BY project_uuid,tag',(self.project_uuid,))
                    self._execute(f'INSERT INTO `{SCHEMA}`.`{AUTHORS}` (project_uuid,tag,profile_uuid,membership_count) '
                        f'SELECT project_uuid,tag,profile_uuid,COUNT(*) FROM `{SCHEMA}`.`{TABLE}` WHERE project_uuid=%s GROUP BY project_uuid,tag,profile_uuid',(self.project_uuid,))
                    self._save_proof(proof)
            self.ready=True;self.fill_fold_keys();self.reason=None
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
