#!/usr/bin/env python3
"""Read-only preflight of a source runtime before desktop packaging.

This does not execute Python packages, open projects, start SQL, or certify an
installer. An absence of known static blockers is not production qualification.
"""
import argparse
import configparser
import datetime
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def _inside(path, root):
    try:
        return Path(path).resolve().is_relative_to(root)
    except (OSError, RuntimeError):
        return False


def _absolute(value):
    return Path(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _json(path):
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Metadata exceeds the preflight size limit')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError('Metadata must be a JSON object')
    return value


def audit_source_runtime(application):
    root = Path(application).resolve(strict=True)
    issues = []
    examined = {'pth_files': 0, 'runtime_symlinks': 0}

    def issue(code, work, path, message):
        issues.append({'code': code, 'work': work, 'path': str(path.relative_to(root)), 'message': message})

    def metadata(path, work):
        if not _inside(path, root):
            issue('metadata_path_escape', work, path, 'Metadata redirects outside the application; it was not read.')
            return {}
        try:
            return _json(path)
        except (OSError, ValueError, TypeError) as error:
            issue('metadata_unavailable', work, path, f'Cannot inspect metadata ({type(error).__name__}).')
            return {}

    runtime = root / '.rieke-runtime'
    config = metadata(runtime / 'runtime.json', 'E02')
    source = metadata(root / 'python/workspace-source.json', 'E01')
    release = metadata(root / 'rieke-release.json', 'E01')
    package = metadata(root / 'workspace-app/package.json', 'E01')
    if release.get('version') and package.get('version') != release['version']:
        issue('version_mismatch', 'E01', root / 'rieke-release.json', 'Application and frontend versions differ.')
    if release and release.get('repository') != 'maxwellsdm1867/Rieke-OS':
        issue('release_repository_mismatch', 'E01', root / 'rieke-release.json', 'Desktop publication must use Rieke-OS.')
    if source.get('commit') and config.get('retinanalysis_commit') != source['commit']:
        issue('parser_receipt_mismatch', 'E02', runtime / 'runtime.json', 'Parser runtime receipt differs from the source pin.')

    python_value = config.get('python', '.rieke-runtime/venv/bin/python')
    parser_value = config.get('retinanalysis', '.rieke-runtime/retinanalysis')
    for key, value in (('python', python_value), ('retinanalysis', parser_value)):
        if not isinstance(value, str) or not value:
            issue('invalid_runtime_path', 'E02', runtime / 'runtime.json', f'Invalid {key} path.')
            continue
        path = root / value
        if _absolute(value):
            issue('absolute_runtime_config', 'E02', runtime / 'runtime.json', f'{key} uses an absolute build-machine path.')
        if not _inside(path, root):
            issue('external_runtime_path', 'E02', runtime / 'runtime.json', f'{key} resolves outside the application.')
        if not path.exists():
            issue('runtime_component_missing', 'E02', runtime / 'runtime.json', f'{key} is missing.')

    # Inspect only application runtime code, never project/database directories.
    # Refuse to traverse a runtime directory that redirects outside the app.
    if runtime.is_dir() and _inside(runtime, root):
        for path in sorted(runtime.rglob('*')):
            if path.is_symlink():
                examined['runtime_symlinks'] += 1
                if not _inside(path, root):
                    issue('external_runtime_symlink', 'E02', path, 'Link points outside the application or forms a loop.')
                elif os.path.isabs(os.readlink(path)):
                    issue('absolute_runtime_symlink', 'E02', path, 'Absolute link must be made relocatable during the build.')
            if path.name == 'pyvenv.cfg' and path.is_file() and _inside(path, root):
                for line in path.read_text().splitlines():
                    key, separator, value = line.partition('=')
                    if separator and key.strip() == 'home' and _absolute(value.strip()):
                        issue('absolute_venv_home', 'E02', path, 'Venv records an absolute interpreter home; do not copy it as a portable runtime.')
            if path.suffix == '.pth' and path.is_file() and _inside(path, root):
                examined['pth_files'] += 1
                for line in path.read_text().splitlines():
                    line = line.strip()
                    if not line or line.startswith(('#', 'import ', 'import\t')):
                        continue
                    if _absolute(line):
                        issue('absolute_python_import_path', 'E02', path, 'Python imports use an absolute editable/dependency path.')
                    elif not _inside(path.parent / line, root):
                        issue('external_python_import_path', 'E02', path, 'Relative Python import path escapes the application.')
        for path in sorted(runtime.rglob('config.ini')):
            if not _inside(path, root):
                continue
            if 'retinanalysis' not in path.parts:
                continue
            parser_config = configparser.ConfigParser(interpolation=None)
            try:
                parser_config.read(path)
            except (OSError, UnicodeError, configparser.Error):
                issue('parser_config_unreadable', 'E03', path, 'Parser configuration cannot be inspected.')
                continue
            values = list(parser_config.defaults().values())
            values.extend(value for section in parser_config.sections() for value in parser_config[section].values())
            if any(_absolute(value) for value in values):
                issue('parser_config_build_paths', 'E03', path, 'Parser configuration embeds instance-specific paths inside application code.')
    else:
        issue('unsafe_or_missing_runtime', 'E02', runtime, 'Runtime is missing or redirects outside the application; it was not traversed.')

    parser_path = root / parser_value if isinstance(parser_value, str) else None
    if parser_path and _inside(parser_path, root) and (parser_path / '.git').exists():
        try:
            revision = subprocess.check_output(['git', '-C', str(parser_path), 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL, timeout=10).strip()
            allowed = [source.get('commit'), *source.get('compatible_local_commits', [])]
            if revision not in allowed:
                issue('parser_source_mismatch', 'E02', runtime / 'runtime.json', 'Actual parser checkout differs from the allowed source revisions.')
        except (OSError, subprocess.SubprocessError):
            issue('parser_source_unverified', 'E02', runtime / 'runtime.json', 'Source checkout provenance could not be inspected.')
    else:
        issue('parser_source_unverified', 'E02', runtime / 'runtime.json', 'This source audit cannot verify parser checkout provenance; a packaged wheel needs a build receipt instead.')

    return {'format': 'rieke-desktop-source-preflight', 'version': 1,
            'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'status': 'blocked' if issues else 'no_known_static_blockers',
            'production_ready': False, 'project_code_executed': False,
            'versions': {'application': release.get('version'), 'frontend': package.get('version'),
                         'python_pin': source.get('python'), 'parser_pin': source.get('commit')},
            'examined': examined, 'blockers': issues,
            'not_validated': ['portable package assembly', 'dynamic library closure', 'real imports and database operations',
                              'signing and notarization', 'Electron startup and shutdown', 'clean-machine install', 'signed old-to-new update']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    report = audit_source_runtime(args.application)
    text = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile('w', dir=args.output.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(text)
            os.replace(temporary, args.output)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
    print(text, end='')
    return 1 if report['blockers'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
