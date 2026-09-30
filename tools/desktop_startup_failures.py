#!/usr/bin/env python3
"""Public startup/retry transport qualification using only owned empty fixtures."""
import argparse
import json
from pathlib import Path

from desktop_backend_smoke import inventory
from desktop_scientific_e2e import Harness, ROOT, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', type=Path, default=ROOT / 'desktop/dist/mac-arm64/Rieke OS.app/Contents/Resources')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/dev/desktop-startup-failures.json')
    args = parser.parse_args()
    harness = Harness(args.resources)
    before = inventory(harness.runtime)
    cases = []
    try:
        harness.start()
        legacy = harness.create('owned-legacy-preflight-fixture')
        directory = Path(legacy['path'])
        catalog = json.loads((directory / 'catalog.json').read_text())
        catalog.pop('managed_database', None)
        catalog['connection'] = {'host': '127.0.0.1', 'port': 3306,
            'credential_provider': {'kind': 'docker-container-env', 'container': 'unavailable-test-source'}}
        (directory / 'catalog.json').write_text(json.dumps(catalog))
        # New project creation has not started SQL. Remove only its empty,
        # never-opened descriptor to model the historical external profile.
        database = directory / 'database'
        assert set(database.iterdir()) == {database / 'service.json'}
        (database / 'service.json').unlink()
        fixture_before = inventory(directory)
        records = harness.call('/api/desktop/health')['services']
        rejected = harness.call('/api/projects/open-folder', {'directory': str(directory)}, expect=409)
        assert rejected['code'] == 'legacy_project_requires_migration'
        assert 'desktop copy' in rejected['error']
        assert harness.call('/api/desktop/health')['services'] == records
        assert fixture_before == inventory(directory)
        assert not (harness.state / 'home/.docker').exists()
        cases.append({'name': 'external-legacy-open-preflight-is-actionable-and-spawns-no-child', 'passed': True})
        harness.call('/api/projects/open-folder', {'directory': str(harness.state / 'missing')}, expect=400)
        cases.append({'name': 'missing-project-returned-as-retryable-transport-error', 'passed': True})
        exited_pid = harness.process.pid
        harness.stop()
        registry = harness.state / 'user-state/desktop-services.json'
        registry.write_text(json.dumps({'version': 1, 'services': [{
            'project_path': str(directory), 'project_uuid': legacy['uuid'], 'bound': False,
            'pid': exited_pid, 'created_at': 0, 'executable': str(harness.python.resolve())}], 'database_operations': []}))
        harness.start()
        assert harness.call('/api/desktop/health')['services'] == []
        assert fixture_before == inventory(directory)
        cases.append({'name': 'dead-bare-legacy-preflight-record-does-not-deadlock-launcher-restart', 'passed': True})
        native = harness.create('native-after-rejected-startup')
        origin, _ = harness.open(native)
        assert harness.call('/api/health', origin=origin)['status'] == 'ready'
        harness.close_project(origin, native)
        cases.append({'name': 'native-project-opens-and-closes-after-startup-rejections', 'passed': True})
    except Exception as error:
        cases.append({'name': 'startup-transport-fixture', 'passed': False, 'error_type': type(error).__name__})
        (harness.state / 'startup-failure-private.txt').write_text(repr(error))
    finally:
        try:
            harness.stop()
        except Exception as error:
            cases.append({'name': 'owned-service-exit', 'passed': False, 'error_type': type(error).__name__})
        unchanged = before == inventory(harness.runtime)
        receipt = {'format': 'rieke-desktop-startup-failure-transport', 'version': 1,
            'application_version': harness.manifest['application_version'],
            'source_commit': harness.manifest['source_commit'],
            'runtime_manifest_sha256': sha(harness.runtime / 'runtime-manifest.json'),
            'app_asar_sha256': sha(harness.resources / 'app.asar'),
            'cases': cases, 'packaged_resources_unchanged': unchanged,
            'limitations': ['Dead legacy registry fixture is deliberately seeded in owned scratch state; no live user app or source database is touched'],
            'passed': all(case['passed'] for case in cases) and unchanged}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt, indent=2))
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
