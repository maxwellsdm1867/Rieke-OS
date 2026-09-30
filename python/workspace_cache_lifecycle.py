"""Reader leases and reclamation for disposable, generation-named caches.

The directory lock serializes lease creation, publication and deletion. A live
reader holds a shared OS lock for its generation, including between file reads.
Reclamation needs the exclusive generation lock and never touches source data.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import weakref


_LOCAL_LOCK=threading.RLock()
_LOCAL_STATE=threading.local()
_HEX=r'[0-9a-f]{64}'


def _open_lock(path):
    descriptor=os.open(path,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
    return os.fdopen(descriptor,'a+b')


def _release(handle,namespace,reclaim):
    # Close rather than explicitly unlocking: after fork, another process can
    # still own a duplicate of this same locked open-file description.
    handle.close()
    if reclaim:
        with contextlib.suppress(OSError,ValueError):namespace.collect()


class CacheLease:
    def __init__(self,handle,namespace,reclaim):
        self._release=weakref.finalize(self,_release,handle,namespace,reclaim)

    def close(self):self._release()
    def __enter__(self):return self
    def __exit__(self,*ignored):self.close()


def _release_group(leases,namespace):
    for lease in leases:lease.close()
    with contextlib.suppress(OSError,ValueError):namespace.collect()


class CacheLeaseGroup:
    def __init__(self,leases,namespace):
        self._release=weakref.finalize(self,_release_group,leases,namespace)

    def close(self):self._release()
    def __enter__(self):return self
    def __exit__(self,*ignored):self.close()


class CacheNamespace:
    """One derived directory, with one durable set of current generation names."""
    def __init__(self,directory,kind,owner=None):
        if kind not in ('metadata','projections'):raise ValueError('Unknown derived cache kind')
        self.directory=Path(directory)
        if self.directory.is_symlink() or self.directory.parent.is_symlink():
            raise ValueError('Derived cache directories cannot be symbolic links')
        self.directory.mkdir(parents=True,exist_ok=True)
        self.kind=kind;self.owner=owner
        self.leases=self.directory/'.reader-leases'
        if self.leases.is_symlink():raise ValueError('Derived reader leases cannot be symbolic links')
        self.leases.mkdir(exist_ok=True)

    @contextlib.contextmanager
    def writer(self,name):
        """Serialize publication with a fixed, bounded set of cross-process locks.

        Stripe collisions only serialize unrelated builds; full cache names and
        verified generations still determine identity. Never hold the directory
        reclamation guard while waiting or performing an expensive build.
        """
        name=self._name(name)
        directory=self.directory/'.writer-locks'
        if directory.is_symlink():raise ValueError('Derived writer locks cannot be symbolic links')
        directory.mkdir(exist_ok=True)
        stripe=int.from_bytes(hashlib.sha256(name.encode()).digest()[:2],'big')%64
        handle=_open_lock(directory/f'{stripe:02d}.lock')
        try:
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
            yield
        finally:
            handle.close()

    @contextlib.contextmanager
    def _locked(self):
        with _LOCAL_LOCK:
            handle=_open_lock(self.directory/'.reclaim.lock')
            previous=getattr(_LOCAL_STATE,'locked',False)
            _LOCAL_STATE.locked=True
            try:
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN);handle.close()
                _LOCAL_STATE.locked=previous

    @staticmethod
    def _name(value):
        name=Path(value).name
        if not name or name in ('.','..') or '/' in name or '\\' in name:
            raise ValueError('Expected a single derived cache filename')
        return name

    def lease(self,name,*,reclaim=True):
        name=self._name(name)
        with self._locked():
            handle=_open_lock(self.leases/(name+'.lock'))
            try:fcntl.flock(handle.fileno(),fcntl.LOCK_SH)
            except BaseException:handle.close();raise
        return CacheLease(handle,self,reclaim)

    def hold(self,names):
        leases=[]
        try:
            for name in sorted({self._name(value) for value in names}):
                leases.append(self.lease(name,reclaim=False))
            return CacheLeaseGroup(leases,self)
        except BaseException:
            _release_group(leases,self);raise

    def _key(self,name):
        if self.kind=='metadata':
            match=re.fullmatch('('+_HEX+r'\.sqlite)(.*)',name)
            if match and (match[2] in ('','.sha256.json','-journal','-wal','-shm')
                    or re.fullmatch(r'\.[A-Za-z0-9_-]+\.building(?:\.json|-journal|-wal|-shm)?',match[2])):
                return match[1]
        else:
            match=re.fullmatch('('+_HEX+r'\.json\.zlib)(.*)',name)
            if match and (not match[2] or re.fullmatch(r'\.[A-Za-z0-9_-]+\.writing(?:-journal|-wal|-shm)?',match[2])):
                return match[1]
            match=re.fullmatch('('+_HEX+r')\.json\.sha256',name)
            if match:return match[1]+'.json.zlib'
        return None

    def _manifest(self):
        path=self.directory/'.current-generations.json'
        if path.is_symlink():raise ValueError('Derived cache manifest cannot be a symbolic link')
        try:record=json.loads(path.read_text())
        except (OSError,ValueError):return None
        if (not isinstance(record,dict) or record.get('version')!=1 or record.get('kind')!=self.kind
                or record.get('owner')!=self.owner or not isinstance(record.get('keep'),list)
                or any(not isinstance(name,str) or self._key(name)!=name for name in record['keep'])):
            return None
        return record

    def publish(self,names):
        keep=sorted({self._name(name) for name in names})
        if any(self._key(name)!=name for name in keep):
            raise ValueError('Expected generation-named derived cache files')
        document={'version':1,'kind':self.kind,'owner':self.owner,'keep':keep}
        with self._locked():
            descriptor,temporary=tempfile.mkstemp(prefix='.publishing-',dir=self.directory)
            try:
                with os.fdopen(descriptor,'w') as stream:
                    json.dump(document,stream,sort_keys=True,separators=(',',':'))
                    stream.flush();os.fsync(stream.fileno())
                os.replace(temporary,self.directory/'.current-generations.json')
                directory_fd=os.open(self.directory,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
                try:os.fsync(directory_fd)
                finally:os.close(directory_fd)
            finally:
                with contextlib.suppress(FileNotFoundError):os.unlink(temporary)
            return self._collect_locked(document)

    def collect(self):
        # A finalizer can run inside another cache operation. Do not re-enter a
        # process-level flock on another descriptor; the next pass will collect.
        if getattr(_LOCAL_STATE,'locked',False):return {'removed_files':[],'leased_generations':[]}
        with self._locked():
            record=self._manifest()
            if record is None:return {'removed_files':[],'leased_generations':[]}
            return self._collect_locked(record)

    def _foreign_metadata(self,key):
        if self.kind!='metadata':return False
        seal=self.directory/(key+'.sha256.json')
        if seal.is_symlink():return True
        try:
            if seal.stat().st_size>16384:return True
            record=json.loads(seal.read_text())
        except (OSError,ValueError):return False
        return isinstance(record,dict) and record.get('project_uuid') not in (None,self.owner)

    def _collect_locked(self,record):
        keep=set(record['keep']);groups={};removed=[];leased=[]
        for path in self.directory.iterdir():
            key=self._key(path.name)
            if key and path.is_file() and not path.is_symlink():groups.setdefault(key,[]).append(path)
        for path in self.leases.iterdir():
            if path.name.endswith('.lock'):
                key=path.name[:-5]
                if self._key(key)==key:groups.setdefault(key,[])
        for key,paths in groups.items():
            if key in keep or self._foreign_metadata(key):continue
            lock_path=self.leases/(key+'.lock')
            try:handle=_open_lock(lock_path)
            except OSError:continue
            try:
                try:fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:leased.append(key);continue
                for path in paths:
                    try:path.unlink();removed.append(path.name)
                    except OSError:pass
                # Removing a lease inode is safe only under the directory guard
                # and its exclusive lease: no reader can reopen the old inode.
                if not any(path.exists() for path in paths):
                    with contextlib.suppress(OSError):lock_path.unlink()
            finally:handle.close()
        return {'removed_files':sorted(removed),'leased_generations':sorted(leased)}
