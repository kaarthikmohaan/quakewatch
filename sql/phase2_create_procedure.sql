-- Phase 2 Snowpark procedure definition. Do not run before explicit cost and
-- deletion approval: the handler may remove duplicate curated fact/bridge rows.
-- First upload data/procedure/quakewatch_procedure.zip to the IMPORTS path.
-- Python 3.12 and Snowpark 1.55.0 were listed in this account's package catalog
-- on 2026-09-29; recheck availability before deploying.
USE ROLE QUAKEWATCH_ROLE;
USE WAREHOUSE QUAKEWATCH_WH;

CREATE OR REPLACE PROCEDURE QUAKEWATCH.CURATED.PROCESS_LOADED_ATTEMPT(ATTEMPT_ID VARCHAR)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.12'
PACKAGES = ('snowflake-snowpark-python==1.55.0')
IMPORTS = ('@QUAKEWATCH.RAW.USGS_JSON_STAGE/procedure/quakewatch_procedure.zip')
HANDLER = 'run'
EXECUTE AS OWNER
AS
$$
from quakewatch.snowpark_procedure import run as process_run

def run(session, attempt_id):
    return process_run(session, attempt_id)
$$;
