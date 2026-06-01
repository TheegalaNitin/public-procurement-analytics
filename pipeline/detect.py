"""
Detection engine — the four anomaly rules. THIS IS THE CORE PRODUCT IP.

Each rule is pure, explainable SQL. No machine learning, no black box.
Every flag can be defended to an auditor: "this contract triggered R-01
because 4 awards went to one vendor in 20 days, summing above the
direct-award threshold." That defensibility is the whole point.

Rules:
  R-01  Contract splitting (Stückelung)        — most legally significant
  R-02  Price outlier vs CPV median            — best demo visual
  R-03  Sole-source concentration              — vendor lock-in
  R-04  Repeat direct awards                   — pattern of avoidance

All rules are idempotent: we DELETE existing flags for the rule before
re-inserting, so re-running never duplicates.
"""
import duckdb
from config.settings import (
    SPLITTING_WINDOW_DAYS, SPLITTING_MIN_CONTRACTS,
    DIRECT_AWARD_THRESHOLD_EUR, PRICE_OUTLIER_MULTIPLE,
    PRICE_OUTLIER_FLOOR_EUR, SOLE_SOURCE_SHARE, SOLE_SOURCE_MIN_EUR,
    REPEAT_DIRECT_MAX,
)
from config.logging_setup import get_logger

log = get_logger("detect")


def run_r01_splitting(con: duckdb.DuckDBPyConnection) -> int:
    """R-01: multiple direct awards to one vendor/dept/CPV-division,
    within a short window, summing above the threshold."""
    con.execute("DELETE FROM anomalies WHERE rule_id = 'R-01'")
    con.execute(f"""
        INSERT INTO anomalies
            (id, contract_id, rule_id, severity, risk_eur, description)
        WITH grouped AS (
            SELECT
                buyer_dept,
                vendor_name,
                cpv_division,
                MIN(award_date)        AS first_award,
                MAX(award_date)        AS last_award,
                COUNT(*)               AS n_contracts,
                SUM(amount_eur)        AS total_eur,
                MIN(contract_id)       AS sample_contract
            FROM contracts
            WHERE procedure_type = 'DIRECT'
                AND nuts_code LIKE 'DE50%'
            GROUP BY buyer_dept, vendor_name, cpv_division
        )
        SELECT
            uuid(),
            sample_contract,
            'R-01',
            'HIGH',
            total_eur - {DIRECT_AWARD_THRESHOLD_EUR},
            'Moegliche Stueckelung: ' || n_contracts
                || ' Direktvergaben an ' || vendor_name
                || ' (' || buyer_dept || '), Summe '
                || ROUND(total_eur) || ' EUR ueber Schwelle'
        FROM grouped
        WHERE n_contracts >= {SPLITTING_MIN_CONTRACTS}
          AND total_eur > {DIRECT_AWARD_THRESHOLD_EUR}
          AND date_diff('day', first_award, last_award)
              <= {SPLITTING_WINDOW_DAYS}
    """)
    n = con.execute(
        "SELECT COUNT(*) FROM anomalies WHERE rule_id='R-01'").fetchone()[0]
    log.info(f"R-01 splitting: {n} flags")
    return n


def run_r02_price_outlier(con: duckdb.DuckDBPyConnection) -> int:
    """R-02: contract amount exceeds N x the median for its CPV code."""
    con.execute("DELETE FROM anomalies WHERE rule_id = 'R-02'")
    con.execute(f"""
        INSERT INTO anomalies
            (id, contract_id, rule_id, severity, risk_eur, description)
        WITH with_median AS (
            SELECT
                contract_id, vendor_name, cpv_label, amount_eur,
                MEDIAN(amount_eur) OVER (PARTITION BY cpv_code) AS cpv_median
            FROM contracts
            WHERE amount_eur > 0
                AND nuts_code LIKE 'DE50%'
        )
        SELECT
            uuid(),
            contract_id,
            'R-02',
            'HIGH',
            amount_eur - cpv_median,
            'Preisausreisser: ' || ROUND(amount_eur)
                || ' EUR ist ' || ROUND(amount_eur / cpv_median, 1)
                || 'x ueber dem Median (' || ROUND(cpv_median)
                || ' EUR) fuer ' || cpv_label
        FROM with_median
        WHERE amount_eur > {PRICE_OUTLIER_MULTIPLE} * cpv_median
          AND amount_eur > {PRICE_OUTLIER_FLOOR_EUR} 
          AND cpv_median > 1000
    """)
    n = con.execute(
        "SELECT COUNT(*) FROM anomalies WHERE rule_id='R-02'").fetchone()[0]
    log.info(f"R-02 price outlier: {n} flags")
    return n


def run_r03_sole_source(con: duckdb.DuckDBPyConnection) -> int:
    """R-03: one vendor takes > X% of a dept's non-open spend."""
    con.execute("DELETE FROM anomalies WHERE rule_id = 'R-03'")
    con.execute(f"""
        INSERT INTO anomalies
            (id, contract_id, rule_id, severity, risk_eur, description)
        WITH dept_total AS (
            SELECT buyer_dept, SUM(amount_eur) AS dept_eur
            FROM contracts
            WHERE procedure_type IN ('NEGOTIATED', 'DIRECT')
                AND nuts_code LIKE 'DE50%'
            GROUP BY buyer_dept
        ),
        vendor_share AS (
            SELECT
                c.buyer_dept, c.vendor_name,
                SUM(c.amount_eur)              AS vendor_eur,
                d.dept_eur,
                SUM(c.amount_eur) / d.dept_eur AS share,
                MIN(c.contract_id)            AS sample_contract
            FROM contracts c
            JOIN dept_total d USING (buyer_dept)
            WHERE c.procedure_type IN ('NEGOTIATED', 'DIRECT')
            GROUP BY c.buyer_dept, c.vendor_name, d.dept_eur
        )
        SELECT
            uuid(),
            sample_contract,
            'R-03',
            'MED',
            vendor_eur * share,
            vendor_name || ' erhaelt ' || ROUND(share * 100)
                || '% der freihaendigen Vergaben von ' || buyer_dept
                || ' (' || ROUND(vendor_eur) || ' EUR)'
        FROM vendor_share
        WHERE share > {SOLE_SOURCE_SHARE}
          AND vendor_eur > {SOLE_SOURCE_MIN_EUR}
    """)
    n = con.execute(
        "SELECT COUNT(*) FROM anomalies WHERE rule_id='R-03'").fetchone()[0]
    log.info(f"R-03 sole-source: {n} flags")
    return n


def run_r04_repeat_direct(con: duckdb.DuckDBPyConnection) -> int:
    """R-04: same vendor + dept + year, more than N direct awards."""
    con.execute("DELETE FROM anomalies WHERE rule_id = 'R-04'")
    con.execute(f"""
        INSERT INTO anomalies
            (id, contract_id, rule_id, severity, risk_eur, description)
        WITH grouped AS (
            SELECT
                buyer_dept, vendor_name,
                date_trunc('year', award_date) AS award_year,
                COUNT(*)        AS n_awards,
                SUM(amount_eur) AS total_eur,
                MIN(contract_id) AS sample_contract
            FROM contracts
            WHERE procedure_type = 'DIRECT'
                AND nuts_code LIKE 'DE50%'
            GROUP BY buyer_dept, vendor_name,
                     date_trunc('year', award_date)
        )
        SELECT
            uuid(),
            sample_contract,
            'R-04',
            'MED',
            total_eur,
            n_awards || ' Direktvergaben an ' || vendor_name
                || ' durch ' || buyer_dept || ' in einem Jahr ('
                || ROUND(total_eur) || ' EUR gesamt)'
        FROM grouped
        WHERE n_awards > {REPEAT_DIRECT_MAX}
    """)
    n = con.execute(
        "SELECT COUNT(*) FROM anomalies WHERE rule_id='R-04'").fetchone()[0]
    log.info(f"R-04 repeat direct: {n} flags")
    return n


def run_all_rules(con: duckdb.DuckDBPyConnection) -> int:
    total = (
        run_r01_splitting(con)
        + run_r02_price_outlier(con)
        + run_r03_sole_source(con)
        + run_r04_repeat_direct(con)
    )
    log.info(f"Detection complete: {total} total flags")
    return total
