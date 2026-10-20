"""Stage, materialize and mark one frozen export; callers keep scientific authority.

``stage_export`` owns the export folder lifecycle shared by the protocol,
saved-candidate and incoming-workbench exports: fresh directory, recipe.json,
reference JSON (or linked package preparation), format materialization and the
failure.json marker. Callers keep validation, locks, membership, package
contents, freshness rechecks and publication (passed in as ``publish``).
``materialize_export_format`` remains the narrow format tail.
"""
from pathlib import Path

FAILURE_MARKER = 'failure.json'


def stage_export(output, recipe, *, format, build_package, publish, matlab_writer,
                 write_json, save_snapshot, now, linked_sources=None, failure_fields=None):
    """Return ``publish(artifact)``; on any failure write the marker and re-raise.

    ``output`` must not exist. Its creation stays outside the catch: a folder
    this call did not create never receives a failure marker. ``build_package()``
    returns the caller's frozen reference package. For ``linked-sqlite``,
    ``linked_sources`` is ``(manifests, project_root, grouping_sources)``.
    ``write_json``/``save_snapshot``/``now`` are the caller's strict writers and
    clock, so existing failure seams stay where callers and tests expect them.
    A marker write that raises OSError never replaces the original error.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    try:
        save_snapshot(output / 'recipe.json', recipe)
        package = build_package()
        if format == 'linked-sqlite':
            from workspace_linked_sqlite import prepare_linked_package
            manifests, project_root, grouping_sources = linked_sources
            package = prepare_linked_package(package, manifests, project_root,
                                             grouping_sources=grouping_sources)
        else:
            write_json(output / 'recordings.json', package)
        artifact = materialize_export_format(package, output, format=format,
            matlab_writer=matlab_writer, write_json=write_json)
        return publish(artifact)
    except Exception as error:
        try:
            write_json(output / FAILURE_MARKER, {'at': now(), 'status': 'failed', 'error': str(error),
                       'artifact_published': False, **(failure_fields or {})})
        except OSError:
            pass  # Preserve the original failure; publication did not succeed.
        raise


def materialize_export_format(package, output, *, format, matlab_writer, write_json):
    """Return the selected artifact, propagating adapter errors unchanged.

    ``matlab_writer(recipe, output_dir, *, epoch_records)`` is caller-bound and
    lazy. ``write_json`` is the caller's existing strict atomic JSON writer.
    The output directory, recipe and reference JSON are already staged.
    """
    if format == 'reference-json':
        return output / 'recordings.json'
    if format == 'linked-sqlite':
        from workspace_linked_sqlite import build_linked_export_bundle
        return build_linked_export_bundle(package, output)
    if format == 'wheeler-sqlite':
        from workspace_sqlite import build_sqlite_export
        artifact = output / 'recordings.sqlite'
        build_sqlite_export(package, artifact)
        from disco.decisions.external_tags import prepare_return_folder
        prepare_return_folder(output, package)
        return artifact
    if format == 'matlab-mat':
        matlab_dir = output / 'matlab'
        result = matlab_writer(package['recipe'], matlab_dir, epoch_records=package['epochs'])
        write_json(matlab_dir / 'export-report.json', {key: value for key, value in result.items()
            if key not in {'mat_path', 'recipe_path'}})
        return Path(result['mat_path'])
    raise ValueError('Unsupported export format')
