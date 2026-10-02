"""Watermarks remain unchanged unless source coverage and RAW evidence agree."""
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from quakewatch.extract_batch import parse_utc
from quakewatch.raw_load import LoadReconciliationError
from quakewatch.update_plan import plan_update_sweep
from quakewatch.update_load import SnowflakeWatermarkStore, load_and_commit, validate_sweep


class MemoryStore:
    """In-memory stand-in for the Snowflake watermark table."""

    def __init__(self, state=None):
        self.state = dict(state) if state else None
        self.commits = []

    def read(self):
        return dict(self.state) if self.state else None

    def commit(self, previous, state):
        current = self.state['committed_watermark'] if self.state else None
        if current != previous:
            raise LoadReconciliationError('watermark changed concurrently; nothing committed')
        self.state = dict(state)
        self.commits.append(state)


class UpdateLoadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.old = {'committed_watermark': '2026-09-29T00:00:00.000Z',
                    'catalog_lower_bound': '1900-01-01T00:00:00.000Z',
                    'origin_time_cutoff': '2026-09-29T00:00:00.000Z'}
        self.store = MemoryStore(self.old)
        m = plan_update_sweep(*map(parse_utc, ['1900-01-01', '2026-09-30', '2026-09-29', '2026-09-30']), 86400)
        m.update(batch_kind='update_sweep', status='complete', coverage_gaps=[],
                 requested_starttime=m['catalog_lower_bound'], requested_endtime=m['origin_time_cutoff'],
                 window_audit=[{'window_id': 'w0001', 'status': 'reconciled',
                                'starttime': m['catalog_lower_bound'], 'endtime': m['origin_time_cutoff'],
                                'count_before': 1, 'returned_rows': 1, 'count_after': 1}])
        events = root / 'events.jsonl'
        events.write_text(json.dumps({'metadata': {'window_id': 'w0001'}}) + '\n')
        self.plan = {'manifest': m, 'attempt_id': 'test-attempt', 'expected_rows': 1,
                     'events_path': str(events)}
        self.connection = MagicMock()
        self.connection.cursor.return_value.fetchone.return_value = (m,)
        self.connection.cursor.return_value.fetchall.return_value = [('w0001', 1)]

    def test_commit_after_new_load_and_independent_verification(self):
        with patch('quakewatch.update_load.check_snowflake', side_effect=[[(1, self.plan, 'ready')], [(1, self.plan, 'loaded')]]), \
             patch('quakewatch.update_load.execute_raw_load') as load:
            result = load_and_commit(self.plan, self.connection, store=self.store)
        load.assert_called_once()
        self.assertEqual(result['committed_watermark'], '2026-09-30T00:00:00.000Z')
        self.assertEqual(self.store.commits, [result])

    def test_loaded_receipt_recovers_after_interrupted_commit(self):
        with patch('quakewatch.update_load.check_snowflake', return_value=[(1, self.plan, 'loaded')]), \
             patch('quakewatch.update_load.execute_raw_load') as load:
            load_and_commit(self.plan, self.connection, store=self.store)
        load.assert_not_called()
        self.assertEqual(len(self.store.commits), 1)

    def test_failed_load_does_not_advance_watermark(self):
        with patch('quakewatch.update_load.check_snowflake', return_value=[(1, self.plan, 'ready')]), \
             patch('quakewatch.update_load.execute_raw_load', side_effect=RuntimeError('COPY failed')):
            with self.assertRaises(RuntimeError):
                load_and_commit(self.plan, self.connection, store=self.store)
        self.assertEqual(self.store.read(), self.old)

    def test_raw_window_mismatch_does_not_advance_watermark(self):
        self.connection.cursor.return_value.fetchall.return_value = [('wrong-window', 1)]
        with patch('quakewatch.update_load.check_snowflake', return_value=[(1, self.plan, 'loaded')]):
            with self.assertRaises(LoadReconciliationError):
                load_and_commit(self.plan, self.connection, store=self.store)
        self.assertEqual(self.store.read(), self.old)

    def test_missing_coverage_rejected(self):
        self.plan['manifest']['window_audit'][0]['starttime'] = '2000-01-01T00:00:00.000Z'
        with self.assertRaises(LoadReconciliationError):
            validate_sweep(self.plan)

    def test_stale_plan_rejected_before_database_call(self):
        self.store = MemoryStore({**self.old, 'committed_watermark': '2026-09-30T00:00:00.000Z'})
        with patch('quakewatch.update_load.check_snowflake') as check:
            with self.assertRaises(LoadReconciliationError):
                load_and_commit(self.plan, self.connection, store=self.store)
        check.assert_not_called()

    def test_changed_receipt_manifest_blocks_commit(self):
        self.connection.cursor.return_value.fetchone.return_value = ({'changed': True},)
        with patch('quakewatch.update_load.check_snowflake', return_value=[(1, self.plan, 'loaded')]):
            with self.assertRaises(LoadReconciliationError):
                load_and_commit(self.plan, self.connection, store=self.store)
        self.assertEqual(self.store.read(), self.old)

    def test_first_run_requires_explicit_bootstrap(self):
        fresh = MemoryStore()
        with patch('quakewatch.update_load.check_snowflake') as check:
            with self.assertRaises(LoadReconciliationError):
                load_and_commit(self.plan, self.connection, store=fresh)
        check.assert_not_called()
        self.assertIsNone(fresh.read())

    def test_first_run_commits_with_bootstrap_watermark(self):
        fresh = MemoryStore()
        with patch('quakewatch.update_load.check_snowflake', return_value=[(1, self.plan, 'loaded')]):
            result = load_and_commit(self.plan, self.connection,
                                     parse_utc('2026-09-29T00:00:00Z'), store=fresh)
        self.assertEqual(fresh.read(), result)

    def test_concurrent_advance_blocks_commit(self):
        store = MemoryStore(self.old)
        original_commit = store.commit

        def race(previous, state):
            store.state = {**self.old, 'committed_watermark': '2026-09-29T12:00:00.000Z'}
            original_commit(previous, state)

        store.commit = race
        with patch('quakewatch.update_load.check_snowflake', return_value=[(1, self.plan, 'loaded')]):
            with self.assertRaises(LoadReconciliationError):
                load_and_commit(self.plan, self.connection, store=store)


class SnowflakeWatermarkStoreTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value
        self.store = SnowflakeWatermarkStore(self.connection)
        self.state = {'committed_watermark': '2026-09-30T00:00:00.000Z', 'attempt_id': 'a1',
                      'catalog_lower_bound': '1900-01-01T00:00:00.000Z',
                      'origin_time_cutoff': '2026-09-30T00:00:00.000Z'}

    def statements(self):
        return [call.args[0] for call in self.cursor.execute.call_args_list]

    def test_read_returns_none_without_row(self):
        self.cursor.fetchall.return_value = []
        self.assertIsNone(self.store.read())

    def test_read_converts_timestamps(self):
        stamp = datetime(2026, 9, 29, tzinfo=UTC)
        self.cursor.fetchall.return_value = [(stamp, datetime(1900, 1, 1, tzinfo=UTC), stamp)]
        self.assertEqual(self.store.read()['committed_watermark'], '2026-09-29T00:00:00.000Z')

    def test_update_is_compare_and_set_and_commits(self):
        self.cursor.rowcount = 1
        self.store.commit('2026-09-29T00:00:00.000Z', self.state)
        statements = self.statements()
        self.assertEqual(statements[0], 'BEGIN')
        self.assertIn('WHERE SWEEP_NAME = %s AND COMMITTED_WATERMARK = %s', statements[1])
        self.assertEqual(self.cursor.execute.call_args_list[1].args[1][-1], '2026-09-29T00:00:00.000Z')
        self.assertEqual(statements[-1], 'COMMIT')

    def test_first_commit_inserts_only_when_absent(self):
        self.cursor.rowcount = 1
        self.store.commit(None, self.state)
        self.assertIn('WHERE NOT EXISTS', self.statements()[1])

    def test_lost_race_rolls_back(self):
        self.cursor.rowcount = 0
        with self.assertRaises(LoadReconciliationError):
            self.store.commit('2026-09-29T00:00:00.000Z', self.state)
        self.assertEqual(self.statements()[-1], 'ROLLBACK')
        self.assertNotIn('COMMIT', self.statements())
