"""Compact, exact membership comparisons for the protocol review interface."""
from __future__ import annotations


def summarize_diff(rows, previous, proposed, detail_limit=100):
    """Summarize two UUID→fingerprint maps against verified source metadata.

    Counts cover every member. Only the descriptive cell lists are truncated;
    adding epochs to an existing cell never increments the added-cell count.
    """
    if type(detail_limit) is not int or not 1 <= detail_limit <= 100:
        raise ValueError('Diff detail limit must be 1–100')
    if (set(previous) | set(proposed)) - rows.keys():
        raise ValueError('Diff membership refers to unavailable source metadata')

    def counts(members):
        selected = [rows[key] for key in members]
        return {'epochs': len(selected), 'cells': len({row['cell_uuid'] for row in selected}),
                'acquisition_protocols': len({row['protocol_name'] for row in selected}),
                'duration_seconds': sum(row['duration_seconds'] for row in selected)}

    def cells(members):
        result = {}
        for key in members:
            result.setdefault(rows[key]['cell_uuid'], set()).add(key)
        return result

    old_cells, new_cells = cells(previous), cells(proposed)
    current, following = counts(previous), counts(proposed)
    additions = set(proposed) - set(previous)
    removals = set(previous) - set(proposed)
    changes = {key for key in set(previous) & set(proposed) if previous[key] != proposed[key]}
    groups = {'added': [], 'removed': [], 'updated': []}
    for identity in old_cells.keys() | new_cells.keys():
        before, after = old_cells.get(identity, set()), new_cells.get(identity, set())
        kind = 'added' if not before else 'removed' if not after else 'updated'
        if kind == 'updated' and before == after and not after & changes:
            continue
        representative = rows[min(after or before, key=lambda key: (
            rows[key].get('date', ''), rows[key].get('start_time', ''), key))]
        groups[kind].append({'cell_uuid': identity, 'label': representative.get('cell_label'),
            'date': representative.get('date'), 'cell_type': representative.get('cell_type'),
            'epoch_count': len(after if after else before), 'previous_epoch_count': len(before),
            'proposed_epoch_count': len(after), 'epochs_added': len(after & additions),
            'epochs_removed': len(before & removals), 'epochs_changed': len(after & changes)})
    for entries in groups.values():
        entries.sort(key=lambda row: (row['date'] or '', row['label'] or '', row['cell_uuid']))
    return {'current': current, 'proposed': following,
            'delta': {key: following[key] - current[key] for key in current},
            'cell_changes': {**{key: entries[:detail_limit] for key, entries in groups.items()},
                'counts': {key: len(entries) for key, entries in groups.items()},
                'truncated': {key: len(entries) > detail_limit for key, entries in groups.items()},
                'detail_limit': detail_limit}}
