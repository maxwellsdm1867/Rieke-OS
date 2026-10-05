"""Current-path receipt interface; stdlib only, no application or SQL imports."""
import hashlib
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from workspace_external_tags import ExternalTags
from workspace_tag_exchange import canonical


class DecisionsPublicTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.annotations = Mock()
        self.receiver = ExternalTags(SimpleNamespace(project_dir=folder.name), Mock(), self.annotations)
        self.message = {'format': 'rieke-external-tags', 'version': 1,
                        'message_uuid': '11111111-1111-4111-8111-111111111111',
                        'export_uuid': '22222222-2222-4222-8222-222222222222'}
        self.record = {'dataset_uuid': self.message['export_uuid']}
        self.receipt = {'content_sha256': hashlib.sha256(canonical(self.message).encode()).hexdigest(),
                        'event_uuid': 'existing-event'}
        self.receipts = {self.message['message_uuid']: self.receipt}

    def test_replay_returns_existing_receipt_without_reapplying(self):
        self.assertIs(self.receiver.receive(self.message, self.record, self.receipts), self.receipt)
        self.assertEqual(self.annotations.mock_calls, [])

    def test_changed_content_cannot_reuse_message_identity(self):
        with self.assertRaisesRegex(ValueError, 'reused with different content'):
            self.receiver.receive({**self.message, 'document': {}}, self.record, self.receipts)
        self.assertEqual(self.annotations.mock_calls, [])
        self.assertEqual(self.receipts, {self.message['message_uuid']: self.receipt})

    def test_replay_still_requires_correct_export(self):
        with self.assertRaisesRegex(ValueError, 'another export'):
            self.receiver.receive(self.message, {'dataset_uuid': 'other'}, self.receipts)
        self.assertEqual(self.annotations.mock_calls, [])

    def test_boolean_version_cannot_replay(self):
        with self.assertRaisesRegex(ValueError, 'version 1'):
            self.receiver.receive({**self.message, 'version': True}, self.record, self.receipts)
        self.assertEqual(self.annotations.mock_calls, [])
