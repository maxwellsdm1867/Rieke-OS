"""Public unsigned release descriptor construction, separate from signed promotion."""
import importlib.util
import json
import plistlib
from pathlib import Path
import tempfile
import unittest
import zipfile
import hashlib

spec=importlib.util.spec_from_file_location('desktop_test_release',Path(__file__).resolve().parents[2]/'tools/desktop_test_release.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class TestUnsignedReleaseDescriptor(unittest.TestCase):
    def test_descriptor_binds_actual_archive_and_app_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);app=root/'Rieke OS.app';resources=app/'Contents/Resources';runtime=resources/'runtime';runtime.mkdir(parents=True)
            manifest={'format':'rieke-desktop-runtime','version':1,'application_version':'0.1.3','platform':'darwin','architecture':'arm64','workspace_formats':[1],'database_compatibility':1,'mysql_version':'8.4.2','minimum_macos_version':'14.0','source_commit':'a'*40,'source_dirty':True}
            (runtime/'runtime-manifest.json').write_text(json.dumps(manifest))
            (resources/'app.asar').write_bytes(b'candidate shell fixture')
            (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'org.riekeos.desktop','CFBundleShortVersionString':'0.1.3'}))
            archive=root/'Rieke-OS-0.1.3-arm64.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for p in app.rglob('*'):
                    if p.is_file():z.write(p,p.relative_to(root))
            descriptor=module.build_descriptor(app,archive)
            self.assertEqual(descriptor['channel'],'unsigned-testing')
            self.assertEqual(descriptor['archive']['sha256'],hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual(descriptor['application_version'],'0.1.3')
            self.assertFalse(descriptor['production_ready'])
            (resources/'app.asar').write_bytes(b'changed after packaging')
            with self.assertRaises(ValueError):module.build_descriptor(app,archive)
