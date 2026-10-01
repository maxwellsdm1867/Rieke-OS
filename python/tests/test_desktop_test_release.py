"""Public unsigned descriptor binds archive bytes and launchable helper identity."""
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
    def fixture(self, root, helper_name='Rieke OS Helper', internal_name='Rieke OS'):
        app=root/'Rieke OS.app';resources=app/'Contents/Resources';runtime=resources/'runtime';runtime.mkdir(parents=True)
        manifest={'format':'rieke-desktop-runtime','version':1,'application_version':'0.1.3','platform':'darwin','architecture':'arm64','workspace_formats':[1],'database_compatibility':1,'mysql_version':'8.4.2','minimum_macos_version':'14.0','source_commit':'a'*40,'source_dirty':True}
        (runtime/'runtime-manifest.json').write_text(json.dumps(manifest))
        (resources/'app.asar').write_bytes(b'candidate shell fixture')
        (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'org.riekeos.desktop','CFBundleShortVersionString':'0.1.3','CFBundleName':internal_name,'CFBundleDisplayName':'Disco'}))
        helper=app/'Contents/Frameworks'/(helper_name+'.app')/'Contents'
        (helper/'MacOS').mkdir(parents=True)
        executable=helper/'MacOS'/helper_name;executable.write_bytes(b'isolated helper fixture');executable.chmod(0o755)
        # Helper CFBundleName need not match the executable: real Electron
        # builder preserves Electron Helper here while renaming the executable.
        (helper/'Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'org.riekeos.desktop.helper','CFBundleExecutable':helper_name,'CFBundleName':'Electron Helper'}))
        archive=root/'Rieke-OS-0.1.3-arm64.zip';self.pack(app,archive)
        return app,archive,helper,executable

    def pack(self, app, archive):
        with zipfile.ZipFile(archive,'w') as z:
            for p in app.rglob('*'):
                if p.is_file():z.write(p,p.relative_to(app.parent))

    def update_plist(self, file, changes):
        value=plistlib.loads(file.read_bytes());value.update(changes);file.write_bytes(plistlib.dumps(value))

    def test_descriptor_binds_actual_archive_and_app_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,archive,_,_=self.fixture(Path(tmp))
            descriptor=module.build_descriptor(app,archive)
            self.assertEqual(descriptor['channel'],'unsigned-testing')
            self.assertEqual(descriptor['repository'],'maxwellsdm1867/Rieke-OS')
            self.assertEqual(descriptor['canonical_repository'],'maxwellsdm1867/Rieke-OS')
            self.assertEqual(descriptor['archive']['sha256'],hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual(descriptor['application_version'],'0.1.3')
            self.assertFalse(descriptor['production_ready'])
            (app/'Contents/Resources/app.asar').write_bytes(b'changed after packaging')
            with self.assertRaises(ValueError):module.build_descriptor(app,archive)

    def test_discovery_matches_electron_default_then_internal_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,archive,_,_=self.fixture(Path(tmp),helper_name='Electron Helper',internal_name='Disco')
            self.assertEqual(module.build_descriptor(app,archive)['application_version'],'0.1.3')

    def test_mismatched_internal_name_rejects_the_confirmed_unlaunchable_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,archive,_,_=self.fixture(Path(tmp),internal_name='Disco')
            with self.assertRaisesRegex(ValueError,'helper executable is missing'):
                module.build_descriptor(app,archive)

    def test_missing_nonexecutable_or_wrongly_declared_helper_rejected(self):
        for fault in ['missing','nonexecutable','executable','identifier']:
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as tmp:
                app,archive,helper,executable=self.fixture(Path(tmp))
                if fault=='missing':executable.unlink()
                elif fault=='nonexecutable':executable.chmod(0o644)
                elif fault=='executable':self.update_plist(helper/'Info.plist',{'CFBundleExecutable':'Disco Helper'})
                else:self.update_plist(helper/'Info.plist',{'CFBundleIdentifier':'foreign.helper'})
                with self.assertRaisesRegex(ValueError,'Electron helper'):
                    module.build_descriptor(app,archive)

    def test_visible_app_name_and_archived_helper_identity_are_bound(self):
        for fault in ['display','main_info','helper_info','helper_bytes']:
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as tmp:
                app,archive,helper,executable=self.fixture(Path(tmp))
                if fault=='display':self.update_plist(app/'Contents/Info.plist',{'CFBundleDisplayName':'Rieke OS'})
                elif fault=='main_info':self.update_plist(app/'Contents/Info.plist',{'CFBundleVersion':'other'})
                elif fault=='helper_info':self.update_plist(helper/'Info.plist',{'CFBundleVersion':'other'})
                else:executable.write_bytes(b'changed helper after archive')
                with self.assertRaises(ValueError):module.build_descriptor(app,archive)

    def test_archive_cannot_omit_the_selected_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            app,archive,_,executable=self.fixture(Path(tmp))
            with zipfile.ZipFile(archive,'w') as z:
                for p in app.rglob('*'):
                    if p.is_file() and p!=executable:z.write(p,p.relative_to(app.parent))
            with self.assertRaisesRegex(ValueError,'Archive omits'):
                module.build_descriptor(app,archive)
