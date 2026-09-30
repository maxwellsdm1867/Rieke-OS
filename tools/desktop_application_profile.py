"""Reviewed Disco application closure, separate from EpicTreeGUI source.

Only application resources are constrained here. Third-party parser/scientific
libraries retain their pinned content, including any MATLAB support they use.
"""
from __future__ import annotations
import ast
import argparse
import fnmatch
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'desktop/application-profile.json'


def load_profile(path=PROFILE):
    value = json.loads(Path(path).read_text())
    if value.get('format') != 'rieke-application-profile' or value.get('version') != 1:
        raise ValueError('Unrecognized Disco application profile')
    names = value.get('python_modules', [])
    if not names or len(names) != len(set(names)) or any(
            Path(name).name != name or not name.endswith('.py') for name in names):
        raise ValueError('Application profile requires explicit unique Python filenames')
    return value


def validate_release_source(root, trackedpaths):
    """Reject a mixed EpicTreeGUI/Disco tracked release source tree.

    This read-only guard checks the supplied Git inventory against the profile
    in that source tree. Canonical repository/commit identity is a separate
    release-builder check; passing this guard alone does not establish it.
    """
    root = Path(root).resolve(strict=True)
    profile = load_profile(root / 'desktop/application-profile.json')
    if isinstance(trackedpaths, (str, bytes)):
        raise ValueError('Release source requires a tracked path inventory')
    paths = set()
    for value in trackedpaths:
        name = str(value)
        path = Path(name)
        if (path.is_absolute() or '..' in path.parts or '\\' in name or
                '\x00' in name or name != path.as_posix() or name in ('', '.')):
            raise ValueError('Unsafe tracked release source path: ' + repr(name))
        paths.add(name)
    if 'desktop/application-profile.json' not in paths:
        raise ValueError('Reviewed application profile is absent from tracked release source')
    patterns = [item['pattern'] for item in profile['source_exclusions']]
    exact = set(profile.get('source_excluded_paths', []))
    rejected = sorted(name for name in paths if name in exact or
                      any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns))
    if rejected:
        raise ValueError('Mixed EpicTreeGUI/Disco release source contains excluded paths: ' +
                         ', '.join(rejected))
    return {'format': profile['format'], 'version': profile['version'],
            'tracked_paths_checked': len(paths), 'excluded_source_paths': []}


def validate_source_closure(root, profile):
    """Reject missing, redirected, or excluded local imports before copying."""
    source = Path(root) / 'python'
    allowed = set(profile['python_modules'])
    local = {path.stem for path in source.glob('*.py')}
    # Excluded module names stay known after canonical source removal.
    local.update(Path(item['pattern']).stem for item in profile['source_exclusions']
                 if item['pattern'].startswith('python/') and '*' not in item['pattern'])
    for name in sorted(allowed):
        path = source / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source.resolve()):
            raise ValueError('Missing or redirected application module: ' + name)
        for node in ast.walk(ast.parse(path.read_text(), filename=name)):
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name.split('.')[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports = [node.module.split('.')[0]]
            elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
                fn = node.func
                if ((isinstance(fn, ast.Name) and fn.id == '__import__') or
                    (isinstance(fn, ast.Attribute) and fn.attr == 'import_module')):
                    if isinstance(node.args[0].value, str):
                        imports = [node.args[0].value.split('.')[0]]
            for dependency in imports:
                if dependency in local and dependency + '.py' not in allowed:
                    raise ValueError(f'Application import closure excludes {dependency} required by {name}')


def copy_python_application(root, application, profile_path=PROFILE):
    profile = load_profile(profile_path)
    validate_source_closure(root, profile)
    destination = Path(application) / 'python'
    destination.mkdir(parents=True, exist_ok=True)
    for name in profile['python_modules']:
        shutil.copy2(Path(root) / 'python' / name, destination / name)
    shutil.copy2(profile_path, Path(application) / 'application-profile.json')
    return profile


def audit_application(application, expected_profile=None):
    application = Path(application)
    profile = load_profile(application / 'application-profile.json')
    if expected_profile is not None and profile != expected_profile:
        raise ValueError('Packaged application profile differs from reviewed profile')
    actual = {path.relative_to(application / 'python').as_posix()
              for path in (application / 'python').rglob('*.py')}
    if actual != set(profile['python_modules']):
        raise ValueError('Packaged Python modules differ from application allowlist')
    unexpected = [path.relative_to(application).as_posix() for path in application.rglob('*')
                  if (path.suffix.lower() == '.m' or
                      path.relative_to(application).parts[0] in ('src', 'examples', 'tests') or
                      path.name in ('epicTreeGUI.m', 'install.m', 'launch_epictree.m'))]
    if unexpected:
        raise ValueError('EpicTreeGUI/MATLAB interactive resources entered Disco: ' + ', '.join(unexpected))
    return {'python_modules': len(actual), 'mat_data_export': profile['capabilities']['mat_data_export'],
            'matlab_gui_resources': [], 'source_exclusions': profile['source_exclusions']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    tracked = subprocess.check_output(['git', '-C', str(args.root), 'ls-files', '-z']).decode().split('\0')
    print(json.dumps(validate_release_source(args.root, filter(None, tracked)), indent=2))
