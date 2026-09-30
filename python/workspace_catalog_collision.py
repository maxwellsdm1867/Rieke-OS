"""Bound catalog identity checks without altering persistent acquisition tables.

Create scratch indexes before the import transaction, while its advisory lock is
held. Use the catalog column's actual collation; Python string normalization must
never decide whether a SQL population routine would reuse an existing identity.
"""
from __future__ import annotations

import re
import uuid


KINDS=('Animal','Preparation','Cell','EpochGroup','EpochBlock','Epoch','Response','Stimulus')
_TABLE=re.compile(r'^`([A-Za-z0-9_]+)`\.`([A-Za-z0-9_]+)`$')
_NAME=re.compile(r'^[A-Za-z0-9_]+$')


def _original_collision(table, values, batch_size):
    for offset in range(0,len(values),batch_size):
        found=(table & [{'h5_uuid':key} for key in values[offset:offset+batch_size]]).fetch('h5_uuid',limit=1)
        if len(found):return found[0]
    return None


class CatalogCollisionLookup:
    """Connection-local scratch relations, owned by one locked import session.

    Unsupported table metadata uses the original DataJoint lookup. SQL setup,
    insert, query and cleanup failures are errors, never permission to skip a
    collision check. The caller must close after its transaction has ended.
    """
    def __init__(self,catalog):
        self.catalog=catalog
        self.connection=getattr(getattr(catalog,'schema',None),'connection',None)
        self.tables={};self.temporary={};self.owner=None;self.prepared=False

    def _query(self,sql,args=(),**options):
        # Reconnecting would silently lose temporary tables and the import lock.
        return self.connection.query(sql,args,reconnect=False,**options)

    def _assert_owner(self,transaction=None):
        if transaction is not None and self.connection.in_transaction is not transaction:
            raise RuntimeError('Catalog identity scratch lookup used outside its required transaction boundary')
        owner,locked=self._query("SELECT CONNECTION_ID(),IS_USED_LOCK('recording_workspace_import')").fetchone()
        if owner!=self.owner or locked!=owner:
            raise RuntimeError('Catalog identity lookup lost its owning connection or import lock')

    def prepare(self):
        if self.prepared:raise RuntimeError('Catalog identity lookup is already prepared')
        self.prepared=True
        # Lightweight relation doubles and non-MySQL adapters retain the exact
        # existing check. Real pinned DataJoint exposes a Boolean transaction flag.
        if self.connection is None or type(getattr(self.connection,'in_transaction',None)) is not bool:
            return self
        if self.connection.in_transaction:
            raise RuntimeError('Prepare catalog identity scratch indexes before starting the import transaction')
        self.owner=self._query('SELECT CONNECTION_ID()').fetchone()[0]
        self._assert_owner(transaction=False)
        try:
            for kind in KINDS:
                relation=getattr(self.catalog,kind)
                full=getattr(relation,'full_table_name',None)
                match=_TABLE.fullmatch(full) if isinstance(full,str) else None
                if not match:continue
                column=self._query(f'SHOW FULL COLUMNS FROM {full} WHERE Field=%s',('h5_uuid',),as_dict=True).fetchone()
                if not column or str(column['Type']).lower()!='varchar(255)':continue
                indexes=self._query(f'SHOW INDEX FROM {full}',as_dict=True).fetchall()
                if any(row.get('Seq_in_index')==1 and row.get('Column_name')=='h5_uuid'
                       and row.get('Visible','YES')!='NO' for row in indexes):
                    continue  # Existing UUID indexes already serve bounded probes.
                collation=column.get('Collation')
                if not isinstance(collation,str) or not _NAME.fullmatch(collation):continue
                charset=self._query('SELECT CHARACTER_SET_NAME FROM information_schema.COLLATIONS WHERE COLLATION_NAME=%s',(collation,)).fetchone()
                if not charset or not _NAME.fullmatch(charset[0]):continue
                # Each collation receives a compatible scratch index, including
                # older utf8mb3 catalogs and catalogs with per-table overrides.
                key=(match[1],charset[0],collation)
                if key not in self.temporary:
                    temporary=f'`{match[1]}`.`_workspace_identity_{uuid.uuid4().hex}`'
                    self._query(f'CREATE TEMPORARY TABLE {temporary} (h5_uuid VARCHAR(255) CHARACTER SET {charset[0]} COLLATE {collation} NOT NULL, KEY candidate_uuid(h5_uuid)) ENGINE=InnoDB')
                    self.temporary[key]=temporary
                self.tables[kind]=(full,self.temporary[key])
        except Exception as error:
            try:self.close()
            except Exception as cleanup:error.add_note(f'Identity scratch cleanup also failed: {cleanup}')
            raise
        return self

    def first_collision(self,kind,values,batch_size=200):
        if not self.prepared:raise RuntimeError('Prepare catalog identity lookup before checking identities')
        if kind not in KINDS:raise ValueError('Unknown acquisition identity table')
        if type(batch_size) is not int or not 1<=batch_size<=500:
            raise ValueError('Identity lookup batches must contain 1–500 identities')
        if not values:return None
        if self.owner is not None:self._assert_owner(transaction=True)
        if kind not in self.tables or len(values)<=batch_size:
            return _original_collision(getattr(self.catalog,kind),values,batch_size)
        full,temporary=self.tables[kind]
        # An empty catalog needs neither staging nor repeated empty scans.
        if self._query(f'SELECT h5_uuid FROM {full} LIMIT 1').fetchone() is None:return None
        self._query(f'DELETE FROM {temporary}')
        for offset in range(0,len(values),batch_size):
            batch=values[offset:offset+batch_size]
            self._query(f'INSERT INTO {temporary} (h5_uuid) VALUES '+','.join(['(%s)']*len(batch)),tuple(batch))
        # Catalog-first join plus indexed probes bounds an unindexed existing
        # catalog to one scan; the server retains its native equality semantics.
        found=self._query(f'SELECT existing.h5_uuid FROM {full} AS existing STRAIGHT_JOIN {temporary} AS incoming FORCE INDEX(candidate_uuid) ON incoming.h5_uuid=existing.h5_uuid LIMIT 1').fetchone()
        self._query(f'DELETE FROM {temporary}')
        return found[0] if found else None

    def close(self):
        if not self.temporary:return
        self._assert_owner(transaction=False)
        failures=[]
        for key,temporary in list(self.temporary.items()):
            try:self._query(f'DROP TEMPORARY TABLE {temporary}')
            except Exception as error:failures.append(error)
            else:del self.temporary[key]
        if failures:
            # Closing this exact connection lets MySQL discard all remaining
            # session-local tables. Never reconnect to perform cleanup.
            self.connection.close();self.temporary.clear()
            raise RuntimeError('Catalog identity scratch cleanup failed; owning connection was closed') from failures[0]

    def __enter__(self):return self.prepare()

    def __exit__(self,kind,error,traceback):
        try:self.close()
        except Exception as cleanup:
            if error is None:raise
            error.add_note(f'Identity scratch cleanup also failed: {cleanup}')
        return False
