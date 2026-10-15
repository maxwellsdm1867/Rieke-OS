"""Owned helper initialization lifecycle; no recording files or sample reads."""
import contextlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch
import uuid

import workspace_trace_native as native


class PendingChild:
    def __init__(self, *, ignore_terminate=False):
        self.returncode = None
        self.exited = threading.Event()
        self.waiting = threading.Event()
        self.ignore_terminate = ignore_terminate
        self.terminated = self.killed = 0
        self.wait_timeouts = []

    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout)
        self.waiting.set()
        if not self.exited.wait(timeout):
            raise subprocess.TimeoutExpired('owned probe', timeout)
        return self.returncode

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated += 1
        if not self.ignore_terminate:
            self.finish(-15)

    def kill(self):
        self.killed += 1
        self.finish(-9)

    def finish(self, code):
        self.returncode = code
        self.exited.set()


class NativeInitializationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.runtime = Path(self.folder.name).resolve() / 'runtime'
        (self.runtime / 'python/bin').mkdir(parents=True)
        (self.runtime / 'python/bin/python3.11').touch()
        (self.runtime / 'native').mkdir()
        (self.runtime / 'native/libdisco_trace_inflate.dylib').touch()
        self.state = patch.object(native, '_INITIALIZER', None)
        self.state.start()
        self.addCleanup(self.state.stop)
        self.addCleanup(lambda: native._INITIALIZER.close() if native._INITIALIZER else None)

    def test_start_is_nonblocking_once_with_fixed_isolated_probe_and_no_parent_load(self):
        child = PendingChild()
        with patch.object(native.subprocess, 'Popen', return_value=child) as spawn, \
                patch.object(native.ctypes, 'CDLL', side_effect=AssertionError('No parent mapping')):
            handle = native.initialize_desktop_helper(self.runtime)
            self.assertTrue(child.waiting.wait(1))
            self.assertFalse(handle.done.is_set())  # Startup already returned while child remains active.
            self.assertIs(native.initialize_desktop_helper(self.runtime), handle)
            spawn.assert_called_once()
            command = spawn.call_args.args[0]
            self.assertEqual(command, [str(self.runtime / 'python/bin/python3.11'),
                '-I', '-S', '-B', '-c', native._HELPER_PROBE,
                str(self.runtime / 'native/libdisco_trace_inflate.dylib')])
            options = spawn.call_args.kwargs
            self.assertFalse(options['shell'])
            self.assertTrue(options['close_fds'])
            self.assertEqual(options['env'], {})
            self.assertEqual(options['cwd'], str(self.runtime))
            self.assertEqual(options['stdin'], subprocess.DEVNULL)
            self.assertEqual(options['stdout'], subprocess.DEVNULL)
            self.assertEqual(options['stderr'], subprocess.DEVNULL)
            child.finish(0)
            self.assertTrue(handle.done.wait(1))
            handle.close()
            self.assertEqual(child.terminated, 0)
            self.assertEqual(child.killed, 0)
            self.assertFalse(handle.thread.is_alive())

    def test_missing_or_redirected_helper_and_spawn_failure_preserve_optional_fallback(self):
        helper = self.runtime / 'native/libdisco_trace_inflate.dylib'
        helper.unlink()
        with patch.object(native.subprocess, 'Popen') as spawn:
            handle = native.initialize_desktop_helper(self.runtime)
            self.assertTrue(handle.done.is_set())
            spawn.assert_not_called()
        helper.symlink_to(Path(self.folder.name) / 'outside.dylib')
        helper.resolve().touch()
        with patch.object(native.subprocess, 'Popen') as spawn:
            handle = native._HelperInitialization(self.runtime)
            self.assertTrue(handle.done.is_set())
            spawn.assert_not_called()
        helper.unlink(); helper.touch()
        with patch.object(native.subprocess, 'Popen', side_effect=OSError('owned spawn failure')):
            handle = native._HelperInitialization(self.runtime)
            self.assertTrue(handle.done.is_set())
            handle.close()
        # No initializer result enters the actual optional loader's cache.
        native._load_helper.cache_clear()
        try:
            with patch.dict(os.environ, {'RIEKE_DESKTOP_RUNTIME': str(self.runtime)}):
                self.assertIsNone(native._load_helper())
        finally:
            native._load_helper.cache_clear()

    def test_probe_failure_is_reaped_without_affecting_caller(self):
        child = PendingChild(); child.finish(1)
        with patch.object(native.subprocess, 'Popen', return_value=child):
            with native.initialize_desktop_helper(self.runtime) as handle:
                self.assertTrue(handle.done.wait(1))
                self.assertEqual(child.returncode, 1)
            self.assertEqual(child.terminated, 0)

    def test_deadline_terminates_kills_and_reaps_with_bounded_waits(self):
        child = PendingChild(ignore_terminate=True)
        with patch.object(native.subprocess, 'Popen', return_value=child), \
                patch.object(native, '_INITIALIZER_DEADLINE', .01), \
                patch.object(native, '_INITIALIZER_STOP_TIMEOUT', .01):
            handle = native.initialize_desktop_helper(self.runtime)
            self.assertTrue(handle.done.wait(1))
            handle.close()
            self.assertEqual(child.terminated, 1)
            self.assertEqual(child.killed, 1)
            self.assertIn(.01, child.wait_timeouts)
            self.assertEqual(child.returncode, -9)
            self.assertFalse(handle.thread.is_alive())

    def test_normal_and_exception_exit_close_only_the_owned_child(self):
        for fail in (False, True):
            child = PendingChild()
            with patch.object(native.subprocess, 'Popen', return_value=child):
                try:
                    with native._HelperInitialization(self.runtime) as handle:
                        self.assertTrue(child.waiting.wait(1))
                        if fail:
                            raise ValueError('owned startup failure')
                except ValueError:
                    self.assertTrue(fail)
                self.assertEqual(child.terminated, 1)
                self.assertEqual(child.killed, 0)
                self.assertFalse(handle.thread.is_alive())
                handle.close()  # Idempotent, no repeat signal.
                self.assertEqual(child.terminated, 1)

    def test_thread_start_failure_still_cleans_spawned_child(self):
        child = PendingChild()
        with patch.object(native.subprocess, 'Popen', return_value=child), \
                patch.object(native.threading.Thread, 'start', side_effect=RuntimeError('owned thread failure')):
            handle = native._HelperInitialization(self.runtime)
            self.assertTrue(handle.done.is_set())
            self.assertEqual(child.terminated, 1)
            handle.close()

    def test_real_isolated_child_only_probes_abi_and_never_calls_sample_functions(self):
        compiler = shutil.which('cc') or shutil.which('clang')
        if compiler is None or sys.platform not in ('darwin', 'linux'):
            self.skipTest('Owned native probe requires a C compiler')
        source = Path(self.folder.name) / 'owned-probe.c'
        source.write_text('#include <stdlib.h>\nunsigned disco_trace_inflate_abi(void){return 4;}\n' +
            '\n'.join('void '+name+'(void){abort();}' for name in (
                'disco_trace_inflate_v1', 'disco_trace_normalize_units_v1',
                'disco_trace_extract_v1', 'disco_trace_m4_v1')))
        library = self.runtime / 'native/libdisco_trace_inflate.dylib'
        subprocess.run([compiler, '-dynamiclib' if sys.platform == 'darwin' else '-shared',
                        '-fPIC', str(source), '-o', str(library)], check=True, capture_output=True)
        original = subprocess.Popen
        # The owned fixture has no packaged interpreter. Substitute this test
        # interpreter only; retain the exact isolated flags/code/library path.
        def spawn(command, **options):
            return original([sys.executable, *command[1:]], **options)
        with patch.object(native.subprocess, 'Popen', side_effect=spawn):
            handle = native.initialize_desktop_helper(self.runtime)
            self.assertTrue(handle.done.wait(5))
            self.assertEqual(handle.process.returncode, 0)
            handle.close()
        self.assertEqual(list(self.runtime.rglob('*.h5')), [])


class DesktopInitializationOrderingTests(unittest.TestCase):
    def run_main(self, failure=None):
        import workspace_desktop as desktop
        from flask import Flask
        events = []
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); resources = root / 'resources'; runtime = resources / 'runtime'
            runtime.mkdir(parents=True); manifest_path = runtime / 'runtime-manifest.json'; manifest_path.write_text('{}')
            user_state = root / 'state'
            if failure == 'configuration':
                preference = user_state / 'preferences/workspace-selection.json'
                preference.parent.mkdir(parents=True)
                preference.write_text('{"version": 2}')
            manifest = dict(application_version='test', source_commit='owned',
                            workspace_formats={}, database_compatibility={})
            def validate(path):
                events.append('validated')
                if failure == 'validation':
                    raise ValueError('owned validation failure')
                return manifest
            @contextlib.contextmanager
            def initialize(path):
                self.assertEqual(path, runtime)
                events.append('probe-started')
                try:
                    yield object()
                finally:
                    events.append('probe-closed')
            def launcher(*args, **kwargs):
                events.append('launcher')
                return Flask(__name__)
            def run():
                events.append('server')
                if failure == 'server':
                    raise ValueError('owned server failure')
            server = types.SimpleNamespace(run=run)
            bootstrap = types.SimpleNamespace(validate_desktop_runtime=validate, prepare_desktop_parser_config=Mock())
            modules = {'workspace_bootstrap': bootstrap,
                       'workspace_launcher': types.SimpleNamespace(create_launcher=launcher),
                       'waitress': types.SimpleNamespace(create_server=lambda *a, **kw: server)}
            with patch.dict(sys.modules, modules), patch.dict(os.environ, {'RIEKE_DESKTOP_CAPABILITY': 'x' * 48}), \
                    patch.object(native, 'initialize_desktop_helper', side_effect=initialize), \
                    patch.object(desktop, 'DesktopServices'), patch.object(desktop, 'DesktopBoundary'), \
                    patch.object(desktop, '_SERVICES', None):
                arguments = ['--resources', str(resources), '--manifest', str(manifest_path),
                    '--user-state', str(user_state), '--session-id', str(uuid.uuid4()), '--port', '18881']
                if failure:
                    with self.assertRaises(ValueError):
                        desktop.main(arguments)
                else:
                    desktop.main(arguments)
        return events

    def test_after_runtime_validation_before_launcher_and_closed_after_normal_server(self):
        self.assertEqual(self.run_main(), ['validated', 'probe-started', 'launcher', 'server', 'probe-closed'])

    def test_invalid_runtime_never_starts_probe(self):
        self.assertEqual(self.run_main('validation'), ['validated'])

    def test_configuration_and_server_errors_close_probe(self):
        self.assertEqual(self.run_main('configuration'), ['validated', 'probe-started', 'probe-closed'])
        self.assertEqual(self.run_main('server'), ['validated', 'probe-started', 'launcher', 'server', 'probe-closed'])
