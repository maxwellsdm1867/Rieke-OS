#!/usr/bin/env python3
"""Check only adopted slice references, direct dependencies and mapped behavior tests.

This is a review aid, not a security sandbox, semantic proof or release receipt.
The catalog indexes existing contracts; it does not define their behavior.
"""
import argparse
import ast
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

CATALOG = 'docs/architecture/adopted-port-checks.json'
LANGUAGES = ('python', 'javascript')
RUNNERS = (*LANGUAGES, 'desktop')


def contained(root, name, *, exists=True):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError(f'Expected repository-relative path: {name!r}')
    target = (root / name).resolve()
    if not target.is_relative_to(root) or '..' in Path(name).parts:
        raise ValueError(f'Path escapes repository: {name}')
    if exists and not target.is_file():
        raise ValueError(f'Missing referenced file: {name}')
    return target


def string_list(value, label):
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f'{label} must be a list of nonempty strings')
    return value


def keys(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError(f'Invalid catalog fields; expected {sorted(required)}, optional {sorted(optional)}')


def catalog(root):
    value = json.loads(contained(root, CATALOG).read_text())
    keys(value, ('format', 'version', 'discovery', 'shared_paths', 'contracts'))
    if value['format'] != 'disco-adopted-port-checks' or value['version'] != 1:
        raise ValueError('Unsupported adopted-port catalog format/version')
    for pattern in string_list(value['shared_paths'], 'shared_paths'):
        contained(root, pattern, exists=False)
    if not isinstance(value['discovery'], list) or not value['discovery']:
        raise ValueError('Discovery links are required')
    for link in value['discovery']:
        keys(link, ('from', 'to'))
        source, target = (contained(root, link[key]) for key in ('from', 'to'))
        # Only owned, inline local Markdown references are accepted here.
        links = re.findall(r'\[[^\]\n]+\]\(([^)\s]+)\)', source.read_text())
        if not any((source.parent / ref.split('#', 1)[0]).resolve() == target for ref in links):
            raise ValueError(f'Missing discovery link: {link["from"]} -> {link["to"]}')
    if not isinstance(value['contracts'], list) or not value['contracts']:
        raise ValueError('At least one adopted contract is required')
    ids = set()
    for entry in value['contracts']:
        keys(entry, ('id', 'contract', 'affected_paths', 'rules', 'tests'))
        if not isinstance(entry['id'], str) or not entry['id'] or entry['id'] in ids:
            raise ValueError('Contract IDs must be unique nonempty strings')
        ids.add(entry['id'])
        keys(entry['contract'], ('path', 'heading'))
        doc = contained(root, entry['contract']['path'])
        headings = re.findall(r'^#{1,6} +(.+?)\s*#*$', doc.read_text(), re.MULTILINE)
        if entry['contract']['heading'] not in headings:
            raise ValueError(f'Missing contract heading: {entry["contract"]}')
        for pattern in string_list(entry['affected_paths'], 'affected_paths'):
            contained(root, pattern, exists=False)
        keys(entry['tests'], LANGUAGES, ('desktop',))
        for language in RUNNERS:
            for path in string_list(entry['tests'].get(language, []), 'test paths'):
                contained(root, path)
                if language == 'python' and not (path.startswith('python/tests/') and path.endswith('.py')):
                    raise ValueError(f'Invalid Python test path: {path}')
                if language == 'javascript' and not (path.startswith('workspace-app/src/') and path.endswith('.test.js')):
                    raise ValueError(f'Invalid JavaScript test path: {path}')
                if language == 'desktop' and not (path.startswith('desktop/tests/') and path.endswith('.test.cjs')):
                    raise ValueError(f'Invalid desktop test path: {path}')
        if not any(entry['tests'].values()):
            raise ValueError(f'Contract has no conformance tests: {entry["id"]}')
        if not isinstance(entry['rules'], list) or not entry['rules']:
            raise ValueError(f'Contract has no ownership rules: {entry["id"]}')
        for rule in entry['rules']:
            keys(rule, ('language', 'file'), ('allow', 'deny', 'require'))
            if rule['language'] not in LANGUAGES or ('allow' in rule) == ('deny' in rule):
                raise ValueError('Ownership rule needs a known language and exactly one allow/deny policy')
            contained(root, rule['file'])
            for kind in ('allow', 'deny', 'require'):
                for dependency in string_list(rule.get(kind, []), kind):
                    if rule['language'] == 'javascript' and dependency.startswith(('workspace-app/', 'desktop/')):
                        contained(root, dependency)
    return value


def python_dependencies(source, filename):
    tree = ast.parse(source, filename=filename)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise ValueError(f'{filename}: relative Python imports require a reviewed ownership rule')
            found.append(node.module or '')
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
            if name in ('__import__', 'import_module'):
                raise ValueError(f'{filename}: dynamic Python loading is not statically checkable')
    return found


def validate_dependencies(entry, rule, dependencies):
    # Python allows submodules of an approved package. JavaScript uses resolved
    # file identities; changing spelling or importing through ../ cannot evade it.
    def matches(dependency, candidate):
        return dependency == candidate or (rule['language'] == 'python' and dependency.startswith(candidate + '.'))
    for dependency in dependencies:
        denied = any(matches(dependency, item) for item in rule.get('deny', []))
        unapproved = 'allow' in rule and not any(matches(dependency, item) for item in rule['allow'])
        if denied or unapproved:
            raise ValueError(f'{rule["file"]}: forbidden dependency {dependency}; contract {entry["id"]} at {entry["contract"]["path"]}')
    for required in rule.get('require', []):
        if required not in dependencies:
            raise ValueError(f'{rule["file"]}: missing required dependency {required}; contract {entry["id"]}')


def check_ownership(root, value, language, node):
    if language == 'desktop':
        language = 'javascript'
    checked = ['metadata']
    for selected in LANGUAGES:
        if language not in ('all', selected):
            continue
        for entry in value['contracts']:
            for rule in entry['rules']:
                if rule['language'] != selected:
                    continue
                source = contained(root, rule['file']).read_text()
                if selected == 'python':
                    dependencies = python_dependencies(source, rule['file'])
                else:
                    helper = contained(root, 'workspace-app/architectureImports.mjs')
                    run = subprocess.run([node, str(helper)], input=json.dumps([{'filename':rule['file'], 'source':source}]),
                                         capture_output=True, text=True, timeout=30)
                    if run.returncode:
                        raise ValueError(f'JavaScript ownership parser unavailable or failed: {run.stderr.strip()}')
                    parsed = json.loads(run.stdout)
                    dependencies = []
                    for specifier in parsed[0]['dependencies']:
                        if specifier.startswith('/') or (':' in specifier and not specifier.startswith('node:')):
                            raise ValueError(f'{rule["file"]}: Absolute or URL module specifier requires a reviewed root mapping: {specifier}')
                        if specifier.startswith('.'):
                            target = (root / rule['file']).parent / specifier
                            if not target.is_file():
                                target = next((candidate for candidate in [Path(str(target)+'.js'), Path(str(target)+'.jsx'), target/'index.js'] if candidate.is_file()), target)
                            target = target.resolve()
                            if not target.is_relative_to(root):
                                raise ValueError(f'{rule["file"]}: dependency escapes repository: {specifier}')
                            dependency = target.relative_to(root).as_posix()
                            contained(root, dependency)
                            dependencies.append(dependency)
                        else:
                            dependencies.append(specifier)
                validate_dependencies(entry, rule, dependencies)
        checked.append(selected)
    return checked


def git(root, *args):
    run = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
    if run.returncode:
        raise ValueError(run.stderr.strip() or 'Git ancestry check failed')
    return run.stdout


def revision(root, ref):
    return git(root, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}').strip()


def affected_plan(root, value, base, head, all_contracts):
    if (base is None) == (not all_contracts):
        raise ValueError('Choose exactly one explicit --base <ancestor> or --all; no automatic baseline')
    head_sha = revision(root, head)
    if head_sha != revision(root, 'HEAD'):
        raise ValueError('Requested head must equal checkout HEAD; tests and catalog read the checkout')
    dirty = bool(git(root, 'status', '--porcelain', '--untracked-files=normal').strip())
    if base is not None and dirty:
        raise ValueError('Committed comparison requires a clean checkout; --all is available as a labelled local diagnostic')
    base_sha = revision(root, base) if base is not None else None
    if base_sha:
        git(root, 'merge-base', '--is-ancestor', base_sha, head_sha)
        # No rename detection intentionally reports both deleted/added names,
        # including moves across watched roots; NUL preserves unusual filenames.
        paths = sorted(set(filter(None, git(root, 'diff', '--no-renames', '--name-only', '-z', base_sha, head_sha, '--').split('\0'))))
    else:
        paths = sorted(set(filter(None, git(root, 'ls-files', '-z').split('\0'))))
    shared = any(fnmatch.fnmatchcase(path, pattern) for path in paths for pattern in value['shared_paths'])
    selected = [entry for entry in value['contracts'] if all_contracts or shared or any(
        fnmatch.fnmatchcase(path, pattern) for path in paths for pattern in entry['affected_paths'])]
    tests = {language: sorted({path for entry in selected for path in entry['tests'].get(language, [])}) for language in RUNNERS}
    # Preserve workspace-ci's previous docs/** and **/*.md exclusion, while
    # reference/contract changes still receive their mapped conformance checks.
    source_changed = all_contracts or any(not path.startswith('docs/') and not path.endswith('.md') for path in paths)
    return {'base':base_sha, 'head':head_sha, 'dirty':dirty, 'selection':'all' if all_contracts else 'changed',
            'changed_paths':paths, 'affected_contracts':[entry['id'] for entry in selected],
            'tests':tests, 'source_changed':source_changed,
            'javascript_required':source_changed or bool(tests['javascript']),
            'python_required':source_changed or bool(tests['python']),
            'desktop_required':bool(tests['desktop'])}


def run_contracts(root, value, plan, language, node):
    if language not in RUNNERS:
        raise ValueError('Mapped tests require an explicit --language python, javascript or desktop')
    tests = plan['tests'][language]
    if not tests:
        return {'status':'not affected', 'runs':[]}
    checked = check_ownership(root, value, language, node)
    if language == 'python':
        command = [sys.executable, '-B', '-m', 'unittest', '-v', *[path[:-3].replace('/', '.') for path in tests]]
        cwd = root
    elif language == 'javascript':
        command = [node, '--import', './src/test-support/reactTestEnvironment.js', '--test', *[str(Path(path).relative_to('workspace-app')) for path in tests]]
        cwd = root / 'workspace-app'
    else:
        command = [node, '--test', *tests]
        cwd = root
    env = {**os.environ, 'PYTHONPATH':os.pathsep.join([str(root / 'python'), str(root / 'python/tests')]), 'PYTHONDONTWRITEBYTECODE':'1'}
    run = subprocess.run(command, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    return {'status':'passed' if run.returncode == 0 else 'failed', 'checked':checked,
            'runs':[{'command':command, 'cwd':str(cwd), 'exit_code':run.returncode, 'output':run.stdout}]}


def source_hashes(root, value):
    paths = {CATALOG}
    for path in ('workspace-app/architectureImports.mjs', 'workspace-app/package-lock.json', 'python/workspace-runtime.lock', 'workspace-app/isolatedViteCache.js'):
        if (root/path).is_file():
            paths.add(path)
    for path in (root/'workspace-app/src/test-support').rglob('*'):
        if path.is_file():
            paths.add(path.relative_to(root).as_posix())
    for link in value['discovery']:
        paths.update(link.values())
    for entry in value['contracts']:
        paths.add(entry['contract']['path'])
        paths.update(rule['file'] for rule in entry['rules'])
        for paths_for_language in entry['tests'].values():
            paths.update(paths_for_language)
    return {path:hashlib.sha256(contained(root,path).read_bytes()).hexdigest() for path in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['check', 'plan', 'test'])
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--language', choices=['all', 'metadata', *RUNNERS], default='all')
    parser.add_argument('--node', default='node')
    parser.add_argument('--base')
    parser.add_argument('--head', default='HEAD')
    parser.add_argument('--all', action='store_true', dest='all_contracts')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--github-output', type=Path)
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        value = catalog(root)
        if args.mode == 'check':
            result = {'status':'passed', 'checked':check_ownership(root, value, args.language, args.node),
                      'contracts':[entry['id'] for entry in value['contracts']]}
        else:
            result = {'status':'planned', **affected_plan(root, value, args.base, args.head, args.all_contracts)}
            if args.mode == 'test':
                result.update(run_contracts(root, value, result, args.language, args.node))
        result['source_sha256'] = source_hashes(root, value)
        result['guard_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        result['runtime'] = {'python':sys.version, 'python_executable':sys.executable}
        if 'javascript' in result.get('checked', []):
            result['runtime']['node'] = subprocess.check_output([args.node, '--version'], text=True).strip()
        if args.output:
            args.output.write_text(json.dumps(result, indent=2)+'\n')
        if args.github_output:
            with args.github_output.open('a') as output:
                for key in ('source_changed','javascript_required','python_required','desktop_required'):
                    output.write(f'{key}={str(result[key]).lower()}\n')
        print(json.dumps(result, indent=2))
        return 1 if result['status'] == 'failed' else 0
    except (ValueError, OSError, KeyError, TypeError, SyntaxError, subprocess.TimeoutExpired) as error:
        result = {'status':'failed', 'error':str(error)}
        if args.output:
            args.output.write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result, indent=2))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
