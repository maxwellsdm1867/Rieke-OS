"""Verified MySQL change authority for derived, discardable read caches.

Native triggers advance scope counters in the same InnoDB transaction as source
DML. A server-global DDL command vector detects interruptions in trigger coverage,
including drop/recreate within the precision of information_schema.CREATED.
Active DDL/prepared/procedure/event statements must be observable in Performance
Schema; disabled witnesses fail closed. Coordinated privileged disabling and
restoring those witnesses or rewriting authority rows is outside this contract.
Unsupported adapters or unverifiable contracts always return None: callers use
the canonical reader. This is not an authorization/security boundary against a
privileged administrator deliberately rewriting both data and its authority.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import contextlib
import contextvars
import hashlib
import json
import threading
import uuid

SCHEMA='recording_workspace'
GENERATION='app_state_generation'
CHANGES='app_annotation_changes'
PREFIX='rieke_state_v1_'
OBSERVER_LOSSES=tuple('Performance_schema_'+name+'_lost' for name in (
    'thread_classes','thread_instances','statement_classes','nested_statement',
    'prepared_statements','program','locker'))
DDL_COUNTERS=('Com_create_trigger','Com_drop_trigger','Com_create_table','Com_drop_table',
              'Com_alter_table','Com_rename_table','Com_truncate','Com_create_db','Com_drop_db',
              'Com_alter_db','Com_alter_tablespace','Com_create_event','Com_alter_event','Com_drop_event')
DDL_EVENTS=tuple('statement/sql/'+key[4:] for key in DDL_COUNTERS)+(
    'statement/sql/execute_sql','statement/com/Execute','statement/sql/call_procedure',
    'statement/scheduler/event')
WATCHED=('curation','shared_annotation','annotation_profile',GENERATION,CHANGES)


def _scope_sql(alias, kind):
    scope=f'{alias}.protocol_uuid' if kind=='protocol_curation' else f'{alias}.project_uuid'
    return (f"INSERT INTO `{SCHEMA}`.`{GENERATION}` (project_uuid,scope_kind,scope_uuid,scope_epoch,generation) "
            f"VALUES ({alias}.project_uuid,'{kind}',{scope},UUID(),1) "
            "ON DUPLICATE KEY UPDATE generation=generation+1;")


def _change_sql(alias, table, deleted):
    kind=f'{alias}.target_kind' if table=='shared_annotation' else "'profile'"
    target=f'{alias}.target_uuid' if table=='shared_annotation' else f'{alias}.profile_uuid'
    return (f"INSERT INTO `{SCHEMA}`.`{CHANGES}` (project_uuid,target_kind,target_uuid,profile_uuid,last_generation,deleted) "
            f"SELECT {alias}.project_uuid,{kind},{target},{alias}.profile_uuid,generation,{int(deleted)} "
            f"FROM `{SCHEMA}`.`{GENERATION}` WHERE project_uuid={alias}.project_uuid "
            f"AND scope_kind='shared_annotations' AND scope_uuid={alias}.project_uuid "
            "ON DUPLICATE KEY UPDATE last_generation=VALUES(last_generation),deleted=VALUES(deleted);")


def trigger_manifest():
    result={}
    for table,short in (('curation','curation'),('shared_annotation','annotation'),('annotation_profile','profile')):
        kind='protocol_curation' if table=='curation' else 'shared_annotations'
        for event,suffix in (('INSERT','ai'),('UPDATE','au'),('DELETE','ad')):
            statements=[]
            for alias in (('NEW',) if event=='INSERT' else ('OLD',) if event=='DELETE' else ('OLD','NEW')):
                statements.append(_scope_sql(alias,kind))
                if table!='curation':statements.append(_change_sql(alias,table,alias=='OLD'))
            result[PREFIX+short+'_'+suffix]={'table':table,'event':event,'timing':'AFTER',
                'body':'BEGIN '+' '.join(statements)+' END'}
    return result


MANIFEST=trigger_manifest()


def _normalized(value):
    return ' '.join(str(value).split())


@dataclass(frozen=True)
class GenerationToken:
    authority: str
    project_uuid: str
    shared_epoch: str
    shared_generation: int
    protocol_uuid: str | None = None
    protocol_epoch: str | None = None
    protocol_generation: int | None = None


class StateGenerationAuthority:
    """One connection's fail-closed view of a server-native authority contract."""
    def __init__(self, connection, project_uuid):
        self.connection=connection
        self.project_uuid=str(uuid.UUID(str(project_uuid)))
        self.reason='not bootstrapped'
        self.ready=False
        self._connection_ref=None
        self._connection_epoch=None
        self._read_generation=contextvars.ContextVar('rieke_native_read_generation',default=None)
        self._response_contract=contextvars.ContextVar('rieke_native_response_contract',default=None)
        self._verified_read_token=None

    def _rows(self, sql, args=()):
        return list(self.connection.query(sql,args,as_dict=True,reconnect=False).fetchall())

    def _in_transaction(self):
        return bool(getattr(self.connection,'in_transaction',True))

    def _ddl(self):
        names=','.join("'"+key+"'" for key in DDL_COUNTERS)
        rows=self._rows(f'SHOW GLOBAL STATUS WHERE Variable_name IN ({names})')
        values={row['Variable_name'].casefold():int(row['Value']) for row in rows}
        if set(values)!={key.casefold() for key in DDL_COUNTERS}:
            raise ValueError('server does not expose the required global DDL counters')
        return tuple((key,values[key.casefold()]) for key in DDL_COUNTERS)

    def _triggers(self):
        return self._rows('SELECT TRIGGER_NAME,EVENT_MANIPULATION,EVENT_OBJECT_TABLE,ACTION_TIMING,ACTION_STATEMENT,CREATED '
                          'FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s',(SCHEMA,))

    @staticmethod
    def _verified_trigger(row):
        expected=MANIFEST.get(row['TRIGGER_NAME'])
        return expected is not None and all(_normalized(row[field])==_normalized(expected[key]) for field,key in
            (('EVENT_OBJECT_TABLE','table'),('EVENT_MANIPULATION','event'),('ACTION_TIMING','timing'),('ACTION_STATEMENT','body')))

    def _observer_status(self):
        names=OBSERVER_LOSSES+('Connections','Threads_connected')
        quoted=','.join("'"+name+"'" for name in names)
        rows=self._rows(f'SHOW GLOBAL STATUS WHERE Variable_name IN ({quoted})')
        values={row['Variable_name']:int(row['Value']) for row in rows}
        if set(values)!=set(names) or any(values[name] for name in OBSERVER_LOSSES):
            raise ValueError('Performance Schema lost a required statement or thread observer')
        return values['Connections'],values['Threads_connected']

    def _active_ddl_guard(self):
        # Command counters advance when a DDL statement begins, even while its
        # metadata lock is pending. An active-statement witness closes that gap.
        # Disabled/unavailable instrumentation is never treated as an empty set.
        population=self._observer_status()
        consumers=self._rows("SELECT NAME,ENABLED FROM performance_schema.setup_consumers WHERE NAME IN "
            "('global_instrumentation','thread_instrumentation','events_statements_current')")
        if len(consumers)!=3 or any(row['ENABLED']!='YES' for row in consumers):
            raise ValueError('DDL statement consumers are unavailable or disabled')
        placeholders=','.join('%s' for _ in DDL_EVENTS)
        instruments=self._rows(f'SELECT NAME,ENABLED FROM performance_schema.setup_instruments WHERE NAME IN ({placeholders})',DDL_EVENTS)
        if len(instruments)!=len(DDL_EVENTS) or any(row['ENABLED']!='YES' for row in instruments):
            raise ValueError('DDL statement instruments are unavailable or disabled')
        threads=self._rows("SELECT PROCESSLIST_ID,NAME,INSTRUMENTED FROM performance_schema.threads "
            "WHERE TYPE='FOREGROUND' AND PROCESSLIST_ID IS NOT NULL")
        if any(row['INSTRUMENTED']!='YES' for row in threads):
            raise ValueError('an uninstrumented SQL connection prevents DDL attestation')
        # Loss counters can be reset by administrative FLUSH STATUS. Match the
        # independently maintained connection population as well, fencing new
        # connections so an omitted live thread cannot look like an empty set.
        known={'thread/sql/one_connection','thread/sql/event_scheduler','thread/sql/compress_gtid_table'}
        clients=sum(row['NAME']=='thread/sql/one_connection' for row in threads)
        if any(row['NAME'] not in known for row in threads) or clients!=population[1] or self._observer_status()!=population:
            raise ValueError('SQL connection observers changed or are incomplete')
        if self._rows('SELECT EVENT_SCHEMA,EVENT_NAME FROM information_schema.EVENTS LIMIT 1'):
            raise ValueError('scheduled database events are outside the native authority contract')
        if self._rows('SELECT CHANNEL_NAME FROM performance_schema.replication_applier_configuration LIMIT 1'):
            raise ValueError('replication appliers are outside the native authority contract')
        active=self._rows(f'SELECT THREAD_ID,EVENT_NAME FROM performance_schema.events_statements_current '
            f'WHERE EVENT_NAME IN ({placeholders}) AND END_EVENT_ID IS NULL LIMIT 1',DDL_EVENTS)
        if active:raise ValueError('DDL is in progress; native cache authority is deferred')

    def _verify_authority_tables(self, ddl):
        if getattr(self,'_schema_counter',None)==ddl:return
        expected={GENERATION:[('project_uuid','varchar(36)'),('scope_kind','varchar(32)'),
            ('scope_uuid','varchar(36)'),('scope_epoch','char(36)'),('generation','bigint unsigned')],
            CHANGES:[('project_uuid','varchar(36)'),('target_kind','varchar(16)'),('target_uuid','varchar(36)'),
                ('profile_uuid','varchar(36)'),('last_generation','bigint unsigned'),('deleted','tinyint unsigned')]}
        rows=self._rows('SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE FROM information_schema.COLUMNS '
            'WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN (%s,%s) ORDER BY TABLE_NAME,ORDINAL_POSITION',
            (SCHEMA,GENERATION,CHANGES))
        for table,columns in expected.items():
            actual=[(row['COLUMN_NAME'],row['COLUMN_TYPE']) for row in rows if row['TABLE_NAME']==table]
            if actual!=columns or any(row['IS_NULLABLE']!='NO' for row in rows if row['TABLE_NAME']==table):
                raise ValueError('authority table columns are incompatible')
        rows=self._rows('SELECT TABLE_NAME,COLUMN_NAME FROM information_schema.STATISTICS '
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN (%s,%s) AND INDEX_NAME='PRIMARY' ORDER BY TABLE_NAME,SEQ_IN_INDEX",
            (SCHEMA,GENERATION,CHANGES))
        for table,keys in ((GENERATION,['project_uuid','scope_kind','scope_uuid']),
                           (CHANGES,['project_uuid','target_kind','target_uuid','profile_uuid'])):
            if [row['COLUMN_NAME'] for row in rows if row['TABLE_NAME']==table]!=keys:
                raise ValueError('authority primary key is incompatible')
        self._schema_counter=ddl

    def _contract(self):
        lease=self._response_contract.get()
        driver=getattr(self.connection,'_conn',None)
        if (lease is not None and lease['active'] and not self._in_transaction()
                and lease['thread']==threading.get_ident() and driver is lease['driver']
                and getattr(driver,'_sock',None) is lease['socket']):
            return lease['authority']
        return self._attest_contract()

    @contextlib.contextmanager
    def response_contract(self):
        """Attest schema once before and after a complete read response.

        Scope generations still read live before/after the response. Contract
        reuse is confined to this thread, socket and autocommit read interval;
        the owner must discard derived work if the closing attestation fails.
        """
        if not self.ready or self._in_transaction() or self._response_contract.get() is not None:
            yield
            return
        try:
            authority=self._attest_contract()
        except Exception:
            # Preserve the ordinary fresh-token/fallback behavior when a native
            # contract cannot be established at the opening boundary.
            yield
            return
        driver=getattr(self.connection,'_conn',None)
        lease={'active':True,'authority':authority,'driver':driver,
            'socket':getattr(driver,'_sock',None),'thread':threading.get_ident()}
        reset=self._response_contract.set(lease)
        try:
            yield
        finally:
            lease['active']=False
            self._response_contract.reset(reset)
        try:
            if self._attest_contract()!=authority:
                raise ValueError('Native database contract changed while reading the response')
        except Exception:
            self._connection_epoch=str(uuid.uuid4())
            self._schema_counter=None
            self._verified_read_token=None
            raise

    def _attest_contract(self):
        underlying=getattr(self.connection,'_conn',None)
        if underlying is None:raise ValueError('unrecognized connection incarnation')
        if underlying is not self._connection_ref:
            self._connection_ref=underlying
            self._connection_epoch=str(uuid.uuid4())
            self._schema_counter=None
        before=self._ddl()
        self._active_ddl_guard()
        self._verify_authority_tables(before)
        server=self._rows('SELECT @@server_uuid AS server_uuid,@@version AS version,CONNECTION_ID() AS connection_id')[0]
        # This contract is validated against the bundled MySQL 8.4 family.
        if not str(server['version']).startswith('8.4.'):
            raise ValueError('native generation authority requires verified MySQL 8.4')
        optional_lookup=('app_shared_tag_lookup','app_shared_tag_lookup_checkpoint',
                         'app_shared_tag_dictionary','app_shared_tag_authors')
        names=','.join('%s' for _ in (*WATCHED,*optional_lookup))
        rows=self._rows(f'SELECT NAME,TABLE_ID FROM information_schema.INNODB_TABLES WHERE NAME IN ({names})',
                        tuple(SCHEMA+'/'+table for table in (*WATCHED,*optional_lookup)))
        incarnations={row['NAME']:int(row['TABLE_ID']) for row in rows}
        if not {SCHEMA+'/'+table for table in WATCHED} <= set(incarnations):
            raise ValueError('watched InnoDB table incarnation is unavailable')
        triggers=self._triggers()
        known={row['TRIGGER_NAME']:row for row in triggers if row['TRIGGER_NAME'] in MANIFEST}
        if set(known)!=set(MANIFEST) or not all(self._verified_trigger(row) for row in known.values()):
            raise ValueError('native generation trigger contract is incomplete or changed')
        # Other application triggers may add effects but cannot silently suppress
        # the AFTER triggers. Unexpected app-owned names are incompatible.
        if any(row['TRIGGER_NAME'].startswith(PREFIX) and row['TRIGGER_NAME'] not in MANIFEST for row in triggers):
            raise ValueError('unknown application generation trigger')
        self._active_ddl_guard()
        after=self._ddl()
        if before!=after:raise ValueError('DDL changed while verifying native authority')
        payload={'server':server,'connection_epoch':self._connection_epoch,'tables':incarnations,
                 'ddl':after,'triggers':known,
                 'lookup_triggers':{row['TRIGGER_NAME']:row for row in triggers
                    if row['TRIGGER_NAME'].startswith('rieke_tag_lookup_v1_')}}
        return hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()

    def bootstrap(self):
        if self._in_transaction():
            self.reason='bootstrap deferred during an active transaction';return self
        locked=False
        try:
            # Avoid attempting DDL against test doubles or other SQL adapters.
            if getattr(self.connection,'_conn',None) is None:
                raise ValueError('native connection required')
            locked=self._rows("SELECT GET_LOCK('rieke_state_generation_v1',10) AS acquired")[0]['acquired']==1
            if not locked:raise ValueError('another authority bootstrap is running')
            existing_tables={row['TABLE_NAME'] for row in self._rows(
                'SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN (%s,%s)',
                (SCHEMA,GENERATION,CHANGES))}
            if GENERATION not in existing_tables:
                self.connection.query(f'''CREATE TABLE IF NOT EXISTS `{SCHEMA}`.`{GENERATION}` (
                    project_uuid varchar(36) NOT NULL,scope_kind varchar(32) NOT NULL,scope_uuid varchar(36) NOT NULL,
                    scope_epoch char(36) NOT NULL,generation bigint unsigned NOT NULL,
                    PRIMARY KEY(project_uuid,scope_kind,scope_uuid)) ENGINE=InnoDB''',reconnect=False)
            if CHANGES not in existing_tables:
                self.connection.query(f'''CREATE TABLE IF NOT EXISTS `{SCHEMA}`.`{CHANGES}` (
                    project_uuid varchar(36) NOT NULL,target_kind varchar(16) NOT NULL,target_uuid varchar(36) NOT NULL,
                    profile_uuid varchar(36) NOT NULL,last_generation bigint unsigned NOT NULL,deleted tinyint unsigned NOT NULL,
                    PRIMARY KEY(project_uuid,target_kind,target_uuid,profile_uuid),KEY changed(project_uuid,last_generation)) ENGINE=InnoDB''',reconnect=False)
            present={row['TRIGGER_NAME']:row for row in self._triggers()}
            for name,expected in MANIFEST.items():
                if name in present:
                    if not self._verified_trigger(present[name]):raise ValueError('existing authority trigger differs from expected contract')
                else:
                    self.connection.query(f"CREATE TRIGGER `{SCHEMA}`.`{name}` AFTER {expected['event']} ON "
                                          f"`{SCHEMA}`.`{expected['table']}` FOR EACH ROW {expected['body']}",reconnect=False)
            self._contract()
            self.ready=True;self.reason=None
        except Exception as error:
            self.ready=False;self.reason=str(error)
        finally:
            if locked:
                try:self.connection.query("SELECT RELEASE_LOCK('rieke_state_generation_v1')",reconnect=False)
                except Exception:pass
        return self

    def _scope(self, kind, identity):
        rows=self._rows(f'SELECT scope_epoch,generation FROM `{SCHEMA}`.`{GENERATION}` '
                        'WHERE project_uuid=%s AND scope_kind=%s AND scope_uuid=%s',(self.project_uuid,kind,identity))
        if not rows:
            # First access or deleted counter: fresh UUID forbids collision with
            # previous cache tokens. Only the derived authority row is created.
            self.connection.query(f'INSERT IGNORE INTO `{SCHEMA}`.`{GENERATION}` '
                '(project_uuid,scope_kind,scope_uuid,scope_epoch,generation) VALUES (%s,%s,%s,%s,0)',
                (self.project_uuid,kind,identity,str(uuid.uuid4())),reconnect=False)
            rows=self._rows(f'SELECT scope_epoch,generation FROM `{SCHEMA}`.`{GENERATION}` '
                'WHERE project_uuid=%s AND scope_kind=%s AND scope_uuid=%s',(self.project_uuid,kind,identity))
        if len(rows)!=1:raise ValueError('scope generation unavailable')
        return str(uuid.UUID(rows[0]['scope_epoch'])),int(rows[0]['generation'])

    @contextlib.contextmanager
    def read_scope(self, expected):
        """Reuse one verified generation only inside an externally fenced read.

        The owner must freshly attest after leaving this scope and discard all
        derived work on failure. This is never a transaction/mutation authority.
        Context-local leases cannot escape their lifetime or cross threads.
        """
        if (type(expected) is not GenerationToken or expected.project_uuid!=self.project_uuid
                or expected!=self._verified_read_token):
            raise ValueError('Read scope belongs to a different native authority')
        previous=self._read_generation.get()
        if previous is not None and previous['active']:
            raise ValueError('Native read scopes cannot be nested')
        lease={'generation':expected,'connection':getattr(self.connection,'_conn',None),
            'thread':threading.get_ident(),'active':True}
        reset=self._read_generation.set(lease)
        try:yield
        finally:
            lease['active']=False
            self._read_generation.reset(reset)

    def token(self, protocol_uuid=None):
        lease=self._read_generation.get()
        if (lease is not None and lease['active'] and self.ready and not self._in_transaction()
                and lease['thread']==threading.get_ident()
                and getattr(self.connection,'_conn',None) is lease['connection']):
            expected=lease['generation']
            protocol=str(uuid.UUID(str(protocol_uuid))) if protocol_uuid is not None else None
            if protocol is None:
                return replace(expected,protocol_uuid=None,protocol_epoch=None,protocol_generation=None)
            if protocol==expected.protocol_uuid:return expected
        return self._fresh_token(protocol_uuid)

    def _fresh_token(self, protocol_uuid=None):
        self._verified_read_token=None
        if not self.ready:return None
        if self._in_transaction():
            self.reason='generation reads require an autocommit snapshot';return None
        try:
            authority=self._contract()
            shared=self._scope('shared_annotations',self.project_uuid)
            protocol=str(uuid.UUID(str(protocol_uuid))) if protocol_uuid is not None else None
            current=self._scope('protocol_curation',protocol) if protocol else (None,None)
            # Fence all metadata and scope queries against concurrent DDL.
            if authority!=self._contract():raise ValueError('authority changed while reading scope generations')
            self.reason=None
            self._verified_read_token=GenerationToken(authority,self.project_uuid,*shared,protocol,*current)
            return self._verified_read_token
        except Exception as error:
            # A failed witness breaks continuity even if a later read sees
            # coincident counters. Never reuse the previous private authority.
            self._connection_epoch=str(uuid.uuid4())
            self._schema_counter=None
            self.reason=str(error);return None

    def assert_current_locked(self, expected):
        """Lock scope rows and reject a stale mutation inside its transaction.

        Trigger writers acquire these same rows, closing the ordinary external
        DML race between preflight and the saved decisions.
        """
        from workspace_curation import RevisionConflict
        if not self.ready or not self._in_transaction():raise RevisionConflict({'generation':'unavailable'})
        try:
            # Short transaction-only metadata locks prevent trigger DDL during
            # the mutation; ordinary source DML remains governed by scope locks.
            for table in WATCHED:self._rows(f'SELECT 1 FROM `{SCHEMA}`.`{table}` LIMIT 0')
            authority=self._contract()
            scopes=[('shared_annotations',self.project_uuid)]
            if expected.protocol_uuid:scopes.append(('protocol_curation',expected.protocol_uuid))
            found=[]
            for kind,identity in scopes:
                rows=self._rows(f'SELECT scope_epoch,generation FROM `{SCHEMA}`.`{GENERATION}` '
                    'WHERE project_uuid=%s AND scope_kind=%s AND scope_uuid=%s FOR UPDATE',
                    (self.project_uuid,kind,identity))
                if len(rows)!=1:raise ValueError('scope generation missing')
                found.append((rows[0]['scope_epoch'],int(rows[0]['generation'])))
            current=GenerationToken(authority,self.project_uuid,*found[0],expected.protocol_uuid,
                *(found[1] if len(found)>1 else (None,None)))
            if current!=expected or self._contract()!=authority:raise ValueError('generation changed')
        except Exception as error:
            raise RevisionConflict({'generation':str(error)}) from error

    def shared_changes(self, after_token, *, limit=10000):
        current=self.token()
        if current is None or after_token is None or (current.authority,current.shared_epoch)!=(after_token.authority,after_token.shared_epoch):
            return None
        rows=self._rows(f'SELECT target_kind,target_uuid,profile_uuid,last_generation,deleted FROM `{SCHEMA}`.`{CHANGES}` '
            'WHERE project_uuid=%s AND last_generation>%s ORDER BY last_generation LIMIT %s',
            (self.project_uuid,after_token.shared_generation,limit+1))
        if len(rows)>limit or self.token()!=current:return None
        return rows,current


def bootstrap(connection,project_uuid):
    return StateGenerationAuthority(connection,project_uuid).bootstrap()


def verify_export_triggers(connection, schemas):
    """Classify dump triggers without ever omitting an unknown SQL behavior.

    ``connection.query`` must return dictionary rows. The transfer layer adapts
    its PyMySQL connection to this read-only interface. A DDL witness fences the
    inventory and lets a caller reject changes across the logical dump.
    """
    reader = StateGenerationAuthority(connection, '00000000-0000-0000-0000-000000000000')
    try:
        before = reader._ddl()
    except Exception:
        before = None
    rows = []
    for schema in schemas:
        rows.extend(connection.query(
            'SELECT TRIGGER_SCHEMA,TRIGGER_NAME,EVENT_MANIPULATION,EVENT_OBJECT_TABLE,'
            'ACTION_TIMING,ACTION_STATEMENT,CREATED FROM information_schema.TRIGGERS '
            'WHERE TRIGGER_SCHEMA=%s', (schema,), as_dict=True).fetchall())
    rows.sort(key=lambda row: (row['TRIGGER_SCHEMA'], row['TRIGGER_NAME']))
    recovery_prefix = 'rieke_recovery_v1_'
    from workspace_native_tag_lookup import PREFIX as lookup_prefix, TRIGGER_MANIFEST
    expected = {**MANIFEST, **TRIGGER_MANIFEST}
    if any(row['TRIGGER_SCHEMA'] == SCHEMA and row['TRIGGER_NAME'].startswith(recovery_prefix) for row in rows):
        try:
            from workspace_recovery_generation import recovery_trigger_manifest
            expected.update(recovery_trigger_manifest(connection))
        except Exception:
            # A schema/observer mismatch cannot authorize stripping a trigger.
            pass
    try:
        after = reader._ddl()
    except Exception:
        after = None
    if before != after:
        raise ValueError('Database trigger coverage changed while preparing its backup')
    managed = any(row['TRIGGER_SCHEMA'] == SCHEMA and row['TRIGGER_NAME'].startswith((PREFIX, recovery_prefix, lookup_prefix))
                  for row in rows)
    known = [row for row in rows if row['TRIGGER_SCHEMA'] == SCHEMA
             and row['TRIGGER_NAME'] in expected
             and all(_normalized(row[field]) == _normalized(expected[row['TRIGGER_NAME']][key])
                     for field, key in (('EVENT_OBJECT_TABLE', 'table'), ('EVENT_MANIPULATION', 'event'),
                                       ('ACTION_TIMING', 'timing'), ('ACTION_STATEMENT', 'body')))]
    # A partial known installation is disposable too, but every present trigger
    # must be verified before --skip-triggers is safe. Foreign triggers remain
    # part of the original dump path or cause a mixed-installation refusal.
    safe = not rows or (len(known) == len(rows) and after is not None)
    reason = None
    if managed and not safe:
        reason = 'Project has unverified or custom database triggers; they cannot be omitted from a portable backup'
    fingerprint = hashlib.sha256(json.dumps({'triggers': rows, 'ddl': after},
                                            sort_keys=True, default=str).encode()).hexdigest()
    return {'safe_to_omit': safe, 'managed_present': managed, 'reason': reason,
            'trigger_count': len(rows), 'known_trigger_count': len(known),
            'trigger_names': [row['TRIGGER_NAME'] for row in rows],
            'contract_fingerprint': fingerprint}
