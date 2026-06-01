"""
Database schema — DuckDB warehouse.

Creating this is idempotent (CREATE TABLE IF NOT EXISTS), so it is safe to
run on every pipeline start. Tables follow the staging -> mart pattern:
  - raw_notices     : as-ingested, minimally processed
  - contracts       : cleaned, normalised analytical table (the mart)
  - anomalies       : detected flags
  - pipeline_runs   : observability — every run logged
  - quality_log     : data quality check results per run
"""
import duckdb
from config.settings import DB_PATH
from config.logging_setup import get_logger

log = get_logger("pipeline.schema")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS raw_notices (
    notice_id       VARCHAR PRIMARY KEY,
    source          VARCHAR,        -- 'ted' | 'vergabe_bremen'
    raw_json        VARCHAR,        -- original payload for lineage
    ingested_at     TIMESTAMP DEFAULT now(),
    source_file     VARCHAR
);

CREATE TABLE IF NOT EXISTS contracts (
    contract_id     VARCHAR PRIMARY KEY,
    source          VARCHAR,
    buyer_name      VARCHAR,
    buyer_dept      VARCHAR,
    vendor_name     VARCHAR,
    vendor_name_norm VARCHAR,       -- normalised for matching
    amount_eur      DOUBLE,
    cpv_code        VARCHAR,
    cpv_division    VARCHAR,        -- first 2 digits of CPV
    cpv_label       VARCHAR,
    award_date      DATE,
    procedure_type  VARCHAR,        -- OPEN|RESTRICTED|NEGOTIATED|DIRECT
    nuts_code       VARCHAR,
    ingested_at     TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cpv_reference (
    code            VARCHAR PRIMARY KEY,
    label           VARCHAR
);

CREATE TABLE IF NOT EXISTS anomalies (
    id              VARCHAR DEFAULT (uuid()),
    contract_id     VARCHAR,
    rule_id         VARCHAR,        -- R-01 .. R-04
    severity        VARCHAR,        -- HIGH | MED | LOW
    risk_eur        DOUBLE,
    description     VARCHAR,
    flagged_at      TIMESTAMP DEFAULT now(),
    reviewed        BOOLEAN DEFAULT false,
    outcome         VARCHAR DEFAULT 'open',  -- open|confirmed|false_positive
    reviewer_note   VARCHAR
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          VARCHAR PRIMARY KEY,
    started_at      TIMESTAMP,
    finished_at     TIMESTAMP,
    status          VARCHAR,        -- success | failed
    rows_ingested   INTEGER,
    contracts_built INTEGER,
    flags_created   INTEGER,
    error_message   VARCHAR
);

CREATE TABLE IF NOT EXISTS quality_log (
    run_id          VARCHAR,
    check_name      VARCHAR,
    failure_count   INTEGER,
    passed          BOOLEAN,
    logged_at       TIMESTAMP DEFAULT now()
);
"""


def create_schema(con: duckdb.DuckDBPyConnection) -> None:
    for statement in SCHEMA_SQL.strip().split(";"):
        stmt = statement.strip()
        if stmt:
            con.execute(stmt)
    log.info("Schema ensured (all tables present)")


def get_connection(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(DB_PATH), read_only=read_only)
    if not read_only:
        create_schema(con)
    return con
