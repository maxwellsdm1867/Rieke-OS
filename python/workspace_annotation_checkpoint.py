"""Sealed shared-tag checkpoints, reusable only after fresh canonical proof.

Working indexes remain private and disposable. Immutable checkpoints are written
at preparation/clean-close boundaries, never for an interactive annotation save.
An old server counter or witness nonce is insufficient: reuse requires the fresh
recovery mirror's table-content seals, source identities and this code contract.
"""
from __future__ import annotations

import contextlib
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from workspace_annotation_preparation import _ordered_rows,_links
from workspace_recipes import checksum
from workspace_shared_tag_index import SharedTagIndex,SCOPE_CACHE_ROWS

FORMAT='rieke-shared-tag-checkpoint'
VERSION=1
SUMMARY_TABLES=('summary_cells','summary_cell_tags','summary_tags','summary_totals')
HEX=re.compile(r'^[0-9a-f]{64}$')


def _contract():
    import workspace_annotations,workspace_shared_tag_index,workspace_shared_vocabulary
    import workspace_annotation_preparation
    paths=[Path(module.__file__) for module in (workspace_annotations,workspace_shared_tag_index,
        workspace_shared_vocabulary,workspace_annotation_preparation)]+[Path(__file__)]
    return checksum({path.name:_sha(path) for path in paths})


def _sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def _signature(path):
    stat=Path(path).stat()
    return stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns


def _regular(path):
    path=Path(path)
    if any(parent.is_symlink() for parent in (path,*path.parents)):
        raise ValueError('Annotation checkpoints cannot follow symbolic links')
    if path.exists() and not path.is_file():raise ValueError('Expected a regular annotation checkpoint file')


@contextlib.contextmanager
def _locked(root):
    folder=Path(root)/'cache'/'annotation-index'
    for path in (folder.parent,folder):
        if path.is_symlink():raise ValueError('Annotation checkpoint directories cannot be symbolic links')
        path.mkdir(exist_ok=True)
    handle=os.fdopen(os.open(folder/'.checkpoint.lock',os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600),'a+b')
    try:
        fcntl.flock(handle,fcntl.LOCK_EX)
        yield folder
    finally:handle.close()


def _sync_directory(folder):
    descriptor=os.open(folder,os.O_RDONLY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def _proof(service):
    from workspace_recovery_store import verified_table_content
    tracker=getattr(service,'_recovery_tracker',None)
    return verified_table_content(service.project_dir,tracker) if tracker is not None else None


def _source(service):
    service._ready()
    index=getattr(service,'disk_index',None)
    if index is None:raise ValueError('A sealed metadata index is required')
    index._check()
    return {'project_uuid':service.project['project_uuid'],'metadata_generation':index.generation,
        'links_sha256':checksum(_links(_ordered_rows(service))),'contract':_contract()}


def _same_source(service,expected):
    return _source(service)==expected


def _metadata(folder):
    pointer=folder/'current.json';_regular(pointer)
    if not pointer.exists():return None
    if pointer.stat().st_size>65536:raise ValueError('Annotation checkpoint receipt is oversized')
    record=json.loads(pointer.read_text())
    if (not isinstance(record,dict) or set(record)!={'format','version','source','proof','sha256','file'}
            or record['format']!=FORMAT or type(record['version']) is not int or record['version']!=VERSION
            or not isinstance(record['sha256'],str) or not HEX.fullmatch(record['sha256'])
            or record['file']!=record['sha256']+'.sqlite'):
        raise ValueError('Unsupported annotation checkpoint receipt')
    return record


def restore_shared_checkpoint(service,shared):
    """Copy a verified immutable checkpoint into a fresh private working DB."""
    result={'restored':False}
    index=None
    try:
        previous=getattr(shared,'_shared_tag_index',None)
        if previous is not None and previous.connection is not None:
            return {**result,'reason':'A working shared index is already open'}
        source=_source(service);before=shared.generation_token();proof=_proof(service)
        if before is None or proof is None:
            return {**result,'reason':'Fresh canonical table-content proof is unavailable'}
        with _locked(service.project_dir) as folder:
            record=_metadata(folder)
            if record is None:return {**result,'reason':'No shared-tag checkpoint is saved'}
            if record['source']!=source or record['proof']!=proof:
                return {**result,'reason':'Canonical tags, source identities or index code changed'}
            path=folder/record['file'];_regular(path);signature=_signature(path)
            if _sha(path)!=record['sha256']:raise ValueError('Shared-tag checkpoint checksum differs')
            index=shared._membership_index([],refresh=False)
            if type(index) is not SharedTagIndex:raise ValueError('Unsupported shared-tag index adapter')
            db=index._open()
            db.create_function('shared_casefold',1,str.casefold,deterministic=True)
            with contextlib.closing(sqlite3.connect(path.absolute().as_uri()+'?mode=ro',uri=True)) as saved:
                saved.backup(db)
            with db:
                for table in SUMMARY_TABLES:
                    db.execute(f'INSERT INTO temp.{table} SELECT * FROM main.checkpoint_{table}')
                    db.execute(f'DROP TABLE main.checkpoint_{table}')
            for kind in ('filter','summary'):
                links=tuple(db.execute(f'SELECT epoch_uuid,cell_uuid FROM {kind}_scope ORDER BY position'))
                index.scopes[kind]=links if len(links)<=SCOPE_CACHE_ROWS else None
            from workspace_shared_vocabulary import SharedVocabulary
            vocabulary=SharedVocabulary.__new__(SharedVocabulary)
            vocabulary.index=index
            vocabulary.sequence=db.execute('SELECT COALESCE(MAX(used),0) FROM shared_vocabulary_ready').fetchone()[0]
            index.shared_vocabulary=vocabulary
            index.token=copy.deepcopy(before)
            index.stats['rows_indexed']=db.execute('SELECT COUNT(*) FROM records').fetchone()[0]
            if (_signature(path)!=signature or not _same_source(service,source)
                    or shared.generation_token()!=before or _proof(service)!=proof):
                raise ValueError('Canonical state changed while reopening the shared-tag checkpoint')
            return {'restored':True,'rows_indexed':index.stats['rows_indexed'],'sha256':record['sha256']}
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error) as error:
        if index is not None:
            with contextlib.suppress(Exception):index.close()
        return {**result,'reason':str(error)}


def save_shared_checkpoint(service,shared):
    """Seal a prepared index after the caller has durably captured SQL state."""
    index=getattr(shared,'_shared_tag_index',None)
    if type(index) is not SharedTagIndex or index.connection is None:
        return {'saved':False,'reason':'No prepared shared-tag index'}
    temporary=None
    with index._lock:
        source=_source(service);before=shared.generation_token();proof=_proof(service)
        if before is None or proof is None or before!=index.token:
            return {'saved':False,'reason':'Prepared index does not match a fresh canonical checkpoint'}
        links=_links(_ordered_rows(service))
        if index.scopes['filter']!=links or index.scopes['summary']!=links or index.shared_vocabulary is None:
            return {'saved':False,'reason':'Shared filter, summary and vocabulary preparation is incomplete'}
        if index.connection.in_transaction:raise ValueError('Annotation checkpoint cannot interrupt an index transaction')
        with _locked(service.project_dir) as folder:
            try:
                descriptor,name=tempfile.mkstemp(prefix='.checkpoint-',suffix='.sqlite',dir=folder)
                os.close(descriptor);temporary=Path(name)
                with contextlib.closing(sqlite3.connect(temporary)) as saved:
                    index.connection.backup(saved)
                attached=False
                try:
                    index.connection.execute('ATTACH DATABASE ? AS annotation_checkpoint',(str(temporary),));attached=True
                    with index.connection:
                        for table in SUMMARY_TABLES:
                            index.connection.execute(f'CREATE TABLE annotation_checkpoint.checkpoint_{table} AS SELECT * FROM temp.{table}')
                        index.connection.execute('DELETE FROM annotation_checkpoint.catalog_scope')
                finally:
                    if attached:index.connection.execute('DETACH DATABASE annotation_checkpoint')
                with temporary.open('rb') as stream:os.fsync(stream.fileno())
                sha=_sha(temporary)
                if (not _same_source(service,source) or shared.generation_token()!=before or _proof(service)!=proof):
                    return {'saved':False,'reason':'Canonical state changed while sealing the shared-tag checkpoint'}
                target=folder/(sha+'.sqlite');_regular(target)
                os.replace(temporary,target);temporary=None
                _sync_directory(folder)
                from recording_workspace import write_json
                write_json(folder/'current.json',{'format':FORMAT,'version':VERSION,'source':source,
                    'proof':proof,'sha256':sha,'file':target.name})
                for old in folder.glob('*.sqlite'):
                    if old!=target and HEX.fullmatch(old.stem) and not old.is_symlink():old.unlink()
                _sync_directory(folder)
                return {'saved':True,'rows_indexed':index.stats['rows_indexed'],'sha256':sha}
            finally:
                if temporary is not None:
                    with contextlib.suppress(FileNotFoundError):temporary.unlink()
