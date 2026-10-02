"""Load one complete sweep and atomically advance its committed watermark in Snowflake."""

import argparse
from collections import Counter
from contextlib import closing
import json
import logging
from pathlib import Path

from quakewatch.extract_batch import iso_utc, parse_utc
from quakewatch.history_load_plan import check_snowflake
from quakewatch.raw_load import connect_project, execute_raw_load, plan_raw_load, LoadReconciliationError
from quakewatch.update_plan import plan_update_sweep
from quakewatch.logs import configure_logging

logger = logging.getLogger(__name__)

WATERMARK_TABLE = 'QUAKEWATCH.RAW.UPDATE_WATERMARK'
DEFAULT_SWEEP = 'catalog'


class SnowflakeWatermarkStore:
    """Committed sweep watermark held in Snowflake, advanced by compare-and-set."""

    def __init__(self, connection, sweep_name=DEFAULT_SWEEP):
        self.connection = connection
        self.sweep_name = sweep_name

    def read(self):
        with closing(self.connection.cursor()) as cursor:
            cursor.execute(
                f'SELECT COMMITTED_WATERMARK, CATALOG_LOWER_BOUND, ORIGIN_TIME_CUTOFF '
                f'FROM {WATERMARK_TABLE} WHERE SWEEP_NAME = %s', (self.sweep_name,))
            rows = cursor.fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            raise LoadReconciliationError('more than one watermark row for this sweep')
        committed, lower_bound, cutoff = rows[0]
        return {'committed_watermark': iso_utc(committed),
                'catalog_lower_bound': iso_utc(lower_bound),
                'origin_time_cutoff': iso_utc(cutoff)}

    def commit(self, previous, state):
        """Advance from ``previous`` (None for the first sweep) or raise without change."""
        params = (state['committed_watermark'], previous, state['attempt_id'],
                  state['catalog_lower_bound'], state['origin_time_cutoff'])
        with closing(self.connection.cursor()) as cursor:
            cursor.execute('BEGIN')
            try:
                if previous is None:
                    cursor.execute(
                        f'INSERT INTO {WATERMARK_TABLE} (SWEEP_NAME, COMMITTED_WATERMARK, '
                        'PREVIOUS_WATERMARK, ATTEMPT_ID, CATALOG_LOWER_BOUND, ORIGIN_TIME_CUTOFF) '
                        'SELECT %s, %s, %s, %s, %s, %s WHERE NOT EXISTS '
                        f'(SELECT 1 FROM {WATERMARK_TABLE} WHERE SWEEP_NAME = %s)',
                        (self.sweep_name, *params, self.sweep_name))
                else:
                    cursor.execute(
                        f'UPDATE {WATERMARK_TABLE} SET COMMITTED_WATERMARK = %s, '
                        'PREVIOUS_WATERMARK = %s, ATTEMPT_ID = %s, CATALOG_LOWER_BOUND = %s, '
                        'ORIGIN_TIME_CUTOFF = %s, COMMITTED_AT = CURRENT_TIMESTAMP() '
                        'WHERE SWEEP_NAME = %s AND COMMITTED_WATERMARK = %s',
                        (*params, self.sweep_name, previous))
                if cursor.rowcount != 1:
                    raise LoadReconciliationError('watermark changed concurrently; nothing committed')
                cursor.execute('COMMIT')
            except Exception:
                cursor.execute('ROLLBACK')
                raise


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


def load_and_commit(plan, connection, initial_watermark=None, store=None):
    """Verify the sweep's RAW evidence, then advance the Snowflake watermark once."""
    counts = validate_sweep(plan)
    m = plan['manifest']
    store = store or SnowflakeWatermarkStore(connection)
    current = store.read()
    if current is not None:
        previous = current['committed_watermark']
        if parse_utc(current['catalog_lower_bound']) != parse_utc(m['catalog_lower_bound']):
            raise LoadReconciliationError('catalog lower bound changed; investigate before committing')
        if parse_utc(current['origin_time_cutoff']) > parse_utc(m['origin_time_cutoff']):
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
    store.commit(None if current is None else previous, state)
    logger.info('Committed update watermark %s (previous %s) for attempt %s',
                state['committed_watermark'], previous, plan['attempt_id'])
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--initial-watermark', type=parse_utc)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    configure_logging()
    plan = plan_raw_load(args.manifest)
    counts = validate_sweep(plan)
    print(f'Validated sweep: {len(counts)} reconciled windows; {plan["expected_rows"]} rows')
    if not args.execute:
        print('Preview only; no Snowflake calls or watermark writes.')
        return
    with closing(connect_project()) as connection:
        state = load_and_commit(plan, connection, args.initial_watermark)
    print('Committed watermark:', state['committed_watermark'])


if __name__ == '__main__':
    main()
