"""Drain a local project before stopping its app-owned database."""
import os
import threading
from flask import g, jsonify, request


def register_project_lifecycle(app, *, busy, stop_database):
    condition = threading.Condition()
    state = {'closing': False, 'requests': 0}

    @app.before_request
    def admit_request():
        with condition:
            if state['closing']:
                return jsonify(error='This project is closing. Reopen it from the project chooser.'), 503
            state['requests'] += 1
            g.rieke_admitted = True

    @app.teardown_request
    def finished_request(error=None):
        if getattr(g, 'rieke_admitted', False):
            g.rieke_admitted = False
            with condition:
                state['requests'] -= 1
                condition.notify_all()

    @app.post('/api/project/close')
    def close_project():
        if request.args or request.get_json(silent=True) != {}:
            return jsonify(error='Close project accepts an empty object.'), 400
        if 'shutdown_project_server' not in app.extensions:
            return jsonify(error='This server does not support managed project shutdown.'), 409
        with condition:
            if busy():
                return jsonify(error='Wait for the current import or project operation to finish before closing.'), 409
            state['closing'] = True
            if not condition.wait_for(lambda: state['requests'] <= 1, timeout=30) or busy():
                state['closing'] = False
                return jsonify(error='Project operations are still active. Wait for them to finish and retry.'), 409
        try:
            stop_database()
        except Exception:
            with condition:
                state['closing'] = False
            app.logger.exception('Project database could not close cleanly')
            return jsonify(error='The database could not close cleanly. Check the project log before copying its folder.'), 500
        threading.Timer(.2, app.extensions['shutdown_project_server']).start()
        return jsonify(state='closed', message='Project database closed cleanly. Its folder is ready to move.',
                       launcher_url=f"http://127.0.0.1:{int(os.environ.get('RIEKE_LAUNCHER_PORT', '8766'))}/"), 202

    return state
