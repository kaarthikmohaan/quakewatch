-- Phase 4 optional recovery demo: read-only preflight for the isolated fixture.
-- REVIEW ONLY. Running the SELECTs may resume QUAKEWATCH_WH and incur credits.
-- Run only after the owner approves that possible cost. No clone or mutation here.

USE ROLE QUAKEWATCH_ROLE;
USE WAREHOUSE QUAKEWATCH_WH;

SELECT CURRENT_ROLE() AS ACTIVE_ROLE,
       CURRENT_WAREHOUSE() AS ACTIVE_WAREHOUSE,
       CURRENT_TIMESTAMP() AS CHECKED_AT;

-- Expect exactly one BASE TABLE named FACT_EVENT_REVISION, no demo clone,
-- and RETENTION_TIME >= 1 day. Stop if any value differs. INFORMATION_SCHEMA
-- lists only objects visible to the active role; absence is not proof that a
-- differently owned object cannot exist. The CREATE step must also use no
-- IF NOT EXISTS guard so a collision fails safely.
SELECT TABLE_NAME, TABLE_TYPE, TABLE_OWNER, ROW_COUNT,
       RETENTION_TIME, IS_TRANSIENT
FROM QUAKEWATCH_PHASE2_FIXTURE.INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'CURATED'
  AND TABLE_NAME IN ('FACT_EVENT_REVISION', 'QW_PHASE4_REVISION_DEMO')
ORDER BY TABLE_NAME;

-- Exact fixture count, separate from the metadata row estimate. Expect 5
-- revisions based on the latest documented fixture snapshot; stop if drifted.
SELECT COUNT(*) AS SOURCE_REVISION_ROWS
FROM QUAKEWATCH_PHASE2_FIXTURE.CURATED.FACT_EVENT_REVISION;

-- The logical fact grain must be unique before cloning. Expect 0 rows.
SELECT CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH,
       COUNT(*) AS DUPLICATE_COUNT
FROM QUAKEWATCH_PHASE2_FIXTURE.CURATED.FACT_EVENT_REVISION
GROUP BY CANONICAL_EVENT_ID, SOURCE_UPDATED_AT, PAYLOAD_HASH
HAVING COUNT(*) > 1;
