"""Existing HTTP mutation completion policy, separate from command transactions."""

from flask import jsonify, request


def register_mutation_recovery(app, scheduler, *, desktop_mode):
    """Register once, at the existing recovery position in app composition.

    ``scheduler.status()`` returns the current independent backup status;
    ``scheduler.flush()`` synchronously checkpoints or raises. ``desktop_mode``
    is a zero-argument boolean callable evaluated per request, preserving runtime
    environment changes. Annotation status errors propagate as before; only flush
    failures receive the existing saved-to-database HTTP 507 translation.

    This adapter classifies existing routes; it does not establish database
    commits or universal replay support. Register after response headers so the
    reverse Flask callback order applies those headers to replacement responses.
    """
    @app.after_request
    def backup_saved_state(response):
        if request.endpoint in {'annotation_update','annotation_undo'} and 200<=response.status_code<300:
            # Rows and their immutable event are already committed together.
            # The post-commit callback queued the independent recovery mirror.
            result=response.get_json()
            result['persistence']={'database':'committed','backup':scheduler.status()}
            response.set_data(app.json.dumps(result))
            return response
        # These POST handlers only read state. Default to checkpointing all
        # other writes, including idempotent/no-op mutations: a previous
        # committed write may still need protection after a backup failure.
        # In particular, explore/run records last-run state and is a write.
        read_posts = {'explorer_preview', 'explorer_summaries', 'explorer_summary_cancel', 'explorer_query_page', 'tree_page', 'matching_epochs',
            'annotation_batch_read', 'curation_batch_read', 'tag_import_preview',
            'preview_source_propagation', 'resolve_search_preset',
            'compare_protocol_revision'}
        read_posts.update({'workbench_preview', 'workbench_tree_page', 'workbench_candidate_summary'})
        read_posts.update({'group_annotation_preview', 'group_annotation_preview_release'})
        readonly = request.method == 'POST' and request.endpoint in read_posts
        desktop_control = desktop_mode() and request.path.startswith('/api/desktop/')
        if not readonly and not desktop_control and request.path not in {'/api/project/close', '/api/projects/unmount'} and request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and 200 <= response.status_code < 300:
            try:
                scheduler.flush()
            except Exception:
                app.logger.exception('App state was saved to SQL but its recovery snapshot failed')
                payload = dict(error='Saved to the database, but the app-state backup failed. '
                    'Check project disk space and permissions before closing the app.', saved=True)
                if request.endpoint in {'group_annotation_apply', 'group_annotation_undo'}:
                    # A receipt exists in SQL even if the independent mirror
                    # failed. Keep exact-operation recovery unambiguous;
                    # replay must traverse this same synchronous flush hook.
                    payload.update(code='recovery_unconfirmed',
                        operation_uuid=request.get_json()['operation_uuid'],
                        persistence=dict(database='committed', backup=scheduler.status()))
                failure = jsonify(payload)
                failure.status_code = 507
                return failure
        return response
