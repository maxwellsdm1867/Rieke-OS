#!/usr/bin/env python3
"""Attach immutable native research evidence; does not grant release qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()

def infrastructure(name):
    return (name.startswith(('benchmarks/', 'docs/', 'python/tests/', 'desktop/tests/', 'desktop/e2e/', 'workspace-app/src/test-support/'))
            or name in {'AGENTS.md', 'README.md', 'tools/benchmark.py', 'tools/benchmark_native.py', 'workspace-app/src/benchmarkNavigation.mjs'}
            or (name.startswith('workspace-app/src/') and name.endswith('.test.js')))

def evidence_file(root, name):
    path = root / name
    if Path(name).is_absolute() or '..' in Path(name).parts or path.resolve() != root.resolve() / name or not path.is_file():
        raise ValueError('Evidence must be a regular file without traversal or symlinks')
    return path

def attach(repo, evidence, measured, candidate, source, reports):
    measured = git(repo, 'rev-parse', '--verify', '--end-of-options', measured + '^{commit}')
    candidate = git(repo, 'rev-parse', '--verify', '--end-of-options', candidate + '^{commit}')
    # Inspect deletions and additions separately: rename detection can hide a
    # production source path when its destination is an allowed docs/test path.
    changed = git(repo, 'diff', '--no-renames', '--name-only', measured, candidate).splitlines()
    if any(not infrastructure(name) for name in changed):
        raise ValueError('Production differs from measured commit; native evidence cannot transfer')
    if json.loads(evidence_file(evidence, source).read_text()).get('commit') != measured:
        raise ValueError('Native source receipt does not identify measured commit')
    if not reports or source in reports or len(set(reports)) != len(reports):
        raise ValueError('Require distinct report paths and source receipt')
    files = {name: hashlib.sha256(evidence_file(evidence, name).read_bytes()).hexdigest() for name in [source, *reports]}
    return {'format':'rieke-native-evidence-attachment', 'schema_version':1,
            'measured_commit':measured, 'candidate_commit':candidate, 'source_receipt':source,
            'reports':reports, 'files':files, 'changed_infrastructure':changed,
            'status':'integrity_verified_not_qualification', 'release_qualified':False,
            'scope':'Research reports only; content, authority, stability and cleanup claims require independent review.'}

def verify(attachment, repo, evidence):
    expected = attach(repo, evidence, attachment['measured_commit'], attachment['candidate_commit'],
                      attachment['source_receipt'], attachment['reports'])
    if attachment != expected:
        raise ValueError('Native attachment provenance or bytes changed')
    return expected

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--measured-commit'); parser.add_argument('--candidate-commit')
    parser.add_argument('--source-receipt'); parser.add_argument('--report', action='append')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.verify:
            verify(json.loads(args.verify.read_text()), ROOT, args.evidence_root)
        else:
            if not all((args.measured_commit, args.candidate_commit, args.source_receipt, args.report, args.output)):
                parser.error('Attachment requires commits, source receipt, reports and output')
            result = attach(ROOT, args.evidence_root, args.measured_commit, args.candidate_commit, args.source_receipt, args.report)
            with args.output.open('x') as stream: stream.write(json.dumps(result, indent=2) + '\n')
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(1, str(exc) + '\n')

if __name__ == '__main__': main()
