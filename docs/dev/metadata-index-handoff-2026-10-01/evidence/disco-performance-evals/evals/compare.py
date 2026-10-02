"""Compare like-for-like raw receipts. No tail percentile estimates from small n."""
import argparse
import json
from pathlib import Path
import statistics


def metrics(receipt, family):
    result = {}
    def add(name, samples, **extra):
        if samples:
            result[name] = {'median_ms': statistics.median(samples) * 1000,
                            'first_ms': samples[0] * 1000, 'max_ms': max(samples) * 1000,
                            'warm_median_ms': statistics.median(samples[1:]) * 1000 if len(samples) > 1 else None,
                            'n': len(samples), **extra}
    if family == 'browser':
        chronological = {}
        for row in receipt.get('measurements', []):
            chronological.setdefault(row['name'], []).append(row['sample_ms'] / 1000)
        for name, samples in chronological.items():
            add(name, samples)
    elif family == 'trace':
        for row in receipt:
            prefix = f"trace_{row['fixture_payload_mib']}mib"
            add(prefix + '_warm_window', row['warm_trace_seconds'])
            add(prefix + '_first_integrity_window', [row['first_uncached_integrity_trace_seconds']])
    else:
        operations = receipt.get('operations', [])
        if isinstance(operations, dict):
            operations = [{'name': name, **row} for name, row in operations.items()]
        for row in operations:
            add(row['name'], row.get('samples_seconds', row.get('warm_samples_seconds', [])),
                bytes=row.get('bytes', row.get('response_json_bytes')))
        for name, seconds in receipt.get('phases', {}).items():
            if isinstance(seconds, (int, float)):
                add('setup_' + name, [seconds])
        for name in ('seed_seconds', 'populated_native_startup_seconds', 'durable_snapshot_verify_seconds'):
            if name in receipt:
                add('setup_' + name, [receipt[name]])
    return result


def valid(receipt, family):
    if family == 'browser':
        return not receipt.get('errors') and bool(receipt.get('summary'))
    if family == 'trace':
        return all(row.get('same_size_mutation_rejected') and row['first_full_hash_calls'] == 1
                   and row['warm_full_hash_calls'] == 0 for row in receipt)
    return receipt.get('passed') is True and all(row.get('passed') for row in receipt.get('checks', []))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--family', choices=('native', 'browser', 'tags', 'trace'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--relative-margin', type=float, default=.20)
    parser.add_argument('--absolute-margin-ms', type=float, default=20)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text())
    candidate = json.loads(args.candidate.read_text())
    a, b = metrics(baseline, args.family), metrics(candidate, args.family)
    correctness = valid(baseline, args.family) and valid(candidate, args.family)
    rows = []
    for name in sorted(a.keys() | b.keys()):
        old, new = a.get(name), b.get(name)
        row = {'name': name, 'baseline': old, 'candidate': new}
        if old is None or new is None:
            row['status'] = 'missing_measurement'
        else:
            delta = new['median_ms'] - old['median_ms']
            threshold = max(args.absolute_margin_ms, old['median_ms'] * args.relative_margin)
            row.update(delta_ms=delta, speedup=old['median_ms'] / new['median_ms'] if new['median_ms'] else None,
                       regression_threshold_ms=threshold,
                       status='regression' if delta > threshold else 'within_margin')
            row['small_sample_warning'] = min(old['n'], new['n']) < (5 if args.family == 'browser' else 10)
            row['single_observation_setup'] = name.startswith('setup_') or 'first_integrity' in name or 'initial_tree' in name
            if row['single_observation_setup']:
                row['status'] = 'descriptive_slowdown' if delta > threshold else 'descriptive_within_margin'
            first_delta = new['first_ms'] - old['first_ms']
            row['first_use_delta_ms'] = first_delta
            row['first_use_slowdown_warning'] = first_delta > max(50, old['first_ms'] * .25)
            row['first_use_warning_scope'] = 'Single first observation; repeat fresh processes before a verdict.'
        rows.append(row)
    report = {'family': args.family, 'baseline': str(args.baseline), 'candidate': str(args.candidate),
              'correctness_passed': correctness,
              'policy': 'Median regression requires both >20% and >20ms by default; setup/first timings are descriptive single observations.',
              'measurements': rows,
              'regressions': [r['name'] for r in rows if r['status'] == 'regression'],
              'descriptive_slowdowns': [r['name'] for r in rows if r['status'] == 'descriptive_slowdown'],
              'missing_measurements': [r['name'] for r in rows if r['status'] == 'missing_measurement']}
    report['passed'] = correctness and not report['regressions'] and not report['missing_measurements']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'correctness_passed': correctness,
                      'regressions': report['regressions'], 'missing': report['missing_measurements']}))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
