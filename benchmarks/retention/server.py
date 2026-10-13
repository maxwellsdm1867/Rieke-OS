"""Owned workflow service plus a real disposable project presentation-cache scope."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import threading


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--epochs', type=int, default=1000)
    parser.add_argument('--protocol-epochs', type=int, default=1000)
    args = parser.parse_args()
    if args.epochs != 1000 or args.protocol_epochs != 1000:
        raise ValueError('Retention diagnostic is bounded at 1000 epochs')
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ['RIEKE_DESKTOP_USER_STATE'] = str(args.output.resolve() / 'user-state')
    spec = importlib.util.spec_from_file_location('owned_workflow_fixture', Path(__file__).parents[1] / 'workflow/server.py')
    fixture_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_module)
    fixture = server = restore = None
    cleanup = {}
    try:
        fixture, app, meta = fixture_module.build(args.source_root.resolve(), args.output.resolve(), 1000, 1000)
        project = Path(fixture.case.temp.name).resolve()
        # This manifest is only for this fresh disposable test fixture. It binds
        # the real presentation-cache API to the independently generated UUID.
        (project / 'project.json').write_text(json.dumps({
            'format': 'recording-project', 'version': 1, 'project_uuid': meta['project'],
            'name': 'Owned retention fixture',
        }))
        meta.update(project_path=str(project), user_state=os.environ['RIEKE_DESKTOP_USER_STATE'])
        timing_spec = importlib.util.spec_from_file_location('owned_retention_timing', Path(__file__).parents[1] / 'workflow/backend_timing.py')
        timing = importlib.util.module_from_spec(timing_spec)
        timing_spec.loader.exec_module(timing)
        restore = timing.install(app, args.output, args.source_root)
        from werkzeug.serving import make_server
        server = make_server('127.0.0.1', 0, app, threaded=True)
        meta['port'] = server.server_port
        (args.output / 'server.json').write_text(json.dumps(meta, indent=2))
        def stop(*_):
            threading.Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        server.serve_forever()
    finally:
        errors = []
        for name, operation in [('server_closed', server.server_close if server else None),
                                ('instrumentation_restored', restore),
                                ('fixture_closed', fixture.doCleanups if fixture else None)]:
            if operation:
                try:
                    result = operation()
                    if result is False:
                        raise RuntimeError('Cleanup returned false')
                    cleanup[name] = True
                except Exception as error:
                    cleanup[name] = False
                    errors.append({'stage': name, 'error': str(error)})
        cleanup['errors'] = errors
        (args.output / 'cleanup.json').write_text(json.dumps(cleanup, indent=2))
        if errors:
            raise RuntimeError('Owned retention fixture cleanup failed')


if __name__ == '__main__':
    main()
