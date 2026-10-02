-- Phase 2 dimensions and event-site bridge. Local DDL only.
-- Apply with QUAKEWATCH_ROLE after cost approval and table-shape inspection.
-- The Snowpark procedure populates these objects; DDL stays outside its transaction.

-- Grain: one UTC calendar date, reused for origin and source-update roles.
CREATE TABLE IF NOT EXISTS QUAKEWATCH.CURATED.DIM_DATE (
    DATE_KEY DATE NOT NULL,
    CALENDAR_YEAR NUMBER(4, 0) NOT NULL,
    CALENDAR_MONTH NUMBER(2, 0) NOT NULL
);

-- Grain: one configured public example site. Never store private locations here.
CREATE TABLE IF NOT EXISTS QUAKEWATCH.CURATED.DIM_SITE (
    SITE_KEY VARCHAR NOT NULL,
    SITE_NAME VARCHAR NOT NULL,
    LATITUDE FLOAT NOT NULL,
    LONGITUDE FLOAT NOT NULL,
    RADIUS_KM FLOAT NOT NULL
);

-- Grain: one observed non-null source magnitude type.
CREATE TABLE IF NOT EXISTS QUAKEWATCH.CURATED.DIM_MAGNITUDE_TYPE (
    MAGNITUDE_TYPE VARCHAR NOT NULL
);

-- Grain: one observed source status, including deleted.
CREATE TABLE IF NOT EXISTS QUAKEWATCH.CURATED.DIM_EVENT_STATUS (
    SOURCE_STATUS VARCHAR NOT NULL
);

-- Grain: one canonical event revision x one configured public example site.
-- Use horizontal great-circle distance from event lon/lat to site lon/lat.
-- This is epicentral distance, not depth-aware distance or shaking.
-- Deleted records with no location retain a bridge row with NULL distance/flag.
-- The procedure must MERGE by all four key columns to enforce this grain.
CREATE TABLE IF NOT EXISTS QUAKEWATCH.CURATED.BRIDGE_EVENT_SITE (
    CANONICAL_EVENT_ID VARCHAR NOT NULL,
    SOURCE_UPDATED_AT TIMESTAMP_TZ NOT NULL,
    PAYLOAD_HASH VARCHAR(64) NOT NULL,
    SITE_KEY VARCHAR NOT NULL,
    EPICENTRAL_DISTANCE_KM FLOAT,
    WITHIN_RADIUS BOOLEAN
);
