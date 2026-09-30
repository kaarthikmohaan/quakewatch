"""Capture a bounded catalog update sweep; never commit its watermark here."""

import argparse
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

from quakewatch.extract_batch import (
    ExtractionError, fetch_window, iso_utc, parse_utc, source_deadline, stable_json,
)
from quakewatch.settings import PARSER_VERSION, SOURCE_WINDOW_DEADLINE_SECONDS, USER_AGENT
from quakewatch.update_plan import plan_update_sweep


def run_update_sweep(catalog_start, cutoff, last_watermark, sweep_started_at,
                     overlap_seconds: int, output_root: Path) -> Path:
    plan = plan_update_sweep(catalog_start, cutoff, last_watermark,
                             sweep_started_at, overlap_seconds)
    logical_id = hashlib.sha256(stable_json(plan['query_parameters']).encode()).hexdigest()[:20]
    attempt_id = f'{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:10]}'
    directory = output_root / attempt_id
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / 'manifest.json'
    manifest = {**plan, 'batch_kind': 'update_sweep', 'logical_batch_id': logical_id,
                'requested_starttime': plan['catalog_lower_bound'],
                'requested_endtime': plan['origin_time_cutoff'],
                'attempt_id': attempt_id, 'fetched_at': iso_utc(datetime.now(UTC)),
                'status': 'running', 'window_audit': [], 'coverage_gaps': [],
                'source_rows_returned': 0, 'raw_rows_written': 0,
                'events_file': 'events.jsonl',
                'note': 'Extraction only. RAW loading and watermark commit remain pending; '
                        'source results are not a consistent catalog snapshot.'}

    def save():
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        temporary.replace(path)

    save()
    try:
        with source_deadline(SOURCE_WINDOW_DEADLINE_SECONDS):
            with httpx.Client(headers={'User-Agent': USER_AGENT}, follow_redirects=True) as client:
                rows, audits = fetch_window(client, None, catalog_start, cutoff, 'w0001',
                                            query_base=plan['query_parameters'])
        temporary_events = directory / 'events.jsonl.tmp'
        with temporary_events.open('w', encoding='utf-8') as stream:
            for feature, window_id in rows:
                record = {'source_feature': feature, 'metadata': {
                    'logical_batch_id': logical_id, 'attempt_id': attempt_id,
                    'window_id': window_id, 'fetched_at': manifest['fetched_at'],
                    'payload_hash': hashlib.sha256(stable_json(feature).encode()).hexdigest(),
                    'parser_version': PARSER_VERSION,
                }}
                stream.write(stable_json(record) + '\n')
        temporary_events.replace(directory / 'events.jsonl')
        manifest.update(status='complete', window_audit=audits, count_sizing_pending=False,
                        source_rows_returned=len(rows), raw_rows_written=len(rows))
        save()
    except (Exception, KeyboardInterrupt) as exc:
        audits = exc.window_audit if isinstance(exc, ExtractionError) else []
        gaps = [audit for audit in audits if audit['status'] == 'unresolved']
        if not gaps:
            gaps = [{'window_id': 'w0001', 'starttime': iso_utc(catalog_start),
                     'endtime': iso_utc(cutoff), 'status': 'unresolved',
                     'reason': str(exc) or type(exc).__name__}]
            audits = [*audits, *gaps]
        manifest.update(status='failed', error_type=type(exc).__name__, error=str(exc),
                        window_audit=audits, coverage_gaps=gaps)
        save()
        raise
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('catalog-start', 'cutoff', 'last-watermark', 'sweep-started-at'):
        parser.add_argument('--' + option, type=parse_utc, required=True)
    parser.add_argument('--overlap-seconds', type=int, required=True)
    parser.add_argument('--output', type=Path, default=Path('data/raw'))
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    values = (args.catalog_start, args.cutoff, args.last_watermark,
              args.sweep_started_at, args.overlap_seconds)
    try:
        plan = plan_update_sweep(*values)
    except ValueError as exc:
        parser.error(str(exc))
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return
    print('Captured manifest:', run_update_sweep(*values, args.output))


if __name__ == '__main__':
    main()
