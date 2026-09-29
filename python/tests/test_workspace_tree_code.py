import unittest
from workspace_tree_code import matlab_tree_command,matlab_split_fields

class MatlabTreeCodeTests(unittest.TestCase):
    def test_readable_fields_and_order_survive_exactly(self):
        self.assertEqual(matlab_tree_command(['date','cell','parameters/history1']),
            "[tree, gui] = launchWorkspaceTree('recordings.mat', {'date', 'cell', 'parameters/history1'});")
        self.assertEqual(matlab_split_fields([]),'{}')
        self.assertEqual(matlab_split_fields(['parameters/a%2Cb','parameters/a~1b']),"{'parameters/a%2Cb', 'parameters/a~1b'}")
        self.assertEqual(matlab_split_fields(['cell','joint/parameters%2Fhistory1+parameters%2Fhistory2+parameters%2Ftarget','block']),
                         "{'cell', {'parameters/history1', 'parameters/history2', 'parameters/target'}, 'block'}")
    def test_matlab_quotes_are_escaped_and_multiline_or_invalid_recipes_rejected(self):
        self.assertEqual(matlab_split_fields(["parameters/a'b"]),"{'parameters/a''b'}")
        for fields in ('date', ['a']*2, list(map(str,range(9))), [''], ['a\nb'], ['a\rb'], [None], ['a\x00b']):
            with self.subTest(fields=fields),self.assertRaises(ValueError):matlab_tree_command(fields)
