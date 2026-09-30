-- Phase 2 transformation audit. Local DDL only; apply after cost approval.
-- Grain: one Snowpark transformation invocation for one loaded RAW ATTEMPT_ID.
-- Insert success inside the model MERGE transaction. On exception, roll back
-- model changes, then insert a separate failed row outside that transaction.
-- Never replace an earlier failed processing attempt on retry.
CREATE TABLE IF NOT EXISTS QUAKEWATCH.CURATED.BATCH_PROCESS_ATTEMPT (
    PROCESS_ATTEMPT_ID VARCHAR NOT NULL,
    ATTEMPT_ID VARCHAR NOT NULL,
    STARTED_AT TIMESTAMP_TZ NOT NULL,
    FINISHED_AT TIMESTAMP_TZ NOT NULL,
    STATUS VARCHAR NOT NULL,
    STAGING_PARSER_VERSION VARCHAR NOT NULL,
    LOADED_ROWS NUMBER(38, 0) NOT NULL,
    PROCESSED_ROWS NUMBER(38, 0) NOT NULL,
    REJECTED_ROWS NUMBER(38, 0) NOT NULL,
    REVISION_ROWS_MERGED NUMBER(38, 0) NOT NULL,
    ERROR_TYPE VARCHAR,
    ERROR_MESSAGE VARCHAR,
    RECORDED_AT TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Append-only success or failure record for one Snowpark transform invocation';
