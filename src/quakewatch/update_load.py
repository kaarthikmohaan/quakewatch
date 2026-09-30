"""Load one complete sweep and atomically advance its local committed watermark."""

import argparse
from collections import Counter
from contextlib import closing
import fcntl
import json
from pathlib import Path

from quakewatch.extract_batch import iso_utc, parse_utc
from quakewatch.history_load_plan import check_snowflake
from quakewatch.raw_load import connect_project, execute_raw_load, plan_raw_load, LoadReconciliationError
from quakewatch.update_plan import plan_update_sweep


def validate_sweep(plan):
    """Require complete origin-time coverage and matching per-window local counts."""
    m = plan['manifest']
    if (m.get('batch_kind') != 'update_sweep' or m.get('status') != 'complete'
            or m.get('coverage_gaps')):
        raise LoadReconciliationError('a complete update sweep is required')
    expected = plan_update_sweep(
        parse_utc(m['catalog_lower_bound']), parse_utc(m['origin_time_cutoff']),
        parse_utc(m['last_committed_watermark']), parse_utc(m['sweep_started_at']),
        m['overlap_seconds'])
    if (m['query_parameters'] != expected['query_parameters']
            or m['requested_starttime'] != expected['catalog_lower_bound']
            or m['requested_endtime'] != expected['origin_time_cutoff']
            or m['proposed_watermark_after_success'] != expected['sweep_started_at']):
        raise LoadReconciliationError('sweep parameters do not match its watermark plan')
    leaves = sorted((a for a in m['window_audit'] if a['status'] == 'reconciled'),
                    key=lambda a: a['starttime'])
    if not leaves or any(a['status'] not in {'split', 'reconciled'} for a in m['window_audit']):
        raise LoadReconciliationError('sweep has unresolved or missing window audit')
    cursor = parse_utc(m['catalog_lower_bound'])
    counts = {}
    for a in leaves:
        end = parse_utc(a['endtime'])
        count = a['returned_rows']
        if (parse_utc(a['starttime']) != cursor or end <= cursor
                or a['window_id'] in counts or type(count) is not int or count < 0
                or not a['count_before'] == count == a['count_after']):
            raise LoadReconciliationError('sweep window coverage or counts disagree')
        counts[a['window_id']] = count
        cursor = end
    if cursor != parse_utc(m['origin_time_cutoff']):
        raise LoadReconciliationError('sweep does not cover its full requested range')
    with Path(plan['events_path']).open() as stream:
        actual = Counter(json.loads(line)['metadata']['window_id'] for line in stream)
    if dict(actual) != {key: value for key, value in counts.items() if value}:
        raise LoadReconciliationError('local rows do not match each reconciled window')
    return counts


def load_and_commit(plan, connection, state_path: Path, initial_watermark=None):
    """Single-host lock + compare previous watermark; commit only after RAW verification."""
    counts = validate_sweep(plan)
    m = plan['manifest']
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if state_path.exists():
            state = json.loads(state_path.read_text())
            previous = state['committed_watermark']
            if state['catalog_lower_bound'] != m['catalog_lower_bound']:
                raise LoadReconciliationError('catalog lower bound changed; investigate before committing')
            if parse_utc(state['origin_time_cutoff']) > parse_utc(m['origin_time_cutoff']):
                raise LoadReconciliationError('origin-time cutoff cannot move backwards')
        else:
            if initial_watermark is None:
                raise LoadReconciliationError('first sweep requires an explicit bootstrap watermark')
            previous = iso_utc(initial_watermark)
        if parse_utc(previous) != parse_utc(m['last_committed_watermark']):
            raise LoadReconciliationError('stale sweep: committed watermark changed')
        candidates = [(1, plan)]
        status = check_snowflake(candidates, connection)[0][2]
        if status == 'ready':
            execute_raw_load(plan, connection)
        elif status != 'loaded':
            raise LoadReconciliationError('sweep load needs investigation')
        if check_snowflake(candidates, connection)[0][2] != 'loaded':
            raise LoadReconciliationError('complete receipt and RAW count are required')
        with closing(connection.cursor()) as cursor:
            cursor.execute('SELECT MANIFEST FROM QUAKEWATCH.RAW.BATCH_ATTEMPT '
                           'WHERE ATTEMPT_ID = %s', (plan['attempt_id'],))
            receipt_manifest = cursor.fetchone()[0]
            if isinstance(receipt_manifest, str):
                receipt_manifest = json.loads(receipt_manifest)
            if receipt_manifest != m:
                raise LoadReconciliationError('receipt manifest differs from the local sweep')
            cursor.execute('SELECT WINDOW_ID, COUNT(*) FROM QUAKEWATCH.RAW.RAW_EVENT_RECORDS '
                           'WHERE ATTEMPT_ID = %s GROUP BY WINDOW_ID', (plan['attempt_id'],))
            raw_counts = dict(cursor.fetchall())
        if raw_counts != {key: value for key, value in counts.items() if value}:
            raise LoadReconciliationError('RAW rows disagree with per-window source counts')
        state = {'committed_watermark': m['sweep_started_at'],
                 'previous_watermark': previous, 'attempt_id': plan['attempt_id'],
                 'catalog_lower_bound': m['catalog_lower_bound'],
                 'origin_time_cutoff': m['origin_time_cutoff']}
        temporary = state_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(state, indent=2) + '\n')
        temporary.replace(state_path)
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--state', type=Path, default=Path('data/watermarks/update.json'))
    parser.add_argument('--initial-watermark', type=parse_utc)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    plan = plan_raw_load(args.manifest)
    counts = validate_sweep(plan)
    print(f'Validated sweep: {len(counts)} reconciled windows; {plan["expected_rows"]} rows')
    if not args.execute:
        print('Preview only; no Snowflake calls or watermark writes.')
        return
    with closing(connect_project()) as connection:
        state = load_and_commit(plan, connection, args.state, args.initial_watermark)
    print('Committed watermark:', state['committed_watermark'])


if __name__ == '__main__':
    main()
