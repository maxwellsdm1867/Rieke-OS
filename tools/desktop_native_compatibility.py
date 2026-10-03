#!/usr/bin/env python3
"""Bounded, read-only whole-bundle Mach-O deployment and containment evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import time

THIN = {b'\xce\xfa\xed\xfe': ('<', False), b'\xfe\xed\xfa\xce': ('>', False),
        b'\xcf\xfa\xed\xfe': ('<', True), b'\xfe\xed\xfa\xcf': ('>', True)}
FAT = {b'\xca\xfe\xba\xbe': ('>', False), b'\xbe\xba\xfe\xca': ('<', False),
       b'\xca\xfe\xba\xbf': ('>', True), b'\xbf\xba\xfe\xca': ('<', True)}
CPUS = {0x100000c: 'arm64', 0x1000007: 'x86_64', 12: 'arm', 7: 'i386'}
LOADS = {0xc, 0x80000018, 0x8000001f, 0x20, 0x80000023}
SYSTEM = ('/usr/lib/', '/System/Library/')


def version(value):
    return f'{value >> 16}.{(value >> 8) & 255}.{value & 255}'


def read_exact(handle, offset, size, end):
    if size < 0 or offset < 0 or offset + size > end:
        raise ValueError('Native structure exceeds its slice')
    handle.seek(offset)
    data = handle.read(size)
    if len(data) != size:
        raise ValueError('Truncated native structure')
    return data


def parse_slice(handle, offset, size, expected_cpu=None):
    end = offset + size
    magic = read_exact(handle, offset, 4, end)
    if magic not in THIN:
        raise ValueError('Unknown native slice magic')
    endian, wide = THIN[magic]
    header_size = 32 if wide else 28
    header = read_exact(handle, offset, header_size, end)
    cpu, subtype, kind, count, command_size = struct.unpack_from(endian + 'IIIII', header, 4)
    if expected_cpu is not None and cpu != expected_cpu:
        raise ValueError('Universal header CPU disagrees with slice')
    if count > 65536 or command_size > 16 * 1024 * 1024:
        raise ValueError('Load command limit exceeded')
    data = read_exact(handle, offset + header_size, command_size, end)
    result = {'architecture': CPUS.get(cpu, f'unknown-{cpu}'), 'cpu_type': cpu,
              'cpu_subtype': subtype, 'file_type': kind, 'offset': offset, 'size': size,
              'minimum_macos': None, 'platform': None, 'sdk': None,
              'version_command': None, 'dependencies': [], 'rpaths': []}
    cursor = 0
    for _ in range(count):
        if cursor + 8 > len(data):
            raise ValueError('Truncated load command')
        command, length = struct.unpack_from(endian + 'II', data, cursor)
        if length < 8 or cursor + length > len(data):
            raise ValueError('Invalid load command size')
        block = data[cursor:cursor + length]
        if command in (0x24, 0x32):
            if result['version_command']:
                raise ValueError('Duplicate deployment version commands')
            if command == 0x32:
                if length < 24:
                    raise ValueError('Truncated build version')
                platform, minimum, sdk, ntools = struct.unpack_from(endian + 'IIII', block, 8)
                if length != 24 + 8 * ntools:
                    raise ValueError('Invalid build tool metadata')
                name = 'LC_BUILD_VERSION'
            else:
                if length != 16:
                    raise ValueError('Invalid legacy version metadata')
                minimum, sdk = struct.unpack_from(endian + 'II', block, 8)
                platform, name = 1, 'LC_VERSION_MIN_MACOSX'
            result.update(platform=platform, version_command=name, sdk=version(sdk),
                          minimum_macos=version(minimum) if platform == 1 and minimum else None)
        elif command in LOADS or command == 0x8000001c:
            if length < 12:
                raise ValueError('Truncated native path command')
            start = struct.unpack_from(endian + 'I', block, 8)[0]
            if start < 12 or start >= length or b'\0' not in block[start:]:
                raise ValueError('Invalid native path string')
            value = block[start:].split(b'\0', 1)[0].decode('utf-8')
            result['rpaths' if command == 0x8000001c else 'dependencies'].append(value)
        cursor += length
    if cursor != len(data):
        raise ValueError('Load command count/size disagreement')
    return result


def parse_macho(handle, size):
    magic = read_exact(handle, 0, 4, size)
    if magic in THIN:
        return [parse_slice(handle, 0, size)]
    endian, wide = FAT[magic]
    count = struct.unpack(endian + 'I', read_exact(handle, 4, 4, size))[0]
    if not 1 <= count <= 32:
        raise ValueError('Invalid universal slice count')
    stride = 32 if wide else 20
    header_end = 8 + count * stride
    table = read_exact(handle, 8, count * stride, size)
    slices, regions = [], []
    for index in range(count):
        values = struct.unpack_from(endian + ('IIQQII' if wide else 'IIIII'), table, index * stride)
        cpu, _, offset, length = values[:4]
        if offset < header_end or length < 28 or offset + length > size:
            raise ValueError('Invalid universal slice range')
        if any(offset < stop and offset + length > start for start, stop in regions):
            raise ValueError('Overlapping universal slices')
        regions.append((offset, offset + length))
        slices.append(parse_slice(handle, offset, length, cpu))
    return slices


def audit_bundle(bundle, *, max_files=200000, max_native_bytes=16 * 1024**3, timeout=300):
    root = Path(bundle).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Bundle must be a directory')
    started = time.monotonic()
    files, links, problems = [], [], []
    visited, hashed = 0, 0

    def issue(path, code, **details):
        problems.append({'path': path, 'code': code, **details})

    def inside(path):
        return path.resolve().is_relative_to(root)

    def check_time():
        if time.monotonic() - started > timeout:
            raise TimeoutError('Audit deadline exceeded')

    try:
        # scandir does not follow directory symlinks; bounds apply before recursion.
        pending = [root]
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    check_time()
                    visited += 1
                    if visited > max_files:
                        raise TimeoutError('File count limit exceeded')
                    path = Path(entry.path)
                    relative = path.relative_to(root).as_posix()
                    if entry.is_symlink():
                        target = os.readlink(path)
                        links.append({'path': relative, 'target': target})
                        try:
                            if os.path.isabs(target) or not inside(path):
                                issue(relative, 'external_symlink')
                            elif not path.exists():
                                issue(relative, 'broken_symlink')
                        except (OSError, RuntimeError):
                            issue(relative, 'invalid_symlink')
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        issue(relative, 'unsupported_file_type')
                        continue
                    with path.open('rb') as handle:
                        before = os.fstat(handle.fileno())
                        magic = handle.read(4)
                        if magic not in THIN and magic not in FAT:
                            continue
                        record = {'path': relative, 'size': before.st_size, 'sha256': None, 'slices': []}
                        files.append(record)
                        hashed += before.st_size
                        if hashed > max_native_bytes:
                            raise TimeoutError('Native byte limit exceeded')
                        digest = hashlib.sha256()
                        handle.seek(0)
                        while chunk := handle.read(1024 * 1024):
                            check_time()
                            digest.update(chunk)
                        record['sha256'] = digest.hexdigest()
                        try:
                            record['slices'] = parse_macho(handle, before.st_size)
                        except (ValueError, UnicodeError, struct.error) as error:
                            issue(relative, 'invalid_macho', detail=str(error))
                            continue
                        after = os.fstat(handle.fileno())
                        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                            issue(relative, 'native_file_changed')
                    slices = record['slices']
                    if not any(s['architecture'] == 'arm64' and (s['cpu_subtype'] & 0xffffff) == 0 for s in slices):
                        issue(relative, 'missing_required_architecture', required='arm64')
                    for native in slices:
                        arch = native['architecture']
                        if native['platform'] not in (None, 1):
                            issue(relative, 'non_macos_slice', architecture=arch, platform=native['platform'])
                        if native['minimum_macos'] is None:
                            issue(relative, 'unknown_macos_minimum', architecture=arch)
                        elif arch == 'arm64' and tuple(map(int, native['minimum_macos'].split('.'))) > (14, 0, 0):
                            issue(relative, 'minimum_above_target', architecture=arch, minimum=native['minimum_macos'])
                        for field, code in [('rpaths', 'external_rpath'), ('dependencies', 'external_native_dependency')]:
                            for value in native[field]:
                                if value.startswith(SYSTEM):
                                    continue
                                if value.startswith('/'):
                                    issue(relative, code, architecture=arch, value=value)
                                elif value.startswith('@loader_path/'):
                                    if not inside(path.parent / value[len('@loader_path/'):]):
                                        issue(relative, code, architecture=arch, value=value)
                                elif value.startswith('@executable_path/'):
                                    # Containment relative to the enclosing app's main
                                    # executable. Loader-chain resolution remains unverified.
                                    app = next((p for p in path.parents if p.suffix == '.app'), root)
                                    anchor = app / 'Contents/MacOS'
                                    if not inside(anchor / value[len('@executable_path/'):]):
                                        issue(relative, code, architecture=arch, value=value)
                                elif value.startswith('@rpath/'):
                                    # Exact resolution depends on the loader chain. Reject
                                    # upward escapes from these symbolic roots conservatively.
                                    depth = 0
                                    for part in value.split('/')[1:]:
                                        depth += -1 if part == '..' else int(part not in ('', '.'))
                                        if depth < 0:
                                            issue(relative, code, architecture=arch, value=value)
                                            break
                                else:
                                    issue(relative, 'unknown_native_path', architecture=arch, value=value)
    except TimeoutError as error:
        issue('.', 'audit_limit_exceeded', detail=str(error))
    except (OSError, RuntimeError) as error:
        issue('.', 'audit_read_failed', detail=str(error))
    if not files:
        issue('.', 'no_native_binaries')
    return {'format': 'rieke-desktop-native-compatibility', 'version': 1,
            'bundle': str(root), 'target_macos': '14.0', 'supported_architectures': ['arm64'],
            'status': 'blocked' if problems else 'no_known_static_blockers',
            'runtime_compatibility_verified': False, 'production_ready': False,
            'scope': 'entire supplied bundle, all regular Mach-O files',
            'entries_examined': visited, 'native_binaries': len(files), 'native_bytes_hashed': hashed,
            'limits': {'max_files': max_files, 'max_native_bytes': max_native_bytes, 'timeout_seconds': timeout},
            'files': sorted(files, key=lambda item: item['path']),
            'symlinks': sorted(links, key=lambda item: item['path']), 'problems': problems,
            'not_validated': ['macOS 14 runtime behavior', 'other OS runtime behavior', 'Intel support',
                              'dynamic loader and symbol closure', 'signing and notarization',
                              'clean-machine installation', 'scientific workflows']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.bundle.resolve(strict=True)
    if args.output.resolve().is_relative_to(root):
        parser.error('Evidence must be written outside the audited bundle')
    report = audit_bundle(root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')
    print(json.dumps({'status': report['status'], 'native_binaries': report['native_binaries'],
                      'problems': len(report['problems']), 'output': str(args.output)}))
    return int(bool(report['problems']))


if __name__ == '__main__':
    raise SystemExit(main())
