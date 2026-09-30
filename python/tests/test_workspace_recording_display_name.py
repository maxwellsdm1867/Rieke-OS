"""Display identity remains independent of managed recording locators."""
import unittest
from workspace_recording_files import recording_display_name

class RecordingDisplayNameTests(unittest.TestCase):
    def test_managed_relocation_retains_original_name(self):
        manifest = {'source_filename': '20260930 retinal recording.h5',
                    'source_path': '/project/raw-uploads/' + 'a' * 64 + '.h5'}
        self.assertEqual(recording_display_name(manifest), '20260930 retinal recording.h5')
        manifest['source_path'] = '/restored/raw-uploads/' + 'a' * 64 + '.h5'
        self.assertEqual(recording_display_name(manifest), '20260930 retinal recording.h5')

    def test_legacy_manifest_falls_back_to_recorded_name(self):
        self.assertEqual(recording_display_name({'source_path': '/old/location/recognizable.h5'}), 'recognizable.h5')

    def test_invalid_display_identity_cannot_expose_a_path(self):
        for name in ('', None, '../private.h5', 'other\\private.h5'):
            self.assertEqual(recording_display_name({'source_filename': name, 'source_path': '/project/retained.h5'}), 'retained.h5')
