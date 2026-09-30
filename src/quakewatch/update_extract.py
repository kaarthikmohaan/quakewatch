"""Capture a bounded catalog update sweep; never commit its watermark here."""

import argparse
import calendar
import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from quakewatch.extract_batch import (
    ExtractionError, fetch_window, iso_utc, parse_utc,
    read_child_checkpoint, save_child_checkpoint, source_deadline, stable_json,
)
from quakewatch.settings import PARSER_VERSION, SOURCE_WINDOW_DEADLINE_SECONDS, USER_AGENT
from quakewatch.update_plan import plan_update_sweep


def initial_sweep_windows(start, end, years_per_window: int,
                          recent_start_year: int = 2001,
                          recent_years_per_window: int = 5,
                          monthly_start_year: int | None = None,
                          recent_months_per_window: int = 1,
                          daily_month: str | None = None):
    """Partition origin time before calling the catalog-wide source endpoint."""
    if not 1 <= years_per_window <= 100 or not 1 <= recent_years_per_window <= 100:
        raise ValueError('window sizes must be between 1 and 100 years')
    if not 2 <= recent_start_year <= 9999:
        raise ValueError('recent-start-year must be between 2 and 9999')
    if monthly_start_year is not None and not recent_start_year <= monthly_start_year <= 9999:
        raise ValueError('monthly-start-year must be between recent-start-year and 9999')
    if not 1 <= recent_months_per_window <= 1200:
        raise ValueError('recent-months-per-window must be between 1 and 1200')
    daily_start = daily_end = None
    if daily_month is not None:
        if not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', daily_month):
            raise ValueError('daily-month must be YYYY-MM')
        year, month = map(int, daily_month.split('-'))
        if monthly_start_year is None or year < monthly_start_year or year > 9999:
            raise ValueError('daily-month requires monthly-start-year at or before it')
        if year == 9999 and month == 12:
            raise ValueError('daily-month exceeds the supported datetime range')
        daily_start = start.replace(year=year, month=month, day=1,
                                    hour=0, minute=0, second=0, microsecond=0)
        daily_end = (daily_start.replace(year=year + 1, month=1) if month == 12
                     else daily_start.replace(month=month + 1))
        if not start <= daily_start < daily_end <= end:
            raise ValueError('daily-month must fit within requested sweep bounds')
    windows = []
    cursor = start
    while cursor < end:
        if daily_start is not None and daily_start <= cursor < daily_end:
            next_end = min(cursor + timedelta(days=1), daily_end, end)
        elif monthly_start_year is not None and cursor.year >= monthly_start_year:
            month_index = (cursor.year - 1) * 12 + cursor.month - 1 + recent_months_per_window
            year, month_offset = divmod(min(month_index, 9999 * 12 - 1), 12)
            year += 1
            month = month_offset + 1
            day = min(cursor.day, calendar.monthrange(year, month)[1])
            next_end = min(cursor.replace(year=year, month=month, day=day), end)
        else:
            duration = recent_years_per_window if cursor.year >= recent_start_year else years_per_window
            year = min(cursor.year + duration, 9999)
            day = min(cursor.day, calendar.monthrange(year, cursor.month)[1])
            next_end = min(cursor.replace(year=year, day=day), end)
        if cursor.year < recent_start_year:
            next_end = min(next_end, cursor.replace(year=recent_start_year, month=1, day=1))
        elif monthly_start_year is not None and cursor.year < monthly_start_year:
            next_end = min(next_end, cursor.replace(year=monthly_start_year, month=1, day=1))
        if daily_start is not None and cursor < daily_start:
            next_end = min(next_end, daily_start)
        if next_end <= cursor:
            raise ValueError('cannot advance the origin-time window')
        windows.append((cursor, next_end))
        cursor = next_end
    return windows


def run_update_sweep(catalog_start, cutoff, last_watermark, sweep_started_at,
                     overlap_seconds: int, output_root: Path,
                     years_per_window: int = 50, recent_start_year: int = 2001,
                     recent_years_per_window: int = 5,
                     monthly_start_year: int | None = None,
                     recent_months_per_window: int = 1,
                     resume_children: bool = False,
                     daily_month: str | None = None) -> Path:
    plan = plan_update_sweep(catalog_start, cutoff, last_watermark,
                             sweep_started_at, overlap_seconds)
    initial_windows = initial_sweep_windows(catalog_start, cutoff, years_per_window,
                                            recent_start_year, recent_years_per_window,
                                            monthly_start_year, recent_months_per_window,
                                            daily_month)
    logical_id = hashlib.sha256(stable_json(plan['query_parameters']).encode()).hexdigest()[:20]
    checkpoints = {}
    if resume_children:
        for prior_path in sorted(output_root.glob('*/manifest.json'), reverse=True):
            try:
                prior = json.loads(prior_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if (prior.get('batch_kind') != 'update_sweep'
                    or prior.get('logical_batch_id') != logical_id
                    or prior.get('sweep_started_at') != plan['sweep_started_at']):
                continue
            for child_path in (prior_path.parent / 'children').glob('*.json'):
                checkpoints.setdefault(child_path.stem, []).append(child_path)
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
                'recent_start_year': recent_start_year,
                'recent_source_years': recent_years_per_window,
                'monthly_start_year': monthly_start_year,
                'recent_source_months': recent_months_per_window if monthly_start_year else None,
                'daily_month': daily_month,
                'resume_children': resume_children,
                'reused_child_windows': [], 'source_rows_reused': 0,
                'source_rows_fetched_this_attempt': 0,
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
        sizing_note = (f'planned slices: {years_per_window} years before '
                       f'{recent_start_year}, {recent_years_per_window} years after')
        if monthly_start_year is not None:
            sizing_note += f'; {recent_months_per_window} months from {monthly_start_year}'
        if daily_month is not None:
            sizing_note += f'; one day within {daily_month}'
        audits.append({'window_id': 'w0001', 'starttime': iso_utc(catalog_start),
                       'endtime': iso_utc(cutoff), 'status': 'split',
                       'reason': sizing_note})
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
                    params = {**plan['query_parameters'], 'starttime': iso_utc(child_start),
                              'endtime': iso_utc(child_end)}
                    checkpoint = (read_child_checkpoint(checkpoints.get(window_id, []),
                                                        params, window_id)
                                  if resume_children else None)
                    if checkpoint is None:
                        try:
                            child_rows, child_audits = fetch_window(
                                client, None, child_start, child_end, window_id,
                                query_base=plan['query_parameters'])
                        except ExtractionError as exc:
                            exc.window_audit = [*audits, *exc.window_audit]
                            raise
                        fetched_at = iso_utc(datetime.now(UTC))
                        manifest['source_rows_fetched_this_attempt'] += len(child_rows)
                        if resume_children:
                            child_audits = [{**audit, 'source_fetched_at': fetched_at}
                                            for audit in child_audits]
                            save_child_checkpoint(directory / 'children' / f'{window_id}.json', {
                                'query_parameters': params, 'window_id': window_id,
                                'attempt_id': attempt_id, 'fetched_at': fetched_at,
                                'window_audit': child_audits,
                                'features': [[feature, row_window_id]
                                             for feature, row_window_id in child_rows],
                            })
                    else:
                        child_rows = [(feature, row_window_id)
                                      for feature, row_window_id in checkpoint['features']]
                        child_audits = [{**audit,
                                         'reused_from_attempt_id': checkpoint['attempt_id']}
                                        for audit in checkpoint['window_audit']]
                        fetched_at = checkpoint['fetched_at']
                        manifest['reused_child_windows'].append(window_id)
                        manifest['source_rows_reused'] += len(child_rows)
                    rows.extend((feature, row_window_id, fetched_at)
                                for feature, row_window_id in child_rows)
                    audits.extend(child_audits)
                    active = None
                    manifest.pop('active_window', None)
                    manifest['window_audit'] = audits
                    save()
        temporary_events = directory / 'events.jsonl.tmp'
        with temporary_events.open('w', encoding='utf-8') as stream:
            for feature, window_id, fetched_at in rows:
                record = {'source_feature': feature, 'metadata': {
                    'logical_batch_id': logical_id, 'attempt_id': attempt_id,
                    'window_id': window_id,
                    'fetched_at': fetched_at if resume_children else manifest['fetched_at'],
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
    parser.add_argument('--recent-start-year', type=int, default=2001)
    parser.add_argument('--recent-years-per-window', type=int, default=5)
    parser.add_argument('--monthly-start-year', type=int)
    parser.add_argument('--recent-months-per-window', type=int, default=1)
    parser.add_argument('--daily-month')
    parser.add_argument('--resume-children', action='store_true')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    values = (args.catalog_start, args.cutoff, args.last_watermark,
              args.sweep_started_at, args.overlap_seconds)
    try:
        plan = plan_update_sweep(*values)
        initial_sweep_windows(args.catalog_start, args.cutoff, args.years_per_window,
                              args.recent_start_year, args.recent_years_per_window,
                              args.monthly_start_year, args.recent_months_per_window,
                              args.daily_month)
    except ValueError as exc:
        parser.error(str(exc))
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return
    print('Captured manifest:', run_update_sweep(*values, args.output,
                                                years_per_window=args.years_per_window,
                                                recent_start_year=args.recent_start_year,
                                                recent_years_per_window=args.recent_years_per_window,
                                                monthly_start_year=args.monthly_start_year,
                                                recent_months_per_window=args.recent_months_per_window,
                                                resume_children=args.resume_children,
                                                daily_month=args.daily_month))


if __name__ == '__main__':
    main()
