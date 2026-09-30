"""Delete one project-owned acquisition with durable filesystem recovery.

No H5 reads or source checksum verification are needed. SQL identities and the
registered manifest select the recording; other acquisitions and saved exports
are never used as deletion targets. A managed file is quarantined outside the
inbox before the atomic catalog/binding/curation transaction.
"""
from __future__ import annotations
import contextlib
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid

from recording_workspace import write_json
from workspace_audit import build_audit_payload
from workspace_recipes import checksum
from workspace_storage import managed_directory


def managed_recording(root, locator):
    root = Path(root).resolve()
    path = Path(locator)
    if not path.is_absolute():
        raise ValueError('Registered recording locator is not absolute')
    # Resolve no links implicitly: a linked original must never be erased.
    if not path.is_relative_to(root / 'raw-uploads'):
        return None
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError('Managed recording deletion cannot follow symbolic links')
    if not path.resolve().is_relative_to(root / 'raw-uploads'):
        raise ValueError('Managed recording locator escapes project storage')
    if path.exists() and not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('Managed recording is not a regular file')
    return path


def prune_preview(recipe, removed, source_sha):
    """Remove exact deleted epochs; do not add new query matches or curation."""
    membership = [copy.deepcopy(row) for row in recipe['epochs'] if row['uuid'] not in removed]
    return {'membership': membership, 'matched_count': len(membership),
        'total_source': max(0, recipe.get('total_source', len(recipe['epochs'])) - len(removed)),
        'predicate': copy.deepcopy(recipe['predicate']),
        'splits': ','.join(recipe['tree_view']['fields']),
        'tree': {'split_order': copy.deepcopy(recipe['tree_view']['fields'])},
        'metadata_fingerprint_version': recipe['metadata_fingerprint_version'],
        'source_revisions': [sha for sha in recipe.get('source_revisions', []) if sha != source_sha]}


class DataStoreDeletion:
    def __init__(self, stores, *, catalog=None):
        self.stores = stores
        self.service = stores.service
        self.connection = stores.dj.conn()
        self.root = self.service.project_dir
        self.project = stores.project_uuid
        self.catalog = catalog

    @staticmethod
    def _sync_directories(*paths):
        for path in set(paths):
            descriptor = os.open(path, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def _catalog(self):
        if self.catalog is None:
            from retinanalysis.config import schema
            self.catalog = schema
        return self.catalog

    def describe(self, identity):
        from workspace_datastores import sha
        identity = sha(identity)
        rows = (self.stores.Source & {'project_uuid': self.project, 'source_sha256': identity}).to_dicts()
        if len(rows) != 1:
            raise KeyError('Data store is not registered in this project')
        row = rows[0]
        manifest = row['manifest']
        if manifest.get('source_sha256') != identity:
            raise ValueError('Source manifest identity differs from its registration')
        path = managed_recording(self.root, manifest['source_path'])
        from workspace_recording_files import recording_display_name
        return {'source_sha256': identity, 'filename': recording_display_name(manifest),
            'source_path': manifest['source_path'], 'managed_file': path is not None,
            'file_exists': path.exists() if path is not None else None,
            'registration_revision': checksum(row), 'external_original_retained': path is None}

    def _journal(self, identity):
        return managed_directory(self.root, 'logs/storage/data-store-deletions') / (identity + '.json')

    def _bindings(self, removed):
        result = []
        history = self.stores.explorer_history
        for header in (history.Binding & {'project_uuid': self.project}).to_dicts():
            binding = history.protocol_binding(header['protocol_uuid'])
            if any(row['uuid'] in removed for row in binding['recipe']['epochs']):
                result.append(binding)
        return sorted(result, key=lambda row: row['protocol_uuid'])

    @contextlib.contextmanager
    def _locks(self):
        # Match the import guard, then project eligibility, then protocol guards.
        if self.connection.query("SELECT GET_LOCK('recording_workspace_import', 30)").fetchone()[0] != 1:
            raise RuntimeError('An import is still writing this project')
        try:
            with self.stores.registration_locks():
                yield
        finally:
            self.connection.query("SELECT RELEASE_LOCK('recording_workspace_import')")

    def recover_pending(self):
        directory = managed_directory(self.root, 'logs/storage/data-store-deletions')
        for path in directory.glob('*.json'):
            if path.is_symlink():
                raise ValueError('Deletion journal cannot be a symbolic link')
            journal = json.loads(path.read_text())
            if journal.get('stage') in {'completed', 'rolled_back'}:
                continue
            identity = journal.get('source_sha256')
            if journal.get('project_uuid') != self.project or path.name != identity + '.json':
                raise ValueError('Deletion recovery project identity differs')
            rows = (self.stores.Source & {'project_uuid': self.project, 'source_sha256': identity}).to_dicts()
            if not rows:
                self._finish_file(journal, path)
                continue
            if checksum(rows[0]) != journal['registration_revision']:
                raise ValueError('Deletion recovery registration changed; preserve quarantine')
            original = managed_recording(self.root, rows[0]['manifest']['source_path'])
            quarantine = self._quarantine(journal)
            if quarantine is not None and quarantine.exists():
                if original is None or original.exists():
                    raise ValueError('Deletion recovery locator is occupied; preserve quarantine')
                quarantine.rename(original)
                self._sync_directories(quarantine.parent, original.parent)
            journal['stage'] = 'rolled_back'
            write_json(path, journal)

    def _quarantine(self, journal):
        operation = str(uuid.UUID(journal['operation_uuid']))
        quarantine = Path(journal['quarantine_path']) if journal.get('quarantine_path') else None
        if quarantine is not None:
            expected = Path(self.root) / '.data-store-deletions' / operation / 'recording.h5'
            if quarantine != expected or quarantine.is_symlink():
                raise ValueError('Deletion quarantine identity differs from its journal')
            for part in quarantine.parents:
                if part == self.root:
                    break
                if part.is_symlink():
                    raise ValueError('Deletion quarantine cannot follow symbolic links')
        return quarantine

    def _finish_file(self, journal, path):
        quarantine = self._quarantine(journal)
        if quarantine is not None:
            quarantine.unlink(missing_ok=True)
            if quarantine.parent.exists():
                self._sync_directories(quarantine.parent)
            if quarantine.parent.exists():
                quarantine.parent.rmdir()
        for cell in journal['removed_cell_uuids']:
            cache = Path(self.root) / 'cache/block-onset-voltage' / (str(uuid.UUID(cell)) + '.json')
            if cache.is_symlink() or cache.parent.is_symlink():
                raise ValueError('Prepared QC cache cannot follow symbolic links')
            cache.unlink(missing_ok=True)
        journal['stage'] = 'completed'
        write_json(path, journal)

    def delete(self, identity, expected_revision, *, confirmed):
        if confirmed is not True:
            raise ValueError('Data store deletion requires explicit confirmation')
        from workspace_datastores import sha, DataStoreConflict
        identity = sha(identity)
        journal_path = self._journal(identity)
        if journal_path.is_symlink():
            raise ValueError('Deletion journals cannot be symbolic links')
        with self._locks():
            self.recover_pending()
            registered = (self.stores.Source & {'project_uuid': self.project, 'source_sha256': identity}).to_dicts()
            if not registered:
                if not journal_path.is_file():
                    raise KeyError('No active source or deletion recovery exists')
                journal = json.loads(journal_path.read_text())
                if journal.get('project_uuid') != self.project or journal.get('source_sha256') != identity or journal.get('registration_revision') != expected_revision:
                    raise ValueError('Deletion recovery identity differs')
                self._finish_file(journal, journal_path)
                return journal
            info = self.describe(identity)
            if info['registration_revision'] != expected_revision:
                raise DataStoreConflict(info, 'Recording registration changed; reopen the deletion confirmation.')
            record = registered[0]
            catalog = self._catalog()
            experiment = catalog.Experiment & {'id': record['experiment_id'], 'h5_uuid': record['experiment_uuid']}
            if len(experiment) != 1:
                raise ValueError('Registered experiment UUID and catalog identity differ')
            selected_path = Path(record['manifest']['source_path']).resolve()
            for other in self.stores.Source.to_dicts():
                if other['source_sha256'] != identity and Path(other['manifest']['source_path']).resolve() == selected_path:
                    raise ValueError('Another registered source references this recording path; preserve the shared file')
            shared = (self.stores.Source & {'experiment_id': record['experiment_id']}).to_dicts()
            if len(shared) != 1 or shared[0]['source_sha256'] != identity:
                raise ValueError('Another registered source owns this catalog experiment; no file was removed')
            removed = {str(uuid.UUID(row['h5_uuid'])) for row in (catalog.Epoch & {'experiment_id': record['experiment_id']}).to_dicts()}
            cells = {str(uuid.UUID(row['h5_uuid'])) for row in (catalog.Cell & {'experiment_id': record['experiment_id']}).to_dicts()}
            other_cells = {str(uuid.UUID(row['h5_uuid'])) for row in (catalog.Cell & f"experiment_id != {int(record['experiment_id'])}").to_dicts()}
            orphan_cells = cells - other_cells
            bindings = self._bindings(removed)
            with contextlib.ExitStack() as held:
                for binding in bindings:
                    lock = hashlib.sha256((self.project + binding['protocol_uuid']).encode()).hexdigest()
                    if self.connection.query(f"SELECT GET_LOCK('{lock}', 10)").fetchone()[0] != 1:
                        raise RuntimeError('Another pinned protocol update is running')
                    held.callback(self.connection.query, f"SELECT RELEASE_LOCK('{lock}')")
                path = managed_recording(self.root, record['manifest']['source_path'])
                operation = str(uuid.uuid4())
                quarantine = managed_directory(self.root, '.data-store-deletions/' + operation) / 'recording.h5' if path is not None else None
                journal = {**info, 'project_uuid': self.project, 'operation_uuid': operation,
                    'stage': 'prepared', 'quarantine_path': str(quarantine) if quarantine else None,
                    'removed_epoch_uuids': sorted(removed), 'removed_cell_uuids': sorted(orphan_cells),
                    'affected_protocol_uuids': [row['protocol_uuid'] for row in bindings],
                    'existing_exports_unchanged': True}
                write_json(journal_path, journal)
                try:
                    if path is not None and path.exists():
                        signature = path.lstat()
                        path.rename(quarantine)
                        actual = quarantine.lstat()
                        if (actual.st_dev, actual.st_ino) != (signature.st_dev, signature.st_ino) or not stat.S_ISREG(actual.st_mode):
                            raise ValueError('Managed recording changed while quarantining it')
                        self._sync_directories(path.parent, quarantine.parent)
                    journal['stage'] = 'file_quarantined'
                    write_json(journal_path, journal)
                    with self.connection.transaction:
                        # Recheck both registration and acquisition ownership in the transaction.
                        if checksum((self.stores.Source & {'project_uuid': self.project, 'source_sha256': identity}).fetch1()) != expected_revision:
                            raise DataStoreConflict(info)
                        self._prune_bindings(bindings, removed, identity)
                        self._delete_annotations(removed, orphan_cells)
                        experiment.delete(transaction=False, prompt=False)
                        (self.stores.State & {'project_uuid': self.project, 'source_sha256': identity}).delete_quick()
                        (self.stores.Source & {'project_uuid': self.project, 'source_sha256': identity}).delete_quick()
                        actor = os.environ.get('USER', 'local-user')
                        payload = build_audit_payload('data_store_deleted', actor, {**journal,
                            'stage': 'catalog_removed', 'catalog_membership_changed': True,
                            'source_files_changed': path is not None, 'working_dataset_membership_changed': True},
                            operation_uuid=operation, context={'project_uuid': self.project})
                        self.stores.Event.insert1({'event_uuid': operation, 'project_uuid': self.project,
                            'occurred_at': dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
                            'actor': actor, 'action': 'data_store_deleted', 'payload': payload})
                except BaseException:
                    # On uncertain commit, consult authoritative registration before restoring bytes.
                    still_registered = bool(self.stores.Source & {'project_uuid': self.project, 'source_sha256': identity})
                    if still_registered and quarantine is not None and quarantine.exists():
                        if path.exists():
                            raise RuntimeError('Deletion rolled back, but the original locator is occupied; preserve the quarantine and retry recovery')
                        quarantine.rename(path)
                        self._sync_directories(path.parent, quarantine.parent)
                    journal['stage'] = 'rolled_back' if still_registered else 'cleanup_pending'
                    write_json(journal_path, journal)
                    raise
                journal['stage'] = 'cleanup_pending'
                write_json(journal_path, journal)
                self._finish_file(journal, journal_path)
                return journal

    def _prune_bindings(self, bindings, removed, identity):
        history = self.stores.explorer_history
        sources = [row for row in self.service.sources if row['source_sha256'] != identity]
        for binding in bindings:
            recipe = binding['recipe']
            preview = prune_preview(recipe, removed, identity)
            gone = sorted(row['uuid'] for row in recipe['epochs'] if row['uuid'] in removed)
            record = history.create(preview, sources, self.root / 'catalog.json', os.environ.get('USER', 'local-user'),
                name=recipe['name'], parent_revision_uuid=binding['revision_uuid'], _in_transaction=True)
            history.bind(record['revision_uuid'], binding['protocol_uuid'], binding['version'], os.environ.get('USER', 'local-user'),
                {'added': [], 'removed': gone, 'changed': []}, len(recipe['epochs']),
                _in_transaction=True, _lock_held=True, reason='data_store_deleted')

    def _delete_annotations(self, removed, orphan_cells):
        if removed:
            (self.stores.store.Curation & [{'project_uuid': self.project, 'epoch_uuid': key} for key in removed]).delete_quick()
        annotations = getattr(self.service, 'shared_annotations', None)
        if annotations is not None:
            targets = [{'project_uuid': self.project, 'target_kind': 'epoch', 'target_uuid': key} for key in removed]
            targets += [{'project_uuid': self.project, 'target_kind': 'cell', 'target_uuid': key} for key in orphan_cells]
            if targets:
                (annotations.Annotation & targets).delete_quick()
