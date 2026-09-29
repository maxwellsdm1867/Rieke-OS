import copy
import json
from pathlib import Path
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
