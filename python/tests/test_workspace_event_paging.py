import datetime as dt
import unittest
from workspace_service import WorkspaceService
try:
    from .test_workspace_curation import Table
except ImportError:
    from test_workspace_curation import Table

class EventPagingTests(unittest.TestCase):
    def setUp(self):
        self.service=WorkspaceService.__new__(WorkspaceService)
        self.service._ready=lambda:None
        self.service.project={'project_uuid':'project'}
        self.table=Table(('event_uuid',))
        for identity in ('a','c','b'):
            self.table.insert1({'event_uuid':identity,'project_uuid':'project',
                'occurred_at':dt.datetime(2026,1,1),'actor':'test','action':'exported',
                'payload':{'membership':'x'*1000000}})
        self.table.insert1({'event_uuid':'z','project_uuid':'different',
            'occurred_at':dt.datetime(2026,1,2),'actor':'test','action':'exported','payload':{}})
        self.service.Event=self.table

    def test_overview_never_fetches_or_returns_large_payloads(self):
        rows=self.service.events(2)
        self.assertEqual([r['event_uuid'] for r in rows],['c','b'])
        self.assertTrue(all('payload' not in r for r in rows))
        self.assertTrue(all(r['projected'] is not None and 'payload' not in r['projected'] for r in self.table.read_log))

    def test_payloads_loaded_only_for_stable_ordered_page(self):
        result=self.service.event_page(limit=1,offset=1,action='exported')
        self.assertEqual([r['event_uuid'] for r in result['events']],['b'])
        self.assertTrue(result['has_more'])
        self.assertEqual(result['events'][0]['payload']['membership'],'x'*1000000)
        reads=self.table.read_log
        self.assertNotIn('payload',reads[0]['projected'])
        self.assertEqual(reads[1]['restrictions'][-1],[{'event_uuid':'b'}])
        self.table.read_log.clear()
        self.assertEqual(self.service.event_page(offset=99)['events'],[])
        self.assertEqual(len(self.table.read_log),1)
