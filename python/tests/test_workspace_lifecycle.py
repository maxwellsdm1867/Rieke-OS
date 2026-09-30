import threading
import unittest
from unittest.mock import Mock
from flask import Flask
from workspace_lifecycle import register_project_lifecycle


class LifecycleTests(unittest.TestCase):
    def create(self,busy=False,stop=None):
        app=Flask(__name__);self.done=threading.Event()
        app.extensions['shutdown_project_server']=self.done.set
        self.stop=stop or Mock()
        self.state=register_project_lifecycle(app,busy=lambda:busy,stop_database=self.stop)
        return app.test_client()

    def test_close_stops_database_then_returns_ready_to_copy(self):
        client=self.create()
        response=client.post('/api/project/close',json={})
        self.assertEqual(response.json['state'],'closed')
        self.stop.assert_called_once()
        self.assertTrue(self.done.wait(1))
        self.assertEqual(client.post('/api/project/close',json={}).status_code,503)

    def test_busy_project_is_not_stopped(self):
        client=self.create(busy=True)
        self.assertEqual(client.post('/api/project/close',json={}).status_code,409)
        self.stop.assert_not_called()
        self.assertFalse(self.state['closing'])

    def test_failed_shutdown_does_not_report_portable_state(self):
        client=self.create(stop=Mock(side_effect=ValueError('not clean')))
        self.assertEqual(client.post('/api/project/close',json={}).status_code,500)
        self.assertFalse(self.state['closing'])
        self.assertFalse(self.done.is_set())


if __name__=='__main__':unittest.main()
