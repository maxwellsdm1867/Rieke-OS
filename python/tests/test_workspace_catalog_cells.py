"""A recording can legitimately retain setup cells that have no epochs."""
import unittest
from recording_workspace import verify_catalog_cells

class CatalogCellTests(unittest.TestCase):
    def setUp(self):
        self.experiment={'animals':[{'preparations':[{'cells':[
            {'uuid':'recorded','epoch_groups':[{'epoch_blocks':[{'epochs':[{'uuid':'epoch'}]}]}]},
            {'uuid':'empty','epoch_groups':[]}]}]}]}

    def test_retains_empty_and_recorded_cells(self):
        verify_catalog_cells(self.experiment,[{'h5_uuid':'empty'},{'h5_uuid':'recorded'}])

    def test_missing_extra_wrong_and_duplicate_members_rejected(self):
        for values in [('recorded',),('recorded','foreign'),('recorded','empty','extra'),('recorded','empty','empty')]:
            with self.subTest(values=values),self.assertRaisesRegex(ValueError,'membership'):
                verify_catalog_cells(self.experiment,[{'h5_uuid':v} for v in values])

    def test_recording_without_epochs_still_has_source_cell(self):
        self.experiment['animals'][0]['preparations'][0]['cells']=self.experiment['animals'][0]['preparations'][0]['cells'][1:]
        verify_catalog_cells(self.experiment,[{'h5_uuid':'empty'}])

    def test_completely_empty_hierarchy(self):
        verify_catalog_cells({'animals':[]},[])
