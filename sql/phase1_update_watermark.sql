-- Phase 1 update-sweep watermark. Apply with QUAKEWATCH_ROLE after RAW tables.
-- Grain: one row per named sweep. The update loader advances it with a
-- compare-and-set UPDATE only after the sweep's RAW receipt and per-window
-- counts reconcile, so a concurrent or stale runner cannot move it.

CREATE TABLE IF NOT EXISTS QUAKEWATCH.RAW.UPDATE_WATERMARK (
    SWEEP_NAME VARCHAR NOT NULL,
    COMMITTED_WATERMARK TIMESTAMP_TZ NOT NULL,
    PREVIOUS_WATERMARK TIMESTAMP_TZ,
    ATTEMPT_ID VARCHAR NOT NULL,
    CATALOG_LOWER_BOUND TIMESTAMP_TZ NOT NULL,
    ORIGIN_TIME_CUTOFF TIMESTAMP_TZ NOT NULL,
    COMMITTED_AT TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Committed updatedafter watermark per update sweep';
