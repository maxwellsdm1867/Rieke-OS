import copy
import tempfile
import unittest
import uuid
from unittest.mock import patch
from workspace_author_preferences import selected_author, author_profiles, remember_author
import test_workspace_annotations as annotation_fixture


class MachineAuthorPreferenceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        environment = patch.dict('os.environ', {'RIEKE_PREFERENCES_DIR': folder.name})
        environment.start()
        self.addCleanup(environment.stop)
        self.first = self.fixture()
        self.second = self.fixture()

    def fixture(self):
        case = annotation_fixture.SharedAnnotationTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def test_choose_once_reuses_the_same_author_uuid_in_another_project_without_rewriting_existing_tags(self):
        old = self.first.store.create_profile('Previous scientist', 'local')
        self.first.edit('epoch', self.first.first, ['old'], author=old['profile_uuid'])
        before = copy.deepcopy(self.first.records.rows)
        author = self.first.store.create_profile('Scientist', 'local')
        response = self.first.client.post('/api/annotation-profiles/selected', json={'profile_uuid': author['profile_uuid']}, headers=self.first.headers)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(selected_author()['profile_uuid'], author['profile_uuid'])
        listing = self.second.client.get('/api/annotation-profiles').get_json()
        self.assertEqual(listing['selected_profile_uuid'], author['profile_uuid'])
        self.assertIn(author['profile_uuid'], [profile['profile_uuid'] for profile in listing['profiles']])
        self.assertFalse(self.second.profiles.rows)  # Listing does not write project data.
        self.second.edit('epoch', self.second.first, ['new'], author=author['profile_uuid'])
        self.assertEqual(self.second.records.rows[0]['author_name'], 'Scientist')
        self.assertEqual(self.second.records.rows[0]['profile_uuid'], author['profile_uuid'])
        self.assertEqual(self.first.records.rows, before)

    def test_master_roster_keeps_previous_authors_available_and_can_switch_back(self):
        alice = self.first.store.create_profile('Alice', 'local')
        bob = self.first.store.create_profile('Bob', 'local')
        self.first.store.select_profile(alice['profile_uuid'], 'local')
        self.first.store.select_profile(bob['profile_uuid'], 'local')
        self.assertEqual({profile['profile_uuid'] for profile in author_profiles()}, {alice['profile_uuid'], bob['profile_uuid']})
        self.assertEqual(self.second.store.create_profile('Alice', 'local')['profile_uuid'], alice['profile_uuid'])
        self.second.store.select_profile(alice['profile_uuid'], 'local')
        self.assertEqual(self.first.store.list_profiles()['selected_profile_uuid'], alice['profile_uuid'])

    def test_invalid_selection_does_not_change_master_preference(self):
        author = self.first.store.create_profile('Scientist', 'local')
        self.first.store.select_profile(author['profile_uuid'], 'local')
        before = selected_author()
        result = self.second.client.post('/api/annotation-profiles/selected', json={'profile_uuid': 'bad'}, headers=self.second.headers)
        self.assertEqual(result.status_code, 400)
        self.assertEqual(selected_author(), before)

    def test_full_master_roster_with_unicode_names_can_be_reopened(self):
        for index in range(100):
            author = {'profile_uuid': str(uuid.uuid4()), 'display_name': '神' * 117 + str(index)}
            remember_author(author)
        self.assertEqual(len(author_profiles()), 100)
        self.assertEqual(selected_author(), author)
        with self.assertRaisesRegex(ValueError, 'at most 100'):
            remember_author({'profile_uuid': str(uuid.uuid4()), 'display_name': 'One too many'})
        self.assertEqual(selected_author(), author)
