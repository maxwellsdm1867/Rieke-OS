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

import architecture_module_policy as module_policy

CATALOG = 'docs/architecture/adopted-port-checks.json'
LANGUAGES = ('python', 'javascript')
RUNNERS = (*LANGUAGES, 'desktop')


def canonical_reviewed_ast(node):
    """Stable parsed-AST encoding matching the catalog's Python 3.14 dumps.

    Omit empty list fields and declared optional None fields, not literal List
    nodes or Constant(value=None). Keep every other field, value and ordering;
    source bytes, reviewed selectors and provenance remain separately checked.
    """
    if isinstance(node, ast.AST):
        fields = []
        for name, value in ast.iter_fields(node):
            if isinstance(value, list) and not value:
                continue
            if value is None and getattr(type(node), name, ...) is None:
                continue
            fields.append(f'{name}={canonical_reviewed_ast(value)}')
        return f'{type(node).__name__}(' + ', '.join(fields) + ')'
    if isinstance(node, list):
        return '[' + ', '.join(canonical_reviewed_ast(item) for item in node) + ']'
    return repr(node)


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


# Python v4 is deliberately a syntactic ownership aid, not an execution sandbox.
# It tracks resolved imports/simple bindings and recognized loader calls only.
PYTHON_LOADERS = {'__import__', 'import_module', 'spec_from_file_location',
                  'exec_module', 'SourceFileLoader', 'SourcelessFileLoader',
                  'run_module', 'run_path', 'exec', 'eval'}
PYTHON_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
                 ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def python_test_name(root, value, name):
    if name.startswith('python/tests/'):
        return name[:-3].replace('/', '.')  # preserve the established runner
    policy = value.get('python_module_policy', {})
    if not any(name.startswith(prefix + '/') for prefix in policy.get('test_roots', [])):
        raise ValueError('Undeclared Python test path: ' + name)
    dotted = name[len(policy['source_root']) + 1:-3].replace('/', '.')
    relative = dotted.replace('.', '/') + '.py'
    choices = [root / relative, root / policy['source_root'] / relative,
               *[root / prefix / relative for prefix in policy['fixture_pythonpath']]]
    found = [path.resolve() for path in choices if path.is_file()]
    if found != [contained(root, name)]:
        raise ValueError('Shadowed or ambiguous Python test target: ' + name)
    return dotted


class PythonModulePolicy:
    """One versioned policy snapshot. No imports of inspected Python are executed."""
    def __init__(self, root, value):
        self.root, self.value, self.policy = root, value, value['python_module_policy']
        policy = self.policy
        keys(policy, ('source_root', 'test_roots', 'fixture_pythonpath', 'reviewed_loader_sites', 'modules'),
             ('reviewed_use_sites',) if value['version'] == 5 else ())
        if policy['source_root'] != 'python' or policy['fixture_pythonpath'] != ['python/tests']:
            raise ValueError('Python policy requires the existing source and fixture roots')
        self.safe('python', directory=True)
        self.test_roots = self.unique(policy['test_roots'])
        if 'python/tests' not in self.test_roots:
            raise ValueError('Python policy requires the central test root')
        for prefix in self.test_roots:
            self.safe(prefix, directory=True)
            if not prefix.startswith('python/'):
                raise ValueError('Python test root must be inside source root')
            if any(prefix != other and prefix.startswith(other + '/') for other in self.test_roots):
                raise ValueError('Overlapping Python test roots')
        self.sources = []
        def walk(directory):
            for path in sorted(directory.iterdir()):
                if path.name == '__pycache__':
                    continue
                if path.is_symlink():
                    raise ValueError('Python source symlink: ' + str(path))
                if path.is_dir():
                    walk(path)
                elif path.suffix == '.py':
                    self.sources.append(path.relative_to(root).as_posix())
        walk(root / 'python')
        self.trees = {name: ast.parse((root / name).read_text(), filename=name) for name in self.sources}
        self.identities, self.names = {}, {}
        for name in self.sources:
            relative = name[len('python/'): -3].split('/')
            if relative[-1] == '__init__': relative.pop()
            identity = '.'.join(relative)
            if identity in self.names:
                raise ValueError('Ambiguous Python module identity: ' + identity)
            self.identities[name] = identity
            self.names[identity] = name
            if Path(name).name.startswith('test_') and not self.is_test(name):
                raise ValueError('Unclassified Python test: ' + name)
        # Existing sibling test imports resolve through the declared fixture root.
        self.fixture_names = {Path(name).stem: name for name in self.sources
                              if Path(name).parent.as_posix() == 'python/tests' and not name.endswith('/__init__.py')}
        self.roots = {identity.split('.')[0] for identity in self.names if identity}
        self.modules = policy['modules']
        self.entries, self.namespaces = [], set()
        if not isinstance(self.modules, list) or not self.modules:
            raise ValueError('Python policy requires adopted modules')
        ids, roots, entries = set(), [], set()
        contracts = {item['id']: item for item in value['contracts']}
        for module in self.modules:
            named = value['version'] == 5 and 'public_entries' in module
            keys(module, ('contract_id', 'root', 'public_entries', 'private_test_edges') if named else
                 ('contract_id', 'root', 'public_module', 'public_entry', 'public_exports', 'private_test_edges'))
            owner = module['root']
            self.safe(owner, directory=True)
            if (not owner.startswith('python/') or self.is_test(owner) or
                    any(owner == other or owner.startswith(other + '/') or other.startswith(owner + '/') for other in roots)):
                raise ValueError('Python owner roots must be disjoint production descendants')
            roots.append(owner)
            if module['contract_id'] not in contracts or module['contract_id'] in ids:
                raise ValueError('Python owner contract must exist and be unique')
            ids.add(module['contract_id'])
            if any(not part.isidentifier() for part in owner.split('/')[1:]):
                raise ValueError('Python owner requires canonical identifiers')
            expected = owner[len('python/'):].replace('/', '.')
            if named:
                declarations = module['public_entries']
                if not isinstance(declarations, list) or not declarations:
                    raise ValueError('Python named public entries must be nonempty')
                for declaration in declarations:
                    keys(declaration, ('path', 'module', 'exports'))
                    path = declaration['path']
                    self.safe(path)
                    if (Path(path).parent.as_posix() != owner or not path.endswith('.py') or
                            Path(path).name == '__init__.py' or self.is_test(path) or path in entries or
                            not Path(path).stem.isidentifier() or declaration['module'] != self.identities.get(path)):
                        raise ValueError('Python named entry requires a unique canonical owned leaf')
                    names = self.unique(declaration['exports'])
                    if not names or any(not name.isidentifier() or name.startswith('__') for name in names):
                        raise ValueError('Invalid Python named public exports')
                    entries.add(path)
                    self.entries.append({'public_entry': path, 'public_module': declaration['module'],
                                         'public_exports': [{'name': name, 'from': path} for name in names], 'named': True})
            else:
                if module['public_module'] != expected or module['public_entry'] != owner + '/__init__.py':
                    raise ValueError('Python public entry must be its canonical package initializer')
                self.safe(module['public_entry'])
                entries.add(module['public_entry'])
                self.entries.append({**module, 'named': False})
                exports = module['public_exports']
                if not isinstance(exports, list) or not exports:
                    raise ValueError('Python public exports must be nonempty')
                exported = set()
                for item in exports:
                    keys(item, ('name', 'from'))
                    if not isinstance(item['name'], str) or not item['name'].isidentifier() or item['name'].startswith('_') or item['name'] in exported:
                        raise ValueError('Invalid or duplicate Python public export')
                    exported.add(item['name'])
                    self.safe(item['from'])
                    if (not item['from'].startswith(owner + '/') or item['from'] == module['public_entry'] or
                            self.is_test(item['from']) or item['from'] not in self.sources):
                        raise ValueError('Python public export requires its owned implementation file')
            # Named owners themselves are inert namespaces; legacy public roots
            # retain their exact initializer contract. Both require inert ancestors.
            parent = Path(owner) if named else Path(owner).parent
            while parent.as_posix() != 'python':
                initializer = parent.as_posix() + '/__init__.py'
                tree = self.trees.get(initializer)
                if tree is None or any(not self.docstring(node) for node in tree.body):
                    raise ValueError('Python package ancestor must have an inert initializer: ' + initializer)
                if named:
                    self.namespaces.add(self.identities[initializer])
                parent = parent.parent
            rules = [rule for rule in contracts[module['contract_id']]['rules'] if rule['language'] == 'python']
            for name in self.sources:
                if name.startswith(owner + '/') and not self.is_test(name):
                    matched = [rule for rule in rules if rule['file'] == name and 'allow' in rule]
                    if len(matched) != 1:
                        raise ValueError('Python production source needs one ownership allow rule: ' + name)
            edges = module['private_test_edges']
            if not isinstance(edges, list):
                raise ValueError('Python private test edges must be a list')
            seen = set()
            for edge in edges:
                keys(edge, ('from', 'to'))
                pair = (edge['from'], edge['to'])
                if pair in seen: raise ValueError('Duplicate Python private test edge')
                seen.add(pair)
                for name in pair: self.safe(name)
                if (not edge['from'].startswith(owner + '/tests/') or not self.is_test(edge['from']) or
                        not Path(edge['from']).name.startswith('test_') or not edge['to'].startswith(owner + '/') or
                        self.is_test(edge['to']) or edge['to'] in entries):
                    raise ValueError('Python private test edge must stay inside its owner')
        if set(self.test_roots) != {'python/tests', *[module['root'] + '/tests' for module in self.modules]}:
            raise ValueError('Python test roots must be central or adopted owner tests')
        mapped = {name for item in value['contracts'] for name in item['tests']['python']}
        for name in self.sources:
            if self.is_test(name) and not name.startswith('python/tests/') and Path(name).name.startswith('test_'):
                if name not in mapped:
                    raise ValueError('Unmapped owner-local Python test: ' + name)
                # Regular test packages ensure supported unittest discovery.
                parent = Path(name).parent
                while parent.as_posix() != 'python':
                    self.safe(parent.as_posix() + '/__init__.py')
                    parent = parent.parent
        for name in mapped:
            if not self.is_test(name) or not Path(name).name.startswith('test_') or not name.endswith('.py'):
                raise ValueError('Invalid declared Python test: ' + name)
            python_test_name(root, value, name)
        self.expected_loaders = {}
        records = policy['reviewed_loader_sites']
        if not isinstance(records, list): raise ValueError('Reviewed Python loader records must be a list')
        for record in records:
            keys(record, ('file', 'file_sha256', 'sites', 'reason'))
            name = record['file']
            if name not in self.sources or name in self.expected_loaders:
                raise ValueError('Missing or duplicate reviewed Python loader file')
            if not isinstance(record['reason'], str) or not record['reason'].strip():
                raise ValueError('Reviewed Python loader requires a reason')
            if not self.sha(record['file_sha256']) or hashlib.sha256((root / name).read_bytes()).hexdigest() != record['file_sha256']:
                raise ValueError('Reviewed Python loader source changed: ' + name)
            if not isinstance(record['sites'], list) or not record['sites']:
                raise ValueError('Reviewed Python loader requires sites')
            sites = {}
            for site in record['sites']:
                keys(site, ('selector', 'ast_sha256', 'kind'))
                if (site['kind'] not in ('ast-call', 'embedded-python') or not self.sha(site['ast_sha256']) or
                        not isinstance(site['selector'], str) or site['selector'] in sites):
                    raise ValueError('Invalid or duplicate reviewed Python loader site')
                sites[site['selector']] = site
            self.expected_loaders[name] = sites
        self.scopes, self.node_scopes, self.parents = {}, {}, {}
        for name, tree in self.trees.items():
            top = {'file': name, 'parent': None, 'bindings': {}, 'kind': 'module'}
            self.scopes[name] = top
            def visit(node, scope):
                self.node_scopes[id(node)] = scope
                if isinstance(node, PYTHON_SCOPES):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        scope['bindings'].setdefault(node.name, []).append(('ordinary',))
                    # Defaults/decorators/bases are evaluated in the enclosing
                    # scope. Function/comprehension free names skip class locals.
                    lexical_parent = scope
                    while lexical_parent and lexical_parent['kind'] == 'class':
                        lexical_parent = lexical_parent['parent']
                    child = {'file': name, 'parent': lexical_parent, 'bindings': {},
                             'kind': 'class' if isinstance(node, ast.ClassDef) else 'local'}
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                        for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs, node.args.vararg, node.args.kwarg):
                            if arg is not None: child['bindings'][arg.arg] = [('ordinary',)]
                    if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                        for index, generator in enumerate(node.generators):
                            if value['version'] == 5 and isinstance(generator.target, ast.Name) and isinstance(generator.iter, (ast.Tuple, ast.List)):
                                child['bindings'].setdefault(generator.target.id, []).append(('iteration', generator.iter, scope if index == 0 else child))
                            self.node_scopes[id(generator)] = child
                            self.parents[id(generator)] = node
                            for part in ast.iter_child_nodes(generator):
                                self.parents[id(part)] = generator
                                visit(part, scope if index == 0 and part is generator.iter else child)
                        for part in ast.iter_child_nodes(node):
                            if part not in node.generators:
                                self.parents[id(part)] = node
                                visit(part, child)
                    else:
                        body = [node.body] if isinstance(node, ast.Lambda) else node.body
                        for part in ast.iter_child_nodes(node):
                            self.parents[id(part)] = node
                            visit(part, child if part in body else scope)
                    return
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        scope['bindings'].setdefault(alias.asname or alias.name.split('.')[0], []).append(
                            ('module', alias.name if alias.asname else alias.name.split('.')[0]))
                elif isinstance(node, ast.ImportFrom):
                    module_name = self.from_module(name, node)
                    for alias in node.names:
                        scope['bindings'].setdefault(alias.asname or alias.name, []).append(('symbol', module_name, alias.name))
                elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Name):
                            scope['bindings'].setdefault(target.id, []).append(('expression', node.value, scope))
                elif value['version'] == 5 and isinstance(node, ast.For) and isinstance(node.target, ast.Name) and isinstance(node.iter, (ast.Tuple, ast.List)):
                    scope['bindings'].setdefault(node.target.id, []).append(('iteration', node.iter, scope))
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    scope['bindings'].setdefault(node.id, [('ordinary',)])
                for part in ast.iter_child_nodes(node):
                    self.parents[id(part)] = node
                    visit(part, scope)
            visit(tree, top)
        self.use_selectors, self.reviewed_uses, self.used_uses = {}, {}, set()
        for name, tree in self.trees.items():
            counts = {}
            for node in sorted(ast.walk(tree), key=lambda n: (getattr(n, 'lineno', 0), getattr(n, 'col_offset', 0), type(n).__name__)):
                kind = type(node).__name__
                counts[kind] = counts.get(kind, 0) + 1
                self.use_selectors[id(node)] = (name, kind + ':' + str(counts[kind]))
        records = policy.get('reviewed_use_sites', [])
        if not isinstance(records, list): raise ValueError('Reviewed Python uses must be a list')
        files = set()
        for record in records:
            keys(record, ('file', 'file_sha256', 'reason', 'sites'))
            name = record['file']
            if name not in self.sources or name in files:
                raise ValueError('Missing or duplicate reviewed Python use file')
            files.add(name)
            if not isinstance(record['reason'], str) or not record['reason'].strip():
                raise ValueError('Reviewed Python use requires a reason')
            if not self.sha(record['file_sha256']) or hashlib.sha256((root / name).read_bytes()).hexdigest() != record['file_sha256']:
                raise ValueError('Reviewed Python use source changed: ' + name)
            if not isinstance(record['sites'], list) or not record['sites']:
                raise ValueError('Reviewed Python use requires sites')
            nodes = {self.use_selectors[id(n)][1]: n for n in ast.walk(self.trees[name])}
            for site in record['sites']:
                keys(site, ('selector', 'ast_sha256', 'category', 'origins', 'targets', 'owners'))
                key = (name, site['selector'], site['category'])
                node = nodes.get(site['selector'])
                if node is None or key in self.reviewed_uses:
                    raise ValueError('Missing or duplicate reviewed Python use site')
                digest = hashlib.sha256(canonical_reviewed_ast(node).encode()).hexdigest()
                context = self.use_context(name, node, site['category'])
                if (not self.sha(site['ast_sha256']) or digest != site['ast_sha256'] or context is None or
                        any(site[k] != context[k] for k in ('origins', 'targets', 'owners'))):
                    raise ValueError('Changed category, provenance or target of reviewed Python use: ' + name)
                self.reviewed_uses[key] = site

    def use_context(self, name, node, category):
        """Exact reviewed syntax and current provenance; never execute inspected source."""
        scope = self.node_scopes[id(node)]
        test = self.is_test(name)
        values, targets = set(), []
        def identity(value): return '.'.join(value[1:])
        def finite_names(variable):
            parent = node
            while id(parent) in self.parents:
                parent = self.parents[id(parent)]
                generators = parent.generators if isinstance(parent, (ast.DictComp, ast.ListComp, ast.SetComp, ast.GeneratorExp)) else [parent] if isinstance(parent, ast.For) else []
                for generator in generators:
                    if isinstance(generator.target, ast.Name) and generator.target.id == variable:
                        try: result = ast.literal_eval(generator.iter)
                        except (ValueError, TypeError): return None
                        if isinstance(result, (tuple, list)) and result and all(isinstance(x, str) for x in result): return list(result)
                        return None
            return None
        def string_origin(target):
            def symbol_origin(module, symbol, seen=frozenset()):
                source = self.target(module)
                if source is None or (module, symbol) in seen: return set()
                resolved = self.binding(self.scopes[source], symbol)
                if resolved: return resolved
                # The general ownership resolver intentionally omits ordinary
                # flat-file functions. Bind only explicit import/definition
                # provenance for a reviewed literal mock target, without
                # changing that resolver or following computed expressions.
                result = set()
                for item in self.scopes[source]['bindings'].get(symbol, []):
                    if item[0] == 'symbol':
                        result.update(symbol_origin(item[1], item[2], seen | {(module, symbol)}))
                    elif item[0] == 'ordinary' and any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == symbol for n in self.trees[source].body):
                        result.add(('source-symbol', self.identities[source], symbol))
                return result
            parts = target.split('.')
            for stop in range(len(parts), 0, -1):
                module = '.'.join(parts[:stop]); source = self.target(module)
                if source:
                    origins = {('module', module)}
                    for part in parts[stop:]:
                        following = set()
                        for value in origins:
                            if value[0] == 'module' and self.target(value[1]):
                                following.update(symbol_origin(value[1], part))
                            elif value[0] == 'module': following.add(('external', value[1] + '.' + part))
                            elif value[0] == 'named': following.add(('named', value[1], value[2] + '.' + part))
                            elif value[0] == 'external': following.add(('external', value[1] + '.' + part))
                        origins = following
                    return origins
            return set()
        if category in ('test-mock-target', 'test-computed-mock-target'):
            if not test or not isinstance(node, ast.Call) or not node.args: return None
            kind = self.patch_kind(node, scope)
            if kind == 'unittest.mock.patch.object' and category == 'test-mock-target':
                if len(node.args) < 2 or not isinstance(node.args[1], ast.Constant) or not isinstance(node.args[1].value, str): return None
                values = self.expression(node.args[0], scope)
                targets = [identity(v) + '.' + node.args[1].value for v in values]
            elif kind == 'unittest.mock.patch':
                target = node.args[0]
                if category == 'test-mock-target' and isinstance(target, ast.Constant) and isinstance(target.value, str):
                    targets = [target.value]
                elif (category == 'test-computed-mock-target' and isinstance(target, ast.BinOp) and isinstance(target.op, ast.Add) and
                      isinstance(target.left, ast.Constant) and isinstance(target.left.value, str) and isinstance(target.right, ast.Name)):
                    names = finite_names(target.right.id)
                    if names is None: return None
                    targets = [target.left.value + suffix for suffix in names]
                else: return None
                for target in targets: values.update(string_origin(target))
            else: return None
        elif category == 'production-method-capture':
            if (test or not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != 'getattr' or
                    len(node.args) != 2 or node.keywords or not isinstance(node.args[1], ast.Name)): return None
            names = finite_names(node.args[1].id)
            if names is None: return None
            values = self.expression(node.args[0], scope)
            if not values or any(v[0] != 'named' for v in values): return None
            targets = [identity(v) + '.' + attribute for v in values for attribute in names]
        elif category in ('test-module-object', 'production-observer-table'):
            if test != (category == 'test-module-object') or not isinstance(node, (ast.Name, ast.Attribute)) or not isinstance(node.ctx, ast.Load): return None
            if not test and not isinstance(self.parents.get(id(node)), ast.Tuple): return None
            values = self.expression(node, scope)
            if not values or any(v[0] != 'module' for v in values): return None
            targets = [identity(v) for v in values]
        elif category == 'test-module-alias':
            if not test or not isinstance(node, ast.Assign): return None
            values = self.expression(node.value, scope)
            if not values or any(v[0] != 'module' for v in values): return None
            targets = [identity(v) for v in values]
        elif category in ('test-constructor-capture', 'test-oracle-call'):
            if not test or not isinstance(node, ast.Attribute): return None
            if category == 'test-constructor-capture':
                if node.attr not in ('__new__', '__init__'): return None
                values = self.expression(node.value, scope)
                if not values or any(v[0] != 'named' for v in values): return None
                targets = [identity(v) + '.' + node.attr for v in values]
            else:
                values = self.expression(node.value, scope) | self.expression(node, scope)
                targets = [identity(v) for v in self.expression(node, scope)]
        else: return None
        if not values or not targets or any(v[0] == 'adopted' for v in values): return None
        owners = {}
        for target in [*targets, *(v[1] for v in values)]:
            parts = target.split('.')
            for stop in range(len(parts), 0, -1):
                module = '.'.join(parts[:stop]); source = self.target(module)
                if source:
                    owner = self.owner(source)
                    owners[source] = {'module': self.identities[source], 'file': source,
                        'file_sha256': hashlib.sha256((self.root / source).read_bytes()).hexdigest(),
                        'contract_id': owner['contract_id'] if owner else None}
                    break
        if not owners: return None
        return {'origins': [list(v) for v in sorted(values)], 'targets': sorted(set(targets)),
                'owners': [owners[p] for p in sorted(owners)]}

    def reviewed_use(self, name, node, category):
        key = (*self.use_selectors[id(node)], category)
        if key not in self.reviewed_uses: return False
        self.used_uses.add(key)
        return True

    @staticmethod
    def unique(value):
        strings = string_list(value, 'Python policy strings')
        if len(strings) != len(set(strings)):
            raise ValueError('Duplicate Python policy string')
        return strings

    @staticmethod
    def sha(value):
        return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value)

    @staticmethod
    def docstring(node):
        return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)

    def safe(self, name, directory=False):
        return module_policy.path(self.root, name, directory)

    def is_test(self, name):
        return any(name == prefix or name.startswith(prefix + '/') for prefix in self.test_roots)

    def owner(self, name):
        return next((module for module in self.modules if name.startswith(module['root'] + '/')), None)

    def target(self, identity):
        return self.names.get(identity) or self.fixture_names.get(identity)

    def from_module(self, name, node):
        if not node.level: return node.module or ''
        identity = self.identities[name]
        package = identity if name.endswith('/__init__.py') else identity.rpartition('.')[0]
        parts = package.split('.') if package else []
        if node.level > len(parts):
            raise ValueError(name + ': relative Python import escapes source root')
        return '.'.join(parts[:len(parts) - node.level + 1] + ([node.module] if node.module else []))

    def dependencies(self, name):
        result = []
        for node in ast.walk(self.trees[name]):
            if isinstance(node, ast.Import): result.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom): result.append(self.from_module(name, node))
            elif isinstance(node, ast.Call) and self.loader(node, self.node_scopes[id(node)]):
                raise ValueError(name + ': adopted Python production cannot load dynamically')
        return result

    def binding(self, scope, name, seen=frozenset()):
        key = (id(scope), name)
        if key in seen: return set()
        seen = seen | {key}
        if name not in scope['bindings']:
            return self.binding(scope['parent'], name, seen) if scope['parent'] else ({('external', 'builtins.' + name)} if name in ('__import__', 'exec', 'eval', 'setattr', 'delattr') else set())
        values = set()
        for item in scope['bindings'][name]:
            if item[0] == 'ordinary' and scope['kind'] == 'module':
                owner = self.owner(scope['file'])
                if owner and 'public_entries' in owner and not self.is_test(scope['file']):
                    values.add(('named', self.identities[scope['file']], name))
            elif item[0] == 'module': values.add(item)
            elif item[0] == 'symbol':
                target = self.target(item[1])
                public = self.public(item[1])
                if public and item[2] in {entry['name'] for entry in public['public_exports']}:
                    values.update(self.public_value(public, item[2], seen))
                elif target:
                    child = self.target(item[1] + '.' + item[2])
                    if child: values.add(('module', item[1] + '.' + item[2]))
                    else: values.update(self.binding(self.scopes[target], item[2], seen))
                else: values.add(('external', item[1] + '.' + item[2]))
            elif item[0] == 'iteration':
                values.update(self.module_tuple(item[1], item[2], seen))
            elif item[0] == 'expression' and item[1] is not None:
                resolved = self.expression(item[1], item[2], seen)
                owner = self.owner(scope['file'])
                if not resolved and scope['kind'] == 'module' and owner and 'public_entries' in owner and not self.is_test(scope['file']):
                    resolved = {('named', self.identities[scope['file']], name)}
                values.update(resolved)
        return values

    def expression(self, node, scope, seen=frozenset()):
        if isinstance(node, ast.Name): return self.binding(scope, node.id, seen)
        if isinstance(node, ast.Attribute):
            result = set()
            for value in self.expression(node.value, scope, seen):
                if value[0] == 'module':
                    identity = value[1] + '.' + node.attr
                    target = self.target(value[1])
                    public = self.public(value[1])
                    if public and node.attr in {e['name'] for e in public['public_exports']}:
                        result.update(self.public_value(public, node.attr, seen))
                    elif self.target(identity): result.add(('module', identity))
                    elif target: result.update(self.binding(self.scopes[target], node.attr, seen))
                    else: result.add(('external', identity))
                elif value[0] == 'external': result.add(('external', value[1] + '.' + node.attr))
                elif value[0] == 'named': result.add(('named', value[1], value[2] + '.' + node.attr))
            return result
        return set()

    def adopted_origin(self, value):
        return value[0] in ('adopted', 'named') or value[0] == 'module' and any(
            value[1] == module['public_module'] or value[1].startswith(module['public_module'] + '.') for module in self.entries)

    def module_tuple(self, node, scope, seen=frozenset()):
        """Only literal, finite module aliases used by a direct iteration."""
        if not isinstance(node, (ast.Tuple, ast.List)) or not node.elts:
            return set()
        values = set()
        for element in node.elts:
            if not isinstance(element, (ast.Name, ast.Attribute)):
                return set()
            found = self.expression(element, scope, seen)
            if not found or any(value[0] != 'module' for value in found):
                return set()
            values.update(found)
        return values if any(self.public(v[1]) and self.public(v[1])['named'] for v in values) else set()

    def witness_element(self, node, scope):
        sequence = self.parents.get(id(node))
        loop = self.parents.get(id(sequence))
        return (isinstance(loop, (ast.For, ast.comprehension)) and loop.iter is sequence and
                isinstance(loop.target, ast.Name) and bool(self.module_tuple(sequence, scope)))

    def unambiguous(self, node, scope, seen=frozenset()):
        """Do not grant mock syntax exceptions to reassigned or shadowed aliases."""
        if isinstance(node, ast.Attribute): return self.unambiguous(node.value, scope, seen)
        if not isinstance(node, ast.Name): return False
        if node.id not in scope['bindings']:
            return bool(scope['parent'] and self.unambiguous(node, scope['parent'], seen))
        key = (id(scope), node.id)
        bindings = scope['bindings'][node.id]
        if key in seen or len(bindings) != 1: return False
        item = bindings[0]
        if item[0] == 'expression': return self.unambiguous(item[1], item[2], seen | {key})
        if item[0] == 'symbol' and self.target(item[1]):
            return self.unambiguous(ast.Name(id=item[2]), self.scopes[self.target(item[1])], seen | {key})
        return item[0] in ('module', 'symbol')

    def patch_kind(self, call, scope):
        if self.value['version'] != 5 or not any(e['named'] for e in self.entries): return None
        values = self.expression(call.func, scope)
        for kind in ('unittest.mock.patch', 'unittest.mock.patch.object'):
            if ('external', kind) in values:
                if values != {('external', kind)} or not self.unambiguous(call.func, scope):
                    raise ValueError(scope['file'] + ': ambiguous Python mock patch binding')
                return kind
        return None

    def mock_mutation(self, node, scope):
        """Reject bounded writes that invalidate a recognized mock call identity."""
        if self.value['version'] != 5 or not any(e['named'] for e in self.entries): return
        target = None
        if isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(node.ctx, (ast.Store, ast.Del)):
            target = node if isinstance(node, ast.Attribute) else node.value
        elif isinstance(node, ast.Call) and node.args:
            functions = self.expression(node.func, scope)
            reflective = isinstance(node.func, ast.Name) and node.func.id in ('setattr', 'delattr')
            reflective = reflective or bool(functions & {('external', 'builtins.setattr'), ('external', 'builtins.delattr')})
            if reflective: target = node.args[0]
        if target is not None and any(
                value[0] in ('external', 'module') and (value[1] == 'unittest.mock' or value[1].startswith('unittest.mock.'))
                for value in self.expression(target, scope)):
            raise ValueError(scope['file'] + ': mutated Python mock patch binding')

    def named_patch(self, call, scope):
        """Validate only known mock calls; return the admitted module argument."""
        kind = self.patch_kind(call, scope)
        if not kind or not call.args: return None
        target = call.args[0]
        if kind.endswith('.object'):
            origins = self.expression(target, scope)
            public = [self.public(v[1]) for v in origins if v[0] == 'module' and self.public(v[1]) and self.public(v[1])['named']]
            if not public: return None
            if (not self.is_test(scope['file']) or len(origins) != 1 or len(call.args) < 2 or
                    not isinstance(call.args[1], ast.Constant) or not isinstance(call.args[1].value, str) or
                    call.args[1].value not in {e['name'] for e in public[0]['public_exports']}):
                if not self.reviewed_use(scope['file'], call, 'test-mock-target'):
                    raise ValueError(scope['file'] + ': invalid Python named-module patch')
            return target
        if not isinstance(target, ast.Constant) or not isinstance(target.value, str):
            if self.reviewed_use(scope['file'], call, 'test-computed-mock-target'): return None
            raise ValueError(scope['file'] + ': computed Python mock patch target is unsupported')
        identity = target.value
        if not any(identity.startswith(namespace + '.') or identity == namespace for namespace in self.namespaces):
            return None
        # Legacy roots retain existing semantics, including their old test rules.
        if any(not e['named'] and (identity == e['public_module'] or identity.startswith(e['public_module'] + '.')) for e in self.entries):
            return None
        entry = next((e for e in self.entries if e['named'] and identity.startswith(e['public_module'] + '.')), None)
        parts = identity[len(entry['public_module']) + 1:].split('.') if entry else []
        if (not self.is_test(scope['file']) or not entry or not parts or
                parts[0] not in {e['name'] for e in entry['public_exports']} or
                any(not part.isidentifier() or part.startswith('__') for part in parts)):
            if not self.reviewed_use(scope['file'], call, 'test-mock-target'):
                raise ValueError(scope['file'] + ': invalid Python named-module string patch')
        origins = {('module', entry['public_module'])}
        for part in parts:
            resolved = set()
            for origin in origins:
                if origin[0] == 'module':
                    public = self.public(origin[1])
                    if public:
                        if part not in {e['name'] for e in public['public_exports']}:
                            if not self.reviewed_use(scope['file'], call, 'test-mock-target'):
                                raise ValueError(scope['file'] + ': invalid Python named-module string patch')
                        resolved.update(self.public_value(public, part, frozenset()))
                    elif self.owner(self.target(origin[1]) or ''):
                        raise ValueError(scope['file'] + ': private Python string patch origin')
                    else:
                        resolved.add(('external', origin[1] + '.' + part))
                elif origin[0] == 'named': resolved.add(('named', origin[1], origin[2] + '.' + part))
                elif origin[0] == 'external': resolved.add(('external', origin[1] + '.' + part))
                else: raise ValueError(scope['file'] + ': invalid Python string patch origin')
            origins = resolved
        return None

    def internal_named(self, importer, target):
        owner = self.owner(target) if target else None
        return bool(owner and 'public_entries' in owner and not self.is_test(importer) and self.owner(importer) == owner)

    def public(self, identity):
        return next((entry for entry in self.entries if entry['public_module'] == identity), None)

    def public_value(self, entry, symbol, seen):
        if not entry['named']:
            return {('adopted', entry['public_module'], symbol)}
        source = entry['public_entry']
        values = self.binding(self.scopes[source], symbol, seen)
        return values or {('named', entry['public_module'], symbol)}

    def has_adopted_bindings(self, identity):
        target = self.target(identity)
        return bool(target and any(any(self.adopted_origin(v) for v in self.binding(self.scopes[target], key))
                                   for key in self.scopes[target]['bindings']))

    def defined(self, source, symbol, seen=frozenset()):
        key = (source, symbol)
        if key in seen: return False
        for item in self.scopes[source]['bindings'].get(symbol, []):
            if item[0] in ('ordinary', 'module') or item[0] == 'expression' and item[1] is not None: return True
            if item[0] == 'symbol':
                target = self.target(item[1])
                public = self.public(self.identities[source])
                if public and public['named'] and self.target(item[1] + '.' + item[2]): return True
                if target and self.defined(target, item[2], seen | {key}): return True
                if not target and item[1].split('.')[0] not in self.roots: return True
        return False

    def loader(self, call, scope):
        names = {item[1].rsplit('.', 1)[-1] for item in self.expression(call.func, scope)
                 if item[0] in ('module', 'external')}
        if isinstance(call.func, ast.Name): names.add(call.func.id)
        elif isinstance(call.func, ast.Attribute): names.add(call.func.attr)
        found = names & PYTHON_LOADERS
        if len(found) > 1: raise ValueError(scope['file'] + ': ambiguous Python loader binding')
        return next(iter(found), None)

    def check(self):
        used_edges = set()
        def edge(importer, target):
            if not target: return
            if not self.is_test(importer) and self.is_test(target):
                raise ValueError(importer + ': production cannot import Python test source ' + target)
            owner = self.owner(target)
            if owner and 'public_entries' in owner and self.is_test(importer) and self.is_test(target): return
            if not owner or self.public(self.identities[target]) or self.identities[target] in self.namespaces: return
            if not self.is_test(importer) and self.owner(importer) == owner: return
            pair = {'from': importer, 'to': target}
            if pair in owner['private_test_edges']:
                used_edges.add((importer, target)); return
            raise ValueError(importer + ': forbidden private Python dependency ' + target)

        def public_import(importer, identity, symbol=None, alias=True):
            target = self.target(identity)
            edge(importer, target)
            public = self.public(identity)
            if public and (symbol is not None and symbol not in {e['name'] for e in public['public_exports']} or not alias and not public['named']):
                raise ValueError(importer + ': invalid Python public import ' + identity)
            if identity in self.namespaces and symbol is not None:
                child = identity + '.' + symbol
                if not self.public(child) and child not in self.namespaces and not self.internal_named(importer, self.target(child)):
                    raise ValueError(importer + ': invalid Python namespace import ' + child)
            if not target and identity.split('.')[0] in self.roots:
                # Module attributes in from-imports are handled by their parent.
                raise ValueError(importer + ': unresolved local Python module ' + identity)
            return target

        for module in self.entries:
            if module['named']:
                for export in module['public_exports']:
                    if not self.defined(module['public_entry'], export['name']):
                        raise ValueError('Missing Python named export: ' + export['name'])
                    for origin in self.public_value(module, export['name'], frozenset()):
                        if origin[0] in ('module', 'named'):
                            target = self.target(origin[1])
                            if target and self.owner(target) and not self.public(origin[1]):
                                raise ValueError('Python named export exposes private module: ' + export['name'])
                continue
            actual, all_names = [], None
            for node in self.trees[module['public_entry']].body:
                if self.docstring(node): continue
                if isinstance(node, ast.ImportFrom):
                    target = self.target(self.from_module(module['public_entry'], node))
                    for alias in node.names:
                        if alias.asname and alias.asname != alias.name:
                            raise ValueError('Python public entry cannot rename exports')
                        actual.append({'name': alias.name, 'from': target})
                elif (isinstance(node, ast.Assign) and len(node.targets) == 1 and
                      isinstance(node.targets[0], ast.Name) and node.targets[0].id == '__all__' and all_names is None):
                    try: all_names = ast.literal_eval(node.value)
                    except (ValueError, TypeError): raise ValueError('Python public __all__ must be literal')
                else: raise ValueError('Python public initializer has undeclared behavior')
            expected = module['public_exports']
            if (actual != expected or not isinstance(all_names, (list, tuple)) or list(all_names) != [e['name'] for e in expected]):
                raise ValueError('Python public export surface changed: ' + module['public_entry'])
            for export in expected:
                # An actual definition/assignment/import must exist; private
                # implementation behavior is checked by its own contract tests.
                if not self.defined(export['from'], export['name']):
                    raise ValueError('Missing Python implementation export: ' + export['name'])

        for name, tree in self.trees.items():
            found_loaders, counts = {}, {}
            for node in sorted(ast.walk(tree), key=lambda n: (getattr(n, 'lineno', 0), getattr(n, 'col_offset', 0))):
                scope = self.node_scopes[id(node)]
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        public_import(name, alias.name, alias=bool(alias.asname))
                elif isinstance(node, ast.ImportFrom):
                    identity = self.from_module(name, node)
                    target = public_import(name, identity)
                    for alias in node.names:
                        public_import(name, identity, alias.name)
                        child = self.target(identity + '.' + alias.name)
                        if child:
                            if any(child == m['public_entry'] and identity != m['public_module'] and not m['named'] for m in self.entries):
                                raise ValueError(name + ': public Python import must use canonical package')
                            edge(name, child)
                        if target and identity not in self.namespaces and not self.public(identity) and not self.internal_named(name, target) and not ((name, target) in used_edges and 'public_entries' in (self.owner(target) or {})):
                            if alias.name == '*':
                                origins = set().union(*(self.binding(self.scopes[target], key) for key in self.scopes[target]['bindings']))
                            else: origins = self.binding(self.scopes[target], alias.name)
                            if any(self.adopted_origin(value) for value in origins):
                                raise ValueError(name + ': forbidden Python public re-export shim')
                elif isinstance(node, ast.Attribute):
                    for value in self.expression(node.value, scope):
                        if value[0] == 'named' and node.attr.startswith('__') and not self.internal_named(name, self.target(value[1])) and not self.reviewed_use(name, node, 'test-constructor-capture'):
                            raise ValueError(name + ': reflective Python named value attribute')
                        if value[0] == 'adopted':
                            raise ValueError(name + ': reflective Python public callable attribute')
                        if value[0] != 'module': continue
                        target = self.target(value[1])
                        public = self.public(value[1])
                        if value[1] in self.namespaces and not self.public(value[1] + '.' + node.attr) and value[1] + '.' + node.attr not in self.namespaces and not self.internal_named(name, self.target(value[1] + '.' + node.attr)):
                            raise ValueError(name + ': forbidden Python namespace attribute ' + node.attr)
                        if public and node.attr not in {e['name'] for e in public['public_exports']} and not (public['named'] and node.attr == '__file__' and isinstance(node.ctx, ast.Load)):
                            raise ValueError(name + ': forbidden Python public attribute ' + node.attr)
                        child = self.target(value[1] + '.' + node.attr)
                        edge(name, child)
                        if child and any(child == m['public_entry'] and not m['named'] for m in self.entries) and not public:
                            raise ValueError(name + ': public Python import must use canonical package')
                        if target and not public and value[1] not in self.namespaces and not self.internal_named(name, target) and not ((name, target) in used_edges and 'public_entries' in (self.owner(target) or {})) and any(self.adopted_origin(v) for v in self.expression(node, scope)) and not self.reviewed_use(name, node, 'test-oracle-call'):
                            raise ValueError(name + ': forbidden Python public re-export shim')
                        if target and not public and self.has_adopted_bindings(value[1]) and (node.attr.startswith('__') or node.attr not in self.scopes[target]['bindings']):
                            raise ValueError(name + ': reflective or unresolved Python shim attribute')
                # Module-object forwarding/reflection is outside supported syntax.
                if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load):
                    values = self.expression(node, scope)
                    protected = [v for v in values if v[0] == 'module' and (any(v[1] == m['public_module'] for m in self.entries) or v[1] in self.namespaces or self.has_adopted_bindings(v[1]))]
                    loaders = [v for v in values if v[0] in ('external', 'module') and v[1].rsplit('.', 1)[-1] in PYTHON_LOADERS]
                    parent = self.parents.get(id(node))
                    simple_alias = ((isinstance(parent, ast.Assign) and len(parent.targets) == 1 and isinstance(parent.targets[0], ast.Name) or
                                     isinstance(parent, ast.AnnAssign) and isinstance(parent.target, ast.Name)) and parent.value is node)
                    named_patch = isinstance(parent, ast.Call) and self.named_patch(parent, scope) is node
                    if protected and not (isinstance(parent, ast.Attribute) and parent.value is node or simple_alias or named_patch or self.witness_element(node, scope) or self.reviewed_use(name, node, 'test-module-object' if self.is_test(name) else 'production-observer-table')):
                        raise ValueError(name + ': opaque Python public module use')
                    if loaders and not (isinstance(parent, ast.Call) and parent.func is node or isinstance(parent, (ast.Assign, ast.AnnAssign)) and parent.value is node):
                        raise ValueError(name + ': opaque Python loader use')
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target_node in targets:
                        if isinstance(target_node, ast.Name) and len(scope['bindings'].get(target_node.id, [])) > 1:
                            if any(v[0] == 'module' and any(v[1] == m['public_module'] for m in self.entries) for v in self.binding(scope, target_node.id)) and not self.reviewed_use(name, node, 'test-module-alias'):
                                raise ValueError(name + ': reassigned Python public module alias')
                            if any(v[0] in ('module', 'external') and v[1].rsplit('.', 1)[-1] in PYTHON_LOADERS for v in self.binding(scope, target_node.id)):
                                raise ValueError(name + ': reassigned Python loader alias')
                    if any(isinstance(t, ast.Name) and t.id == '__all__' for t in targets) and not any(name == m['public_entry'] for m in self.entries):
                        try: exports = ast.literal_eval(node.value)
                        except (ValueError, TypeError): exports = []
                        if isinstance(exports, (list, tuple)) and any(any(self.adopted_origin(v) for v in self.binding(scope, key)) for key in exports if isinstance(key, str)):
                            raise ValueError(name + ': forbidden Python public re-export declaration')
                self.mock_mutation(node, scope)
                if isinstance(node, ast.Call):
                    self.named_patch(node, scope)
                    if isinstance(node.func, ast.Name) and node.func.id in ('getattr', 'setattr', 'delattr', 'vars') and any(
                            v[0] == 'adopted' or v[0] == 'named' and not (
                                node.func.id == 'getattr' and index == 0 and self.internal_named(name, self.target(v[1])))
                            for index, arg in enumerate(node.args) for v in self.expression(arg, scope)):
                        if not self.reviewed_use(name, node, 'production-method-capture'):
                            raise ValueError(name + ': reflective Python public callable access')
                    loader = self.loader(node, scope)
                    if loader:
                        counts[loader] = counts.get(loader, 0) + 1
                        selector = f'call:{loader}:{counts[loader]}'
                        literal = (loader in ('__import__', 'import_module') and node.args and
                                   isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str))
                        if literal:
                            identity = node.args[0].value
                            from_names = []
                            if loader == '__import__':
                                # Only absolute imports with explicit literal
                                # fromlists are statically admitted. Relative or
                                # computed forms require a reviewed exact site.
                                keywords = {keyword.arg: keyword.value for keyword in node.keywords}
                                level = node.args[4] if len(node.args) > 4 else keywords.get('level', ast.Constant(0))
                                fromlist = node.args[3] if len(node.args) > 3 else keywords.get('fromlist', ast.Tuple(elts=[]))
                                try:
                                    literal_level = ast.literal_eval(level)
                                    from_names = ast.literal_eval(fromlist)
                                except (ValueError, TypeError):
                                    literal_level, from_names = None, None
                                literal = (len(node.args) <= 5 and not set(keywords) - {'globals', 'locals', 'fromlist', 'level'} and
                                           type(literal_level) is int and literal_level == 0 and isinstance(from_names, (tuple, list)) and
                                           all(isinstance(symbol, str) and symbol != '*' for symbol in from_names))
                            if identity.startswith('.'):
                                package = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == 'package'), None)
                                if loader != 'import_module' or not isinstance(package, ast.Constant) or not isinstance(package.value, str):
                                    literal = False
                                else:
                                    level = len(identity) - len(identity.lstrip('.'))
                                    parts = package.value.split('.')
                                    if level > len(parts): raise ValueError(name + ': relative Python loader escapes package')
                                    identity = '.'.join(parts[:len(parts) - level + 1] + [identity[level:]])
                            if literal:
                                if any(identity == m['public_module'] or identity.startswith(m['public_module'] + '.') or m['public_module'].startswith(identity + '.') for m in self.entries) or self.has_adopted_bindings(identity):
                                    raise ValueError(name + ': dynamic access to adopted Python module')
                                target = public_import(name, identity)
                                for symbol in from_names:
                                    child = self.target(identity + '.' + symbol)
                                    if child: edge(name, child)
                                    if target and any(self.adopted_origin(v) for v in self.binding(self.scopes[target], symbol)):
                                        raise ValueError(name + ': dynamic access to adopted Python binding')
                        if not literal:
                            found_loaders[selector] = {'selector': selector, 'kind': 'ast-call',
                                'ast_sha256': hashlib.sha256(canonical_reviewed_ast(node).encode()).hexdigest()}
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PROBE' for t in node.targets) and name == 'python/workspace_bootstrap.py':
                    if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
                        raise ValueError('Python embedded PROBE must remain literal')
                    found_loaders['assignment:PROBE'] = {'selector': 'assignment:PROBE', 'kind': 'embedded-python',
                        'ast_sha256': hashlib.sha256(node.value.value.encode()).hexdigest()}
            if found_loaders != self.expected_loaders.get(name, {}):
                raise ValueError(name + ': unclassified, changed or unused Python loader site')
        expected_edges = {(e['from'], e['to']) for m in self.modules for e in m['private_test_edges']}
        if used_edges != expected_edges:
            raise ValueError('Unused Python private test exception')
        if self.used_uses != set(self.reviewed_uses):
            raise ValueError('Unused reviewed Python use site')


def python_policy(root, value):
    return PythonModulePolicy(root, value) if value['version'] in (4, 5) else None


def catalog(root):
    value = json.loads(contained(root, CATALOG).read_text())
    keys(value, ('format', 'version', 'discovery', 'shared_paths', 'contracts'),
         ('javascript_module_policy', 'python_module_policy') if value.get('version') in (4, 5) else ('javascript_module_policy',))
    if value['format'] != 'disco-adopted-port-checks' or value['version'] not in (1, 2, 3, 4, 5):
        raise ValueError('Unsupported adopted-port catalog format/version')
    if value['version'] == 1 and 'javascript_module_policy' in value:
        raise ValueError('Catalog version 1 forbids module policy')
    if value['version'] in (2, 3, 4, 5) and 'javascript_module_policy' not in value:
        raise ValueError(f"Catalog version {value['version']} requires module policy")
    if value['version'] in (4, 5) and not isinstance(value.get('javascript_module_policy'), dict):
        raise ValueError('Catalog version 4 requires JavaScript module policy')
    if value['version'] in (4, 5) and not isinstance(value.get('python_module_policy'), dict):
        raise ValueError('Catalog version 4 requires Python module policy')
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
            declared_tests = string_list(entry['tests'].get(language, []), 'test paths')
            if value['version'] in (4, 5) and len(declared_tests) != len(set(declared_tests)):
                raise ValueError('Duplicate test path within contract: ' + entry['id'])
            for path in declared_tests:
                contained(root, path)
                if language == 'python' and not (path.endswith('.py') and (path.startswith('python/tests/') or
                        value['version'] in (4, 5) and any(path.startswith(prefix + '/') for prefix in value['python_module_policy'].get('test_roots', [])))):
                    raise ValueError(f'Invalid Python test path: {path}')
                if language == 'javascript' and not (path.startswith('workspace-app/src/') and path.endswith('.test.js')):
                    raise ValueError(f'Invalid JavaScript test path: {path}')
                if language == 'desktop' and not ((path.startswith('desktop/tests/') or Path(path).parent.as_posix() in {'desktop/close/tests', 'desktop/drafts/tests', 'desktop/startup/tests', 'desktop/integrity/tests', 'desktop/updates/tests'}) and path.endswith('.test.cjs')):
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
    module_policy.validate(root, value)
    python_policy(root, value)
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
    python_owner = python_policy(root, value) if language in ('all', 'python') else None
    for selected in LANGUAGES:
        if language not in ('all', selected):
            continue
        for entry in value['contracts']:
            for rule in entry['rules']:
                if rule['language'] != selected:
                    continue
                source = contained(root, rule['file']).read_text()
                if selected == 'python':
                    dependencies = (python_owner.dependencies(rule['file']) if python_owner and python_owner.owner(rule['file'])
                                    else python_dependencies(source, rule['file']))
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
        if selected == 'javascript':
            module_policy.check(root, value, node)
        elif python_owner:
            python_owner.check()
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
    if value.get('python_module_policy') and any(path.startswith('python/') or path in ('tools/architecture_guard.py', 'tools/architecture_module_policy.py', 'desktop/application-profile.json', 'tools/desktop_application_profile.py') for path in paths):
        shared = True  # include new/deleted Python consumers, not only current inventory
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
        command = [sys.executable, '-B', '-m', 'unittest', '-v', *[python_test_name(root, value, path) for path in tests]]
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
    paths = {CATALOG, 'tools/architecture_module_policy.py'} if value.get('javascript_module_policy') else {CATALOG}
    paths.update(module_policy.inputs(root, value))
    owner = python_policy(root, value)
    if owner:
        paths.update(owner.sources)
        paths.add('tools/architecture_guard.py')
        for name in ('desktop/application-profile.json', 'tools/desktop_application_profile.py'):
            if (root / name).is_file(): paths.add(name)
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
