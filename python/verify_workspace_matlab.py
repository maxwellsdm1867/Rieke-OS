"""Repeatable local generator integration check, without publishing research exports.

Reads a managed project's starter protocol query, freezes a disposable export
using the production writer, then runs its generated scripts in the native harness.
This tests generator contracts, not the current applied dataset/curation selection;
HTTP export tests cover those saved-query and inclusion boundaries separately.
Requires the project's normal DataJoint environment and a licensed MATLAB install.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from workspace_matlab import build_matlab_export
from workspace_matlab_masks import write_ugm
from workspace_recipes import capture_query, prepare_export
from workspace_service import WorkspaceService
from workspace_tree import value_key


def prepare(project_dir, protocol_uuid, output_dir, splits=None):
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    service = WorkspaceService(str(Path(project_dir).resolve()))
    result = service.query_result(protocol_uuid)
    result['epochs'] = [{**item, 'metadata_hash': service._fingerprints[item['uuid']]}
                        for item in result['epochs']]
    result['metadata_fingerprint_version'] = 2
    if splits is None:
        suggested = service.tree_fields(protocol_uuid).get('suggested_layout')
        splits = ','.join(suggested['fields'] if suggested else ['date', 'cell', 'block'])
    fields = service.validate_tree_splits(protocol_uuid, splits)
    snapshot = capture_query(service.protocol(protocol_uuid)['definition'], result,
                             str(service.project_dir / 'catalog.json'))
    identities = [item['uuid'] for item in result['epochs']]
    recipe = prepare_export(snapshot, identities, destination='epictree-mat',
                            review_policy='include_unreviewed', actor='isolated-generator-verification',
                            options={'split_order': splits})
    bundle = output / 'bundle'
    exported = build_matlab_export(service, recipe, bundle,
                                  epoch_records=[service.epoch(key) for key in identities])
    write_ugm(bundle / 'selection.ugm', exported['epoch_order'], [True] * len(identities),
              metadata={'dataset_uuid': recipe['export_uuid']})
    tree = service.tree(protocol_uuid, splits=splits)
    leaves = []

    def collect(node, path):
        if 'value' in node:
            path = [*path, '<not recorded>' if node.get('missing') else value_key(node['value'])]
        if 'epoch_uuids' in node:
            # Sequence matters: deliberately do NOT sort UUIDs here.
            leaves.append({'path': path, 'epochs': node['epoch_uuids']})
        for child in node.get('children', []):
            collect(child, path)

    collect(tree, [])
    oracle = {'epoch_count': len(identities), 'fields': fields, 'leaves': leaves,
              'verification_scope': 'starter protocol query; isolated generator fixture'}
    (bundle / 'expected-tree.json').write_text(json.dumps(oracle, indent=2))
    (bundle / 'recipe.json').write_text(json.dumps(recipe, indent=2))
    archive = output / 'generated-bundle.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
        for member in sorted(bundle.iterdir()):
            zipped.write(member, member.name)
    extracted = output / "extracted bundle's files"
    # All archive members above are generated, flat filenames under our own folder.
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(extracted)
    return extracted


def matlab_string(value):
    value = str(value)
    if any(char in value for char in '\r\n\x00'):
        raise ValueError('MATLAB verification paths must be single-line paths')
    return "'" + value.replace("'", "''") + "'"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir', required=True)
    parser.add_argument('--protocol', required=True, help='Protocol UUID in the managed project')
    parser.add_argument('--splits', help='Exact saved split order; defaults to suggested layout')
    parser.add_argument('--output', help='New directory for disposable bundle and evidence')
    parser.add_argument('--matlab', default=shutil.which('matlab'), help='MATLAB executable')
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if not args.prepare_only and not args.matlab:
        parser.error('Pass --matlab /path/to/matlab or --prepare-only')
    output = Path(args.output) if args.output else Path(tempfile.mkdtemp(prefix='rieke-generator-check-')) / 'verification'
    bundle = prepare(args.project_dir, args.protocol, output, args.splits)
    print(f'Isolated starter-query generator fixture (not a published or curated export): {bundle}', flush=True)
    if args.prepare_only:
        return
    repo = Path(__file__).resolve().parents[1]
    command = f"addpath(genpath({matlab_string(repo)})); proof=verify_workspace_generated_bundle({matlab_string(bundle)}); disp(jsonencode(proof));"
    # Arguments are passed directly, not interpreted by a shell.
    subprocess.run([args.matlab, '-batch', command], check=True)


if __name__ == '__main__':
    main()
