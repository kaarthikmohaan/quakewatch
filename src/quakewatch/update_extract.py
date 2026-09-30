"""Capture a bounded catalog update sweep; never commit its watermark here."""

import argparse
import calendar
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


def initial_sweep_windows(start, end, years_per_window: int):
    """Partition origin time before calling the catalog-wide source endpoint."""
    if not 1 <= years_per_window <= 100:
        raise ValueError('years-per-window must be between 1 and 100')
    windows = []
    cursor = start
    while cursor < end:
        year = min(cursor.year + years_per_window, 9999)
        day = min(cursor.day, calendar.monthrange(year, cursor.month)[1])
        next_end = min(cursor.replace(year=year, day=day), end)
        if next_end <= cursor:
            raise ValueError('cannot advance the origin-time window')
        windows.append((cursor, next_end))
        cursor = next_end
    return windows


def run_update_sweep(catalog_start, cutoff, last_watermark, sweep_started_at,
                     overlap_seconds: int, output_root: Path,
                     years_per_window: int = 50) -> Path:
    plan = plan_update_sweep(catalog_start, cutoff, last_watermark,
                             sweep_started_at, overlap_seconds)
    initial_windows = initial_sweep_windows(catalog_start, cutoff, years_per_window)
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
                'initial_source_years': years_per_window,
                'source_rows_returned': 0, 'raw_rows_written': 0,
                'events_file': 'events.jsonl',
                'note': 'Extraction only. RAW loading and watermark commit remain pending; '
                        'source results are not a consistent catalog snapshot.'}

    def save():
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        temporary.replace(path)

    save()
    audits = []
    active = None
    if len(initial_windows) > 1:
        audits.append({'window_id': 'w0001', 'starttime': iso_utc(catalog_start),
                       'endtime': iso_utc(cutoff), 'status': 'split',
                       'reason': f'planned source slices of at most {years_per_window} years'})
    try:
        rows = []
        with source_deadline(SOURCE_WINDOW_DEADLINE_SECONDS):
            with httpx.Client(headers={'User-Agent': USER_AGENT}, follow_redirects=True) as client:
                for index, (child_start, child_end) in enumerate(initial_windows, start=1):
                    window_id = f'w0001.{index}' if len(initial_windows) > 1 else 'w0001'
                    active = (window_id, child_start, child_end)
                    manifest['active_window'] = {'window_id': window_id,
                                                 'starttime': iso_utc(child_start),
                                                 'endtime': iso_utc(child_end)}
                    manifest['window_audit'] = audits
                    save()
                    try:
                        child_rows, child_audits = fetch_window(
                            client, None, child_start, child_end, window_id,
                            query_base=plan['query_parameters'])
                    except ExtractionError as exc:
                        exc.window_audit = [*audits, *exc.window_audit]
                        raise
                    rows.extend(child_rows)
                    audits.extend(child_audits)
                    active = None
                    manifest.pop('active_window', None)
                    manifest['window_audit'] = audits
                    save()
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
        failed_audits = exc.window_audit if isinstance(exc, ExtractionError) else list(audits)
        gaps = [audit for audit in failed_audits if audit['status'] == 'unresolved']
        if not gaps:
            gap_id, gap_start, gap_end = active or ('w0001', catalog_start, cutoff)
            gaps = [{'window_id': gap_id, 'starttime': iso_utc(gap_start),
                     'endtime': iso_utc(gap_end), 'status': 'unresolved',
                     'reason': str(exc) or type(exc).__name__}]
            failed_audits = [*failed_audits, *gaps]
        manifest.update(status='failed', error_type=type(exc).__name__, error=str(exc),
                        window_audit=failed_audits, coverage_gaps=gaps)
        save()
        raise
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('catalog-start', 'cutoff', 'last-watermark', 'sweep-started-at'):
        parser.add_argument('--' + option, type=parse_utc, required=True)
    parser.add_argument('--overlap-seconds', type=int, required=True)
    parser.add_argument('--output', type=Path, default=Path('data/raw'))
    parser.add_argument('--years-per-window', type=int, default=50)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    values = (args.catalog_start, args.cutoff, args.last_watermark,
              args.sweep_started_at, args.overlap_seconds)
    try:
        plan = plan_update_sweep(*values)
        initial_sweep_windows(args.catalog_start, args.cutoff, args.years_per_window)
    except ValueError as exc:
        parser.error(str(exc))
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return
    print('Captured manifest:', run_update_sweep(*values, args.output,
                                                years_per_window=args.years_per_window))


if __name__ == '__main__':
    main()
