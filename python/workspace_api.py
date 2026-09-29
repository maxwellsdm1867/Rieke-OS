"""Loopback-only HTTP adapter for the integrated local React workspace.

Start with the RetinAnalysis environment. Scientific parsing and query evaluation
remain in recording_workspace / RetinAnalysis; this module owns HTTP and jobs.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import datetime as dt
import gzip
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
import uuid
import zipfile

from flask import Flask, jsonify, request, send_file, send_from_directory
from workspace_export_names import naming_options, export_download_name
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from recording_workspace import digest, now, write_json
from workspace_recipes import capture_query, checksum, compare_query, parse_splits, prepare_export, save_snapshot
from workspace_storage import ManagedStorage, log_dir
from workspace_diff import summarize_diff
from workspace_protocol_identity import selection_protocols, protocol_compatibility, require_protocol_compatibility
from workspace_import_check import classify_source
from workspace_audit import build_audit_payload, normalize_event, normalize_events, repeat_suggestions


class StaleWorkspace(ValueError):
    pass


def summarize_cell_membership(rows, approved, exported, included=None):
    """One pass over epochs, rather than one complete scan per cell."""
    summaries = {}
    for row in rows:
        current = summaries.setdefault(row['cell_uuid'], {'reviewed': 0, 'unreviewed': 0, 'exported': 0})
        identity = row['epoch_uuid']
        reviewed = identity in approved
        current['reviewed'] += reviewed
        current['unreviewed'] += not reviewed
        current['exported'] += identity in exported
        if included is not None:
            current['included'] = current.get('included', 0) + (identity in included)
    return summaries


class ExactMetadataJSON(DefaultJSONProvider):
    """Preserve source tick integers beyond JavaScript's exact Number range."""
    def dumps(self, obj, **kwargs):
        def browser_safe(value):
            if type(value) is int and abs(value) > 2**53 - 1:
                return str(value)
            if isinstance(value, dict):
                return {key: browser_safe(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [browser_safe(item) for item in value]
            return value
        return super().dumps(browser_safe(obj), **kwargs)


def create_app(project_dir, retinanalysis_dir, *, service=None, store=None, explorer_history=None, data_stores=None, protocol_suggestions=None, shared_annotations=None):
    from workspace_service import WorkspaceService, WorkspaceNeedsRefresh
    from workspace_curation import CurationStore, RevisionConflict
    from workspace_explorer import ExplorerHistory
    from workspace_datastores import DataStores
    from workspace_suggestions import ProtocolSuggestions
    from workspace_tag_predicates import annotation_locks

    project_dir, retinanalysis_dir = Path(project_dir).resolve(), Path(retinanalysis_dir).resolve()
    app = Flask(__name__, static_folder=None)
    app.json = ExactMetadataJSON(app)
    app.config.update(MAX_CONTENT_LENGTH=16 * 1024**3, MAX_FORM_MEMORY_SIZE=1024**2)
    db_lock = threading.RLock()
    importing = threading.Lock()
    from workspace_import_progress import ProgressReporter, read_jobs, recover_jobs, progress_for, load_json
    owner_run_id = str(uuid.uuid4())
    active_jobs = set()
    recover_jobs(log_dir(project_dir, 'app-jobs'), owner_run_id)
    service = service or WorkspaceService(project_dir)
    store = store or CurationStore(service.dj, service.project["project_uuid"])
    storage = ManagedStorage(project_dir, service.project['project_uuid'], Path(__file__).resolve().parents[1])
    explorer_history = explorer_history or ExplorerHistory(service.dj, service.project['project_uuid'])
    app.extensions['explorer_history'] = explorer_history
    protocol_suggestions = protocol_suggestions or ProtocolSuggestions(service, explorer_history)
    app.extensions['protocol_suggestions'] = protocol_suggestions
    service.set_binding_provider(explorer_history.protocol_binding)
    store.binding_provider = explorer_history.protocol_binding
    data_stores = data_stores or DataStores(service, store, explorer_history)
    app.extensions["data_stores"] = data_stores
    service.set_source_state_provider(data_stores.source_states)
    if hasattr(service, 'set_annotation_provider'):
        service.set_annotation_provider(lambda protocol_uuid, fingerprints:
            store.read(protocol_uuid, list(fingerprints), fingerprints))
    if shared_annotations is None and hasattr(service.dj,'Schema'):
        from workspace_annotations import SharedAnnotations
        shared_annotations=SharedAnnotations(service)
    service.shared_annotations=shared_annotations
    app.extensions['shared_annotations']=shared_annotations
    frontend = Path(__file__).resolve().parents[1] / "workspace-app/dist"
    app.extensions["workspace_service"] = service
    app.extensions["curation_store"] = store

    def filters(allowed=()):
        if set(request.args) - {"cell_uuid", "cell_type", "group_label", "offset", "limit", "splits"} - set(allowed):
            raise ValueError("Unknown query filter; no unrestricted fallback was applied")
        return {key: request.args[key] for key in ("cell_uuid", "cell_type", "group_label")
                if request.args.get(key)}

    def state(protocol_uuid):
        result = service.query_result(protocol_uuid)
        fingerprints = service.fingerprints(protocol_uuid)
        for row in result["epochs"]:
            row["metadata_hash"] = fingerprints[row["uuid"]]
        result["metadata_fingerprint_version"] = 2
        result["source_scope"] = service.source_scope()
        if shared_annotations:
            result['shared_annotations_revision']=shared_annotations.snapshot()['revision']
        curation = store.read(protocol_uuid, list(fingerprints), fingerprints)
        revision = checksum({"query": {**result, "source_scope": {"revision": result["source_scope"]["revision"]}}, "curation": curation})
        return result, curation, revision

    def status(value):
        return {**value, "reviewed": value["review_state"] == "approved"}

    def enrich_protocol(payload, protocol_uuid, query_filters, export_memberships=None):
        result, curation, revision = state(protocol_uuid)
        rows = service.filtered_rows(protocol_uuid, query_filters)
        ids = [r["epoch_uuid"] for r in rows]
        payload["source_sha256s"] = sorted({row["source_sha256"] for row in rows})
        export_memberships = store.export_memberships() if export_memberships is None else export_memberships
        exported_ids = {key for key, links in export_memberships.items()
                        if any(link["protocol_uuid"] == protocol_uuid for link in links)}
        archived = set(result['source_scope']['excluded_source_revisions'])
        affected = [service.rows[row['uuid']] for row in result['epochs']
                    if service.rows[row['uuid']]['source_sha256'] in archived]
        payload['source_eligibility'] = {'excluded_epoch_count': len(affected),
            'excluded_sources': sorted({row['source_sha256'] for row in affected}),
            'propagation_required': bool(affected),
            'source_scope_revision': result['source_scope']['revision']}
        payload["query_revision"] = revision
        payload["expected_query_revision"] = revision
        payload["binding"] = compact_binding(result.get('dataset_binding'))
        payload["expected_binding_version"] = result.get('dataset_binding', {}).get('version', 0)
        starter = service.protocols[protocol_uuid]['definition']['query']
        payload["starter_query"] = starter
        payload["effective_query"] = result.get('effective_query', starter)
        payload["counts"].update(
            included=sum(curation[k]["included"] for k in ids),
            reviewed=sum(curation[k]["review_state"] == "approved" for k in ids),
            unreviewed=sum(curation[k]["review_state"] != "approved" for k in ids),
            exported=sum(key in exported_ids for key in ids),
            exportable=sum(curation[k]["included"] for k in ids),
            approved_exportable=sum(curation[k]["included"] and curation[k]["review_state"] == "approved" for k in ids))
        payload["counts"].update(approved=payload["counts"]["reviewed"],
                                 excluded=len(ids) - payload["counts"]["included"])
        if payload.get('cells'):
            cell_counts = summarize_cell_membership(rows,
                {key for key in ids if curation[key]['review_state'] == 'approved'}, exported_ids,
                {key for key in ids if curation[key]['included']})
            for cell in payload['cells']:
                cell.update(cell_counts[cell['cell_uuid']])
        if shared_annotations:
            summary=shared_annotations.summary(rows)
            payload['counts'].update({key:summary[key] for key in ('shared_tagged_cells','shared_tagged_epochs')})
            payload['annotation_summary']={key:summary[key] for key in ('tags','total_tags','truncated')}
            add_cell_annotations(payload.get('cells',[]))
        return payload

    def add_cell_annotations(cells):
        if not shared_annotations or not cells:return
        records={}
        for start in range(0,len(cells),1000):
            records.update(shared_annotations.read_targets('cell',[cell['cell_uuid'] for cell in cells[start:start+1000]]))
        for cell in cells:
            record=records[cell['cell_uuid']]
            cell['annotations']={'cell_tags':record['tags'],'revisions':record['revisions']}

    @app.before_request
    def local_boundary():
        if request.host.split(":")[0] not in {"127.0.0.1", "localhost"}:
            return jsonify(error="This workspace accepts local connections only."), 403
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("X-Workspace-Request") != "1":
                return jsonify(error="Missing workspace request header."), 403
            origin = request.headers.get("Origin")
            if origin and origin not in {"http://127.0.0.1:5173", "http://localhost:5173",
                                         "http://127.0.0.1:8766", "http://localhost:8766", request.host_url.rstrip("/")}:
                return jsonify(error="Unrecognized request origin."), 403

    @app.after_request
    def headers(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            if response.mimetype == 'application/json' and not response.direct_passthrough:
                response.vary.add('Accept-Encoding')
                if (request.method != 'HEAD' and not response.headers.get('Content-Encoding')
                        and request.accept_encodings['gzip'] > 0):
                    payload = response.get_data()
                    if len(payload) >= 4096:
                        compressed = gzip.compress(payload, compresslevel=1, mtime=0)
                        if len(compressed) < len(payload):
                            response.set_data(compressed)
                            response.headers['Content-Encoding'] = 'gzip'
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.errorhandler(Exception)
    def failure(error):
        if isinstance(error, HTTPException):
            return jsonify(error=error.description), error.code
        if isinstance(error, (RevisionConflict, StaleWorkspace)):
            return jsonify(error=str(error), code="stale_workspace"), 409
        if isinstance(error, WorkspaceNeedsRefresh):
            return jsonify(error=str(error), code='workspace_needs_refresh'), 500
        if isinstance(error, (ValueError, KeyError, FileNotFoundError)):
            return jsonify(error=str(error)), 400
        incident = str(uuid.uuid4())
        folder = log_dir(project_dir, 'errors')
        (folder / (incident + ".txt")).write_text(traceback.format_exc())
        app.logger.exception("Workspace error %s", incident)
        return jsonify(error="Operation failed. No success was recorded. See the local error log.",
                       incident=incident), 500

    @app.get("/api/health")
    def health():
        return jsonify(status="ready", project_uuid=service.project["project_uuid"])

    @app.get('/api/metadata/status')
    def metadata_status():
        return jsonify(status='ready' if service._loaded else 'needs_refresh',
                       last_refresh=getattr(service, 'last_successful_refresh', None),
                       latest_attempt=getattr(service, 'last_refresh', None))

    @app.post('/api/metadata/refresh')
    def refresh_metadata():
        if request.args or request.get_json(silent=True) != {}:
            raise ValueError('Metadata refresh accepts an empty JSON object')
        if not importing.acquire(blocking=False):
            raise StaleWorkspace('An import or metadata refresh is already running. Wait for it to finish.')
        started = time.perf_counter()
        try:
            with db_lock, data_stores.registration_locks():
                result = service.refresh()
                result = {**result, 'completed_at': now(),
                          'elapsed_seconds': round(time.perf_counter() - started, 3)}
                service.last_refresh = result
                service.last_successful_refresh = result
                warnings = []
                try:
                    record_event('metadata_refreshed', result)
                except Exception as error:
                    warnings.append('Metadata refreshed, but its SQL audit record could not be saved: ' + str(error))
                    app.logger.exception('Metadata refresh audit failed')
                return jsonify(refresh=result, warnings=warnings)
        except Exception as error:
            with db_lock:
                try:
                    record_event('metadata_refresh_failed', {'error': str(error),
                        'elapsed_seconds': round(time.perf_counter() - started, 3)}, outcome='failed')
                except Exception:
                    app.logger.exception('Failed metadata refresh could not be added to SQL history')
            raise
        finally:
            importing.release()

    from workspace_launcher import register_project_routes
    register_project_routes(app, retinanalysis_dir=retinanalysis_dir, project_dir=project_dir)

    @app.post('/api/project/display-name')
    def project_display_name():
        body = request.get_json()
        name = body.get('display_name') if isinstance(body, dict) else None
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
            raise ValueError('Project display name must contain 1–200 characters')
        with db_lock:
            path = project_dir / 'project.json'
            before = json.loads(path.read_text())
            if before.get('project_uuid') != service.project['project_uuid']:
                raise StaleWorkspace('Project identity changed; restart the workspace')
            after = {**before, 'display_name': name.strip()}
            if before != after:
                write_json(path, after)
                try:
                    record_event('project_display_name_changed', {'before': before.get('display_name', before.get('name')),
                        'after': name.strip()})
                except Exception:
                    write_json(path, before)
                    raise
                service.project = after
            return jsonify(project=after)

    @app.get('/api/storage')
    def storage_overview():
        return jsonify(storage.describe(service.config, service.sources))

    @app.get('/api/files')
    def project_files():
        if set(request.args) - {'path', 'offset', 'limit'}:
            raise ValueError('Unknown file inventory option')
        return jsonify(storage.files(request.args.get('path', ''),
                        int(request.args.get('offset', 0)), int(request.args.get('limit', 100))))

    @app.get('/api/data-stores')
    def data_store_inventory():
        if request.args:
            raise ValueError('Unknown data store inventory option')
        with db_lock, data_stores.registration_locks():
            return jsonify(data_stores.inventory())

    @app.get('/api/data-stores/<source_sha256>')
    def data_store_detail(source_sha256):
        if request.args:
            raise ValueError('Unknown data store detail option')
        with db_lock, data_stores.registration_locks():
            return jsonify(data_stores.detail(source_sha256))

    @app.get('/api/data-stores/<source_sha256>/events')
    def data_store_events(source_sha256):
        if set(request.args) - {'limit', 'offset'}:
            raise ValueError('Unknown source history pagination option')
        with db_lock, data_stores.registration_locks():
            return jsonify(data_stores.events(source_sha256, int(request.args.get('limit', 50)),
                                              int(request.args.get('offset', 0))))

    @app.post('/api/data-stores/<source_sha256>/state')
    def data_store_state(source_sha256):
        body = request.get_json()
        if request.args or not isinstance(body, dict) or set(body) - {'action', 'expected_version', 'actor', 'reason'} or isinstance(body, dict) and not {'action', 'expected_version', 'reason'} <= set(body):
            raise ValueError('Lifecycle changes require action, expected_version and reason; actor is an optional client claim')
        with db_lock:
            return jsonify(data_stores.transition(source_sha256, **body))

    def propagation_plan(source_sha256):
        plan = data_stores.propagation_preview(source_sha256)
        for item in plan['protocols']:
            _, _, query_revision = state(item['protocol_uuid'])
            if item.get('view_adaptation'):
                item['preview']['view_adaptation'] = copy.deepcopy(item['view_adaptation'])
            item['expected_query_revision'] = query_revision
            item['diff_counts'] = {key: len(value) for key, value in item['diff'].items()}
            item['next_count'] = item['preview']['matched_count']
            item['previous_count'] = item['next_count'] - item['diff_counts']['added'] + item['diff_counts']['removed']
            item['can_apply'] = any(item['diff_counts'].values())
            item['expected_preview_revision'] = checksum({
                'source_sha256': source_sha256, 'source_scope_revision': plan['source_scope']['revision'],
                'protocol_uuid': item['protocol_uuid'], 'query_revision': query_revision,
                'binding_version': item['binding_version'], 'predicate': item['predicate'],
                'splits': item['splits'], 'view_adaptation': item.get('view_adaptation'), 'membership': item['preview']['membership'], 'diff': item['diff']})
        return plan

    @app.post('/api/data-stores/<source_sha256>/propagation-preview')
    def preview_source_propagation(source_sha256):
        body = request.get_json()
        if request.args or body != {}:
            raise ValueError('Propagation preview takes an empty JSON object')
        with db_lock, data_stores.registration_locks():
            plan = propagation_plan(source_sha256)
            return jsonify({**plan, 'protocols': [{key: value for key, value in item.items()
                if key not in {'preview', 'expected_query_revision'}} for item in plan['protocols']]})

    @app.post('/api/data-stores/<source_sha256>/propagate')
    def apply_source_propagation(source_sha256):
        body = request.get_json()
        if (request.args or not isinstance(body, dict) or
                set(body) != {'protocol_uuid', 'expected_preview_revision'} or
                not isinstance(body['protocol_uuid'], str) or not isinstance(body['expected_preview_revision'], str)):
            raise ValueError('Propagation requires a protocol UUID and the exact preview revision')
        with db_lock, data_stores.registration_locks():
            service.refresh()
            plan = propagation_plan(source_sha256)
            item = next((item for item in plan['protocols'] if item['protocol_uuid'] == body['protocol_uuid']), None)
            if item is None or item['expected_preview_revision'] != body['expected_preview_revision']:
                raise StaleWorkspace('Source eligibility, data or curation changed. Preview propagation again before applying.')
            if not item['can_apply']:
                raise ValueError('This protocol is already up to date')
            record, saved = explorer_history.create_and_bind(item['preview'], service.sources,
                project_dir / 'catalog.json', os.environ.get('USER', 'local-user'),
                protocol_uuid=item['protocol_uuid'], expected_version=item['binding_version'],
                expected_query_revision=item['expected_query_revision'],
                current_query_revision=lambda: state(item['protocol_uuid'])[2],
                diff=item['diff'], previous_count=item['previous_count'], diff_summary=item['diff_summary'],
                name=item['name'], parent_revision_uuid=item['current_revision_uuid'])
            return jsonify(protocol_uuid=item['protocol_uuid'], revision_uuid=record['revision_uuid'],
                binding_version=saved['version'], event_uuid=saved['event_uuid'], diff_counts=item['diff_counts'],
                previous_count=item['previous_count'], next_count=item['next_count'])

    @app.get("/api/overview")
    def overview():
        with db_lock:
            payload = copy.deepcopy(service.overview())
            memberships = {}
            export_memberships = store.export_memberships()
            for protocol in payload["protocols"]:
                details = enrich_protocol({"counts": protocol["counts"]}, protocol["protocol_uuid"], {}, export_memberships)
                protocol.update(counts=details["counts"], query_revision=details["query_revision"], binding=details["binding"])
                _, decisions, _ = state(protocol["protocol_uuid"])
                for key, decision in decisions.items():
                    memberships.setdefault(key, []).append(decision)
            approved = {key for key, decisions in memberships.items()
                        if all(d["review_state"] == "approved" for d in decisions)}
            exported_ids = set(export_memberships) & set(service.rows)
            payload["counts"].update(exported=len(exported_ids), reviewed=len(approved), approved=len(approved),
                                     unreviewed=payload["counts"]["epochs"] - len(approved))
            cell_counts = summarize_cell_membership(service.rows.values(), approved, exported_ids)
            for cell in payload['cells']:
                cell.update(cell_counts[cell['cell_uuid']])
            add_cell_annotations(payload.get('cells',[]))
            if shared_annotations:
                summary=shared_annotations.summary(service.rows.values())
                payload['counts'].update({key:summary[key] for key in ('shared_tagged_cells','shared_tagged_epochs')})
                payload['annotation_summary']={key:summary[key] for key in ('tags','total_tags','truncated')}
            payload["exports"] = store.list_dataset_revisions()
            return jsonify(payload)

    @app.get('/api/tags')
    def tags():
        if set(request.args) - {'q','limit'} or any(len(request.args.getlist(key)) != 1 for key in request.args):
            raise ValueError('Tag suggestions accept one q and one limit parameter only')
        raw_limit = request.args.get('limit','30')
        if not raw_limit.isascii() or not raw_limit.isdecimal() or len(raw_limit)>3:
            raise ValueError('Tag suggestion limit must be an integer from 1 to 100')
        with db_lock:
            return jsonify(store.tag_suggestions(request.args.get('q',''),int(raw_limit)))

    @app.get("/api/protocols/<protocol_uuid>")
    def protocol(protocol_uuid):
        with db_lock:
            return jsonify(enrich_protocol(copy.deepcopy(service.protocol(protocol_uuid, filters())),
                                           protocol_uuid, filters()))

    def tree_layout_store():
        if 'tree_layouts' not in app.extensions:
            from workspace_tree_layouts import TreeLayouts
            app.extensions['tree_layouts'] = TreeLayouts(store)
        return app.extensions['tree_layouts']

    @app.route("/api/protocols/<protocol_uuid>/tree-layout", methods=["GET", "PUT"])
    def protocol_tree_layout(protocol_uuid):
        with db_lock:
            result = service.query_result(protocol_uuid)  # Validate project membership first.
            layouts = tree_layout_store()
            if request.args:
                raise ValueError('Tree layouts belong to the complete protocol, not a filtered cell')
            if request.method == 'GET':
                saved = layouts.read(protocol_uuid)
                if saved:
                    return jsonify(saved)
                definition = service.protocols[protocol_uuid]['definition']
                fallback = result.get('dataset_binding', {}).get('splits')
                fields = fallback.split(',') if fallback is not None else definition.get('view', {}).get('group_by', ['date', 'cell', 'block'])
                return jsonify(project_uuid=service.project['project_uuid'], protocol_uuid=protocol_uuid,
                               split_order=[field.strip() for field in fields if field.strip()], version=0)
            body = request.get_json()
            if not isinstance(body, dict) or set(body) != {'split_order', 'expected_version'}:
                raise ValueError('Tree layout requires split_order and expected_version')
            fields = body['split_order']
            if not isinstance(fields, list) or any(not isinstance(field, str) for field in fields):
                raise ValueError('Tree split order must be an array of field IDs')
            validated = service.validate_tree_splits(protocol_uuid, ','.join(fields))
            if validated != fields:
                raise ValueError('Tree fields must use their exact registered identifiers')
            return jsonify(layouts.save(protocol_uuid, fields, body['expected_version'],
                                        os.environ.get('USER', 'local-user')))

    @app.get("/api/protocols/<protocol_uuid>/epochs")
    def epoch_page(protocol_uuid):
        with db_lock:
            page = service.epoch_page(protocol_uuid, filters({'anchor_uuid'}), int(request.args.get("offset", 0)),
                                      int(request.args.get("limit", 80)), anchor_uuid=request.args.get('anchor_uuid'))
            _, curation, revision = state(protocol_uuid)
            page = copy.deepcopy(page)
            export_memberships = store.export_memberships()
            shared=shared_annotations.for_epochs([service.rows[row['epoch_uuid']] for row in page['epochs']]) if shared_annotations else {}
            for row in page["epochs"]:
                if shared:row['annotations']=shared[row['epoch_uuid']]
                row["curation"] = status(curation[row["epoch_uuid"]])
                row["export_count"] = len(export_memberships.get(row["epoch_uuid"], []))
            page["query_revision"] = revision
            return jsonify(page)

    @app.get("/api/protocols/<protocol_uuid>/tree")
    def tree(protocol_uuid):
        with db_lock:
            return jsonify(service.tree(protocol_uuid, filters(), request.args.get("splits", service.query_result(protocol_uuid).get("dataset_binding", {}).get("splits", "date, cell, block"))))

    @app.get("/api/protocols/<protocol_uuid>/tree-fields")
    def tree_fields(protocol_uuid):
        with db_lock:
            return jsonify(service.tree_fields(protocol_uuid, filters(), splits=request.args.get('splits')))

    @app.get("/api/explore/tree-fields")
    def explore_fields():
        with db_lock, data_stores.registration_locks():
            return jsonify(service.tree_fields(None, filters(), splits=request.args.get('splits')))

    @app.get("/api/explore/tree")
    def explore_tree():
        with db_lock, data_stores.registration_locks():
            return jsonify(service.tree(None, filters(), request.args.get("splits", "date,protocol,cell")))

    def explorer_request(allowed, required):
        if request.args:
            raise ValueError('Explorer predicate requests do not accept URL filters')
        if request.content_length is not None and request.content_length > 65536:
            raise ValueError('Predicate request exceeds 64 KiB')
        try:
            body = request.get_json()
        except (RecursionError, OverflowError) as error:
            raise ValueError('Predicate JSON nesting or numeric value exceeds limits') from error
        if not isinstance(body, dict) or set(body) - allowed or required - set(body):
            raise ValueError('Malformed explorer predicate request or unsupported fields')
        return body

    @app.get('/api/explore/predicate-fields')
    def explorer_predicate_fields():
        if request.args:
            raise ValueError('Predicate fields describe the whole main catalog')
        with db_lock, data_stores.registration_locks():
            return jsonify(service.predicate_fields())

    @app.post('/api/explore/preview')
    def explorer_preview():
        body = explorer_request({'predicate', 'splits', 'summary_only', 'baseline_revision_uuid', 'focused_uuid'}, {'predicate', 'splits'})
        if type(body.get('summary_only', False)) is not bool:
            raise ValueError('summary_only must be a boolean')
        for key in ('baseline_revision_uuid', 'focused_uuid'):
            if key in body:
                if not isinstance(body[key], str):
                    raise ValueError(key + ' must be a UUID string')
                body[key] = str(uuid.UUID(body[key]))
        with db_lock, data_stores.registration_locks(), annotation_locks(service, body['predicate']):
            preview = service.explore_preview(body['predicate'], body['splits'], include_tree=not body.get('summary_only', False))
            if 'baseline_revision_uuid' in body:
                baseline = explorer_history.get(body['baseline_revision_uuid'])['recipe']
                before = {item['uuid']: item['metadata_hash'] for item in baseline['epochs']}
                after = {item['uuid']: item['metadata_hash'] for item in preview['membership']}
                preview['baseline_diff'] = {'added': len(after.keys() - before.keys()), 'removed': len(before.keys() - after.keys()),
                    'changed': sum(before[key] != after[key] for key in before.keys() & after.keys())}
                if preview.get('annotation_scope') or baseline.get('annotation_scope'):
                    preview['baseline_diff']['annotation_changed'] = (preview.get('annotation_scope', {}).get('revision') != baseline.get('annotation_scope', {}).get('revision'))
            if 'focused_uuid' in body:
                focused = str(uuid.UUID(body['focused_uuid']))
                preview['focused_in_scope'] = any(item['uuid'] == focused for item in preview['membership'])
                preview['focused_uuid'] = focused
            return jsonify(compact_preview(preview) if body.get('summary_only') else preview)

    def compact_annotations(scope):
        result={**scope, 'protocols': [{**{key:value for key,value in protocol.items() if key != 'records'},
                                      'record_count': len(protocol['records']) if 'records' in protocol else protocol.get('record_count', 0)}
                                     for protocol in scope.get('protocols', [])]}
        if 'shared' in result:
            result['shared']={key:value for key,value in scope['shared'].items() if key!='records'}
            result['shared']['record_count']=len(scope['shared'].get('records',[]))
        return result

    def compact_binding(binding):
        if binding is None:
            return None
        return {**binding, **({'annotation_scope': compact_annotations(binding['annotation_scope'])}
                            if binding.get('annotation_scope') else {})}

    def compact_preview(preview):
        result = {key: value for key, value in preview.items() if key != 'membership'}
        if result.get('annotation_scope'):
            result['annotation_scope'] = compact_annotations(result['annotation_scope'])
        return result

    def compact_revision(result):
        recipe = result['recipe']
        compact = {**result, 'recipe': {**{key: value for key, value in recipe.items() if key not in {'epochs', 'diff', 'content_sha256'}},
                                    'summary_only': True, 'full_recipe_sha256': recipe.get('content_sha256'),
                                    'epoch_count': len(recipe['epochs'])}}
        if compact['recipe'].get('annotation_scope'):
            compact['recipe']['annotation_scope'] = compact_annotations(compact['recipe']['annotation_scope'])
        return compact

    @app.post('/api/explore/revisions')
    def explorer_apply():
        body = explorer_request({'predicate', 'splits', 'name', 'parent_revision_uuid', 'summary_only'}, {'predicate', 'splits'})
        if type(body.get('summary_only', False)) is not bool:
            raise ValueError('summary_only must be a boolean')
        with db_lock, data_stores.registration_locks(), annotation_locks(service, body['predicate']):
            service.refresh()
            preview = service.explore_preview(body['predicate'], body['splits'], include_tree=not body.get('summary_only', False))
            result = explorer_history.create(preview, service.sources, project_dir / 'catalog.json',
                os.environ.get('USER', 'local-user'), name=body.get('name'),
                parent_revision_uuid=body.get('parent_revision_uuid'))
            if body.get('summary_only'):
                preview['baseline_diff'] = {'added': 0, 'removed': 0, 'changed': 0}
            return jsonify(**(compact_revision(result) if body.get('summary_only') else result),
                           preview=compact_preview(preview) if body.get('summary_only') else preview), 201

    def search_preset_store():
        if 'search_presets' not in app.extensions:
            from workspace_search_presets import SearchPresets
            app.extensions['search_presets'] = SearchPresets(store)
        return app.extensions['search_presets']

    @app.post('/api/search-presets/resolve')
    def resolve_search_preset():
        body = explorer_request({'predicate'}, {'predicate'})
        with db_lock:
            validated, _, _ = service.match_predicate(body['predicate'], [])
            return jsonify(preset=search_preset_store().resolve(validated))

    @app.get('/api/search-presets/<preset_uuid>/versions')
    def search_preset_versions(preset_uuid):
        if set(request.args) - {'limit', 'offset'}:
            raise ValueError('Unsupported version pagination option')
        with db_lock:
            return jsonify(search_preset_store().versions(str(uuid.UUID(preset_uuid)),
                int(request.args.get('limit',20)), int(request.args.get('offset',0))))

    @app.post('/api/explore/run')
    def run_search_query():
        body = explorer_request({'predicate', 'splits'}, {'predicate', 'splits'})
        with db_lock, data_stores.registration_locks(), annotation_locks(service, body['predicate']):
            preview = service.explore_preview(body['predicate'], body['splits'], include_tree=False)
            result = search_preset_store().record_run(preview, service.rows, os.environ.get('USER', 'local-user'))
            return jsonify(**compact_preview(preview), last_run=result)

    @app.route('/api/search-presets', methods=['GET', 'POST'])
    @app.route('/api/search-presets/<preset_uuid>', methods=['GET', 'PUT'])
    def search_presets(preset_uuid=None):
        body = None
        if request.method != 'GET':
            if not request.is_json:
                raise ValueError('Saved query requests require JSON')
            raw = request.stream.read(65537)
            if len(raw) > 65536:
                raise ValueError('Saved query request exceeds 64 KiB')
            try:
                body = json.loads(raw)
            except (ValueError, RecursionError, OverflowError) as error:
                raise ValueError('Saved query JSON is invalid or exceeds nesting limits') from error
        with db_lock:
            presets = search_preset_store()
            if request.method == 'GET':
                if preset_uuid:
                    if request.args:
                        raise ValueError('Preset detail does not accept query options')
                    return jsonify(presets.read(preset_uuid))
                if set(request.args) - {'limit', 'offset'}:
                    raise ValueError('Unsupported preset pagination option')
                return jsonify(presets.list(int(request.args.get('limit', 100)), int(request.args.get('offset', 0))))
            if request.args:
                raise ValueError('Preset writes do not accept query options')
            presets.validate(body, update=preset_uuid is not None)
            # Validate query methods against the catalog without loading traces or
            # materializing any selection. Membership is always determined at run time.
            validated, _, _ = service.match_predicate(body['predicate'], [])
            fields = service.validate_tree_splits(None, body['splits'])
            body = {**body, 'predicate': validated, 'splits': ','.join(fields)}
            result = presets.save(body, os.environ.get('USER', 'local-user'), preset_uuid)
            return jsonify(result), 200 if preset_uuid or result.get('reused') else 201

    @app.get('/api/search-presets/<preset_uuid>/download')
    def download_search_preset(preset_uuid):
        if set(request.args) != {'version'} or len(request.args.getlist('version')) != 1:
            raise ValueError('Choose an exact saved query version to download')
        version = int(request.args['version'])
        with db_lock:
            presets = search_preset_store()
            presets.read(preset_uuid)
            rows = (presets.Version & dict(project_uuid=store.project_uuid,
                       preset_uuid=str(uuid.UUID(preset_uuid)), version=version)).to_dicts()
            if not rows:
                raise KeyError('Saved query version not found')
            response = jsonify(rows[0]['recipe'])
            response.headers['Content-Disposition'] = f'attachment; filename="query-{preset_uuid}-v{version}.json"'
            response.headers['Cache-Control'] = 'no-store'
            return response

    @app.get('/api/search-presets/<preset_uuid>/versions/<int:version>')
    def search_preset_version(preset_uuid, version):
        if request.args:
            raise ValueError('Preset versions do not accept query options')
        with db_lock:
            presets = search_preset_store()
            presets.read(preset_uuid)
            rows = (presets.Version & dict(project_uuid=store.project_uuid,
                       preset_uuid=str(uuid.UUID(preset_uuid)), version=version)).to_dicts()
            if not rows:
                raise KeyError('Saved query version not found')
            return jsonify(rows[0]['recipe'])

    @app.get('/api/explore/revisions')
    def explorer_revisions():
        if set(request.args) - {'limit', 'offset'}:
            raise ValueError('Unsupported revision pagination option')
        with db_lock:
            return jsonify(explorer_history.list(int(request.args.get('limit', 20)), int(request.args.get('offset', 0))))

    @app.get('/api/explore/revisions/<revision_uuid>')
    def explorer_revision(revision_uuid):
        if request.args and (set(request.args) != {'summary'} or request.args['summary'] != '1'):
            raise ValueError('Stored revisions do not accept evaluation options')
        with db_lock:
            result = explorer_history.get(revision_uuid)
            return jsonify(compact_revision(result) if request.args.get('summary') == '1' else result)

    def candidate_annotation_guard(revision_uuid, protocol_uuid=None):
        # Called only after db_lock and registration_locks have been entered.
        # Fetching this recipe also uses the shared, non-thread-safe SQL connection.
        recipe = explorer_history.get(revision_uuid)['recipe']
        return annotation_locks(service, recipe['predicate'],
                                extra_protocols=(protocol_uuid,) if protocol_uuid is not None else ())

    def validated_candidate(revision_uuid):
        record = explorer_history.get(revision_uuid)
        recipe = record['recipe']
        preview = service.explore_preview(recipe['predicate'], recipe['splits'])
        candidate = {row['uuid']: row['metadata_hash'] for row in recipe['epochs']}
        current_candidate = {row['uuid']: row['metadata_hash'] for row in preview['membership']}
        scope = preview['source_scope']
        if (recipe.get('annotation_scope', {}).get('revision') != preview.get('annotation_scope', {}).get('revision') or
                candidate != current_candidate or set(recipe['source_revisions']) !=
                set(scope['active_source_revisions']) or
                (recipe.get('source_scope', {}).get('revision') != scope['revision']
                 if recipe.get('source_scope') else bool(scope['excluded_source_revisions']))):
            raise StaleWorkspace('This saved source query is stale. Rerun it and save a new revision before applying.')
        return record, candidate

    def compare_protocol_candidate(revision_uuid, protocol_uuid):
        record, candidate = validated_candidate(revision_uuid)
        result, _, query_revision = state(protocol_uuid)
        compatibility = protocol_compatibility(service, protocol_uuid, candidate)
        binding = explorer_history.protocol_binding(protocol_uuid)
        previous = ({row['uuid']: row['metadata_hash'] for row in binding['recipe']['epochs']} if binding else
                    {row['uuid']: row['metadata_hash'] for row in result['epochs']})
        delta = {'added': sorted(candidate.keys() - previous.keys()),
                 'removed': sorted(previous.keys() - candidate.keys()),
                 'changed': sorted(key for key in candidate.keys() & previous.keys() if candidate[key] != previous[key])}
        return {'protocol_uuid': protocol_uuid, 'revision_uuid': revision_uuid,
                'previous_count': len(previous), 'next_count': len(candidate), 'diff': delta,
                'compatibility': compatibility,
                'diff_summary': summarize_diff(service.rows, previous, candidate),
                'diff_counts': {key: len(value) for key, value in delta.items()},
                'expected_binding_version': binding['version'] if binding else 0,
                'expected_query_revision': query_revision, 'binding': compact_binding(result.get('dataset_binding'))}

    @app.get('/api/explore/revisions/<revision_uuid>/protocol-options')
    def protocol_options(revision_uuid):
        if request.args:
            raise ValueError('Protocol choices do not accept query options')
        with db_lock, data_stores.registration_locks(), candidate_annotation_guard(revision_uuid):
            record, candidate = validated_candidate(revision_uuid)
            return jsonify(**selection_protocols(service, candidate),
                expected_recipe_sha256=record['recipe']['content_sha256'])

    @app.post('/api/explore/revisions/<revision_uuid>/create-protocol')
    def create_protocol_from_candidate(revision_uuid):
        from workspace_protocol_identity import create_pinned_protocol
        body = explorer_request({'name', 'protocol_id', 'expected_recipe_sha256'},
                                {'name', 'protocol_id', 'expected_recipe_sha256'})
        with db_lock, data_stores.registration_locks(), candidate_annotation_guard(revision_uuid):
            service.refresh()
            record, candidate = validated_candidate(revision_uuid)
            if body['expected_recipe_sha256'] != record['recipe']['content_sha256']:
                raise StaleWorkspace('The saved selection changed. Review it again before creating a protocol.')
            result = create_pinned_protocol(service, explorer_history, record, body['name'],
                                            body['protocol_id'], os.environ.get('USER', 'local-user'))
            return jsonify(result), 201 if result['created'] else 200

    @app.post('/api/explore/revisions/<revision_uuid>/compare-to-protocol')
    def compare_protocol_revision(revision_uuid):
        body = explorer_request({'protocol_uuid'}, {'protocol_uuid'})
        if not isinstance(body['protocol_uuid'], str):
            raise ValueError('Protocol identity must be a UUID string')
        with db_lock, data_stores.registration_locks(), candidate_annotation_guard(revision_uuid, body['protocol_uuid']):
            return jsonify(compare_protocol_candidate(revision_uuid, body['protocol_uuid']))

    @app.post('/api/explore/revisions/<revision_uuid>/apply-to-protocol')
    def apply_protocol_revision(revision_uuid):
        body = explorer_request({'protocol_uuid', 'expected_binding_version', 'expected_query_revision'},
                                {'protocol_uuid', 'expected_binding_version', 'expected_query_revision'})
        if not isinstance(body['protocol_uuid'], str) or type(body['expected_binding_version']) is not int:
            raise ValueError('Protocol UUID and integer expected binding version are required')
        with db_lock, data_stores.registration_locks(), candidate_annotation_guard(revision_uuid, body['protocol_uuid']):
            service.refresh()
            comparison = compare_protocol_candidate(revision_uuid, body['protocol_uuid'])
            if (body['expected_binding_version'] != comparison['expected_binding_version'] or
                    body['expected_query_revision'] != comparison['expected_query_revision']):
                raise StaleWorkspace('The protocol working dataset or curation changed. Compare again before applying.')
            require_protocol_compatibility(service, body['protocol_uuid'],
                [row['uuid'] for row in explorer_history.get(revision_uuid)['recipe']['epochs']])
            saved = explorer_history.bind(revision_uuid, body['protocol_uuid'], body['expected_binding_version'],
                os.environ.get('USER', 'local-user'), comparison['diff'], comparison['previous_count'],
                expected_query_revision=body['expected_query_revision'],
                current_query_revision=lambda: state(body['protocol_uuid'])[2],
                diff_summary=comparison['diff_summary'])
            protocol = enrich_protocol(copy.deepcopy(service.protocol(body['protocol_uuid'])), body['protocol_uuid'], {})
            return jsonify(binding=protocol['binding'], event_uuid=saved['event_uuid'], diff=comparison['diff'],
                           diff_counts=comparison['diff_counts'], previous_count=comparison['previous_count'],
                           next_count=comparison['next_count'], diff_summary=comparison['diff_summary'], protocol=protocol)

    @app.get("/api/epochs/<epoch_uuid>")
    def epoch(epoch_uuid):
        with db_lock:
            row = copy.deepcopy(service.epoch(epoch_uuid))
            protocol_uuid = request.args.get("protocol_uuid")
            if protocol_uuid:
                _, curation, _ = state(protocol_uuid)
                if epoch_uuid not in curation:
                    raise ValueError("Epoch is outside the protocol query")
                row["curation"] = status(curation[epoch_uuid])
            row["catalog_ref"] = {"database": service.config["database"],
                "project_uuid": service.project["project_uuid"], "protocol_uuid": protocol_uuid}
            links = store.epoch_exports(epoch_uuid)
            fingerprint_maps = {}
            for link in links:
                scope = (link["protocol_uuid"], link["metadata_fingerprint_version"])
                if scope not in fingerprint_maps:
                    try:
                        if scope[1] == 2:
                            fingerprint_maps[scope] = service.fingerprints(scope[0])
                        elif scope[1] == 1:
                            fingerprint_maps[scope] = {member["uuid"]: member["metadata_hash"]
                                for member in service.query_result(scope[0])["epochs"]}
                        else:
                            fingerprint_maps[scope] = {}
                    except KeyError:
                        fingerprint_maps[scope] = {}  # The historical protocol may no longer be loaded.
                current_hash = fingerprint_maps[scope].get(epoch_uuid)
                link["metadata_matches"] = current_hash == link["metadata_hash"] if current_hash else None
                link["download_url"] = "/api/exports/" + link["dataset_uuid"] + "/download"
            row["exports"] = links
            if shared_annotations:
                row['annotations']=shared_annotations.for_epochs([service.rows[epoch_uuid]])[epoch_uuid]
                row['annotations']['cell_epoch_count']=sum(item['cell_uuid']==row['cell_uuid'] for item in service.rows.values())
            return jsonify(row)

    @app.get("/api/epochs/<epoch_uuid>/trace")
    def trace(epoch_uuid):
        with db_lock:
            return jsonify(service.trace(epoch_uuid, request.args["stream_uuid"],
                                         int(request.args.get("start", 0)), int(request.args.get("count", 20000))))

    @app.post("/api/protocols/<protocol_uuid>/curation")
    def curate(protocol_uuid):
        body = request.get_json()
        ids = body["epoch_uuids"]
        if not isinstance(ids, list) or not ids or len(ids) > 10000 or len(set(ids)) != len(ids):
            raise ValueError("Choose a nonempty, unique list of epochs (at most 10,000).")
        with db_lock:
            if body.get("changes", {}).get("review_state") == "approved":
                service.refresh()
            result, _, revision = state(protocol_uuid)
            if body.get("query_revision") != revision:
                raise StaleWorkspace("The inspected query or metadata changed. Refresh before saving.")
            fingerprints = {r["uuid"]: r["metadata_hash"] for r in result["epochs"]}
            if set(ids) - fingerprints.keys():
                raise ValueError("Curation includes epochs outside this protocol query")
            changed = store.update(protocol_uuid, ids, body["changes"], body["expected_revisions"],
                                   {key: fingerprints[key] for key in ids}, os.environ.get("USER", "local-user"),
                                   audit_context={"query_revision": revision, "source_revisions": result["source_revisions"]},
                                   expected_binding_version=result.get("dataset_binding", {}).get("version", 0))
            return jsonify(changed)

    @app.get("/api/protocols/<protocol_uuid>/masks/export")
    def export_mask(protocol_uuid):
        if request.args:
            raise ValueError("Masks cover the entire protocol query; filtered mask exports are unsupported")
        with db_lock:
            service.refresh()
            result, curation, _ = state(protocol_uuid)
            response = jsonify(format="recording-selection-mask", version=1,
                               protocol_uuid=protocol_uuid,
                               source_revisions=sorted(set(result["source_revisions"])),
                               epochs=[{"epoch_uuid": key, "included": curation[key]["included"]}
                                       for key in sorted(curation)])
            response.headers['Content-Disposition'] = f'attachment; filename="recording-mask-{protocol_uuid[:8]}.json"'
            response.headers['Cache-Control'] = 'no-store'
            return response

    @app.post("/api/protocols/<protocol_uuid>/masks/import")
    def import_mask(protocol_uuid):
        if request.args:
            raise ValueError("Masks must cover the entire protocol query")
        body = request.get_json()
        if not isinstance(body, dict) or set(body) != {"mask", "query_revision"}:
            raise ValueError("Mask import requires exactly mask and query_revision")
        mask = body["mask"]
        if not isinstance(mask, dict) or set(mask) != {"format", "version", "protocol_uuid", "source_revisions", "epochs"}:
            raise ValueError("Malformed selection mask or unsupported fields")
        if (mask["format"] != "recording-selection-mask" or type(mask["version"]) is not int
                or mask["version"] != 1 or mask["protocol_uuid"] != protocol_uuid):
            raise ValueError("Unsupported mask format/version or different protocol")
        sources = mask["source_revisions"]
        if (not isinstance(sources, list) or any(not isinstance(value, str) or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value) for value in sources)
                or len(sources) != len(set(sources))):
            raise ValueError("Mask source revisions must be unique SHA256 strings")
        members = mask["epochs"]
        if not isinstance(members, list) or not members or len(members) > 10000:
            raise ValueError("A mask must contain 1–10,000 epochs and cover the complete protocol query")
        inclusion = {}
        for member in members:
            if (not isinstance(member, dict) or set(member) != {"epoch_uuid", "included"}
                    or not isinstance(member["epoch_uuid"], str) or type(member["included"]) is not bool):
                raise ValueError("Mask epochs require exactly epoch_uuid and a Boolean included value")
            identity = str(uuid.UUID(member["epoch_uuid"]))
            if identity != member["epoch_uuid"] or identity in inclusion:
                raise ValueError("Mask has a noncanonical or duplicate epoch UUID")
            inclusion[identity] = member["included"]
        with db_lock:
            service.refresh()
            result, current, revision = state(protocol_uuid)
            if body["query_revision"] != revision:
                raise StaleWorkspace("The query, source metadata, or curation changed. Refresh before importing the mask.")
            if set(sources) != set(result["source_revisions"]):
                raise ValueError("Mask source revisions differ from the current main database query")
            if set(inclusion) != set(current):
                raise ValueError("Mask must match exactly the current query membership; no partial import was applied")
            changed = store.update(protocol_uuid, sorted(inclusion), {},
                {key: current[key]["revision"] for key in inclusion},
                {row["uuid"]: row["metadata_hash"] for row in result["epochs"]},
                os.environ.get("USER", "local-user"), inclusion_by_epoch=inclusion,
                audit_context={"query_revision": revision, "source_revisions": result["source_revisions"],
                               "input_format": "recording-selection-mask", "input_version": 1},
                expected_binding_version=result.get("dataset_binding", {}).get("version", 0))
            _, _, new_revision = state(protocol_uuid)
            return jsonify(**changed, query_revision=new_revision,
                           imported_count=len(inclusion), included_count=sum(inclusion.values()))

    @app.post("/api/protocols/<protocol_uuid>/refresh")
    def refresh(protocol_uuid):
        with db_lock, data_stores.registration_locks():
            service.refresh()
            binding = explorer_history.protocol_binding(protocol_uuid)
            if binding:
                recipe = binding['recipe']
                preview = service.explore_preview(recipe['predicate'], recipe['splits'])
                candidate = explorer_history.create(preview, service.sources, project_dir / 'catalog.json',
                    os.environ.get('USER', 'local-user'), name=recipe['name'],
                    parent_revision_uuid=binding['revision_uuid'])
                _, _, working_revision = state(protocol_uuid)
                return jsonify(candidate_revision_uuid=candidate['revision_uuid'],
                    diff=candidate['recipe']['diff'], diff_counts=candidate['summary']['diff_counts'],
                    diff_summary=summarize_diff(service.rows,
                        {member['uuid']: member['metadata_hash'] for member in recipe['epochs']},
                        {member['uuid']: member['metadata_hash'] for member in candidate['recipe']['epochs']}),
                    query_revision=working_revision, working_dataset_unchanged=True,
                    candidate=candidate, preview=preview,
                    message='Saved source query rerun. Compare and apply the candidate to update this protocol.')
            definition = service.protocol(protocol_uuid)["definition"]
            result, _, revision = state(protocol_uuid)
            archived = set(result['source_scope']['excluded_source_revisions'])
            affected_source = next((service.rows[row['uuid']]['source_sha256'] for row in result['epochs']
                                    if service.rows[row['uuid']]['source_sha256'] in archived), None)
            if affected_source:
                item = next(item for item in propagation_plan(affected_source)['protocols']
                            if item['protocol_uuid'] == protocol_uuid)
                candidate = explorer_history.create(item['preview'], service.sources, project_dir / 'catalog.json',
                    os.environ.get('USER', 'local-user'), name=item['name'])
                return jsonify(candidate_revision_uuid=candidate['revision_uuid'], diff=item['diff'],
                    diff_counts=item['diff_counts'], diff_summary=item['diff_summary'], query_revision=revision,
                    working_dataset_unchanged=True, candidate=candidate, preview=item['preview'],
                    message='Source eligibility changed. Review the proposed dataset update before applying.')
            snapshot = capture_query(definition, result, str(project_dir / "catalog.json"))
            folder = project_dir / "query-snapshots" / protocol_uuid
            previous_files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime_ns)
            previous = json.loads(previous_files[-1].read_text()) if previous_files else None
            baseline_created = previous is None or previous.get("metadata_fingerprint_version", 1) != 2
            delta = {"added": [], "changed": [], "removed": []} if baseline_created else compare_query(previous, snapshot)
            save_snapshot(folder / (snapshot["snapshot_uuid"] + ".json"), snapshot)
            record_event("query_refreshed", {"protocol_uuid": protocol_uuid,
                         "snapshot_uuid": snapshot["snapshot_uuid"], "query_revision": revision,
                         "query_sha256": snapshot["query_sha256"], "source_revisions": snapshot["source_revisions"], "counts": {k: len(v) for k, v in delta.items()}})
            return jsonify(diff=delta, query_revision=revision, snapshot_uuid=snapshot["snapshot_uuid"],
                           baseline_created=baseline_created,
                           message="Comparison baseline created for source and ancestor metadata." if baseline_created else "Query refreshed.")

    def record_event(action, payload, *, operation_uuid=None, outcome="completed"):
        from recording_workspace import workspace_tables
        _, _, Event, _ = workspace_tables(service.dj)
        identity = str(uuid.uuid4())
        Event.insert1({"event_uuid": identity, "project_uuid": service.project["project_uuid"],
                       "occurred_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
                       "actor": os.environ.get("USER", "local-user"), "action": action,
                       "payload": build_audit_payload(action, os.environ.get("USER", "local-user"), payload,
                           operation_uuid=operation_uuid, outcome=outcome,
                           context={"project_uuid": service.project["project_uuid"]})})
        return identity

    @app.post("/api/protocols/<protocol_uuid>/exports")
    def export(protocol_uuid):
        body = request.get_json()
        if not isinstance(body, dict):
            raise ValueError('Export requires an options object')
        export_format = body.get('format', 'reference-json')
        if not isinstance(export_format, str) or export_format not in {'reference-json', 'epictree-mat', 'wheeler-sqlite'}:
            raise ValueError('Unsupported export format')
        with db_lock, data_stores.registration_locks(), (shared_annotations.lock() if shared_annotations else contextlib.nullcontext()):
            service.refresh()  # Recheck source identity and live query before publication.
            result, curation, revision = state(protocol_uuid)
            if body.get("query_revision") != revision:
                raise StaleWorkspace("The query or curation changed. Refresh before exporting.")
            require_protocol_compatibility(service, protocol_uuid, [row['uuid'] for row in result['epochs']])
            archived = set(result['source_scope']['excluded_source_revisions'])
            if any(service.rows[row['uuid']]['source_sha256'] in archived for row in result['epochs']):
                raise StaleWorkspace('This working dataset contains sources excluded from new queries. Propagate source changes before creating a new export. Saved exports are unchanged.')
            definition = service.protocol(protocol_uuid)["definition"]
            snapshot = capture_query(definition, {**result, 'source_revisions': result['source_scope']['active_source_revisions']}, str(project_dir / "catalog.json"))
            query_filters = body.get("filters", {})
            if not isinstance(query_filters, dict):
                raise ValueError("Export filters must be an object")
            split_order = body.get("split_order", result.get("dataset_binding", {}).get("splits", "date, cell, block"))
            if not isinstance(split_order, str):
                raise ValueError("Tree split order must be text")
            grouping = service.validate_tree_splits(protocol_uuid, split_order)
            field_catalog = {field["id"]: field for field in service.tree_fields(protocol_uuid, splits=split_order)["fields"]}
            rows = service.filtered_rows(protocol_uuid, query_filters)
            included = [r["epoch_uuid"] for r in rows if curation[r["epoch_uuid"]]["included"]]
            approved = [key for key, value in curation.items() if value["review_state"] == "approved"]
            naming = naming_options(body.get("name"), definition["name"], body.get("export_date"))
            recipe = prepare_export(snapshot, included, destination=export_format,
                       review_policy=body.get("review_policy", "include_unreviewed"), approved_ids=approved,
                       actor=os.environ.get("USER", "local-user"),
                       options={**naming, "filters": query_filters,
                                "split_order": split_order,
                                "tree_view": {"format": "recording-tree-view", "version": 1,
                                    "fields": [{key: field_catalog[field][key] for key in ("id", "label", "path", "category", "components") if key in field_catalog[field]}
                                               for field in grouping]}})
            output = project_dir / "exports" / recipe["export_uuid"]
            output.mkdir(parents=True, exist_ok=False)
            save_snapshot(output / "recipe.json", recipe)
            eligible = {r["uuid"] for r in recipe["epochs"]}
            package = {"format": "recording-reference-package", "version": 1,
                       "recipe": recipe, "epochs": [{**service.epoch(r["epoch_uuid"]),
                                    "curation": status(curation[r["epoch_uuid"]])} for r in rows
                                    if r["epoch_uuid"] in eligible],
                       "sources": [{"source_sha256": s["source_sha256"], "source_path": s["source_path"]}
                                   for s in service.sources if s['source_sha256'] in snapshot['source_revisions']],
                       "waveforms": "references-only; original H5 files must remain accessible"}
            if shared_annotations:
                annotations=shared_annotations.for_epochs([service.rows[item['epoch_uuid']] for item in package['epochs']])
                for item in package['epochs']:item['annotations']=annotations[item['epoch_uuid']]
            artifact = output / "recordings.json"
            write_json(artifact, package)
            try:
                if export_format == 'wheeler-sqlite':
                    from workspace_sqlite import build_sqlite_export
                    artifact = output / 'recordings.sqlite'
                    build_sqlite_export(package, artifact)
                elif export_format == 'epictree-mat':
                    from workspace_matlab import build_matlab_export
                    from workspace_matlab_masks import write_ugm
                    matlab = build_matlab_export(service, recipe, output / 'matlab', epoch_records=package['epochs'])
                    write_ugm(output / 'matlab' / 'selection.ugm', matlab['epoch_order'],
                        [True] * len(matlab['epoch_order']), metadata={
                            'project_uuid': recipe['project_uuid'], 'protocol_uuid': protocol_uuid,
                            'dataset_uuid': recipe['export_uuid'], 'export_uuid': recipe['export_uuid'],
                            'query_sha256': recipe['query_sha256'], 'recipe_sha256': recipe['content_sha256'],
                            'mat_file_basename': 'recordings',
                            'source_scope_revision': result['source_scope']['revision']})
                    write_json(output / 'matlab' / 'export-report.json', {key: value for key, value in matlab.items()
                        if key not in {'mat_path', 'launch_script_path', 'recipe_path'}})
                    (output / 'matlab' / 'README.txt').write_text(
                        'EpicTreeGUI handoff\n\nAdd EpicTreeGUI to your MATLAB path, then run launch_epictree.m.\n'
                        'tree_layout.m contains the same readable one-line command shown in Rieke OS.\n'
                        'launchWorkspaceTree.m resolves field IDs through this bundle; unavailable fields fail explicitly.\n'
                        'Run the copied command from this extracted bundle with EpicTreeGUI on your MATLAB path.\n'
                        'The line reconstructs grouping over this frozen export; it does not rerun the source query.\n'
                        'Grouping and exact epoch sequence come from recorded metadata; no LLM is called.\n'
                        'Original H5 files must remain accessible at their recorded paths; traces load on demand.\n'
                        'Use the current EpicTreeGUI checkout: workspace traces verify source SHA-256 before loading, with a cache for unchanged files.\n'
                        'selection.ugm contains this export only, matched by stable epoch UUID.\n'
                        'Save Epoch Mask updates this extracted bundle selection.ugm; reopening the generated command resumes it.\n'
                        'The original exported ZIP remains unchanged. Global latest-mask discovery is disabled for workspace bundles.\n'
                        'Save MATLAB selections as .ugm and explicitly import them in Rieke OS.\n'
                        'Tags and the exact query are frozen in recordings.json and matlab_recipe.json.\n'
                        'Existing exports and non-exported epochs are never overwritten by mask import.\n')
                    artifact = output / 'epictree-bundle.zip'
                    with zipfile.ZipFile(artifact, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
                        bundle.write(output / 'recordings.json', 'recordings.json')
                        bundle.write(output / 'recipe.json', 'recipe.json')
                        for member in sorted((output / 'matlab').iterdir()):
                            bundle.write(member, member.name)
                saved = store.record_dataset_revision(recipe, actor=os.environ.get("USER", "local-user"),
                    expected_revisions={k: v["revision"] for k, v in curation.items()},
                    artifact_path=str(artifact), artifact_sha256=digest(artifact))
            except Exception as error:
                write_json(output / "failure.json", {"at": now(), "status": "failed",
                           "error": str(error), "artifact_published": False})
                raise
            saved["format"] = export_format
            saved["download_url"] = "/api/exports/" + saved["dataset_uuid"] + "/download"
            return jsonify(saved), 201

    @app.get("/api/exports")
    def exports():
        with db_lock:
            return jsonify(exports=[{**row, "download_url": "/api/exports/" + row["dataset_uuid"] + "/download"}
                for row in store.list_dataset_revisions(request.args.get("protocol_uuid"))])

    @app.get("/api/exports/<dataset_uuid>/download")
    def download(dataset_uuid):
        with db_lock:
            record = store.get_dataset_revision(dataset_uuid)
        path = Path(record["artifact_path"]).resolve()
        if not path.is_relative_to(project_dir / "exports") or digest(path) != record["artifact_sha256"]:
            raise ValueError("Export artifact changed or is outside this project's exports")
        return send_file(path, as_attachment=True, download_name=export_download_name(record, path.suffix))

    @app.get("/api/exports/<dataset_uuid>/reuse")
    def reuse_export(dataset_uuid):
        with db_lock:
            record = store.get_dataset_revision(dataset_uuid)
            recipe = record["recipe"]
            scope = recipe.get('options', {}).get('export_scope')
            if scope and scope.get('kind') == 'explorer_candidate':
                from workspace_candidate_exports import candidate_scope_uuid
                saved = explorer_history.get(scope['revision_uuid'])['recipe']
                expected_scope = candidate_scope_uuid(service.project['project_uuid'], scope['revision_uuid'])
                if (recipe['protocol_uuid'] != expected_scope or scope.get('export_only_scope_uuid') != expected_scope
                        or saved['content_sha256'] != scope.get('candidate_recipe_sha256')
                        or recipe['query_snapshot'].get('export_scope') != scope
                        or recipe['query'].get('predicate') != saved['predicate']):
                    raise ValueError('Saved candidate export scope failed integrity validation')
                return jsonify(kind='explorer_candidate', candidate_revision_uuid=scope['revision_uuid'],
                    export_scope=scope, query=recipe['query'],
                    split_order=recipe['options']['split_order'],
                    export_intent={'name': recipe['options']['name'], 'format':recipe['destination']},
                    source_export_uuid=dataset_uuid, review_required=True)
            definition = service.protocol(recipe["protocol_uuid"])["definition"]
            effective = service.query_result(recipe["protocol_uuid"]).get("effective_query", definition["query"])
            if checksum(effective) != recipe["query_sha256"]:
                raise StaleWorkspace("This protocol's query definition changed. The saved export retains its original query; it cannot be silently replaced.")
            options = recipe.get("options", {})
            return jsonify(protocol_uuid=recipe["protocol_uuid"], format=recipe.get("destination", "reference-json"), query=recipe["query"],
                           filters=options.get("filters", {}), review_policy=recipe["review"]["policy"],
                           split_order=options.get("split_order", "date, cell, block"),
                           name=options.get("name", definition["name"]), source_export_uuid=dataset_uuid)

    @app.get("/api/events")
    def events():
        if set(request.args) - {"limit", "offset", "action"}:
            raise ValueError("Unknown history filter")
        with db_lock:
            page = service.event_page(int(request.args.get("limit", 50)), int(request.args.get("offset", 0)),
                                      request.args.get("action"))
            page["suggestions"] = repeat_suggestions(page["events"])
            page["events"] = [{key: value for key, value in row.items() if key not in {"payload", "provenance"}}
                              for row in normalize_events(page["events"])]
            return jsonify(page)

    @app.get("/api/events/<event_uuid>")
    def event_details(event_uuid):
        with db_lock:
            return jsonify(event=normalize_event(service.event_detail(event_uuid)))

    @app.get('/api/protocol-suggestions')
    def pending_protocol_suggestions():
        if request.args:
            raise ValueError('Protocol suggestions do not accept query filters')
        with db_lock:
            return jsonify(protocol_suggestions.list())

    @app.get("/api/jobs")
    def jobs():
        # No SQL or global database lock: polling remains responsive while the
        # parser/importer works. Heartbeat means monitor connectivity only.
        return jsonify(jobs=read_jobs(log_dir(project_dir, 'app-jobs'), owner_run_id, active_jobs))

    def import_job(source, job_file):
        progress_file = job_file.parent / 'progress' / (job_file.stem + '.json')
        reporter = ProgressReporter(progress_file)
        job = {'source': str(source), 'owner_run_id': owner_run_id, 'catalog_committed': False}
        try:
            job.update(load_json(job_file))
            job.update(status="checking_duplicates", started_at=now(), catalog_committed=False,
                       progress_path=str(progress_file))
            write_json(job_file, job)
            reporter.emit('checking_duplicates', completed=0, total=source.stat().st_size, unit='bytes')
            def registered_sources():
                with db_lock:
                    return data_stores.Source.to_dicts()
            check = classify_source(source, registered_sources, reporter.emit)
            job.update(source_sha256=check['source_sha256'], source_size=check['source_size'],
                       duplicate_check={'algorithm': 'sha256', 'same_name_warnings': check['same_name_warnings']})
            if check['duplicate']:
                duplicate = check['duplicate']
                if duplicate.get('project_uuid') != service.project['project_uuid']:
                    raise ValueError('This exact file is already registered to another project; explicit linking is required.')
                job.update(status='duplicate', finished_at=now(), existing_source=duplicate,
                           message='Already imported. No parsing or new catalog records; registration and query participation are unchanged.')
                reporter.emit('duplicate', outcome='completed', catalog_committed=False)
                if job.get('managed_upload'):
                    upload_root = (project_dir / 'raw-uploads').resolve()
                    if source.parent.parent.resolve() != upload_root or source.parent.name != job.get('upload_directory_uuid'):
                        raise ValueError('Duplicate staging cleanup path failed validation')
                    try:
                        source.unlink()
                        source.parent.rmdir()
                        job['duplicate_staging_removed'] = True
                    except OSError as cleanup_error:
                        job['duplicate_staging_removed'] = False
                        job['staging_cleanup_error'] = str(cleanup_error)
                return
            job.update(status='freezing_baselines')
            reporter.emit('freezing_baselines')
            write_json(job_file, job)
            with db_lock, data_stores.registration_locks():
                service.refresh()
                baselines = protocol_suggestions.freeze_baselines(os.environ.get('USER', 'local-user'), state)
            job['protocol_baselines'] = [{key: baseline[key] for key in
                ('protocol_uuid', 'revision_uuid', 'binding_version')} for baseline in baselines]
            job.update(status='validating')
            write_json(job_file, job)
            log_file = job_file.with_suffix(".log")
            job['log_path'] = str(log_file)
            command = [sys.executable, str(Path(__file__).with_name("recording_workspace.py")), str(source),
                       "--project-dir", str(project_dir), "--retinanalysis", str(retinanalysis_dir),
                       "--progress-file", str(progress_file), "--expected-sha256", check['source_sha256']]
            with log_file.open("w") as log:
                job['catalog_committed'] = None
                completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
            child, progress_error = progress_for(job_file, job)
            if child:
                reporter.current = child
            if completed.returncode:
                with log_file.open('rb') as log:
                    log.seek(0, 2)
                    log.seek(max(0, log.tell() - 8192))
                    tail = log.read().decode('utf-8', errors='replace')
                reason = (child or {}).get('error') or next((line for line in reversed(tail.splitlines()) if line.startswith('Import stopped: ')), None)
                reason = reason or ('Import process stopped. Details: ' + str(log_file))
                known_failure = child and child.get('stage') == 'failed' and child.get('outcome') == 'failed'
                committed = True if child and child.get('commit_state') == 'committed' else child.get('catalog_committed') if known_failure else None
                job.update(catalog_committed=committed,
                    diagnostics={'stage': (child or {}).get('workflow_stage', (child or {}).get('stage', 'subprocess')),
                        'error_type': (child or {}).get('error_type', 'ImportProcessStopped'), 'message': reason,
                        'traceback_path': (child or {}).get('traceback_path')})
                if committed is True:
                    job.update(status='complete_with_warnings', requires_reconciliation=True,
                        warnings=[{'stage': 'workspace_finalization', 'message': reason}], finished_at=now(),
                        message='Catalog committed, but workspace finalization needs attention. Check Data stores and diagnostics; do not assume the source rolled back.')
                    return
                if committed is not False:
                    job.update(status='interrupted', error=reason, requires_reconciliation=True, finished_at=now())
                    return
                raise ValueError(reason)
            job.update(status='refreshing_workspace', catalog_committed=True, warnings=[])
            reporter.emit('refreshing_workspace', commit_state='committed', catalog_committed=True)
            write_json(job_file, job)
            try:
                with db_lock, data_stores.registration_locks():
                    service.refresh()
                    job['status'] = 'rerunning_protocols'
                    reporter.emit('rerunning_protocols')
                    write_json(job_file, job)
                    proposals = protocol_suggestions.rerun(baselines, check['source_sha256'],
                        source.name, os.environ.get('USER', 'local-user'))
                job['protocol_suggestions'] = proposals['counts']
                job['warnings'].extend(proposals['warnings'])
            except Exception as query_error:
                job['warnings'].append({'stage': 'post_import_refresh', 'message': str(query_error)})
                app.logger.exception('Import succeeded; post-import query suggestions could not complete')
            job.update(status='complete_with_warnings' if job['warnings'] else 'complete', finished_at=now())
            reporter.emit('complete', outcome='completed', commit_state='committed', catalog_committed=True)
        except Exception as error:
            error_message = str(error) or f'{type(error).__name__} during {reporter.current.get("stage", "job setup")}; inspect import diagnostics.'
            committed = job.get('catalog_committed')
            job.update(status='complete_with_warnings' if committed is True else 'interrupted' if committed is None else 'failed',
                       error=error_message, finished_at=now(),
                       diagnostics={'stage': reporter.current.get('stage', 'job_log'),
                           'error_type': type(error).__name__, 'message': error_message})
            if committed is True:
                job.setdefault('warnings', []).append({'stage': 'post_commit', 'message': error_message})
            elif committed is None:
                job['requires_reconciliation'] = True
            reporter.emit('failed', outcome='failed', error=error_message, error_type=type(error).__name__,
                catalog_committed=committed, commit_state='committed' if committed is True else 'unknown' if committed is None else 'not_started')
        finally:
            try:
                with db_lock:
                    record_event("import_job_" + job.get("status", 'interrupted'), {"job_file": str(job_file), **job},
                                 operation_uuid=job_file.stem,
                                 outcome="completed" if job.get("status") in {"complete", "complete_with_warnings", "duplicate"} else "failed")
            except Exception as audit_error:
                job["audit_write_error"] = str(audit_error)
                app.logger.exception("Import job could not be added to SQL action history")
            try:
                write_json(job_file, job)
            except Exception as persistence_error:
                app.logger.exception('Could not persist terminal import job; durable child progress may require reconciliation')
                reporter.emit('failed', outcome='failed', error='Terminal job log could not be saved: ' + str(persistence_error),
                    catalog_committed=job.get('catalog_committed'),
                    commit_state='committed' if job.get('catalog_committed') is True else 'unknown')
            finally:
                active_jobs.discard(job_file.stem)
                importing.release()

    @app.post("/api/imports")
    def import_recording():
        if not importing.acquire(blocking=False):
            raise StaleWorkspace("An import is already running. Its progress is shown in Imports.")
        try:
            for old in read_jobs(log_dir(project_dir, 'app-jobs'), owner_run_id, active_jobs):
                if old.get('status') != 'interrupted':
                    continue
                progress = old.get('progress') or {}
                pid = progress.get('pid')
                if type(pid) is int and pid > 0 and pid != os.getpid() and progress.get('stage') not in {'complete', 'failed', 'duplicate'}:
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        continue
                    except PermissionError:
                        pass
                    raise StaleWorkspace('An earlier import child may still be running. Check Data stores and the interrupted job diagnostics before starting another import.')
            managed_upload, upload_directory_uuid = False, None
            if request.files:
                if set(request.files) != {'file'} or len(request.files.getlist('file')) != 1 or request.form:
                    raise ValueError('Upload exactly one recording file without additional fields')
                upload = request.files["file"]
                name = secure_filename(upload.filename or "")
                if Path(name).suffix.lower() not in {".h5", ".hdf5"}:
                    raise ValueError("Select a Symphony .h5 recording")
                managed_upload, upload_directory_uuid = True, str(uuid.uuid4())
                folder = project_dir / "raw-uploads" / upload_directory_uuid
                folder.mkdir(parents=True)
                source = folder / name
                upload.save(source)
            else:
                body = request.get_json(silent=True)
                if not isinstance(body, dict) or set(body) != {'source_path'} or not isinstance(body['source_path'], str) or not body['source_path'].strip():
                    raise ValueError('Provide exactly one nonempty source_path string or upload one recording')
                source = Path(body["source_path"]).expanduser().resolve()
            if not source.is_file() or source.suffix.lower() not in {".h5", ".hdf5"}:
                raise ValueError("Choose an existing .h5 recording file")
            identity = str(uuid.uuid4())
            job_file = log_dir(project_dir, 'app-jobs') / (identity + ".json")
            write_json(job_file, {"status": "queued", "source": str(source), "created_at": now(),
                                  "managed_upload": managed_upload, "upload_directory_uuid": upload_directory_uuid,
                                  "owner_run_id": owner_run_id, "catalog_committed": False})
            active_jobs.add(identity)
            threading.Thread(target=import_job, args=(source, job_file), daemon=True).start()
            return jsonify(job_uuid=identity, status="queued"), 202
        except Exception:
            if 'identity' in locals():
                active_jobs.discard(identity)
            if importing.locked():
                importing.release()
            raise

    @app.get("/")
    @app.get("/<path:path>")
    def ui(path="index.html"):
        if path.startswith("api/"):
            return jsonify(error="Unknown API endpoint"), 404
        if not frontend.exists():
            return "Build workspace-app first with npm run build.", 503
        return send_from_directory(frontend, path)

    if shared_annotations:
        from workspace_annotations import register_annotation_routes
        register_annotation_routes(app,service,shared_annotations,db_lock)
        from workspace_tag_exchange import register_tag_exchange_routes
        register_tag_exchange_routes(app,service,shared_annotations,db_lock)
    from workspace_qc import register_qc_routes
    register_qc_routes(app, service, db_lock)
    from workspace_search import register_search_routes
    register_search_routes(app, service, db_lock)

    from workspace_matlab_routes import register_matlab_mask_routes
    register_matlab_mask_routes(app, service, store, state, db_lock)
    from workspace_tree_pages import register_tree_page_routes
    register_tree_page_routes(app, service, db_lock, data_stores.registration_locks)
    from workspace_matching_epochs import register_matching_epoch_routes
    register_matching_epoch_routes(app, service, db_lock, data_stores.registration_locks, explorer_request)
    from workspace_candidate_exports import register_candidate_export_routes
    register_candidate_export_routes(app, service, store, explorer_history, db_lock, data_stores.registration_locks)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--retinanalysis", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    try:
        app = create_app(args.project_dir, args.retinanalysis)
    except Exception:
        failure = log_dir(args.project_dir, 'errors') / ('startup-' + str(uuid.uuid4()) + '.txt')
        failure.write_text(traceback.format_exc())
        raise
    handler = RotatingFileHandler(log_dir(args.project_dir, 'app-jobs') / 'server.log',
                                  maxBytes=5 * 1024 * 1024, backupCount=3)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    app.logger.addHandler(handler)
    logging.getLogger('werkzeug').addHandler(handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Workspace started; managed project directory: %s', args.project_dir.resolve())
    from workspace_project_servers import write_server_record
    write_server_record(args.project_dir, app.extensions["workspace_service"].project["project_uuid"], args.port)
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
