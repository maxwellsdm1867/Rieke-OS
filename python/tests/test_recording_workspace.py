import copy
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

import numpy as np

import recording_workspace as workspace


class RecordingWorkspaceSafetyTests(unittest.TestCase):
    def definition(self):
        return {"format": "recording-protocol-workspace", "version": 1,
                "protocol_uuid": str(uuid.uuid4()), "project_uuid": str(uuid.uuid4()),
                "query": {"version": 1, "all": [{"field": "EpochBlock.protocol_name",
                          "operator": "eq", "value": "example.Protocol"}]}}

    def test_unknown_query_never_falls_back_to_all_epochs(self):
        valid = self.definition()
        self.assertEqual(workspace.validate_protocol_definition(valid), "example.Protocol")
        cases = []
        for key, value in [("operator", "contains"), ("field", "unrecognized.field"), ("value", "")]:
            definition = copy.deepcopy(valid)
            definition["query"]["all"][0][key] = value
            cases.append(definition)
        extra = copy.deepcopy(valid)
        extra["query"]["any"] = []
        cases.append(extra)
        empty = copy.deepcopy(valid)
        empty["query"]["all"] = []
        cases.append(empty)
        for definition in cases:
            with self.subTest(definition=definition), self.assertRaises(ValueError):
                workspace.validate_protocol_definition(definition)

    def test_invalid_metadata_does_not_replace_a_valid_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            workspace.write_json(path, {"count": 1086})
            original = path.read_bytes()
            with self.assertRaises(ValueError):
                workspace.write_json(path, {"rate": float("nan")})
            self.assertEqual(path.read_bytes(), original)

    def test_ticks_keep_exact_integer_precision(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            ticks = np.int64(639258608779858225)
            workspace.write_json(path, {"ticks": ticks})
            self.assertEqual(json.loads(path.read_text())["ticks"], int(ticks))

    def test_durable_json_flushes_file_before_publish_and_directory_after(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'metadata.json'
            events = []
            real_fsync, real_replace = os.fsync, os.replace
            def sync(fd):
                events.append('sync')
                return real_fsync(fd)
            def replace(source, destination):
                events.append('replace')
                return real_replace(source, destination)
            with patch('workspace_state_snapshot.os.fsync', side_effect=sync), \
                    patch('workspace_state_snapshot.os.replace', side_effect=replace):
                workspace.write_json(path, {'revision': 2})
            self.assertEqual(events, ['sync', 'replace', 'sync'])
            self.assertEqual(json.loads(path.read_text()), {'revision': 2})

    def test_failed_file_flush_or_replace_preserves_previous_json_and_cleans_temporary(self):
        for operation in ('fsync', 'replace'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'metadata.json'
                workspace.write_json(path, {'revision': 1})
                before = path.read_bytes()
                with patch('workspace_state_snapshot.os.' + operation, side_effect=OSError('disk fault')):
                    with self.assertRaisesRegex(OSError, 'disk fault'):
                        workspace.write_json(path, {'revision': 2})
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_directory_flush_failure_is_reported_after_atomic_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'metadata.json'
            workspace.write_json(path, {'revision': 1})
            with patch('workspace_state_snapshot.os.fsync', side_effect=[None, OSError('directory fault')]):
                with self.assertRaisesRegex(OSError, 'directory fault'):
                    workspace.write_json(path, {'revision': 2})
            # Publication already happened. Never report success or pretend the
            # old value was restored after a failed durability confirmation.
            self.assertEqual(json.loads(path.read_text()), {'revision': 2})
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_general_json_preserves_existing_permissions_but_snapshots_remain_private(self):
        from workspace_state_snapshot import atomic_write
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'metadata.json'
            path.write_text('{"revision":1}\n');path.chmod(0o640)
            workspace.write_json(path, {'revision':2})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o640)
            self.assertEqual(json.loads(path.read_text()),{'revision':2})
            atomic_write(path,b'{"revision":3}\n')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)

    def test_new_general_json_uses_normal_creation_umask_without_changing_parent_process(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'metadata.json'
            code = '''import os,stat,sys
from pathlib import Path
from recording_workspace import write_json
os.umask(0o027)
path=Path(sys.argv[1])
write_json(path,{'revision':1})
assert stat.S_IMODE(path.stat().st_mode)==0o640
assert os.umask(0o027)==0o027
'''
            env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])}
            result=subprocess.run([sys.executable,'-c',code,str(path)],env=env,
                                  capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o640)

    def test_permission_failure_preserves_previous_json_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'metadata.json'
            workspace.write_json(path,{'revision':1});path.chmod(0o640)
            with patch('workspace_state_snapshot.os.fchmod',side_effect=OSError('permission fault')):
                with self.assertRaisesRegex(OSError,'permission fault'):
                    workspace.write_json(path,{'revision':2})
            self.assertEqual(json.loads(path.read_text()),{'revision':1})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o640)
            self.assertEqual(list(Path(directory).iterdir()),[path])

    def test_tampered_parser_cache_is_rejected_before_reading_h5(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.h5"
            source.write_bytes(b"fixture source, never parsed")
            parser = root / "parser.py"
            parser.write_text("# fixture parser\n")
            source_hash = workspace.digest(source)
            cache = root / "project/imports" / (source.stem + "-" + source_hash[:12])
            cache.mkdir(parents=True)
            raw = cache / "metadata.raw.json"
            raw.write_text('{"original":true}')
            workspace.write_json(cache / "parse-manifest.json", {
                "status": "parsed", "sha256": source_hash,
                "metadata_sha256": workspace.digest(raw), "parser_sha256": workspace.digest(parser)})
            raw.write_text('{"silently_changed":true}')
            with patch.object(workspace, "load_parser", return_value=(None, parser)):
                with self.assertRaisesRegex(ValueError, "checksum changed"):
                    workspace.prepare(source, root / "project", root)


if __name__ == "__main__":
    unittest.main()
