"""Standalone public restore-refusal example; no native/scientific libraries.

Run with python3 -I -B. Actual checkpoint/annotation source modules load, but the
recording adapter rejects every operation. A public recovery-proof stand-in proves
only orchestration. Never combine this import environment with app discovery.
"""
import builtins
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

# Exact pre-move basename/content contract at d0ae570; not a compatibility key.
OLD_CONTRACT = 'a3bf9faf23e2b0b727973779683348a31c9e2e2790d107d28465268894793899'


class CheckpointRefusalExample(unittest.TestCase):
    def test_old_source_contract_refuses_before_open_and_preserves_receipt(self):
        upstream = types.ModuleType('recording_workspace')
        def forbidden(*args, **kwargs):
            raise AssertionError('No recording, database, or scientific operation is permitted')
        for name in ('workspace_tables', 'now', 'validate_protocol_definition', 'write_json'):
            setattr(upstream, name, forbidden)
        original_import = builtins.__import__
        def guarded(name, *args, **kwargs):
            if name.split('.')[0] in {'datajoint', 'h5py', 'numpy', 'scipy', 'flask', 'pymysql'}:
                raise AssertionError('Native/scientific library import forbidden: ' + name)
            return original_import(name, *args, **kwargs)
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        try:
            with patch.dict(sys.modules, {'recording_workspace': upstream}), patch('builtins.__import__', guarded):
                from disco.decisions.annotation_checkpoint import restore_shared_checkpoint
                import disco.backup.recovery_store as recovery
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary).resolve()
                    folder = root / 'cache/annotation-index'; folder.mkdir(parents=True)
                    tracker = object()
                    proof = {'project_uuid': 'owned-project', 'tables': {'shared_annotation': {'owned': True}}}
                    source = {'project_uuid': 'owned-project', 'metadata_generation': 'owned-generation',
                              'links_sha256': hashlib.sha256(b'[]').hexdigest(), 'contract': OLD_CONTRACT}
                    asset_bytes = b'owned checkpoint sentinel; never open as SQLite'
                    asset_sha = hashlib.sha256(asset_bytes).hexdigest()
                    receipt = {'format': 'rieke-shared-tag-checkpoint', 'version': 1, 'source': source,
                               'proof': proof, 'sha256': asset_sha, 'file': asset_sha + '.sqlite'}
                    asset = folder / receipt['file']; asset.write_bytes(asset_bytes)
                    pointer = folder / 'current.json'
                    before = json.dumps(receipt, sort_keys=True).encode(); pointer.write_bytes(before)
                    service = types.SimpleNamespace(project_dir=root, project={'project_uuid': 'owned-project'},
                        rows={}, _ready=lambda: None, _recovery_tracker=tracker,
                        disk_index=types.SimpleNamespace(generation='owned-generation', _check=lambda: None))
                    shared = types.SimpleNamespace(generation_token=lambda: {'current': True}, _membership_index=forbidden)
                    def verified(request_root, request_tracker):
                        self.assertEqual(request_root, root); self.assertIs(request_tracker, tracker)
                        return proof
                    with patch.object(recovery, 'verified_table_content', verified), patch('sqlite3.connect', forbidden):
                        result = restore_shared_checkpoint(service, shared)
                    self.assertEqual(result, {'restored': False,
                        'reason': 'Canonical tags, source identities or index code changed'})
                    self.assertEqual(pointer.read_bytes(), before)
                    self.assertEqual(asset.read_bytes(), asset_bytes)
                    self.assertEqual({p.name for p in folder.iterdir()}, {'current.json', '.checkpoint.lock', receipt['file']})
        finally:
            sys.path.pop(0)


if __name__ == '__main__':
    unittest.main()
