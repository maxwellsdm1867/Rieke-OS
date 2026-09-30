"""Portable bootstrap safeguards; no network, package install or SQL writes."""
import configparser
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import workspace_bootstrap as boot


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "clone with spaces and 'quote"
        (self.root/'python').mkdir(parents=True)
        (self.root/'workspace-app/node_modules/vite').mkdir(parents=True)
        (self.root/'workspace-app/node_modules/vite/package.json').write_text('{"version":"8.3.1"}')
        self.spec={'commit':'a'*40,'compatible_local_commits':[], 'python':'3.11.13',
                   'repository':'https://example.invalid/parser.git','submodule':'lib/vision',
                   'submodule_commit':'b'*40,'utilities':'lib/vision/utilities'}
        (self.root/'python/workspace-source.json').write_text(json.dumps(self.spec))

    def test_unconfigured_paths_are_clone_local_not_personal_checkout(self):
        result=boot.runtime_paths(self.root,{})
        self.assertEqual(Path(result['python']), self.root/'.rieke-runtime/venv/bin/python')
        self.assertEqual(Path(result['retinanalysis']),self.root/'.rieke-runtime/retinanalysis')
        self.assertNotIn('Documents/GitHub',result['retinanalysis'])
        self.assertFalse((self.root/'.rieke-runtime').exists())

    def test_runtime_and_explicit_overrides_are_resolved_separately(self):
        folder=self.root/'.rieke-runtime';folder.mkdir()
        (folder/'runtime.json').write_text(json.dumps({'version':1,'python':'env/bin/python',
            'retinanalysis':'parser','managed_root':str(Path(self.temp.name)/'projects')}))
        env={'RETINANALYSIS_DIR':str(Path(self.temp.name)/'other-parser')}
        result=boot.runtime_paths(self.root,env)
        self.assertEqual(result['python'],str(self.root/'env/bin/python'))
        self.assertEqual(result['retinanalysis'],env['RETINANALYSIS_DIR'])

    def test_compatibility_config_has_existing_isolated_paths_and_preserves_existing(self):
        checkout=self.root/'parser';runtime=self.root/'.rieke-runtime'
        self.assertTrue(boot.write_compatibility_config(checkout,runtime))
        target=checkout/'src/retinanalysis/config/config.ini'
        config=configparser.ConfigParser();config.read(target)
        for section in ('DEFAULT','SECONDARY','LINUX_DEFAULT','LINUX_SECONDARY'):
            for key in ('analysis','data','raw','h5','meta','tags','query'):
                path=Path(config[section][key])
                self.assertTrue(path.is_dir())
                self.assertTrue(path.is_relative_to(runtime))
        target.write_text('scientist configuration\n')
        self.assertFalse(boot.write_compatibility_config(checkout,runtime))
        self.assertEqual(target.read_text(),'scientist configuration\n')

    def test_checkout_pin_dirty_source_and_submodule_fail_closed(self):
        checkout=self.root/'parser';(checkout/'lib/vision/utilities').mkdir(parents=True)
        (checkout/'lib/vision/utilities/setup.py').touch()
        with patch.object(boot,'captured',side_effect=['a'*40,'','b'*40]):
            self.assertEqual(boot.verify_checkout(checkout,self.spec),checkout)
        for answers in (['c'*40],['a'*40,' M parser.py'],['a'*40,'','c'*40]):
            with self.subTest(answers=answers),patch.object(boot,'captured',side_effect=answers):
                with self.assertRaises(ValueError):boot.verify_checkout(checkout,self.spec)

    def test_node_supported_versions(self):
        for value in ('v20.19.0','v22.12.0','v24.1.0'):
            self.assertTrue(boot.supported_node(value))
        for value in ('v18.20.0','v20.18.9','v21.9.0','v22.11.9'):
            self.assertFalse(boot.supported_node(value))

    def test_doctor_missing_native_mysql_is_read_only_and_separate_from_import_readiness(self):
        def capture(args,**kwargs):
            if args[0]=='docker':raise FileNotFoundError('Docker not installed')
            return 'v24.1.0' if args[0]=='node' else '10.0.0'
        with patch.object(boot,'captured',side_effect=capture), \
             patch.object(boot,'verify_checkout',return_value=self.root/'parser'), \
             patch.object(boot,'probe_runtime',return_value={'parser_import':'ok'}):
            result=boot.doctor(self.root,{})
        self.assertTrue(result['ready']);self.assertFalse(result['project_open_ready'])
        self.assertFalse((self.root/'.rieke-runtime').exists())

    def test_probe_rejects_wrong_installed_origin_and_does_not_hide_errors(self):
        with patch.object(boot,'captured',side_effect=subprocess.CalledProcessError(1,['python'],stderr='wrong origin')):
            with self.assertRaises(subprocess.CalledProcessError):boot.probe_runtime('python','parser')
        with patch.object(boot,'captured',return_value='RIEKE_PROBE={"parser_import":"ok"}'):
            self.assertEqual(boot.probe_runtime('python','parser'),{'parser_import':'ok'})

    def test_setup_uses_owned_environment_locked_registry_and_no_database(self):
        checkout=self.root/'.rieke-runtime/retinanalysis'
        def commands(args,**kwargs):
            if args[:2]==['git','clone']:
                Path(args[-1]).mkdir(parents=True)
        with patch.object(boot.shutil,'which',return_value='/tools/tool'), \
             patch.object(boot,'captured',side_effect=lambda args,**kw:'v24.0.0' if args[0]=='node' else 'a'*40), \
             patch.object(boot,'verify_checkout',return_value=checkout), \
             patch.object(boot,'run',side_effect=commands) as invoked, \
             patch.object(boot,'install_mysql_runtime',return_value={'root':str(self.root/'.rieke-runtime/mysql')}), \
             patch.object(boot,'probe_runtime',return_value={'parser_import':'ok'}):
            result=boot.setup(self.root)
        commands=[list(map(str,call.args[0])) for call in invoked.call_args_list]
        self.assertTrue(any('--require-hashes' in row for row in commands))
        self.assertTrue(any('submodule' in row and '--recursive' in row for row in commands))
        self.assertTrue(any('--no-build-isolation' in row for row in commands))
        self.assertFalse(any(row[0]=='docker' for row in commands))
        self.assertEqual(result['retinanalysis_commit'],'a'*40)
        self.assertTrue((self.root/'.rieke-runtime/runtime.json').is_file())
        self.assertFalse((self.root/'project.json').exists())

    def test_managed_doctor_uses_private_mysql_without_node_git_or_docker(self):
        runtime = self.root / '.rieke-runtime'
        runtime.mkdir()
        (runtime/'runtime.json').write_text(json.dumps({'version':1,'retinanalysis_commit':'a'*40}))
        (self.root/'workspace-app/dist').mkdir()
        (self.root/'workspace-app/dist/index.html').write_text('<html></html>')
        with patch.object(boot,'captured',side_effect=AssertionError('No external development commands at runtime')), \
                patch.object(boot,'source_spec',return_value={**self.spec,'commit':'a'*40}), \
                patch.object(boot,'mysql_runtime',return_value={'version':'8.4.2'}), \
                patch.object(boot,'probe_runtime',return_value={'parser_import':'ok'}):
            result=boot.doctor(self.root,{'RIEKE_INSTALLATION_ROOT':str(self.root.parent/'installed')})
        self.assertTrue(result['ready'])
        self.assertTrue(result['project_open_ready'])
        self.assertNotIn('docker',[row['check'] for row in result['checks']])

    def test_failed_install_does_not_publish_ready_runtime(self):
        checkout=self.root/'parser';checkout.mkdir()
        with patch.object(boot.shutil,'which',return_value='/tools/tool'), \
             patch.object(boot,'captured',return_value='v24.0.0'), \
             patch.object(boot,'verify_checkout',return_value=checkout), \
             patch.object(boot,'run',side_effect=subprocess.CalledProcessError(1,['uv'])):
            with self.assertRaises(subprocess.CalledProcessError):boot.setup(self.root,checkout=checkout)
        self.assertFalse((self.root/'.rieke-runtime/runtime.json').exists())

    def test_malformed_runtime_paths_are_clear_errors(self):
        folder=self.root/'.rieke-runtime';folder.mkdir()
        (folder/'runtime.json').write_text(json.dumps({'version':1,'python':{'wrong':'type'}}))
        with self.assertRaisesRegex(ValueError,'Invalid runtime python'):
            boot.runtime_paths(self.root,{})

    def test_setup_rejects_linked_external_environment(self):
        external=Path(self.temp.name)/'scientist-env';external.mkdir()
        runtime=self.root/'.rieke-runtime';runtime.mkdir()
        (runtime/'venv').symlink_to(external,target_is_directory=True)
        checkout=self.root/'parser';checkout.mkdir()
        with patch.object(boot.shutil,'which',return_value='/tools/tool'), \
             patch.object(boot,'captured',return_value='v24.0.0'), \
             patch.object(boot,'verify_checkout',return_value=checkout), \
             patch.object(boot,'run') as run:
            with self.assertRaisesRegex(ValueError,'symbolic link'):
                boot.setup(self.root,checkout=checkout)
            run.assert_not_called()

    def test_direct_import_container_comes_from_project_not_lab_default(self):
        from recording_workspace import configured_container
        with self.assertRaisesRegex(ValueError,'no default'):
            configured_container(self.root)
        (self.root/'catalog.json').write_text(json.dumps({'connection':{'credential_provider':{
            'kind':'docker-container-env','container':'rieke-owned-fixture'}}}))
        self.assertEqual(configured_container(self.root),'rieke-owned-fixture')
        self.assertEqual(configured_container(self.root,'explicit-fixture'),'explicit-fixture')



if __name__=='__main__':unittest.main()
