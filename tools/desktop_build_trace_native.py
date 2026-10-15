#!/usr/bin/env python3
"""Build the bounded trace inflater at package time, never during app launch."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = 'libdisco_trace_inflate.dylib'


def build_trace_native(output: Path, root: Path = ROOT) -> dict:
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise ValueError('Desktop trace inflater requires a macOS arm64 build host')
    root = Path(root).resolve(strict=True)
    source = root / 'desktop/native/trace_inflate.c'
    if (any(path.is_symlink() for path in (source, source.parent, source.parent.parent))
            or not source.is_file()):
        raise ValueError('Missing or redirected trace inflater source')
    output = Path(output).absolute()
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError('Trace inflater output must not traverse symbolic links')
    output.mkdir(parents=True, exist_ok=True)
    target = output / LIBRARY
    if target.is_symlink():
        raise ValueError('Trace inflater output cannot be a symbolic link')
    compiler = subprocess.check_output(['/usr/bin/xcrun', '--find', 'clang'], text=True).strip()
    sdk = subprocess.check_output(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()
    version = subprocess.check_output([compiler, '--version'], text=True).strip()
    options = ['-O3', '-std=c11', '-Wall', '-Wextra', '-Werror', '-dynamiclib',
               '-arch', 'arm64', '-isysroot', sdk, '-mmacosx-version-min=14.0',
               '-Wl,-install_name,@rpath/' + LIBRARY, '-pthread']
    with tempfile.TemporaryDirectory(prefix='trace-native-', dir=output) as temporary:
        built = Path(temporary) / LIBRARY
        subprocess.run([compiler, *options, str(source), '-lz', '-o', str(built)], check=True)
        subprocess.run(['/usr/bin/codesign', '--force', '--sign', '-', str(built)],
                       check=True, capture_output=True)
        library = ctypes.CDLL(str(built))
        library.disco_trace_inflate_abi.argtypes = []
        library.disco_trace_inflate_abi.restype = ctypes.c_uint
        if library.disco_trace_inflate_abi() != 3:
            raise ValueError('Unexpected native trace inflater ABI')
        built.replace(target)
    receipt = {
        'abi': 3, 'library': LIBRARY,
        'source': 'desktop/native/trace_inflate.c',
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
        'compiler': version, 'options': options, 'system_libraries': ['zlib', 'pthread'],
        'target': 'macOS 14.0 arm64',
    }
    (output / 'trace-inflate-build.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_trace_native(args.output), indent=2))
