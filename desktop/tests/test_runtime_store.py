"""Filesystem lifecycle decisions with explicit inert process/OS adapters."""
import importlib.util
import fcntl
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("runtime_store", Path(__file__).parents[1] / "runtime-store.py")
store = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store)


class MissingProcess(Exception):
    pass


class DeniedProcess(Exception):
    pass


class RuntimeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="disco-runtime-store-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.identifiers = [letter * 64 for letter in "abc"]
        self.bundles = {}
        for index, identifier in enumerate(self.identifiers):
            bundle = self.root / "generations" / identifier / "Disco.app"
            framework = bundle / "Contents/Frameworks/Electron Framework.framework/Versions/A/Electron Framework"
            framework.parent.mkdir(parents=True)
            framework.write_text("inert framework")
            store.write(bundle.parent / "generation.json", dict(format="disco-runtime-generation", version=1, id=identifier,
                        manifest=dict(application_version=f"0.2.{index + 4}",format="rieke-desktop-runtime",version=1,platform="darwin",architecture="arm64",mysql_version="8.4.2",database_compatibility=1,workspace_formats=[1])))
            self.bundles[identifier] = bundle
        store.write(self.root / "current.json", dict(format="disco-current-runtime", version=1, id=self.identifiers[2], previous=self.identifiers[1], revision="current"))
        (self.root / "admissions").mkdir()
        self.token = "11111111-1111-4111-8111-111111111111"
        self.file = self.root / "admissions" / (self.token + ".json")
        self.owner = types.SimpleNamespace(pid=123, exe=lambda: str(self.bundles[self.identifiers[0]] / "Contents/MacOS/Disco"), create_time=lambda: 456.5, status=lambda: "running")
        self.psutil = types.SimpleNamespace(Process=lambda pid: self.owner, NoSuchProcess=MissingProcess, ZombieProcess=MissingProcess,
                                            AccessDenied=DeniedProcess, STATUS_ZOMBIE="zombie")
        self.psutil_patch = patch.dict(sys.modules, psutil=self.psutil)
        self.psutil_patch.start()
        self.addCleanup(self.psutil_patch.stop)

    def ticket(self, **changes):
        value = dict(format="disco-runtime-admission", version=1, id=self.identifiers[0], profile=str(self.root / "profile"),
                     token=self.token, recover=False, fresh=False, expires_at=time.time() + 300)
        value.update(changes)
        store.write(self.file, value)
        return value

    def request(self, operation, **changes):
        value = dict(operation=operation, token=self.token, pid=123, profile=str(self.root / "profile"), fresh=False, recover=False)
        value.update(changes)
        with patch.object(store.os, "getppid", return_value=123):
            return store.execute(self.root, value)

    def collect(self, *, process_path="/usr/bin/inert-test", framework_open=False, uncertain=False, dock=None):
        def command(args, **_options):
            if args[0] == "/usr/bin/defaults":
                return types.SimpleNamespace(stdout=plistlib.dumps(dock or {}))
            if args[0] == "/bin/ps":
                return types.SimpleNamespace(stdout=" 456 " + process_path + "\n")
            if args[0] == "/usr/sbin/lsof":
                return types.SimpleNamespace(returncode=0 if framework_open else 1, stdout="456\n" if framework_open else "", stderr="inspection refused" if uncertain else "")
            raise AssertionError(args)
        with patch.object(store.subprocess, "run", side_effect=command):
            return store.execute(self.root, dict(operation="collect"))

    def test_admission_is_one_use_and_binds_final_selected_profile(self):
        self.ticket()
        self.request("admit")
        accepted = self.file.read_bytes()
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.request("admit")
        self.assertEqual(self.file.read_bytes(), accepted)
        self.request("bind-profile", profile=str(self.root / "sessions/session-2"))
        value = store.read(self.file)
        self.assertEqual(value["created_at"], 456.5)
        self.assertEqual(value["selected_profile"], str(self.root / "sessions/session-2"))

    def test_expired_reservation_cannot_start_scientific_session(self):
        self.ticket(expires_at=time.time() - 1)
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.request("admit")
        self.assertNotIn("pid", store.read(self.file))

    def test_reused_pid_cannot_retire_another_lease(self):
        self.ticket(pid=123, created_at=455.0)
        with self.assertRaisesRegex(ValueError, "owner changed"):
            self.request("retire")
        self.assertNotIn("retired", store.read(self.file))

    def test_live_descendant_protects_generation_after_gui_disappears(self):
        self.ticket(pid=123, created_at=456.5)
        self.psutil.Process = lambda pid: (_ for _ in ()).throw(MissingProcess())
        child = str(self.bundles[self.identifiers[0]] / "Contents/Resources/runtime/mysql/bin/mysqld")
        self.assertEqual(self.collect(process_path=child)["removed"], [])
        self.assertNotIn("retired", store.read(self.file))

    def test_crashed_gui_bytes_retire_when_its_last_descendant_is_gone(self):
        self.ticket(pid=123, created_at=456.5)
        self.psutil.Process = lambda pid: (_ for _ in ()).throw(MissingProcess())
        self.assertEqual(self.collect()["removed"], [self.identifiers[0]])
        self.assertFalse(self.bundles[self.identifiers[0]].exists())
        self.assertTrue(self.bundles[self.identifiers[1]].exists())
        self.assertTrue(self.bundles[self.identifiers[2]].exists())

    def test_open_framework_or_inspection_uncertainty_retains_bytes(self):
        self.ticket(retired=True)
        self.assertEqual(self.collect(framework_open=True)["removed"], [])
        self.assertEqual(self.collect(uncertain=True)["removed"], [])
        self.assertTrue(self.bundles[self.identifiers[0]].exists())

    def test_unconsumed_launch_pin_expires_without_blocking_future_versions(self):
        self.ticket()
        self.assertEqual(self.collect()["removed"], [])
        self.ticket(expires_at=time.time() - 1)
        self.assertEqual(self.collect()["removed"], [self.identifiers[0]])

    def test_pinned_dock_entry_keeps_its_redirecting_executable(self):
        self.ticket(retired=True)
        dock={"persistent-apps": [{"tile-data": {"file-data": {"_CFURLString": str(self.bundles[self.identifiers[0]])}}}]}
        self.assertEqual(self.collect(dock=dock)["removed"], [])

    def test_malformed_retention_record_prevents_deletion(self):
        self.file.write_text("interrupted record")
        with self.assertRaises(ValueError):
            self.collect()
        self.assertTrue(self.bundles[self.identifiers[0]].exists())

    def test_dead_recoveries_of_one_profile_do_not_pin_each_other(self):
        value = self.ticket(pid=123, created_at=456.5, selected_profile=str(self.root / "profile"))
        second = dict(value, token="22222222-2222-4222-8222-222222222222", pid=124)
        store.write(self.file.with_name(second["token"] + ".json"), second)
        self.psutil.Process = lambda pid: (_ for _ in ()).throw(MissingProcess())
        self.assertEqual(self.collect()["removed"], [self.identifiers[0]])

    def test_front_door_profile_waits_for_parent_and_chromium_helpers(self):
        self.ticket(retired=True)
        directory = self.root / "front-doors/launch-owned"
        profile = directory / "profile"
        profile.mkdir(parents=True)
        (profile / "cache").write_text("inert Chromium cache")
        store.write(directory / "owner.json", dict(format="disco-front-door-profile", version=1, pid=321))
        with patch.object(store.os, "kill", return_value=None):
            self.collect()
        self.assertTrue(profile.exists())
        with patch.object(store.os, "kill", side_effect=ProcessLookupError()):
            self.collect(process_path="/inert/Chromium --user-data-dir=" + str(profile))
        self.assertTrue(profile.exists())
        with patch.object(store.os, "kill", side_effect=ProcessLookupError()):
            self.collect()
        self.assertFalse(directory.exists())

    def test_malformed_prior_version_types_preserve_evidence_and_recover_current(self):
        file = self.bundles[self.identifiers[2]].parent / "generation.json"
        record = store.read(file)
        for invalid in (None, 42, []):
            with self.subTest(invalid=invalid):
                record["manifest"]["application_version"] = invalid
                store.write(file, record)
                store.write(self.root / "current.json", dict(format="disco-current-runtime", version=1, id=self.identifiers[2], previous=None, revision="damaged"))
                value = store.execute(self.root, dict(operation="activate", id=self.identifiers[0]))
                self.assertEqual(value["id"], self.identifiers[0])
                self.assertEqual(store.read(file)["manifest"]["application_version"], invalid)

    def test_activation_pin_survives_two_newer_activations_until_launch_reservation(self):
        prepared = store.execute(self.root, dict(operation="prepare", id=self.identifiers[0]))
        activated = store.execute(self.root, dict(operation="activate", id=prepared["id"], preparation=prepared["preparation"], rollbackRevision="current"))
        store.execute(self.root, dict(operation="activate", id=self.identifiers[1]))
        store.execute(self.root, dict(operation="activate", id=self.identifiers[2]))
        self.assertEqual(self.collect()["removed"], [])
        reserved = store.execute(self.root, dict(operation="reserve", id=activated["id"], preparation=activated["generation"]["preparation"], profile=str(self.root / "profile")))
        self.assertEqual(reserved["generation"], self.identifiers[0])
        self.assertFalse((self.root / "preparations" / (activated["generation"]["preparation"] + ".json")).exists())
        self.assertEqual(self.collect()["removed"], [])

    def test_claimed_restart_stays_pinned_past_deadline_until_reserved(self):
        self.owner.ppid = lambda: 88
        with patch.object(store.os, "getppid", return_value=123):
            handoff = store.execute(self.root, dict(operation="restart-handoff", id=self.identifiers[0], profile=str(self.root / "profile"),
                            identity=dict(pid=88, executable=self.owner.exe(), created_at=333)))
            store.execute(self.root, dict(operation="claim-handoff", token=handoff["nonce"]))
            file = Path(handoff["file"])
            receipt = store.read(file)
            receipt["expires_at"] = time.time() - 1000
            store.write(file, receipt)
            self.assertEqual(self.collect()["removed"], [])
            store.execute(self.root, dict(operation="reserve", id=self.identifiers[0], profile=str(self.root / "profile"), recover=True, handoff=handoff["nonce"]))
            self.assertFalse(file.exists())
            self.assertEqual(self.collect()["removed"], [])

    def test_crashed_gui_cannot_retire_while_backend_lock_is_held(self):
        profile = self.root / "profile"
        backend = profile / "backend"
        backend.mkdir(parents=True)
        lock = backend / "desktop-session.lock"
        fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.ticket(pid=123, created_at=456.5, selected_profile=str(profile))
        self.psutil.Process = lambda pid: (_ for _ in ()).throw(MissingProcess())
        self.assertEqual(self.collect()["removed"], [])
        self.assertNotIn("retired", store.read(self.file))

    def test_registry_witness_blocks_collection_even_if_snapshot_misses_child(self):
        profile = self.root / "profile"
        backend = profile / "backend"
        backend.mkdir(parents=True)
        (backend / "desktop-session.lock").touch(mode=0o600)
        store.write(backend / "desktop-services.json", dict(version=1, services=[dict(pid=321, created_at=456.5, project_path=str(self.root / "project"))]))
        self.ticket(pid=123, created_at=456.5, selected_profile=str(profile))
        self.psutil.Process = lambda pid: self.owner if pid == 321 else (_ for _ in ()).throw(MissingProcess())
        self.assertEqual(self.collect()["removed"], [])

    def test_stale_unclean_database_evidence_is_preserved_after_bytes_retire(self):
        profile = self.root / "profile"
        backend = profile / "backend"
        backend.mkdir(parents=True)
        lock = backend / "desktop-session.lock"
        lock.touch(mode=0o600)
        registry = backend / "desktop-services.json"
        store.write(registry, dict(version=1, services=[dict(pid=321, created_at=456.5, project_path=str(self.root / "project"))]))
        evidence = registry.read_bytes()
        self.ticket(pid=123, created_at=456.5, selected_profile=str(profile))
        self.psutil.Process = lambda pid: (_ for _ in ()).throw(MissingProcess())
        runtime = types.SimpleNamespace(project_runtime_state=lambda project: {"state":"stopped_unclean"}, RUNNING={"running_owned","running_foreign"})
        original = store.shutil.rmtree
        def checked_remove(directory, *args, **kwargs):
            fd = os.open(lock, os.O_RDONLY)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)
            original(directory, *args, **kwargs)
        with patch.dict(sys.modules, {"disco.projects.runtime_state":runtime}), patch.object(store.shutil, "rmtree", side_effect=checked_remove):
            # This path is only an injected import adapter; no project data API
            # is started by the store's read-only ownership call.
            with patch.object(store, "hold_profile_witnesses", wraps=store.hold_profile_witnesses) as witness:
                original_execute = store.execute
                def execute(root, request):
                    if request["operation"] == "collect":
                        request = dict(request, runtime_application=str(self.root))
                    return original_execute(root, request)
                with patch.object(store, "execute", side_effect=execute):
                    self.assertEqual(self.collect()["removed"], [self.identifiers[0]])
                self.assertTrue(witness.called)
        self.assertEqual(registry.read_bytes(), evidence)


if __name__ == "__main__":
    unittest.main()
