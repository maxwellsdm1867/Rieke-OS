import json
from pathlib import Path
import socket
import tempfile
import unittest
from workspace_project_servers import choose_project_port

class ProjectPortTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'logs').mkdir()

    def save(self,identity,port):
        (self.root/'logs/workspace-server.json').write_text(json.dumps({'project_uuid':identity,'port':port}))

    def test_free_owned_port_is_reused(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        self.save('project',port)
        self.assertEqual(choose_project_port(self.root,'project'),port)

    def test_busy_owned_port_does_not_interrupt_other_listener(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));s.listen();port=s.getsockname()[1]
            self.save('project',port)
            self.assertNotEqual(choose_project_port(self.root,'project'),port)
            self.assertEqual(s.getsockname()[1],port)

    def test_malformed_or_foreign_record_falls_back(self):
        for content in ('[]','{bad','{"project_uuid":"other","port":true}', '{"project_uuid":"project","port":-1}'):
            (self.root/'logs/workspace-server.json').write_text(content)
            port=choose_project_port(self.root,'project')
            self.assertGreaterEqual(port,1024)
            self.assertLessEqual(port,65535)
