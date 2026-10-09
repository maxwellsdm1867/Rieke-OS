"""Materialize a frozen export after its caller stages the reference package.

Callers retain scientific validation, locks, failure reports and publication.
This helper neither copies the package nor claims that an artifact is published.
"""
from pathlib import Path


def materialize_export_format(package, output, *, format, matlab_writer, write_json):
    """Return the selected artifact, propagating adapter errors unchanged.

    ``matlab_writer(recipe, output_dir, *, epoch_records)`` is caller-bound and
    lazy. ``write_json`` is the caller's existing strict atomic JSON writer.
    The output directory, recipe and reference JSON already belong to the caller.
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
