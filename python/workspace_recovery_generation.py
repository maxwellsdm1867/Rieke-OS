"""Transactional, bounded recovery deltas for current project state.

Only exact primary-key identities are retained in a fixed-slot SQL hint ring. A project clock
serializes commit order; capture holds that clock while its SQL snapshot and
outside-SQL mirror are made durable. Overwriting an old slot advances a retention
floor, so an older mirror rebuilds instead of silently missing a deletion. The
ring has no tag payload or secondary generation index that can grow during bulk
transactions; captured keys are deduplicated by their complete typed identity.
"""
from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import re
import uuid

from workspace_state_generation import StateGenerationAuthority, SCHEMA

PREFIX='rieke_recovery_v1_'
CLOCK='app_recovery_clock'
FEED='app_recovery_changes'
INSTANCE='app_recovery_instance'
ANCHOR_LOCK='rieke_recovery_instance_v1'
RECOVERY_WINDOW=20000
TRIM_INTERVAL=1000
TABLE_NAMES=('annotation_profile','shared_annotation','curation','protocol_workspace',
    'data_store_state','protocol_tree_layout','search_preset','search_preset_version',
    'protocol_binding','explorer_revision','dataset_revision','search_query_last_run','source')
TABLE_IDS={name:index+1 for index,name in enumerate(TABLE_NAMES)}
IDENTIFIER=re.compile(r'^[a-z][a-z0-9_]*$')


def _name(value):
    if not isinstance(value,str) or not IDENTIFIER.fullmatch(value):raise ValueError('Unsupported recovery SQL identifier')
    return '`'+value+'`'


def table_specs(connection):
    """Canonical table/column/PK ordering, including absent optional tables."""
    placeholders=','.join('%s' for _ in TABLE_NAMES)
    table_rows=connection.query(f'SELECT TABLE_NAME,ENGINE FROM information_schema.TABLES '
        f'WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ({placeholders})',(SCHEMA,*TABLE_NAMES),as_dict=True,reconnect=False).fetchall()
    present={row['TABLE_NAME']:row['ENGINE'] for row in table_rows}
    if any(engine!='InnoDB' for engine in present.values()):raise ValueError('Recovery deltas require InnoDB source tables')
    columns=connection.query('SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,DATA_TYPE,CHARACTER_MAXIMUM_LENGTH,IS_NULLABLE '
        f'FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ({placeholders}) '
        'ORDER BY TABLE_NAME,ORDINAL_POSITION',(SCHEMA,*TABLE_NAMES),as_dict=True,reconnect=False).fetchall()
    keys=connection.query('SELECT TABLE_NAME,COLUMN_NAME FROM information_schema.STATISTICS '
        f"WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ({placeholders}) AND INDEX_NAME='PRIMARY' "
        'ORDER BY TABLE_NAME,SEQ_IN_INDEX',(SCHEMA,*TABLE_NAMES),as_dict=True,reconnect=False).fetchall()
    result={}
    for table in TABLE_NAMES:
        if table not in present:continue
        fields=[row for row in columns if row['TABLE_NAME']==table]
        primary=[row['COLUMN_NAME'] for row in keys if row['TABLE_NAME']==table]
        by_name={row['COLUMN_NAME']:row for row in fields}
        if not primary or 'project_uuid' not in by_name:raise ValueError('Recovery source lacks project identity or primary key')
        maximum=2
        for key in primary:
            _name(key)
            field=by_name[key]
            if field['IS_NULLABLE']!='NO':raise ValueError('Recovery primary keys cannot be nullable')
            if field['DATA_TYPE'] in {'char','varchar','enum'}:
                maximum+=4+6*int(field['CHARACTER_MAXIMUM_LENGTH'])
            elif field['DATA_TYPE'] in {'tinyint','smallint','mediumint','int','bigint'}:maximum+=33
            else:raise ValueError('Unsupported recovery primary-key type')
        if maximum>1024:raise ValueError('Recovery primary key exceeds the exact bounded feed key')
        result[table]={'primary_keys':primary,'columns':[row['COLUMN_NAME'] for row in fields],
            'json_columns':[row['COLUMN_NAME'] for row in fields if row['DATA_TYPE']=='json'],
            'signature':[(row['COLUMN_NAME'],row['COLUMN_TYPE'],row['IS_NULLABLE']) for row in fields]}
    return result


def _change(alias, table, keys, deleted):
    array='JSON_ARRAY('+','.join(alias+'.'+_name(key) for key in keys)+')'
    return (f'INSERT INTO `{SCHEMA}`.`{CLOCK}` (project_uuid,scope_epoch,generation,retained_after) '
        f'VALUES ({alias}.project_uuid,UUID(),1,0) ON DUPLICATE KEY UPDATE generation=generation+1; '
        f'UPDATE `{SCHEMA}`.`{CLOCK}` SET retained_after=GREATEST(retained_after,GREATEST(generation,{RECOVERY_WINDOW})-{RECOVERY_WINDOW}) '
        f'WHERE project_uuid={alias}.project_uuid; '
        f'INSERT INTO `{SCHEMA}`.`{FEED}` (project_uuid,slot,table_id,key_bytes,generation,deleted) '
        f'SELECT {alias}.project_uuid,MOD(generation,{RECOVERY_WINDOW}),{TABLE_IDS[table]},'
        f'CAST({array} AS CHAR CHARACTER SET utf8mb4),generation,{int(deleted)} '
        f'FROM `{SCHEMA}`.`{CLOCK}` WHERE project_uuid={alias}.project_uuid '
        'ON DUPLICATE KEY UPDATE table_id=VALUES(table_id),key_bytes=VALUES(key_bytes),'
        'generation=VALUES(generation),deleted=VALUES(deleted);')


def _legacy_change(alias, table, keys, deleted, *, trim=True):
    array='JSON_ARRAY('+','.join(alias+'.'+_name(key) for key in keys)+')'
    body=(f'INSERT INTO `{SCHEMA}`.`{CLOCK}` (project_uuid,scope_epoch,generation,retained_after) '
        f'VALUES ({alias}.project_uuid,UUID(),1,0) ON DUPLICATE KEY UPDATE generation=generation+1; '
        f'INSERT INTO `{SCHEMA}`.`{FEED}` (project_uuid,table_id,key_bytes,generation,deleted) '
        f'SELECT {alias}.project_uuid,{TABLE_IDS[table]},CAST({array} AS CHAR CHARACTER SET utf8mb4),generation,{int(deleted)} '
        f'FROM `{SCHEMA}`.`{CLOCK}` WHERE project_uuid={alias}.project_uuid '
        'ON DUPLICATE KEY UPDATE generation=VALUES(generation),deleted=VALUES(deleted); '
        f'IF (SELECT MOD(generation,{TRIM_INTERVAL})=0 FROM `{SCHEMA}`.`{CLOCK}` WHERE project_uuid={alias}.project_uuid) THEN '
        f'UPDATE `{SCHEMA}`.`{CLOCK}` SET retained_after=GREATEST(retained_after,GREATEST(generation,{RECOVERY_WINDOW})-{RECOVERY_WINDOW}) '
        f'WHERE project_uuid={alias}.project_uuid; '
        f'DELETE FROM `{SCHEMA}`.`{FEED}` WHERE project_uuid={alias}.project_uuid AND generation<='
        f'(SELECT retained_after FROM `{SCHEMA}`.`{CLOCK}` WHERE project_uuid={alias}.project_uuid); END IF;')

    return body if trim else body.split(' IF (SELECT MOD(generation',1)[0]


def manifest_from_specs(specs, *, legacy=None):
    manifest={}
    for table,spec in specs.items():
        for event,suffix in (('INSERT','ai'),('UPDATE','au'),('DELETE','ad')):
            aliases=('NEW',) if event=='INSERT' else ('OLD',) if event=='DELETE' else ('OLD','NEW')
            body='BEGIN '+' '.join((_change(alias,table,spec['primary_keys'],alias=='OLD') if legacy is None else
                _legacy_change(alias,table,spec['primary_keys'],alias=='OLD',trim=legacy)) for alias in aliases)+' END'
            manifest[PREFIX+table+'_'+suffix]={'table':table,'event':event,'timing':'AFTER','body':body}
    return manifest


def recovery_trigger_manifest(connection):
    return manifest_from_specs(table_specs(connection))


def _equal_trigger(row, expected):
    return all(' '.join(str(row[field]).split())==' '.join(expected[key].split()) for field,key in
        (('EVENT_OBJECT_TABLE','table'),('EVENT_MANIPULATION','event'),('ACTION_TIMING','timing'),('ACTION_STATEMENT','body')))


@dataclasses.dataclass
class RecoveryCapture:
    watermark: dict
    complete: bool
    keys: dict
    primary_keys: dict
    columns: dict
    json_columns: dict
    _verify: object=dataclasses.field(repr=False)

    def verify(self):
        self._verify()
        return True


class RecoveryGenerationAuthority:
    def __init__(self, connection, project_uuid):
        self.connection=connection;self.project_uuid=str(uuid.UUID(str(project_uuid)))
        self.observer=StateGenerationAuthority(connection,self.project_uuid)
        self.ready=False;self.reason='not bootstrapped';self.specs={};self.manifest={}
        self._driver=None;self._socket=None;self._private_epoch=str(uuid.uuid4())
        self._schema_ddl=None;self._source_specs_ddl=None;self._needs_full=False

    def _rows(self, sql, args=()):return self.observer._rows(sql,args)

    def _triggers(self):return self.observer._triggers()

    def _instance(self, *, initialize=False):
        owner=self._rows('SELECT IS_USED_LOCK(%s) AS owner',(ANCHOR_LOCK,))[0]['owner']
        current=self._rows('SELECT CONNECTION_ID() AS identity')[0]['identity']
        if owner is None and initialize:
            if self._rows('SELECT GET_LOCK(%s,0) AS acquired',(ANCHOR_LOCK,))[0]['acquired']!=1:
                raise ValueError('Recovery instance anchor changed during bootstrap')
            owner=current
            self.connection.query(f'INSERT INTO `{SCHEMA}`.`{INSTANCE}` (singleton,instance_epoch,owner_connection_id) '
                'VALUES (1,%s,%s) ON DUPLICATE KEY UPDATE instance_epoch=VALUES(instance_epoch),owner_connection_id=VALUES(owner_connection_id)',
                (str(uuid.uuid4()),owner),reconnect=False)
        rows=self._rows(f'SELECT instance_epoch,owner_connection_id FROM `{SCHEMA}`.`{INSTANCE}` WHERE singleton=1')
        if owner is None or len(rows)!=1 or int(rows[0]['owner_connection_id'])!=int(owner):
            raise ValueError('Recovery server-instance anchor is unavailable')
        return {'epoch':str(uuid.UUID(rows[0]['instance_epoch'])),'owner':int(owner)}

    def _clock(self, *, lock=False, create=False):
        rows=self._rows(f'SELECT scope_epoch,generation,retained_after FROM `{SCHEMA}`.`{CLOCK}` '
            'WHERE project_uuid=%s'+(' FOR UPDATE' if lock else ''),(self.project_uuid,))
        if not rows and create:
            self.connection.query(f'INSERT IGNORE INTO `{SCHEMA}`.`{CLOCK}` '
                '(project_uuid,scope_epoch,generation,retained_after) VALUES (%s,%s,0,0)',
                (self.project_uuid,str(uuid.uuid4())),reconnect=False)
            return self._clock(lock=lock)
        if len(rows)!=1:raise ValueError('Recovery generation row is unavailable')
        row=rows[0]
        return {'scope_epoch':str(uuid.UUID(row['scope_epoch'])),'generation':int(row['generation']),
                'retained_after':int(row['retained_after'])}

    def _verify_tables(self, ddl):
        if self._schema_ddl==ddl:return
        expected={CLOCK:[('project_uuid','varchar(36)'),('scope_epoch','char(36)'),
            ('generation','bigint unsigned'),('retained_after','bigint unsigned')],
            FEED:[('project_uuid','varchar(36)'),('slot','smallint unsigned'),('table_id','smallint unsigned'),('key_bytes','varbinary(1024)'),
                ('generation','bigint unsigned'),('deleted','tinyint unsigned')],
            INSTANCE:[('singleton','tinyint unsigned'),('instance_epoch','char(36)'),('owner_connection_id','bigint unsigned')]}
        rows=self._rows('SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE FROM information_schema.COLUMNS '
            'WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN (%s,%s,%s) ORDER BY TABLE_NAME,ORDINAL_POSITION',(SCHEMA,CLOCK,FEED,INSTANCE))
        for table,columns in expected.items():
            actual=[(row['COLUMN_NAME'],row['COLUMN_TYPE']) for row in rows if row['TABLE_NAME']==table]
            if actual!=columns or any(row['IS_NULLABLE']!='NO' for row in rows if row['TABLE_NAME']==table):
                raise ValueError('Recovery authority columns are incompatible')
        rows=self._rows("SELECT TABLE_NAME,COLUMN_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s "
            "AND TABLE_NAME IN (%s,%s,%s) AND INDEX_NAME='PRIMARY' ORDER BY TABLE_NAME,SEQ_IN_INDEX",(SCHEMA,CLOCK,FEED,INSTANCE))
        for table,keys in ((CLOCK,['project_uuid']),(FEED,['project_uuid','slot']),(INSTANCE,['singleton'])):
            if [row['COLUMN_NAME'] for row in rows if row['TABLE_NAME']==table]!=keys:
                raise ValueError('Recovery authority primary key is incompatible')
        self._schema_ddl=ddl

    def _contract(self):
        driver=getattr(self.connection,'_conn',None)
        if driver is None:raise ValueError('Native connection required for recovery deltas')
        socket=getattr(driver,'_sock',None)
        if driver is not self._driver or socket is not self._socket:
            self._needs_full=self._driver is not None
            self._driver,self._socket=driver,socket;self._private_epoch=str(uuid.uuid4());self._schema_ddl=None;self._source_specs_ddl=None
        before=self.observer._ddl();self.observer._active_ddl_guard()
        server=self._rows('SELECT @@server_uuid AS server_uuid,@@version AS version,CONNECTION_ID() AS connection_id')[0]
        if not str(server['version']).startswith('8.4.'):raise ValueError('Recovery deltas require verified MySQL 8.4')
        self._verify_tables(before)
        # Column/primary-key metadata only changes through the guarded DDL
        # vector. Keep live table-incarnation and trigger checks on every pass.
        if self._source_specs_ddl != before:
            current_specs=table_specs(self.connection)
            if current_specs!=self.specs:raise ValueError('Recovery source schema changed; bootstrap required')
            self._source_specs_ddl=before
        watched=(*self.specs,CLOCK,FEED,INSTANCE)
        placeholders=','.join('%s' for _ in watched)
        rows=self._rows(f'SELECT NAME,TABLE_ID FROM information_schema.INNODB_TABLES WHERE NAME IN ({placeholders})',
            tuple(SCHEMA+'/'+table for table in watched))
        tables={row['NAME']:int(row['TABLE_ID']) for row in rows}
        if set(tables)!={SCHEMA+'/'+table for table in watched}:raise ValueError('Recovery InnoDB table incarnation unavailable')
        rows=self._triggers();found={row['TRIGGER_NAME']:row for row in rows if row['TRIGGER_NAME'].startswith(PREFIX)}
        if set(found)!=set(self.manifest) or not all(_equal_trigger(row,self.manifest[name]) for name,row in found.items()):
            raise ValueError('Recovery trigger contract changed or is incomplete')
        self.observer._active_ddl_guard();after=self.observer._ddl()
        if before!=after:raise ValueError('DDL changed during recovery attestation')
        instance=self._instance()
        payload={'contract':'rieke-recovery-v1','server':{key:server[key] for key in ('server_uuid','version')},'instance':instance,
            'tables':tables,'schema':self.specs,'ddl':after,'triggers':found}
        return hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()

    def bootstrap(self):
        if self.observer._in_transaction():
            self.reason='Recovery bootstrap requires no active transaction';return self
        locked=False
        try:
            if getattr(self.connection,'_conn',None) is None:raise ValueError('Native connection required')
            locked=self._rows("SELECT GET_LOCK('rieke_recovery_generation_v1',10) AS acquired")[0]['acquired']==1
            if not locked:raise ValueError('Another recovery bootstrap is running')
            specs=table_specs(self.connection)
            existing_tables={row['TABLE_NAME'] for row in self._rows(
                'SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN (%s,%s,%s)',
                (SCHEMA,CLOCK,FEED,INSTANCE))}
            expected=manifest_from_specs(specs)
            present={row['TRIGGER_NAME']:row for row in self._triggers() if row['TRIGGER_NAME'].startswith(PREFIX)}
            legacy_manifests=[manifest_from_specs(specs,legacy=trim) for trim in (False,True)]
            if set(present)-set(expected):raise ValueError('Unknown recovery trigger or removed source table')
            old_triggers=[]
            for name,row in present.items():
                if _equal_trigger(row,expected[name]):continue
                if not any(_equal_trigger(row,manifest[name]) for manifest in legacy_manifests):
                    raise ValueError('Existing recovery trigger differs from a known app-owned contract')
                old_triggers.append(name)
            if FEED in existing_tables:
                columns=self._rows('SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE FROM information_schema.COLUMNS '
                    'WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION',(SCHEMA,FEED))
                primary=self._rows("SELECT COLUMN_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                    "AND INDEX_NAME='PRIMARY' ORDER BY SEQ_IN_INDEX",(SCHEMA,FEED))
                actual=[(row['COLUMN_NAME'],row['COLUMN_TYPE']) for row in columns]
                legacy=[('project_uuid','varchar(36)'),('table_id','smallint unsigned'),('key_bytes','varbinary(1024)'),
                    ('generation','bigint unsigned'),('deleted','tinyint unsigned')]
                ring=[legacy[0],('slot','smallint unsigned'),*legacy[1:]]
                if any(row['IS_NULLABLE']!='NO' for row in columns):raise ValueError('Recovery feed schema is incompatible')
                if actual==legacy and [row['COLUMN_NAME'] for row in primary]==['project_uuid','table_id','key_bytes']:
                    # Only this discardable hint table and exactly known owned
                    # triggers are replaced. Canonical authored rows stay put.
                    for name in present:self.connection.query(f'DROP TRIGGER `{SCHEMA}`.`{name}`',reconnect=False)
                    self.connection.query(f'DROP TABLE `{SCHEMA}`.`{FEED}`',reconnect=False)
                    existing_tables.remove(FEED);present={};old_triggers=[];self._needs_full=True
                elif actual!=ring or [row['COLUMN_NAME'] for row in primary]!=['project_uuid','slot']:
                    raise ValueError('Recovery feed schema is incompatible')
            for name in old_triggers:
                self.connection.query(f'DROP TRIGGER `{SCHEMA}`.`{name}`',reconnect=False)
                present.pop(name);self._needs_full=True
            if CLOCK not in existing_tables:
                self.connection.query(f'''CREATE TABLE IF NOT EXISTS `{SCHEMA}`.`{CLOCK}` (
                    project_uuid varchar(36) NOT NULL,scope_epoch char(36) NOT NULL,
                    generation bigint unsigned NOT NULL,retained_after bigint unsigned NOT NULL,
                    PRIMARY KEY(project_uuid)) ENGINE=InnoDB''',reconnect=False)
            if FEED not in existing_tables:
                self.connection.query(f'''CREATE TABLE IF NOT EXISTS `{SCHEMA}`.`{FEED}` (
                    project_uuid varchar(36) NOT NULL,slot smallint unsigned NOT NULL,table_id smallint unsigned NOT NULL,key_bytes varbinary(1024) NOT NULL,
                    generation bigint unsigned NOT NULL,deleted tinyint unsigned NOT NULL,
                    PRIMARY KEY(project_uuid,slot)) ENGINE=InnoDB''',reconnect=False)
            if INSTANCE not in existing_tables:
                self.connection.query(f'''CREATE TABLE IF NOT EXISTS `{SCHEMA}`.`{INSTANCE}` (
                    singleton tinyint unsigned NOT NULL,instance_epoch char(36) NOT NULL,owner_connection_id bigint unsigned NOT NULL,
                    PRIMARY KEY(singleton)) ENGINE=InnoDB''',reconnect=False)
            self._instance(initialize=True)
            expected=manifest_from_specs(specs)
            present={row['TRIGGER_NAME']:row for row in self._triggers() if row['TRIGGER_NAME'].startswith(PREFIX)}
            if set(present)-set(expected):raise ValueError('Unknown recovery trigger or removed source table')
            for name,trigger in expected.items():
                if name in present:
                    if not _equal_trigger(present[name],trigger):raise ValueError('Existing recovery trigger differs from expected contract')
                else:
                    self.connection.query(f"CREATE TRIGGER `{SCHEMA}`.`{name}` AFTER {trigger['event']} ON "
                        f"`{SCHEMA}`.`{trigger['table']}` FOR EACH ROW {trigger['body']}",reconnect=False)
            self.specs,self.manifest=specs,expected
            self._source_specs_ddl=None
            self._contract();self._clock(create=True)
            self.ready=True;self.reason=None
        except Exception as error:
            self.ready=False;self.reason=str(error)
        finally:
            if locked:
                with contextlib.suppress(Exception):self.connection.query("SELECT RELEASE_LOCK('rieke_recovery_generation_v1')",reconnect=False)
        return self

    def token(self):
        if not self.ready or self.observer._in_transaction():return None
        try:
            before=self._contract();clock=self._clock(create=True)
            if self._contract()!=before:raise ValueError('Recovery authority changed while reading watermark')
            return {'format':'rieke-recovery-watermark','version':1,'project_uuid':self.project_uuid,
                'authority':before,'scope_epoch':clock['scope_epoch'],'generation':clock['generation']}
        except Exception as error:
            self.reason=str(error);self._private_epoch=str(uuid.uuid4());self._schema_ddl=None;self._needs_full=True
            return None

    @staticmethod
    def _continues(prior,current,floor):
        return (isinstance(prior,dict) and set(prior)==set(current)
            and all(prior[key]==current[key] for key in current if key!='generation')
            and type(prior['generation']) is int and floor<=prior['generation']<=current['generation'])

    @contextlib.contextmanager
    def capture(self, prior_watermark=None, *, limit=100000):
        if self.observer._in_transaction():raise ValueError('Recovery capture cannot nest inside a transaction')
        # Optional tables can be created lazily by a newly used UI feature.
        try:
            if not self.ready:
                self.bootstrap()
            if self.ready:
                try:self._contract()
                except Exception:self.bootstrap()
            if self.ready:self._clock(create=True)
        except Exception as error:
            self.reason=str(error);self._needs_full=True;self.ready=False
        if not self.ready:
            yield None
            return
        try:
            # DataJoint normally starts WITH CONSISTENT SNAPSHOT. Read committed
            # is scoped to this next transaction only; after the clock lock no
            # watched project writer can commit, so all row reads are coherent.
            self.connection.query('SET TRANSACTION ISOLATION LEVEL READ COMMITTED',reconnect=False)
            with self.connection.transaction:
                # A locking read does not establish an old RR consistent-read
                # snapshot. The first canonical read comes after this lock, so
                # every project trigger writer is either committed or blocked.
                clock=self._clock(lock=True)
                for table in (*self.specs,CLOCK,FEED,INSTANCE):self._rows(f'SELECT 1 FROM `{SCHEMA}`.{_name(table)} LIMIT 0')
                authority=self._contract()
                watermark={'format':'rieke-recovery-watermark','version':1,'project_uuid':self.project_uuid,
                    'authority':authority,'scope_epoch':clock['scope_epoch'],'generation':clock['generation']}
                complete=not self._needs_full and self._continues(prior_watermark,watermark,clock['retained_after'])
                keys={table:[] for table in self.specs}
                if complete:
                    changes=self._rows(f'SELECT table_id,key_bytes FROM `{SCHEMA}`.`{FEED}` '
                        'WHERE project_uuid=%s AND generation>%s ORDER BY generation LIMIT %s',
                        (self.project_uuid,prior_watermark['generation'],limit+1))
                    if len(changes)>limit:complete=False
                    else:
                        by_id={value:key for key,value in TABLE_IDS.items()};seen=set()
                        for row in changes:
                            table=by_id.get(int(row['table_id']))
                            if table not in self.specs:raise ValueError('Recovery feed references an unknown table')
                            raw=row['key_bytes'];raw=raw.decode('utf8') if isinstance(raw,(bytes,bytearray)) else raw
                            key=json.loads(raw)
                            if not isinstance(key,list) or len(key)!=len(self.specs[table]['primary_keys']):
                                raise ValueError('Recovery feed primary key is malformed')
                            identity=(table,raw)
                            if identity not in seen:
                                keys[table].append(tuple(key));seen.add(identity)
                def verify():
                    now=self._clock(lock=True)
                    if self._contract()!=authority or now['scope_epoch']!=clock['scope_epoch'] or now['generation']!=clock['generation']:
                        raise ValueError('Recovery snapshot changed during capture')
                plan=RecoveryCapture(watermark,complete,keys,
                    {table:spec['primary_keys'] for table,spec in self.specs.items()},
                    {table:spec['columns'] for table,spec in self.specs.items()},
                    {table:spec['json_columns'] for table,spec in self.specs.items()},verify)
                yield plan
                verify()
                self._needs_full=False
        except Exception as error:
            self.reason=str(error);self._private_epoch=str(uuid.uuid4());self._schema_ddl=None;self._needs_full=True
            raise

    def prune(self, durable_watermark, *, keep_generations=RECOVERY_WINDOW):
        """Keep a bounded recent window for derived consumers after durability.

        Trigger-side trimming may already have advanced the floor during a large
        transaction. A lagging mirror/index always rebuilds canonical state.
        """
        if self.observer._in_transaction():raise ValueError('Recovery pruning cannot nest inside a transaction')
        if not isinstance(durable_watermark,dict):raise ValueError('Expected a durable recovery watermark')
        if type(keep_generations) is not int or not 0<=keep_generations<=RECOVERY_WINDOW:
            raise ValueError('Recovery retention must fit the bounded generation window')
        with self.connection.transaction:
            clock=self._clock(lock=True)
            if (durable_watermark.get('project_uuid')!=self.project_uuid
                    or durable_watermark.get('scope_epoch')!=clock['scope_epoch']
                    or type(durable_watermark.get('generation')) is not int
                    or not 0<=durable_watermark['generation']<=clock['generation']):
                raise ValueError('Durable watermark does not match this recovery clock')
            floor=max(clock['retained_after'],max(0,durable_watermark['generation']-keep_generations))
            self.connection.query(f'DELETE FROM `{SCHEMA}`.`{FEED}` WHERE project_uuid=%s AND (generation<=%s OR generation>%s)',
                (self.project_uuid,floor,clock['generation']),reconnect=False)
            self.connection.query(f'UPDATE `{SCHEMA}`.`{CLOCK}` SET retained_after=%s WHERE project_uuid=%s',
                (floor,self.project_uuid),reconnect=False)


def bootstrap(connection, project_uuid):return RecoveryGenerationAuthority(connection,project_uuid).bootstrap()

# Public name used by the snapshot mirror integration.
RecoveryTracker=RecoveryGenerationAuthority
