"""Scoped frontend module import policy. Syntactic review aid, not a sandbox."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess

EXTENSIONS = {'.js', '.jsx', '.mjs', '.cjs'}
UNSUPPORTED = {'.ts', '.tsx', '.mts', '.cts', '.vue', '.svelte', '.coffee'}


def exact(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f'Invalid module policy fields; expected {sorted(fields)}')


def strings(value):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value) or len(set(value)) != len(value):
        raise ValueError('Module policy requires unique nonempty strings')
    return value


def path(root, name, directory=False):
    if not isinstance(name, str) or not name or '\\' in name or str(PurePosixPath(name)) != name or Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError(f'Invalid module policy path: {name}')
    lexical = root / name
    for part in [lexical, *lexical.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise ValueError(f'Module policy rejects symlink: {name}')
    target = lexical.resolve()
    if not target.is_relative_to(root) or not (target.is_dir() if directory else target.is_file()):
        raise ValueError(f'Missing or escaping module policy path: {name}')
    return target


def sources(root, policy):
    base = path(root, policy['source_root'], True)
    found = []
    def walk(directory):
        for entry in sorted(directory.iterdir()):
            if entry.is_symlink():
                raise ValueError(f'Module policy rejects symlink: {entry.relative_to(root)}')
            if entry.is_dir():
                walk(entry)
            elif entry.suffix in UNSUPPORTED or ('.test.' in entry.name and not entry.name.endswith('.test.js')):
                raise ValueError(f'Unsupported source/test suffix: {entry.relative_to(root)}')
            elif entry.suffix in EXTENSIONS:
                found.append(entry.relative_to(root).as_posix())
    walk(base)
    for name in strings(policy['additional_sources']):
        target = path(root, name)
        if target.is_relative_to(base) or target.suffix not in EXTENSIONS or name not in policy['test_tool_files']:
            raise ValueError(f'Additional source must be an outside executable test tool: {name}')
        found.append(name)
    return sorted(found)


def is_test(name, policy):
    return (name.endswith('.test.js') or name in policy['test_tool_files'] or
            any(name.startswith(prefix + '/') for prefix in policy['test_support_roots']))


def public_entries(module, version):
    """Normalize strict versioned records without changing catalog/receipt bytes."""
    if version == 2:
        exact(module, ['contract_id', 'root', 'public_entry', 'public_exports', 'private_test_edges'])
        entries = [{'path': module['public_entry'], 'exports': module['public_exports']}]
    elif version in (3, 4):
        exact(module, ['contract_id', 'root', 'public_entries', 'private_test_edges'])
        entries = module['public_entries']
        if not isinstance(entries, list) or not entries:
            raise ValueError('Public entries must be a nonempty list')
    else:
        raise ValueError('Unsupported JavaScript module policy version')
    seen = set()
    for entry in entries:
        exact(entry, ['path', 'exports'])
        if version in (3, 4):
            if not isinstance(entry['path'], str) or not entry['path']:
                raise ValueError('Public entry path must be a nonempty string')
            if entry['path'] in seen:
                raise ValueError('Duplicate public entry path')
            seen.add(entry['path'])
        if not strings(entry['exports']):
            raise ValueError('Public exports cannot be empty')
        if version in (3, 4) and '*' in entry['exports']:
            raise ValueError('Public exports cannot contain a star')
    return entries


def validate(root, catalog):
    policy = catalog.get('javascript_module_policy')
    if policy is None:
        return
    exact(policy, ['source_root', 'test_support_roots', 'test_tool_files', 'package_manifest', 'package_lock', 'resolver_config', 'dom_override_test_files', 'modules', 'additional_sources', 'tool_external_imports', 'virtual_import_edges'])
    strings(policy['additional_sources'])
    source_root = path(root, policy['source_root'], True)
    for prefix in strings(policy['test_support_roots']):
        if not path(root, prefix, True).is_relative_to(source_root):
            raise ValueError('Test support must be inside source root')
    for key in ('test_tool_files', 'dom_override_test_files'):
        for name in strings(policy[key]):
            target = path(root, name)
            permitted = target.is_relative_to(source_root) or (key == 'test_tool_files' and name in policy['additional_sources'])
            if not permitted or (key == 'dom_override_test_files' and not name.endswith('.test.js')):
                raise ValueError(f'Invalid test-only policy file: {name}')
    exact(policy['resolver_config'], ['path', 'sha256'])
    config = path(root, policy['resolver_config']['path'])
    if hashlib.sha256(config.read_bytes()).hexdigest() != policy['resolver_config']['sha256']:
        raise ValueError('Resolver config changed; module policy review required')
    manifest_path = path(root, policy['package_manifest'])
    path(root, policy['package_lock'])
    frontend = manifest_path.parent
    # Config additions must not introduce unreviewed aliases. Skip generated and
    # installed dependencies; inspect owned source/config directories recursively.
    def configs(directory):
        for entry in directory.iterdir():
            if entry.name in ('node_modules', 'dist', '.git'):
                continue
            if entry.is_symlink():
                if entry.name.startswith(('vite.config.', 'jsconfig', 'tsconfig')):
                    raise ValueError(f'Unreviewed resolver config symlink: {entry.relative_to(root)}')
                continue  # source symlinks independently fail in sources()
            if entry.is_dir():
                configs(entry)
            elif ((entry.name.startswith('vite.config.') and entry != config) or
                  (entry.name.endswith('.json') and entry.name.startswith(('jsconfig', 'tsconfig')))):
                raise ValueError(f'Unreviewed resolver config: {entry.relative_to(root)}')
    configs(frontend)
    manifest = json.loads(manifest_path.read_text())
    if 'imports' in manifest:
        raise ValueError('Package imports mappings require resolver review')
    for section in ('dependencies', 'devDependencies'):
        for package, version in manifest.get(section, {}).items():
            if not isinstance(version, str) or version.startswith(('file:', 'link:', 'workspace:', 'npm:', '.', '/', 'git', 'http')):
                raise ValueError(f'Unreviewed dependency mapping: {package}')
    if not isinstance(policy['modules'], list) or not policy['modules']:
        raise ValueError('Module policy requires modules')
    roots, ids = [], set()
    contracts = {entry['id']: entry for entry in catalog['contracts']}
    available = sources(root, policy)
    lock = json.loads((root/policy['package_lock']).read_text())
    if not isinstance(policy['tool_external_imports'], list) or not isinstance(policy['virtual_import_edges'], list):
        raise ValueError('Resolver exceptions must be lists')
    seen_tools, seen_virtual = set(), set()
    for edge in policy['tool_external_imports']:
        exact(edge, ['from', 'specifier', 'lock_package'])
        pair = (edge['from'], edge['specifier'])
        if pair in seen_tools or edge['from'] not in policy['additional_sources']:
            raise ValueError('Duplicate or invalid tool external import')
        seen_tools.add(pair)
        package = '/'.join(edge['specifier'].split('/')[:2]) if edge['specifier'].startswith('@') else edge['specifier'].split('/')[0]
        entry = lock.get('packages', {}).get(edge['lock_package'], {})
        if (edge['lock_package'] != 'node_modules/' + package or not entry.get('version') or
                not entry.get('integrity') or not entry.get('resolved', '').startswith('https://registry.npmjs.org/') or entry.get('link')):
            raise ValueError('Tool external import needs a pinned registry package')
    for edge in policy['virtual_import_edges']:
        exact(edge, ['from', 'specifier', 'to', 'resolver_path', 'resolver_sha256'])
        pair = (edge['from'], edge['specifier'])
        if pair in seen_virtual:
            raise ValueError('Duplicate virtual import mapping')
        seen_virtual.add(pair)
        for name in (edge['from'], edge['resolver_path']):
            path(root, name)
            if name not in available or not any(name.startswith(prefix + '/') for prefix in policy['test_support_roots']):
                raise ValueError('Virtual import and resolver must be scanned test support')
        target = path(root, edge['to'])
        if edge['to'] not in available and target.suffix != '.css':
            raise ValueError('Virtual target must be scanned source or CSS')
        if hashlib.sha256((root/edge['resolver_path']).read_bytes()).hexdigest() != edge['resolver_sha256']:
            raise ValueError('Virtual resolver hash changed; review required')
    for module in policy['modules']:
        entries = public_entries(module, catalog['version'])
        if module['contract_id'] not in contracts or module['contract_id'] in ids:
            raise ValueError('Module contract must exist and be unique')
        ids.add(module['contract_id'])
        module_root = path(root, module['root'], True)
        if not module_root.is_relative_to(source_root) or any(module_root.is_relative_to(r) or r.is_relative_to(module_root) for r in roots):
            raise ValueError('Module roots must be disjoint source descendants')
        roots.append(module_root)
        for entry in entries:
            if not path(root, entry['path']).is_relative_to(module_root) or is_test(entry['path'], policy):
                raise ValueError('Public entry must be module production source')
            # V2 keeps its historical path validation; V3 entries must also be
            # parsed executable sources, never CSS or another unscanned asset.
            if catalog['version'] in (3, 4) and entry['path'] not in available:
                raise ValueError('Public entry must be scanned executable production source')
        entry_paths = {entry['path'] for entry in entries}
        rules = {rule['file']: rule for rule in contracts[module['contract_id']]['rules'] if rule['language'] == 'javascript'}
        for name in available:
            if name.startswith(module['root'] + '/') and not is_test(name, policy):
                if name not in rules or 'allow' not in rules[name]:
                    raise ValueError(f'New module production source needs an ownership allow rule: {name}')
        if not isinstance(module['private_test_edges'], list):
            raise ValueError('Private test edges must be a list')
        seen = set()
        for edge in module['private_test_edges']:
            exact(edge, ['from', 'to'])
            pair = (edge['from'], edge['to'])
            if pair in seen:
                raise ValueError('Duplicate private test edge')
            seen.add(pair)
            for name in pair:
                if not path(root, name).is_relative_to(module_root):
                    raise ValueError('Private test edge must stay in its module')
            if not edge['from'].endswith('.test.js') or edge['to'] in entry_paths or is_test(edge['to'], policy):
                raise ValueError('Private test edge must run from colocated test to private production')


def inputs(root, catalog):
    policy = catalog.get('javascript_module_policy')
    if not policy:
        return []
    names = sources(root, policy) + [policy['package_manifest'], policy['package_lock'], policy['resolver_config']['path'],
                                   'tools/architecture_module_policy.py', 'workspace-app/runTests.mjs']
    names += [edge['to'] for edge in policy['virtual_import_edges']]
    return sorted(set(names))


def check(root, catalog, node):
    policy = catalog.get('javascript_module_policy')
    if not policy:
        return
    if 'RIEKE_TEST_DOM_MODULE' in os.environ:
        raise ValueError('RIEKE_TEST_DOM_MODULE must be unset for frontend test evidence')
    names = sources(root, policy)
    payload = [{'filename': name, 'source': (root/name).read_text(), 'allowDomOverride': name in policy['dom_override_test_files']} for name in names]
    run = subprocess.run([node, str(root/'workspace-app/architectureImports.mjs')], input=json.dumps(payload), text=True, capture_output=True, timeout=30)
    if run.returncode:
        raise ValueError(f'JavaScript ownership parser unavailable or failed: {run.stderr.strip()}')
    parsed = json.loads(run.stdout)
    manifest = json.loads((root/policy['package_manifest']).read_text())
    packages = set(manifest.get('dependencies', {})) | set(manifest.get('devDependencies', {}))
    used, used_tools, used_virtual = set(), set(), set()
    def resolve(importer, specifier, builtins):
        pair = (importer, specifier)
        virtual = next((edge for edge in policy['virtual_import_edges'] if (edge['from'], edge['specifier']) == pair), None)
        if virtual:
            used_virtual.add(pair)
            return virtual['to']
        if specifier.startswith('/') or '\\' in specifier or '?' in specifier or '#' in specifier or (':' in specifier and not specifier.startswith('node:')):
            raise ValueError(f'{importer}: unreviewed absolute/URL/alias/suffix dependency: {specifier}')
        if not specifier.startswith('.'):
            if any((edge['from'], edge['specifier']) == pair for edge in policy['tool_external_imports']):
                used_tools.add(pair)
                return None
            package = '/'.join(specifier.split('/')[:2]) if specifier.startswith('@') else specifier.split('/')[0]
            if specifier in builtins or specifier.removeprefix('node:') in builtins or package in packages:
                return None
            raise ValueError(f'{importer}: undeclared package or alias: {specifier}')
        target = (root/importer).parent/specifier
        if not target.is_file():
            candidates = [p for p in [Path(str(target)+'.js'), Path(str(target)+'.jsx'), target/'index.js'] if p.is_file()]
            if len(candidates) != 1:
                raise ValueError(f'{importer}: unresolved or ambiguous dependency: {specifier}')
            target = candidates[0]
        # Check lexical symlinks before normalization can erase them.
        for part in [target, *target.parents]:
            if part == root:
                break
            if part.is_symlink():
                raise ValueError(f'{importer}: symlink dependency: {specifier}')
        target = target.resolve()
        if not target.is_relative_to(root):
            raise ValueError(f'{importer}: escaping dependency: {specifier}')
        if target.suffix not in EXTENSIONS | {'.css'}:
            raise ValueError(f'{importer}: unsupported dependency type: {specifier}')
        identity = target.relative_to(root).as_posix()
        if target.suffix in EXTENSIONS and identity not in names:
            raise ValueError(f'{importer}: executable dependency outside scanned sources: {specifier}')
        return identity
    modules = [(module, {entry['path']: entry['exports'] for entry in public_entries(module, catalog['version'])})
               for module in policy['modules']]
    for item in parsed:
        importer = item['filename']
        for module, entries in modules:
            if importer in entries and (item['hasReexports'] or sorted(item['exports']) != sorted(entries[importer])):
                raise ValueError(f'{importer}: public export surface changed')
        for specifier in item['dependencies']:
            target = resolve(importer, specifier, set(item['builtins']))
            if target is None:
                continue
            if not is_test(importer, policy) and is_test(target, policy):
                raise ValueError(f'{importer}: production cannot import test source {target}')
            for module, entries in modules:
                if not target.startswith(module['root'] + '/') or target in entries:
                    continue
                if not is_test(importer, policy) and importer.startswith(module['root'] + '/'):
                    continue  # all module production has a separately checked allow rule
                edge = {'from': importer, 'to': target}
                if edge in module['private_test_edges']:
                    used.add((importer, target))
                else:
                    raise ValueError(f'{importer}: forbidden private module dependency {target}')
    expected = {(edge['from'], edge['to']) for module in policy['modules'] for edge in module['private_test_edges']}
    if expected != used:
        raise ValueError(f'Unused private test exception: {sorted(expected-used)}')
    for label, edges, actual in [('tool external', policy['tool_external_imports'], used_tools), ('virtual', policy['virtual_import_edges'], used_virtual)]:
        expected = {(edge['from'], edge['specifier']) for edge in edges}
        if expected != actual:
            raise ValueError(f'Unused {label} import mapping: {sorted(expected-actual)}')
