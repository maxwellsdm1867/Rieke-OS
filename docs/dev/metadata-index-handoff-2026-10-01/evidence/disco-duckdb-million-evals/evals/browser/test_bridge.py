"""Small owned fixture validates the experimental browser bridge contract."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('browser_bridge', Path(__file__).with_name('bridge.py'))
bridge_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge_module)


class BridgeContractTests(unittest.TestCase):
    def test_bounded_tree_continuation_identity_and_details(self):
        with tempfile.TemporaryDirectory(prefix='disco-browser-bridge-test-') as directory:
            directory = Path(directory)
            module = bridge_module.module
            module.generate_csv(directory / 'rows.csv', 7000)
            projection = module.AnalyticalProjection('sqlite', directory / 'fixture.sqlite')
            try:
                projection.build(directory / 'rows.csv')
                bridge = bridge_module.Bridge(projection, 7000)
                request = {'protocol_uuid': module.PROTOCOL_UUID, 'filters': {}, 'splits': 'cell,block', 'path': [], 'offset': 0, 'limit': 60}
                first = bridge.page(request)
                second = bridge.page(request | {'offset': 60, 'revision': first['revision']})
                self.assertEqual((first['total'], len(first['branches']), len(second['branches'])), (70, 60, 10))
                self.assertEqual(len({item['value'] for item in first['branches'] + second['branches']}), 70)
                self.assertTrue(first['has_more'])
                self.assertFalse(second['has_more'])
                cell = bridge.page(request | {'path': first['branches'][0]['path'], 'revision': first['revision']})
                self.assertEqual(cell['total'], 5)
                self.assertEqual([x['start_time'] for x in cell['branches']], sorted(x['start_time'] for x in cell['branches']))
                leaf = bridge.page(request | {'path': cell['branches'][0]['path'], 'revision': first['revision']})
                self.assertEqual(leaf['total'], 20)
                self.assertEqual(len({row['epoch_uuid'] for row in leaf['epochs']}), 20)
                self.assertEqual(bridge.detail(leaf['epochs'][0]['epoch_uuid'])['epoch_uuid'], leaf['epochs'][0]['epoch_uuid'])
                self.assertTrue(all(row['passed'] for row in bridge.checks))
                with self.assertRaisesRegex(ValueError, 'Stale revision'):
                    bridge.page(request | {'revision': '0' * 64})
                with self.assertRaisesRegex(ValueError, 'empty filters'):
                    bridge.page(request | {'filters': {'contrast': 0.3}})
            finally:
                projection.close()


if __name__ == '__main__':
    unittest.main()
