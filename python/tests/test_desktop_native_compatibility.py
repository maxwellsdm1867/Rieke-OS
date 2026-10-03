"""Synthetic Mach-O fixtures: no compiler, native execution or Apple tools required."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('native_compatibility', Path(__file__).resolve().parents[2] / 'tools/desktop_native_compatibility.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def thin(cpu=0x100000c, minimum=0x000e0000, command=0x32, extra=b''):
    version = b'' if minimum is None else (struct.pack('<IIIIII', command, 24, 1, minimum, 0x001b0000, 0) if command == 0x32 else struct.pack('<IIII', command, 16, minimum, 0x001b0000))
    commands = version + extra
    return struct.pack('<IIIIIIII', 0xfeedfacf, cpu, 0, 2, int(bool(version)) + int(bool(extra)), len(commands), 0, 0) + commands


def fat(*slices):
    offset = 8 + 20 * len(slices)
    headers, payload = [], b''
    for cpu, value in slices:
        headers.append(struct.pack('>IIIII', cpu, 0, offset, len(value), 0))
        offset += len(value)
        payload += value
    return struct.pack('>II', 0xcafebabe, len(slices)) + b''.join(headers) + payload


def path_command(command, value):
    payload = value.encode() + b'\0'
    size = 12 + len(payload)
    return struct.pack('<III', command, size, 12) + payload


class NativeCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'Example.app'
        self.root.mkdir()

    def put(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def report(self):
        return audit.audit_bundle(self.root)

    def codes(self):
        return {p['code'] for p in self.report()['problems']}

    def test_full_bundle_evidence_and_legacy_version_command(self):
        for name in ['Contents/MacOS/App', 'Contents/Frameworks/Electron', 'Contents/Resources/runtime/python/scipy/a.so', 'Contents/Resources/runtime/mysql/bin/mysqld']:
            self.put(name, thin(command=0x24))
        result = self.report()
        self.assertEqual(result['status'], 'no_known_static_blockers')
        self.assertEqual(result['native_binaries'], 4)
        self.assertFalse(result['runtime_compatibility_verified'])
        for item in result['files']:
            self.assertEqual(len(item['sha256']), 64)
            self.assertEqual(item['slices'][0]['minimum_macos'], '14.0.0')

    def test_unknown_newer_missing_arm64_and_malformed_fail_closed(self):
        for name, value in [('unknown', thin(minimum=None)), ('new', thin(minimum=0x000e0100)), ('intel', thin(cpu=0x1000007)), ('bad', thin()[:10])]:
            self.put(name, value)
        self.assertTrue({'unknown_macos_minimum', 'minimum_above_target', 'missing_required_architecture', 'invalid_macho'} <= self.codes())

    def test_universal_intel_minimum_is_evidence_not_intel_promise(self):
        self.put('universal', fat((0x100000c, thin()), (0x1000007, thin(cpu=0x1000007, minimum=0x00100000))))
        result = self.report()
        self.assertEqual(result['problems'], [])
        self.assertEqual(result['files'][0]['slices'][1]['minimum_macos'], '16.0.0')
        self.assertEqual(result['supported_architectures'], ['arm64'])

    def test_fat_header_architecture_cannot_disguise_intel(self):
        self.put('liar', fat((0x100000c, thin(cpu=0x1000007))))
        self.assertIn('invalid_macho', self.codes())

    def test_symlink_escape_and_dependency_escape(self):
        self.put('bin/app', thin(extra=path_command(0x8000001c, '@loader_path/../../../outside')))
        self.put('lib/external', thin(extra=path_command(0xc, '/opt/homebrew/lib/libbad.dylib')))
        (self.root / 'outside').symlink_to('/tmp')
        self.assertTrue({'external_symlink', 'external_rpath', 'external_native_dependency'} <= self.codes())

    def test_internal_and_system_paths_allowed(self):
        self.put('bin/app', thin(extra=path_command(0xc, '/usr/lib/libSystem.B.dylib')))
        (self.root / 'alias').symlink_to('bin/app')
        self.assertEqual(self.report()['problems'], [])

    def test_no_native_files_and_bounds_fail_closed(self):
        self.assertIn('no_native_binaries', self.codes())
        self.put('app', thin())
        result = audit.audit_bundle(self.root, max_files=0)
        self.assertIn('audit_limit_exceeded', {p['code'] for p in result['problems']})

    def test_other_platform_and_duplicate_version_rejected(self):
        value = bytearray(thin())
        struct.pack_into('<I', value, 40, 2)
        self.put('ios', value)
        self.put('duplicate', thin(extra=struct.pack('<IIII', 0x24, 16, 0x000e0000, 0)))
        self.assertTrue({'non_macos_slice', 'invalid_macho'} <= self.codes())


if __name__ == '__main__':
    unittest.main()
