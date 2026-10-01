"""One bounded, on-demand Cortex trial over the public Seattle sample."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from scripts.phase4_usage import checked_admin_profile


MODEL = "llama3.1-8b"
SITE = "seattle"
START = "2026-09-28T00:00:00Z"
END = "2026-09-29T00:00:00Z"
FILTER = """
FROM QUAKEWATCH.CURATED.EVENT_CURRENT e
JOIN QUAKEWATCH.CURATED.BRIDGE_EVENT_SITE b
  ON e.CANONICAL_EVENT_ID = b.CANONICAL_EVENT_ID
 AND e.SOURCE_UPDATED_AT = b.SOURCE_UPDATED_AT
 AND e.PAYLOAD_HASH = b.PAYLOAD_HASH
WHERE b.SITE_KEY = %s AND b.WITHIN_RADIUS = TRUE
  AND e.ORIGIN_TIME >= TO_TIMESTAMP_TZ(%s)
  AND e.ORIGIN_TIME < TO_TIMESTAMP_TZ(%s)
"""


def prompt_for(summary: dict) -> str:
    """Send aggregate facts only: no coordinates, raw payload, or credentials."""
    return (
        "Write exactly one short sentence from these SQL facts. Include every "
        "fact. Do not invent a radius size; radius size is not supplied. "
        "Do not infer risk, shaking, damage, or actions. Call this a modeled "
        "sample, not complete coverage.\n"
        f"Site={SITE}; UTC window={START} to {END}; "
        f"count={summary['event_count']}; "
        f"nearest ID={summary['nearest_event_id']}; "
        f"nearest distance={summary['nearest_distance_km']} km; "
        f"nearest magnitude={summary['nearest_magnitude']}; "
        f"nearest source status={summary['nearest_source_status']}; "
        f"nearest source record age={summary['nearest_age_hours']} hours."
    )


def validate_brief(message: str, summary: dict) -> list[str]:
    """Reject unsafe, incomplete, or obviously invented facts; SQL remains source."""
    problems = []
    lowered = message.lower()
    for field in ("event_count", "nearest_event_id", "nearest_distance_km",
                  "nearest_magnitude", "nearest_source_status", "nearest_age_hours"):
        if str(summary[field]).lower() not in lowered:
            problems.append(f"missing {field}")
    if re.search(r"\b(risk|shaking|damage|evacuat\w*|shelter|safe|danger)\b", lowered):
        problems.append("hazard or action language")
    if re.search(r"\b(?:within|radius)(?:\W+\w+){0,4}\W+\d+(?:\.\d+)?\s*km\b", lowered):
        problems.append("unsupported radius size")
    if re.search(r"\baway from\s+" + re.escape(str(summary["nearest_event_id"]).lower()) + r"\b", lowered):
        problems.append("distance incorrectly anchored to event ID")
    if not message.rstrip().endswith((".", "!", "?")):
        problems.append("incomplete ending")
    return problems


def execute() -> dict:
    import snowflake.connector

    profile = checked_admin_profile(Path.home() / ".snowflake" / "config.toml")
    profile["role"] = "QUAKEWATCH_ROLE"
    with snowflake.connector.connect(**profile, warehouse="QUAKEWATCH_WH") as connection:
        with connection.cursor() as cursor:
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 120")
            cursor.execute("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE()")
            if cursor.fetchone() != ("QUAKEWATCH_ROLE", "QUAKEWATCH_WH"):
                raise RuntimeError("unexpected Snowflake role or warehouse")
            cursor.execute(
                "SELECT COUNT(*) " + FILTER,
                (SITE, START, END),
            )
            event_count = int(cursor.fetchone()[0])
            count_query_id = cursor.sfqid
            if not 0 < event_count <= 100:
                raise RuntimeError(f"sample count outside trial bounds: {event_count}")
            cursor.execute(
                "SELECT e.CANONICAL_EVENT_ID, ROUND(b.EPICENTRAL_DISTANCE_KM, 1), "
                "e.MAGNITUDE, e.SOURCE_STATUS, "
                "ROUND(DATEDIFF('minute', e.SOURCE_UPDATED_AT, CURRENT_TIMESTAMP()) / 60.0, 1) "
                + FILTER +
                " ORDER BY b.EPICENTRAL_DISTANCE_KM, e.CANONICAL_EVENT_ID LIMIT 1",
                (SITE, START, END),
            )
            nearest = cursor.fetchone()
            nearest_query_id = cursor.sfqid
            if nearest is None:
                raise RuntimeError("count and nearest-event queries disagree")
            summary = dict(zip(
                ("nearest_event_id", "nearest_distance_km", "nearest_magnitude",
                 "nearest_source_status", "nearest_age_hours"), nearest,
            ))
            summary["event_count"] = event_count
            prompt = prompt_for(summary)
            if len(prompt) > 1200:
                raise RuntimeError("Cortex prompt exceeds trial cap")
            try:
                cursor.execute(
                    "SELECT AI_COMPLETE(model => 'llama3.1-8b', prompt => %s, "
                    "model_parameters => {'temperature': 0, 'max_tokens': 120}, "
                    "show_details => TRUE)",
                    (prompt,),
                )
            except snowflake.connector.errors.ProgrammingError as error:
                if error.errno != 399258:
                    raise
                return {
                    "status": "cortex_unavailable_for_trial_account",
                    "site": SITE,
                    "window_utc": [START, END],
                    "sql_facts": summary,
                    "count_query_id": count_query_id,
                    "nearest_query_id": nearest_query_id,
                    "model": MODEL,
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    "snowflake_error_code": error.errno,
                    "fallback": "Show the deterministic SQL facts; no AI summary exists.",
                }
            details = cursor.fetchone()[0]
            cortex_query_id = cursor.sfqid
            if isinstance(details, str):
                details = json.loads(details)
            message = details.get("choices", [{}])[0].get("messages", "")
            problems = validate_brief(message, summary)
            return {
                "site": SITE,
                "window_utc": [START, END],
                "sql_facts": summary,
                "count_query_id": count_query_id,
                "nearest_query_id": nearest_query_id,
                "cortex_query_id": cortex_query_id,
                "model": MODEL,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "cortex_details": details,
                "brief_status": "rejected" if problems else "needs_human_fact_check",
                "validation_problems": problems,
                "fallback": None if not problems else "Show deterministic SQL facts instead.",
                "note": "One Cortex call only; passing automatic checks still requires human fact review.",
            }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="run the approved paid trial")
    args = parser.parse_args()
    if args.execute:
        print(json.dumps(execute(), indent=2, sort_keys=True, default=str))
    else:
        print(f"Preview: {MODEL}, {SITE}, {START} to {END}; one AI_COMPLETE call, max 120 output tokens")


if __name__ == "__main__":
    main()
