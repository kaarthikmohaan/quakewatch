"""Watermarks remain unchanged unless source coverage and RAW evidence agree."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from quakewatch.extract_batch import parse_utc
from quakewatch.raw_load import LoadReconciliationError
from quakewatch.update_plan import plan_update_sweep
from quakewatch.update_load import load_and_commit, validate_sweep


class UpdateLoadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.state = root / 'state.json'
        self.old = {'committed_watermark': '2026-09-29T00:00:00.000Z',
                    'catalog_lower_bound': '1900-01-01T00:00:00.000Z',
                    'origin_time_cutoff': '2026-09-29T00:00:00.000Z'}
        self.state.write_text(json.dumps(self.old))
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
            result = load_and_commit(self.plan, self.connection, self.state)
        load.assert_called_once()
        self.assertEqual(result['committed_watermark'], '2026-09-30T00:00:00.000Z')
        self.assertEqual(json.loads(self.state.read_text()), result)

    def test_loaded_receipt_recovers_after_interrupted_local_commit(self):
        with patch('quakewatch.update_load.check_snowflake', return_value=[(1, self.plan, 'loaded')]), \
             patch('quakewatch.update_load.execute_raw_load') as load:
            load_and_commit(self.plan, self.connection, self.state)
        load.assert_not_called()

    def test_failed_load_does_not_advance_watermark(self):
        with patch('quakewatch.update_load.check_snowflake', return_value=[(1, self.plan, 'ready')]), \
             patch('quakewatch.update_load.execute_raw_load', side_effect=RuntimeError('COPY failed')):
            with self.assertRaises(RuntimeError):
                load_and_commit(self.plan, self.connection, self.state)
        self.assertEqual(json.loads(self.state.read_text()), self.old)

    def test_raw_window_mismatch_does_not_advance_watermark(self):
        self.connection.cursor.return_value.fetchall.return_value = [('wrong-window', 1)]
        with patch('quakewatch.update_load.check_snowflake', return_value=[(1, self.plan, 'loaded')]):
            with self.assertRaises(LoadReconciliationError):
                load_and_commit(self.plan, self.connection, self.state)
        self.assertEqual(json.loads(self.state.read_text()), self.old)

    def test_missing_coverage_rejected(self):
        self.plan['manifest']['window_audit'][0]['starttime'] = '2000-01-01T00:00:00.000Z'
        with self.assertRaises(LoadReconciliationError):
            validate_sweep(self.plan)

    def test_stale_plan_rejected_before_database_call(self):
        self.old['committed_watermark'] = '2026-09-30T00:00:00.000Z'
        self.state.write_text(json.dumps(self.old))
        with patch('quakewatch.update_load.check_snowflake') as check:
            with self.assertRaises(LoadReconciliationError):
                load_and_commit(self.plan, self.connection, self.state)
        check.assert_not_called()

    def test_changed_receipt_manifest_blocks_commit(self):
        self.connection.cursor.return_value.fetchone.return_value = ({'changed': True},)
        with patch('quakewatch.update_load.check_snowflake', return_value=[(1, self.plan, 'loaded')]):
            with self.assertRaises(LoadReconciliationError):
                load_and_commit(self.plan, self.connection, self.state)
        self.assertEqual(json.loads(self.state.read_text()), self.old)

    def test_first_run_requires_explicit_bootstrap(self):
        fresh_state = Path(self.temp.name) / 'new-state.json'
        with patch('quakewatch.update_load.check_snowflake') as check:
            with self.assertRaises(LoadReconciliationError):
                load_and_commit(self.plan, self.connection, fresh_state)
        check.assert_not_called()
        self.assertFalse(fresh_state.exists())
