-- Phase 3 read-only quality checks. Each query should return zero rows.
-- Run only with QUAKEWATCH_ROLE after Snowflake compute-cost approval.

-- One logical revision per canonical event, source update time, and payload.
SELECT CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH,
       COUNT(*) AS DUPLICATE_ROWS
FROM QUAKEWATCH.CURATED.FACT_EVENT_REVISION
GROUP BY CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH
HAVING COUNT(*) > 1;

-- One site relationship for each logical revision and public site.
SELECT CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH, SITE_KEY,
       COUNT(*) AS DUPLICATE_ROWS
FROM QUAKEWATCH.CURATED.BRIDGE_EVENT_SITE
GROUP BY CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH, SITE_KEY
HAVING COUNT(*) > 1;
