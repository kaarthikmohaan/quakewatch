"""Offline update-sweep extraction and failure evidence."""

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import httpx

from quakewatch.extract_batch import ExtractionError, SourceDeadlineExceeded
from quakewatch.raw_load import validate_local_batch
from quakewatch.update_extract import run_update_sweep


class UpdateExtractTests(unittest.TestCase):
    def setUp(self):
        self.values = (datetime(1900, 1, 1, tzinfo=UTC), datetime(2026, 9, 30, tzinfo=UTC),
                       datetime(2026, 9, 29, tzinfo=UTC), datetime(2026, 9, 30, tzinfo=UTC), 86400)

    def test_split_preserves_update_filter_and_old_deleted_records(self):
        requests = []
        def respond(request):
            params = dict(request.url.params)
            requests.append(params)
            self.assertEqual(params['updatedafter'], '2026-09-28T00:00:00.000Z')
            self.assertEqual(params['includedeleted'], 'true')
            self.assertFalse({'latitude', 'longitude', 'minmagnitude', 'maxradiuskm'} & params.keys())
            parent = params['starttime'].startswith('1900-') and params['endtime'].startswith('2026-')
            if request.url.path.endswith('/count'):
                return httpx.Response(200, json={'count': 10000 if parent else 1})
            self.assertFalse(parent)
            return httpx.Response(200, json={'features': [
                {'id': 'old-event', 'properties': {'status': 'deleted', 'time': -1000}}]})
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with tempfile.TemporaryDirectory() as directory:
            with patch('quakewatch.update_extract.httpx.Client', return_value=client):
                path = run_update_sweep(*self.values, Path(directory))
            manifest, count = validate_local_batch(path)
            self.assertEqual(count, 2)
            self.assertEqual([a['status'] for a in manifest['window_audit']],
                             ['split', 'reconciled', 'reconciled'])
            self.assertFalse(manifest['watermark_advanced'])
            self.assertEqual(manifest['last_committed_watermark'], '2026-09-29T00:00:00.000Z')
            self.assertEqual(manifest['coverage_gaps'], [])
            self.assertIn('deleted', (path.parent / 'events.jsonl').read_text())

    def test_failure_preserves_watermark_and_explicit_gap(self):
        gap = {'window_id': 'w0001.a', 'status': 'unresolved', 'reason': 'counts disagree'}
        for error in (ExtractionError('counts disagree', [gap]),
                      SourceDeadlineExceeded('deadline')):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as directory:
                with patch('quakewatch.update_extract.fetch_window', side_effect=error):
                    with self.assertRaises(type(error)):
                        run_update_sweep(*self.values, Path(directory))
                path = next(Path(directory).glob('*/manifest.json'))
                m = json.loads(path.read_text())
                self.assertEqual(m['status'], 'failed')
                self.assertFalse(m['watermark_advanced'])
                self.assertEqual(m['last_committed_watermark'], '2026-09-29T00:00:00.000Z')
                self.assertTrue(m['coverage_gaps'])
                self.assertFalse((path.parent / 'events.jsonl').exists())
