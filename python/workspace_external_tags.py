"""Receive immutable tag messages beside registered exports; never mutate exports."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import os
import tempfile
import uuid

from workspace_tag_exchange import MAX_BYTES, canonical, identity, preview_import

FORMAT = 'rieke-external-tags'


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(canonical(value)); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def prepare_return_folder(output, package):
    """Describe a writable sidecar without changing the frozen artifact."""
    output = Path(output)
    recipe = package['recipe']
    (output / 'annotations/incoming').mkdir(parents=True, exist_ok=True)
    targets = {}
    for row in package['epochs']:
        for kind in ('cell', 'epoch'):
            key = (kind, row[kind + '_uuid'])
            entry = dict(target_kind=kind, target_uuid=key[1], source_sha256=row['source_sha256'])
            if key in targets and targets[key] != entry:
                raise ValueError('Conflicting source identity in annotation return targets')
            targets[key] = entry
    manifest = dict(format='rieke-annotation-return', version=1,
                    project_uuid=recipe['project_uuid'], export_uuid=recipe['export_uuid'],
                    incoming='annotations/incoming', receipts='annotations/receipts',
                    targets=list(targets.values()),
                    instructions='Write complete rieke-external-tags v1 JSON messages here. '
                    'The project app scans on open and while running. Keep recordings.sqlite unchanged. '
                    'Copied exports need their messages delivered to the original project export folder.')
    if targets:
        manifest['message_example'] = dict(format=FORMAT, version=1,
            message_uuid=str(uuid.uuid4()), export_uuid=recipe['export_uuid'],
            document=dict(format='rieke-tag-exchange', version=1, project_uuid=recipe['project_uuid'],
                entries=[{**next(e for e in targets.values() if e['target_kind']=='epoch'), 'tags':[dict(tag='publication:example',
                    profile_uuid=str(uuid.uuid5(uuid.NAMESPACE_URL, 'rieke:external-actor:Wheeler')),
                    author_name='Wheeler')]}]))
        manifest['instructions'] += ' Use a fresh message UUID for each submission, and the same profile UUID for each author.'
    atomic_json(output / 'annotation-return.json', manifest)
    return manifest


def submit_tags(export_folder, entries, *, author_name, profile_uuid, message_uuid=None):
    """Actor helper: entries contain target_kind, target_uuid and a list of tag strings."""
    folder = Path(export_folder)
    manifest = json.loads((folder / 'annotation-return.json').read_text())
    if manifest.get('format') != 'rieke-annotation-return' or manifest.get('version') != 1:
        raise ValueError('Unsupported annotation return manifest')
    registry = {(e['target_kind'], e['target_uuid']): e for e in manifest['targets']}
    normalized = []
    for entry in entries:
        target = registry[(entry['target_kind'], identity(entry['target_uuid']))]
        normalized.append({**target, 'tags': [dict(tag=tag, profile_uuid=identity(profile_uuid),
                                                  author_name=author_name) for tag in entry['tags']]})
    message = dict(format=FORMAT, version=1, message_uuid=identity(message_uuid or str(uuid.uuid4())),
                   export_uuid=manifest['export_uuid'],
                   document=dict(format='rieke-tag-exchange', version=1,
                                 project_uuid=manifest['project_uuid'], entries=normalized))
    if len(canonical(message).encode()) > MAX_BYTES: raise ValueError('Tag message exceeds 8 MiB')
    path = folder / 'annotations/incoming' / (message['message_uuid'] + '.json')
    if path.exists():
        if json.loads(path.read_text()) != message: raise ValueError('Message UUID already has different content')
    else:
        # Unique message names avoid actor contention. Publish without overwriting an existing message.
        fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as handle:
                handle.write(canonical(message)); handle.flush(); os.fsync(handle.fileno())
            os.link(temporary, path)
        finally:
            os.unlink(temporary)
    return str(path)


class ExternalTags:
    def __init__(self, service, exports, annotations):
        self.service, self.exports, self.annotations = service, exports, annotations
        self.root = Path(service.project_dir).resolve() / 'exports'
        self.offsets = {}

    def receipts(self):
        rows = (self.annotations.Event & dict(project_uuid=self.service.project['project_uuid'],
                                              action='external_annotation_received')).to_dicts()
        return {row['payload']['receipt']['message_uuid']:
                {**row['payload']['receipt'], 'event_uuid': row['event_uuid']}
                for row in rows}

    def receive(self, message, record, receipts):
        if not isinstance(message, dict) or message.get('format') != FORMAT or type(message.get('version')) is not int or message['version'] != 1:
            raise ValueError('Expected rieke-external-tags version 1')
        message_id = identity(message.get('message_uuid'))
        export_id = identity(message.get('export_uuid'))
        if export_id != record['dataset_uuid']: raise ValueError('Message belongs to another export')
        content_hash = hashlib.sha256(canonical(message).encode()).hexdigest()
        old = receipts.get(message_id)
        if old:
            if old['content_sha256'] != content_hash: raise ValueError('Message UUID reused with different content')
            return old
        doc = message.get('document')
        if not isinstance(doc, dict) or doc.get('format') != 'rieke-tag-exchange' or doc.get('project_uuid') != self.service.project['project_uuid']:
            raise ValueError('Tag document must name this project')
        recipe = record['recipe']
        members = {row['uuid'] for row in recipe['epochs']}
        rows = [self.service.rows[key] for key in members if key in self.service.rows]
        targets = {(kind, row[kind + '_uuid']): row['source_sha256']
                   for row in rows for kind in ('epoch', 'cell')}
        if not isinstance(doc.get('entries'), list) or not doc['entries']:
            raise ValueError('A message must contain tag additions')
        for entry in doc['entries']:
            if not isinstance(entry, dict): raise ValueError('Invalid tag entry')
            key = (entry.get('target_kind'), entry.get('target_uuid'))
            if key not in targets: raise ValueError('Target is not registered in this export; retry after registration')
            if entry.get('source_sha256') != targets[key] or targets[key] not in recipe['source_revisions']:
                raise ValueError('Tag source differs from registered export')
        preview = preview_import(doc, self.service, self.annotations)
        if not preview['profiles']: raise ValueError('A message must contain authored tags')
        receipt = dict(message_uuid=message_id, export_uuid=export_id, content_sha256=content_hash,
                       addition_count=preview['addition_count'], unchanged_count=preview['unchanged_count'],
                       authors=preview['profiles'], received_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                       status='received')
        result = self.annotations.apply_batch(preview['operations'], actor='External tag receiver',
            profiles=preview['profiles'], audit_context={'operation': 'external_tag_return',
            'export_uuid': export_id, 'message_uuid': message_id, 'attribution': 'file_claim'},
            external_receipt=receipt)
        receipt = {**receipt, 'event_uuid': result['event_uuid']}
        receipts[message_id] = receipt
        return receipt

    def scan(self):
        statuses = []
        ready = getattr(self.service, '_ready', None)
        if ready: ready()
        with self.annotations.lock():
            receipts = self.receipts()
            for summary in self.exports.list_dataset_revisions():
                export_id = identity(summary['dataset_uuid'])
                folder = self.root / export_id
                state = dict(export_uuid=export_id, name=summary.get('name',export_id),
                             path=str(folder / 'annotations/incoming'), errors=[], pending=0)
                try:
                    if folder.resolve() != folder or not folder.is_dir():
                        raise ValueError('Export folder unavailable or redirected')
                    incoming = folder / 'annotations/incoming'
                    if (folder / 'annotations').resolve() != folder / 'annotations':
                        raise ValueError('Annotation folder must not redirect outside the export')
                    record = self.exports.get_dataset_revision(export_id)
                    if not incoming.exists() and summary.get('format') == 'wheeler-sqlite':
                        # Existing registered exports gain sidecars without rewriting the artifact.
                        members = [row['uuid'] for row in record['recipe']['epochs']]
                        if any(key not in self.service.rows for key in members):
                            raise ValueError('Export targets are not registered; retry after registration')
                        prepare_return_folder(folder, dict(recipe=record['recipe'],
                            epochs=[self.service.rows[key] for key in members]))
                    if not incoming.exists():
                        state['status'] = 'not_enabled'; statuses.append(state); continue
                    if incoming.resolve() != incoming: raise ValueError('Annotation folder must not redirect outside the export')
                    paths = sorted(incoming.glob('*.json'))
                    # Rotate bounded batches so a large or failing folder cannot starve later messages.
                    start = self.offsets.get(export_id, 0) % max(1, len(paths))
                    paths = paths[start:] + paths[:start]
                    self.offsets[export_id] = start + min(100, len(paths))
                    state['pending'] = max(0, len(paths) - 100)
                    for path in paths[:100]:
                        try:
                            if path.is_symlink() or not path.is_file(): raise ValueError('Expected a regular message file')
                            with path.open('rb') as handle: raw = handle.read(MAX_BYTES + 1)
                            if len(raw) > MAX_BYTES: raise ValueError('Tag message exceeds 8 MiB')
                            message = json.loads(raw)
                            if not isinstance(message, dict) or path.stem != identity(message.get('message_uuid')):
                                raise ValueError('Filename must match message UUID')
                            receipt = self.receive(message, record, receipts)
                            destination = folder / 'annotations/receipts'
                            if destination.resolve() != destination: raise ValueError('Receipt folder must not redirect')
                            target = destination / path.name
                            try:
                                saved = None if target.is_symlink() else json.loads(target.read_text())
                            except (OSError, ValueError):
                                saved = None
                            if saved != receipt:
                                atomic_json(target, receipt)
                        except (ValueError, KeyError, TypeError, OSError, RecursionError) as error:
                            state['errors'].append(dict(file=path.name, error=str(error)))
                    state['status'] = 'needs_attention' if state['errors'] else 'watching'
                except (ValueError, KeyError, TypeError, OSError) as error:
                    state['status'] = 'unavailable'; state['errors'].append(dict(error=str(error)))
                statuses.append(state)
            ordered = sorted(receipts.values(), key=lambda item: (item['received_at'], item['message_uuid']))
            return dict(revision=self.annotations.change_revision(), exports=statuses,
                        received_tag_count=sum(item['addition_count'] for item in ordered),
                        latest_import=next((item for item in reversed(ordered) if item['addition_count']>0),None),
                        receipts=ordered[-20:], receipt_count=len(ordered),
                        checked_at=dt.datetime.now(dt.timezone.utc).isoformat())


def register_external_tag_routes(app, service, exports, annotations, db_lock):
    from flask import jsonify
    receiver = ExternalTags(service, exports, annotations)
    app.extensions['external_tags'] = receiver

    @app.post('/api/annotations/scan')
    def scan_tags():
        with db_lock:
            return jsonify(receiver.scan())


def main():
    import argparse
    parser=argparse.ArgumentParser(description='Submit external tags beside a Rieke SQLite export.')
    parser.add_argument('export_folder')
    parser.add_argument('--author', required=True)
    parser.add_argument('--profile-uuid', help='Stable author UUID; defaults to a deterministic UUID from author name')
    parser.add_argument('--target-kind', choices=('epoch','cell'), default='epoch')
    parser.add_argument('--uuid', action='append', required=True, dest='targets')
    parser.add_argument('--tag', action='append', required=True, dest='tags')
    args=parser.parse_args()
    profile=args.profile_uuid or str(uuid.uuid5(uuid.NAMESPACE_URL, 'rieke:external-actor:'+args.author))
    print(submit_tags(args.export_folder, [dict(target_kind=args.target_kind,target_uuid=key,tags=args.tags)
                                          for key in args.targets], author_name=args.author,profile_uuid=profile))


if __name__ == '__main__': main()
