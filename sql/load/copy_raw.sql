-- Phase 1 RAW mapping. Upload events.jsonl under a unique attempt directory first.
-- Render attempt_id with Snowflake CLI -D or the Python loader.
-- COPY keeps Snowflake's file-load history, so repeating this file without FORCE
-- should not append a second copy of the same rows.
COPY INTO QUAKEWATCH.RAW.RAW_EVENT_RECORDS (
    LOGICAL_BATCH_ID, ATTEMPT_ID, WINDOW_ID, PAYLOAD, FETCHED_AT,
    PAYLOAD_HASH, PARSER_VERSION, STAGE_FILE_NAME, STAGE_FILE_ROW_NUMBER
)
FROM (
    SELECT
        t.$1:metadata:logical_batch_id::VARCHAR,
        t.$1:metadata:attempt_id::VARCHAR,
        t.$1:metadata:window_id::VARCHAR,
        t.$1:source_feature,
        t.$1:metadata:fetched_at::TIMESTAMP_TZ,
        t.$1:metadata:payload_hash::VARCHAR,
        t.$1:metadata:parser_version::VARCHAR,
        METADATA$FILENAME,
        METADATA$FILE_ROW_NUMBER
    FROM @QUAKEWATCH.RAW.USGS_JSON_STAGE/{{ attempt_id }}/events.jsonl t
)
FILE_FORMAT = (TYPE = JSON)
ON_ERROR = ABORT_STATEMENT;
