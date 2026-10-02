"""One bounded clone and Time Travel drill in the QuakeWatch fixture database."""

import json
from pathlib import Path

import snowflake.connector

from scripts.checks.phase4_usage import checked_admin_profile


SOURCE = "QUAKEWATCH_PHASE2_FIXTURE.CURATED.FACT_EVENT_REVISION"
CLONE_NAME = "QW_LIVE_DEMO_EE3A351BE3"
CLONE = f"QUAKEWATCH_PHASE2_FIXTURE.CURATED.{CLONE_NAME}"


def main():
    profile = checked_admin_profile(Path.home() / ".snowflake" / "config.toml")
    profile["role"] = "QUAKEWATCH_ROLE"
    with snowflake.connector.connect(**profile, warehouse="QUAKEWATCH_WH") as connection:
        with connection.cursor() as cursor:
            cursor.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 120")
            cursor.execute("SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE()")
            if cursor.fetchone() != ("QUAKEWATCH_ROLE", "QUAKEWATCH_WH"):
                raise RuntimeError("Unexpected role or warehouse")
            cursor.execute("""
                SELECT TABLE_NAME, TABLE_TYPE, TABLE_OWNER, RETENTION_TIME
                FROM QUAKEWATCH_PHASE2_FIXTURE.INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = 'CURATED'
                  AND TABLE_NAME IN ('FACT_EVENT_REVISION', %s)
            """, (CLONE_NAME,))
            metadata = cursor.fetchall()
            if metadata != [("FACT_EVENT_REVISION", "BASE TABLE", "QUAKEWATCH_ROLE", 1)]:
                raise RuntimeError(f"Fixture or clone metadata changed: {metadata}")
            cursor.execute(f"SELECT COUNT(*) FROM {SOURCE}")
            if int(cursor.fetchone()[0]) != 5:
                raise RuntimeError("Fixture source must have exactly five rows")
            cursor.execute(f"""
                SELECT COUNT(*) FROM (
                    SELECT CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH
                    FROM {SOURCE}
                    GROUP BY CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH
                    HAVING COUNT(*) > 1
                )
            """)
            if int(cursor.fetchone()[0]) != 0:
                raise RuntimeError("Fixture source has duplicate keys")
            cursor.execute(f"""
                SELECT CANONICAL_EVENT_ID, SOURCE_UPDATED_AT::VARCHAR, PAYLOAD_HASH, MAGNITUDE
                FROM {SOURCE} WHERE MAGNITUDE IS NOT NULL
                ORDER BY CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH LIMIT 1
            """)
            event_id, source_updated_at, payload_hash, magnitude = cursor.fetchone()
            original = float(magnitude)
            bad = original + 1000.0
            print(json.dumps({"preflight": "pass", "source_rows": 5,
                              "clone": CLONE, "original_magnitude": original}), flush=True)

            cursor.execute(f"CREATE TABLE {CLONE} CLONE {SOURCE}")
            clone_query_id = cursor.sfqid
            cursor.execute(f"SELECT COUNT(*) FROM {CLONE}")
            if int(cursor.fetchone()[0]) != 5:
                raise RuntimeError("Clone count differs; leave clone for inspection")
            cursor.execute(f"""
                MERGE INTO {CLONE} target
                USING (SELECT %s::VARCHAR AS CANONICAL_EVENT_ID,
                              TO_TIMESTAMP_TZ(%s) AS SOURCE_UPDATED_AT,
                              %s::VARCHAR AS PAYLOAD_HASH,
                              %s::FLOAT AS BAD_MAGNITUDE) incoming
                ON target.CANONICAL_EVENT_ID = incoming.CANONICAL_EVENT_ID
                   AND target.SOURCE_UPDATED_AT = incoming.SOURCE_UPDATED_AT
                   AND target.PAYLOAD_HASH = incoming.PAYLOAD_HASH
                WHEN MATCHED THEN UPDATE SET MAGNITUDE = incoming.BAD_MAGNITUDE
            """, (event_id, source_updated_at, payload_hash, bad))
            merge_query_id = cursor.sfqid
            if cursor.rowcount != 1:
                raise RuntimeError("Unexpected clone MERGE count; leave clone for inspection")
            where = "WHERE CANONICAL_EVENT_ID = %s AND SOURCE_UPDATED_AT = TO_TIMESTAMP_TZ(%s) AND PAYLOAD_HASH = %s"
            key = (event_id, source_updated_at, payload_hash)
            cursor.execute(f"SELECT MAGNITUDE FROM {SOURCE} {where}", key)
            source_after = float(cursor.fetchone()[0])
            cursor.execute(f"SELECT MAGNITUDE FROM {CLONE} {where}", key)
            clone_after = float(cursor.fetchone()[0])
            cursor.execute(f"SELECT MAGNITUDE FROM {CLONE} BEFORE (STATEMENT => '{merge_query_id}') {where}", key)
            before = float(cursor.fetchone()[0])
            if (source_after, clone_after, before) != (original, bad, original):
                raise RuntimeError("Clone or Time Travel check failed; leave clone for inspection")
            print(json.dumps({"clone_check": "pass", "source_value": source_after,
                              "changed_clone_value": clone_after, "time_travel_value": before,
                              "clone_query_id": clone_query_id, "merge_query_id": merge_query_id}), flush=True)
            cursor.execute(f"DROP TABLE {CLONE}")
            drop_query_id = cursor.sfqid
            cursor.execute("""
                SELECT COUNT(*) FROM QUAKEWATCH_PHASE2_FIXTURE.INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = 'CURATED' AND TABLE_NAME = %s
            """, (CLONE_NAME,))
            if int(cursor.fetchone()[0]) != 0:
                raise RuntimeError("Demo clone still exists")
            print(json.dumps({"cleanup": "pass", "dropped_only": CLONE,
                              "drop_query_id": drop_query_id}), flush=True)


if __name__ == "__main__":
    main()
