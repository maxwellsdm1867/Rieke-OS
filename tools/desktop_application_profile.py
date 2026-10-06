"""Reviewed Disco application closure, separate from EpicTreeGUI source.

Only application resources are constrained here. Third-party parser/scientific
libraries retain their pinned content, including any MATLAB support they use.
"""
from __future__ import annotations
import ast
import argparse
import fnmatch
import json
import hashlib
import re
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'desktop/application-profile.json'


def validate_profile(value):
    """v1 stays flat; v2 admits explicit regular-package files, never tree copies."""
    if (not isinstance(value, dict) or value.get('format') != 'rieke-application-profile'
            or type(value.get('version')) is not int or value['version'] not in (1, 2)):
        raise ValueError('Unrecognized Disco application profile')
    names = value.get('python_modules')
    if (not isinstance(names, list) or not names or
            any(not isinstance(name, str) or not name for name in names) or
            len(names) != len(set(names))):
        raise ValueError('Application profile requires explicit unique Python filenames')
    if value['version'] == 2:
        for item in value.get('source_exclusions', []):
            pattern = item.get('pattern') if isinstance(item, dict) else None
            if not isinstance(pattern, str) or any(c in pattern for c in '[]\\'):
                raise ValueError('Unsupported source exclusion pattern')
    identities, folded = set(), set()
    for name in names:
        parts = name.split('/')
        if (any(part in ('', '.', '..') for part in parts) or
                any(char in name for char in ('\\', '\x00', ':')) or
                not name.endswith('.py') or
                (value['version'] == 1 and len(parts) != 1)):
            raise ValueError('Unsafe application Python path: ' + repr(name))
        if value['version'] == 2:
            # Deliberately portable ASCII identifiers; same grammar in JS reader.
            if any(not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', part)
                   for part in [*parts[:-1], parts[-1][:-3]]):
                raise ValueError('Invalid application module identifier: ' + name)
            if name == '__init__.py':
                raise ValueError('Python source root is not an application package')
            if 'tests' in parts or parts[-1].startswith('test_'):
                raise ValueError('Test source in application profile: ' + name)
            if name.casefold() in folded:
                raise ValueError('Case-colliding application paths: ' + name)
            folded.add(name.casefold())
            identity = module_name(name)
            if identity in identities:
                raise ValueError('Ambiguous application module identity: ' + name)
            identities.add(identity)
            source_name = 'python/' + name
            if (source_name in value.get('source_excluded_paths', []) or
                    any(fnmatch.fnmatchcase(source_name, item['pattern'])
                        for item in value.get('source_exclusions', [])) or
                    any(source_name == item['path'] for item in value.get('runtime_only_exclusions', []))):
                raise ValueError('Excluded application source: ' + name)
    if value['version'] == 2:
        for name in names:
            parts = name.split('/')
            for end in range(1, len(parts)):
                parent = '/'.join(parts[:end]) + '/__init__.py'
                if parent not in names:
                    raise ValueError('Missing application package initializer: ' + parent)
    return value


def module_name(name):
    parts = name[:-3].split('/')
    if parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


def regular_path(base, name, *, missing=False):
    """Reject redirected ancestors before resolving; base is the owned boundary."""
    base = Path(base)
    target = base
    if base.is_symlink():
        raise ValueError('Missing or redirected application path: ' + str(base))
    for part in Path(name).parts:
        if target.exists() and not target.is_dir():
            raise ValueError('Non-directory application parent: ' + str(target))
        target = target / part
        if target.is_symlink():
            raise ValueError('Missing or redirected application path: ' + str(target))
    if not target.resolve().is_relative_to(base.resolve()):
        raise ValueError('Escaping application path: ' + name)
    if target.exists() and not target.is_file():
        raise ValueError('Non-file application path: ' + name)
    if not missing and not target.is_file():
        raise ValueError('Missing or redirected application module: ' + name)
    return target


def load_profile(path=PROFILE):
    path = Path(path)
    regular_path(path.parent, path.name)
    return validate_profile(json.loads(path.read_text()))


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


# Existing external parser/probe boundaries. Changing either file requires review
# and an explicit rebind. This is static local closure, not external loader proof.
EXTERNAL_LOADER_SOURCES = {'recording_workspace.py': '92181e6cee8b4d3b50cd535a152d5dc3b584f2ec5734f090ee2e2a94f23a47e1', 'workspace_bootstrap.py': 'cdf014e61d3754eac6ce700a3054c849b77af3f5dec55ca4a23be1f66f7d499a'}


def validate_source_closure(root, profile):
    """Check static local imports without executing application or parser code.

    Return the named unchanged external boundaries separately from local proof.
    Recognized new computed/file-loader calls fail; arbitrary reflection is not
    proved by this syntactic checker. No loader or subprocess is executed here.
    """
    validate_profile(profile)
    source = Path(root) / 'python'
    allowed = set(profile['python_modules'])
    files = {name: regular_path(source, name) for name in allowed}
    local = {}
    for path in source.rglob('*.py'):
        name = path.relative_to(source).as_posix()
        identity = module_name(name)
        if identity in local:
            raise ValueError('Ambiguous local module identity: ' + identity)
        local[identity] = name
    for item in profile.get('source_exclusions', []):
        name = item['pattern']
        if name.startswith('python/') and name.endswith('.py') and not any(c in name for c in '*?['):
            local.setdefault(module_name(name[7:]), name[7:])
    roots = {name.split('.')[0] for name in local if name}
    roots.update(path.name for path in source.iterdir() if path.is_dir() and path.name.isidentifier() and path.name != '__pycache__')
    boundaries = []

    def require(identity, importer):
        if identity.split('.')[0] not in roots:
            return  # external library, not a local application-closure claim
        pieces = identity.split('.')
        for end in range(1, len(pieces) + 1):
            part = '.'.join(pieces[:end])
            path = local.get(part)
            if path not in allowed:
                raise ValueError(f'Application import closure excludes {part} required by {importer}')
            regular_path(source, path)

    def relative(module, level, package):
        parts = package.split('.') if package else []
        if level > len(parts):
            raise ValueError('Relative application import escapes package: ' + module)
        return '.'.join(parts[:len(parts) - level + 1] + ([module] if module else []))

    parsed = {}

    def bindings(identity):
        path = local.get(identity)
        if path not in allowed:
            return []
        if identity not in parsed:
            parsed[identity] = ast.parse(files[path].read_text(), filename=path)
        pending, result = list(parsed[identity].body), []
        while pending:
            node = pending.pop()
            result.append(node)
            # Comprehension targets and lambda-local assignments do not
            # establish module attributes (nor do function/class locals).
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                     ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                pending.extend(ast.iter_child_nodes(node))
        return result

    def exported(identity, symbol, seen=frozenset()):
        """Resolve declared bindings, never use an import to justify itself."""
        if (identity, symbol) in seen:
            return False
        if identity.split('.')[0] not in roots:
            return True  # external exports are outside static local proof
        seen = seen | {(identity, symbol)}
        path = local.get(identity, '')
        package = identity if path.endswith('/__init__.py') else identity.rpartition('.')[0]
        for node in bindings(identity):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol:
                return True
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == symbol:
                return True
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if (alias.asname or alias.name.split('.')[0]) == symbol:
                        # The import's own closure is independently checked.
                        return alias.name.split('.')[0] not in roots or local.get(alias.name) in allowed
            elif isinstance(node, ast.ImportFrom):
                target = relative(node.module or '', node.level, package) if node.level else node.module or ''
                for alias in node.names:
                    if (alias.asname or alias.name) != symbol:
                        continue
                    child = target + '.' + alias.name
                    if child in local:
                        if local[child] in allowed:
                            return True
                    elif exported(target, alias.name, seen):
                        return True
        return False

    def package_attributes(identity):
        path = local.get(identity, '')
        if not path.endswith('/__init__.py') or path not in allowed:
            return None
        candidates = set()
        for node in bindings(identity):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                candidates.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                candidates.add(node.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                candidates.update(alias.asname or alias.name.split('.')[0] for alias in node.names)
        return {name for name in candidates if exported(identity, name)}

    for name, path in sorted(files.items()):
        text = path.read_text()
        tree = ast.parse(text, filename=name)
        identity = module_name(name)
        package = identity if name.endswith('/__init__.py') else identity.rpartition('.')[0]
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    aliases[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                for alias in node.names:
                    aliases[alias.asname or alias.name] = (node.module or '') + '.' + alias.name

        def qualified(node):
            if isinstance(node, ast.Name):
                return aliases.get(node.id, node.id)
            if isinstance(node, ast.Attribute):
                return qualified(node.value) + '.' + node.attr
            return ''

        # Follow simple loader aliases, including assignment chains, without
        # attempting general value-flow or executing a loader.
        for _ in range(len(list(ast.walk(tree)))):
            changed = False
            for assignment in ast.walk(tree):
                if isinstance(assignment, ast.Assign):
                    binding = qualified(assignment.value)
                    if binding.rsplit('.', 1)[-1] in ('__import__', 'import_module', 'spec_from_file_location', 'exec_module', 'run_module', 'run_path', 'SourceFileLoader', 'SourcelessFileLoader', 'exec', 'eval'):
                        for target in assignment.targets:
                            if isinstance(target, ast.Name) and aliases.get(target.id) != binding:
                                aliases[target.id] = binding
                                changed = True
            if not changed:
                break

        external = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    require(alias.name, name)
            elif isinstance(node, ast.ImportFrom):
                target = relative(node.module or '', node.level, package) if node.level else node.module or ''
                require(target, name)
                attrs = package_attributes(target)
                for alias in node.names:
                    child = target + '.' + alias.name
                    if child in local:
                        require(child, name)
                    elif attrs is not None and alias.name not in attrs:
                        raise ValueError(f'Unresolved application package export {child} required by {name}')
            elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PROBE' for t in node.targets) and name == 'workspace_bootstrap.py':
                external.append('embedded PROBE subprocess source')
            elif isinstance(node, ast.Call):
                fn = qualified(node.func)
                leaf = fn.rsplit('.', 1)[-1]
                if leaf in ('__import__', 'import_module'):
                    if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                        raise ValueError('Unclassified dynamic application import: ' + name)
                    target = node.args[0].value
                    if target.startswith('.'):
                        argument = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == 'package'), None)
                        if leaf != 'import_module' or not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
                            raise ValueError('Unresolved relative dynamic application import: ' + name)
                        level = len(target) - len(target.lstrip('.'))
                        target = relative(target[level:], level, argument.value)
                    require(target, name)
                    if leaf == '__import__':
                        level = node.args[4] if len(node.args) > 4 else next((k.value for k in node.keywords if k.arg == 'level'), ast.Constant(0))
                        if not isinstance(level, ast.Constant) or level.value != 0:
                            raise ValueError('Unsupported dynamic import level: ' + name)
                        fromlist = node.args[3] if len(node.args) > 3 else next((k.value for k in node.keywords if k.arg == 'fromlist'), ast.Tuple(elts=[]))
                        if not isinstance(fromlist, (ast.List, ast.Tuple)) or any(not isinstance(x, ast.Constant) or not isinstance(x.value, str) for x in fromlist.elts):
                            raise ValueError('Unresolved dynamic import fromlist: ' + name)
                        for item in fromlist.elts:
                            child = target + '.' + item.value
                            attrs = package_attributes(target)
                            if child in local:
                                require(child, name)
                            elif attrs is not None and item.value not in attrs:
                                raise ValueError('Unresolved application package export: ' + child)
                elif leaf in ('spec_from_file_location', 'exec_module', 'SourceFileLoader', 'SourcelessFileLoader', 'run_module', 'run_path', 'exec', 'eval'):
                    external.append(leaf)
        if external or name in EXTERNAL_LOADER_SOURCES:
            if (hashlib.sha256(path.read_bytes()).hexdigest() != EXTERNAL_LOADER_SOURCES.get(name) or
                    external != ({'recording_workspace.py': ['spec_from_file_location', 'exec_module'],
                                  'workspace_bootstrap.py': ['embedded PROBE subprocess source']}.get(name))):
                raise ValueError('Unclassified external application loader: ' + name)
            boundaries.append({'file': name, 'sha256': EXTERNAL_LOADER_SOURCES[name], 'sites': external})
    return {'static_local_closure': 'verified', 'external_loader_boundaries': boundaries,
            'limit': 'Resolved static/literal imports and recognized loader calls only; no arbitrary reflection or external execution proof.'}


def copy_python_application(root, application, profile_path=PROFILE):
    profile = load_profile(profile_path)
    validate_source_closure(root, profile)
    destination = Path(application) / 'python'
    # Preflight the entire destination before writing any file.
    regular_path(Path(application), 'python/.profile-preflight', missing=True)
    regular_path(Path(application), 'application-profile.json', missing=True)
    for name in profile['python_modules']:
        regular_path(destination, name, missing=True)
    destination.mkdir(parents=True, exist_ok=True)
    for name in profile['python_modules']:
        target = regular_path(destination, name, missing=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(root) / 'python' / name, target)
    shutil.copy2(profile_path, Path(application) / 'application-profile.json')
    return profile


def audit_application(application, expected_profile=None):
    application = Path(application)
    regular_path(application, 'application-profile.json')
    profile = load_profile(application / 'application-profile.json')
    for name in profile['python_modules']:
        regular_path(application, 'python/' + name)
    if expected_profile is not None and profile != expected_profile:
        raise ValueError('Packaged application profile differs from reviewed profile')
    # rglob does not follow directory symlinks; reject those explicitly so an
    # unlisted redirected subtree cannot disappear from the exact inventory.
    for path in (application / 'python').rglob('*'):
        if path.is_symlink():
            raise ValueError('Missing or redirected application path: ' + str(path))
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
