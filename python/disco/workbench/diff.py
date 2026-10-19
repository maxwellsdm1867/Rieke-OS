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


def summarize_additions(rows, profile, added, detail_limit=100):
    """``summarize_diff`` for an additive change, from the previous revision's profile.

    ``profile`` holds the previous members' per-cell [count, representative rank]
    and protocol/duration totals, so the cost is O(added + touched cells), not
    O(previous). The result equals ``summarize_diff(rows, previous, previous | added)``.
    """
    if type(detail_limit) is not int or not 1 <= detail_limit <= 100:
        raise ValueError('Diff detail limit must be 1–100')
    if set(added) - rows.keys():
        raise ValueError('Diff membership refers to unavailable source metadata')
    current = {'epochs': profile['epochs'], 'cells': len(profile['cells']),
               'acquisition_protocols': len(profile['protocols']), 'duration_seconds': profile['duration']}
    touched = {}
    protocols = set(profile['protocols'])
    duration = profile['duration']
    for key in added:
        row = rows[key]
        entry = touched.setdefault(row['cell_uuid'], [0, None])
        entry[0] += 1
        rank = (row.get('date', ''), row.get('start_time', ''), key)
        if entry[1] is None or rank < entry[1]:
            entry[1] = rank
        protocols.add(row['protocol_name'])
        duration += row['duration_seconds']
    following = {'epochs': profile['epochs'] + len(added), 'cells': len(profile['cells'].keys() | touched.keys()),
                 'acquisition_protocols': len(protocols), 'duration_seconds': duration}
    groups = {'added': [], 'removed': [], 'updated': []}
    for identity, (count, rank) in touched.items():
        before, before_rank = profile['cells'].get(identity, (0, None))
        best = min(rank, before_rank) if before_rank is not None else rank
        representative = rows[best[2]]
        groups['added' if not before else 'updated'].append({'cell_uuid': identity,
            'label': representative.get('cell_label'), 'date': representative.get('date'),
            'cell_type': representative.get('cell_type'), 'epoch_count': before + count,
            'previous_epoch_count': before, 'proposed_epoch_count': before + count, 'epochs_added': count,
            'epochs_removed': 0, 'epochs_changed': 0})
    for entries in groups.values():
        entries.sort(key=lambda row: (row['date'] or '', row['label'] or '', row['cell_uuid']))
    return {'current': current, 'proposed': following,
            'delta': {key: following[key] - current[key] for key in current},
            'cell_changes': {**{key: entries[:detail_limit] for key, entries in groups.items()},
                'counts': {key: len(entries) for key, entries in groups.items()},
                'truncated': {key: len(entries) > detail_limit for key, entries in groups.items()},
                'detail_limit': detail_limit}}
