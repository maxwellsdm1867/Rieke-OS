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
    header_size = 12 if command == 0x8000001c else 24
    size = header_size + len(payload)
    header = struct.pack('<III', command, size, header_size)
    if header_size == 24:
        header += struct.pack('<III', 0, 0, 0)
    return header + payload


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

    def test_fat64_and_big_endian_legacy_macho(self):
        value = thin()
        self.put('fat64', struct.pack('>II', 0xcafebabf, 1) +
                 struct.pack('>IIQQII', 0x100000c, 0, 40, len(value), 0, 0) + value)
        legacy = struct.pack('>IIIIIII', 0xfeedface, 0x100000c, 0, 2, 1, 16, 0)
        self.put('big', legacy + struct.pack('>IIII', 0x24, 16, 0x000b0000, 0))
        self.assertEqual(self.report()['problems'], [])

    def test_arm64e_alone_does_not_satisfy_regular_arm64(self):
        value = bytearray(thin())
        struct.pack_into('<I', value, 8, 2)
        self.put('arm64e', value)
        self.assertIn('missing_required_architecture', self.codes())

    def test_hash_budget_and_deadline_cannot_return_pass(self):
        self.put('app', thin())
        for limits in [{'max_native_bytes': 1}, {'timeout': -1}]:
            result = audit.audit_bundle(self.root, **limits)
            self.assertEqual(result['status'], 'blocked')
            self.assertIn('audit_limit_exceeded', {p['code'] for p in result['problems']})

    def test_symlink_escape_and_dependency_escape(self):
        self.put('bin/app', thin(extra=path_command(0x8000001c, '@loader_path/../../../outside')))
        self.put('lib/external', thin(extra=path_command(0xc, '/opt/homebrew/lib/libbad.dylib')))
        (self.root / 'outside').symlink_to('/tmp')
        self.assertTrue({'external_symlink', 'external_rpath', 'external_native_dependency'} <= self.codes())

    def test_internal_and_system_paths_allowed(self):
        self.put('bin/app', thin(extra=path_command(0xc, '/usr/lib/libSystem.B.dylib')))
        (self.root / 'alias').symlink_to('bin/app')
        self.assertEqual(self.report()['problems'], [])

    def test_bare_loader_path_and_nested_executable_context(self):
        self.put('Contents/Resources/runtime/lib/library', thin(extra=path_command(0x8000001c, '@loader_path')))
        self.put('Contents/Frameworks/Squirrel.framework/Versions/A/Resources/ShipIt',
                 thin(extra=path_command(0x8000001c, '@executable_path/../../../..')))
        self.assertEqual(self.report()['problems'], [])

    def test_executable_context_uses_real_location_and_rejects_escape(self):
        self.put('app', thin(extra=path_command(0x8000001c, '@executable_path/..')))
        self.assertIn('external_rpath', self.codes())

    def test_dylib_executable_context_fails_closed_without_candidates(self):
        library = bytearray(thin(extra=path_command(0x8000001c, '@executable_path/../lib')))
        struct.pack_into('<I', library, 12, 6)
        self.put('Contents/lib/library', library)
        self.assertIn('unresolved_executable_context', self.codes())

    def test_dylib_checks_every_matching_executable_candidate(self):
        library = bytearray(thin(extra=path_command(0x8000001c, '@executable_path/../lib')))
        struct.pack_into('<I', library, 12, 6)
        self.put('Contents/lib/library', library)
        self.put('Contents/MacOS/app', thin())
        report = self.report()
        self.assertEqual(report['problems'], [])
        record = next(item for item in report['files'] if item['path'] == 'Contents/lib/library')
        evidence = record['slices'][0]['executable_path_containment'][0]
        self.assertEqual(evidence['candidate_executables'], ['Contents/MacOS/app'])
        self.assertFalse(evidence['actual_loader_verified'])
        self.put('other-app', thin())
        self.assertIn('external_rpath', self.codes())

    def test_system_path_prefix_cannot_hide_parent_escape(self):
        for index, value in enumerate(['/usr/lib/../../tmp/libbad.dylib',
                                       '/System/Library/../../tmp/libbad.dylib']):
            for command in (0xc, 0x8000001c):
                self.put(f'escape-{index}-{command}', thin(extra=path_command(command, value)))
        result = self.report()
        self.assertEqual(sum(p['code'] == 'external_native_dependency' for p in result['problems']), 2)
        self.assertEqual(sum(p['code'] == 'external_rpath' for p in result['problems']), 2)

    def test_dylib_header_requires_24_bytes_and_string_after_header(self):
        short = struct.pack('<III', 0xc, 16, 12) + b'x\0\0\0'
        offset = bytearray(path_command(0xc, '/usr/lib/libSystem.B.dylib'))
        struct.pack_into('<I', offset, 8, 12)
        for name, command in [('short', short), ('offset', offset)]:
            self.put(name, thin(extra=command))
        result = self.report()
        self.assertEqual(sum(p['code'] == 'invalid_macho' for p in result['problems']), 2)

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
