"""
Detection engine — the four anomaly rules plus jurisdiction tagging
and auto-validation using structured TED fields.
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


# ── Jurisdiction classification (rule-based, no hardcoded names) ───────
def classify_jurisdiction(buyer: str) -> str:
    """Bremen state bodies name themselves after the state or its cities."""
    if not buyer:
        return 'unknown'
    b = buyer.lower()
    markers = ('bremen', 'bremerhaven', 'hansestadt', 'hanseatische')
    return 'bremen_state' if any(m in b for m in markers) else 'external'


def tag_jurisdiction(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute(
        "SELECT contract_id, buyer_dept FROM contracts"
    ).fetchall()
    for cid, buyer in rows:
        con.execute(
            "UPDATE contracts SET jurisdiction = ? WHERE contract_id = ?",
            [classify_jurisdiction(buyer), cid]
        )
    log.info("Jurisdiction tagging complete")


# ── R-01 Contract splitting ────────────────────────────────────────────
def run_r01_splitting(con: duckdb.DuckDBPyConnection) -> int:
    con.execute("DELETE FROM anomalies WHERE rule_id = 'R-01'")
    con.execute(f"""
        INSERT INTO anomalies
            (id, contract_id, rule_id, severity, risk_eur, description)
        WITH grouped AS (
            SELECT
                buyer_dept, vendor_name, cpv_division,
                MIN(award_date) AS first_award,
                MAX(award_date) AS last_award,
                COUNT(*)        AS n_contracts,
                SUM(amount_eur) AS total_eur,
                MIN(contract_id) AS sample_contract
            FROM contracts
            WHERE procedure_type = 'DIRECT'
              AND nuts_code LIKE 'DE50%'
              AND jurisdiction = 'bremen_state'
            GROUP BY buyer_dept, vendor_name, cpv_division
        )
        SELECT
            uuid(), sample_contract, 'R-01', 'HIGH',
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


# ── R-02 Price outlier (frameworks compared only to frameworks) ────────
def run_r02_price_outlier(con: duckdb.DuckDBPyConnection) -> int:
    con.execute("DELETE FROM anomalies WHERE rule_id = 'R-02'")
    con.execute(f"""
        INSERT INTO anomalies
            (id, contract_id, rule_id, severity, risk_eur, description)
        WITH with_median AS (
            SELECT
                contract_id, vendor_name, cpv_label, amount_eur, is_framework,
                MEDIAN(amount_eur) OVER (
                    PARTITION BY cpv_code, is_framework
                ) AS cpv_median
            FROM contracts
            WHERE amount_eur > 0
              AND nuts_code LIKE 'DE50%'
              AND jurisdiction = 'bremen_state'
        )
        SELECT
            uuid(), contract_id, 'R-02', 'HIGH',
            amount_eur - cpv_median,
            CASE WHEN is_framework
                 THEN 'Rahmenvereinbarung: ' ELSE 'Einzelvertrag: ' END
            || 'Preisausreisser: ' || ROUND(amount_eur)
            || ' EUR ist ' || ROUND(amount_eur / cpv_median, 1)
            || 'x ueber dem Median (' || ROUND(cpv_median)
            || ' EUR) fuer ' || cpv_label
            || CASE WHEN is_framework
                    THEN ' (Vergleich nur mit anderen Rahmenvereinbarungen)'
                    ELSE '' END
        FROM with_median
        WHERE amount_eur > {PRICE_OUTLIER_MULTIPLE} * cpv_median
          AND amount_eur > {PRICE_OUTLIER_FLOOR_EUR}
          AND cpv_median > 1000
    """)
    n = con.execute(
        "SELECT COUNT(*) FROM anomalies WHERE rule_id='R-02'").fetchone()[0]
    log.info(f"R-02 price outlier: {n} flags")
    return n


# ── R-03 Sole-source concentration ─────────────────────────────────────
def run_r03_sole_source(con: duckdb.DuckDBPyConnection) -> int:
    con.execute("DELETE FROM anomalies WHERE rule_id = 'R-03'")
    con.execute(f"""
        INSERT INTO anomalies
            (id, contract_id, rule_id, severity, risk_eur, description)
        WITH dept_total AS (
            SELECT buyer_dept, SUM(amount_eur) AS dept_eur
            FROM contracts
            WHERE procedure_type IN ('NEGOTIATED', 'DIRECT')
              AND jurisdiction = 'bremen_state'
            GROUP BY buyer_dept
        ),
        dept_counts AS (
            SELECT buyer_dept, COUNT(*) AS dept_contract_count
            FROM contracts
            WHERE procedure_type IN ('NEGOTIATED', 'DIRECT')
              AND jurisdiction = 'bremen_state'
            GROUP BY buyer_dept
        ),
        vendor_share AS (
            SELECT
                c.buyer_dept, c.vendor_name,
                SUM(c.amount_eur)              AS vendor_eur,
                d.dept_eur,
                SUM(c.amount_eur) / d.dept_eur AS share,
                dc.dept_contract_count,
                MIN(c.contract_id)            AS sample_contract
            FROM contracts c
            JOIN dept_total d USING (buyer_dept)
            JOIN dept_counts dc USING (buyer_dept)
            WHERE c.procedure_type IN ('NEGOTIATED', 'DIRECT')
              AND c.jurisdiction = 'bremen_state'
            GROUP BY c.buyer_dept, c.vendor_name, d.dept_eur,
                     dc.dept_contract_count
        )
        SELECT
            uuid(), sample_contract, 'R-03', 'MED',
            vendor_eur * share,
            vendor_name || ' erhaelt ' || ROUND(share * 100)
                || '% der freihaendigen Vergaben von ' || buyer_dept
                || ' (' || ROUND(vendor_eur) || ' EUR)'
        FROM vendor_share
        WHERE share > {SOLE_SOURCE_SHARE}
          AND vendor_eur > {SOLE_SOURCE_MIN_EUR}
          AND dept_contract_count >= 3
    """)
    n = con.execute(
        "SELECT COUNT(*) FROM anomalies WHERE rule_id='R-03'").fetchone()[0]
    log.info(f"R-03 sole-source: {n} flags")
    return n


# ── R-04 Repeat direct awards ──────────────────────────────────────────
def run_r04_repeat_direct(con: duckdb.DuckDBPyConnection) -> int:
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
              AND jurisdiction = 'bremen_state'
            GROUP BY buyer_dept, vendor_name,
                     date_trunc('year', award_date)
        )
        SELECT
            uuid(), sample_contract, 'R-04', 'MED',
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


# ── Auto-validation using structured fields ────────────────────────────
def apply_validation(con: duckdb.DuckDBPyConnection) -> None:
    # Downgrade flags with healthy open competition (3+ bidders).
    con.execute("""
        UPDATE anomalies
        SET severity = 'LOW',
            description = description
                || ' [Auto-Validierung: offenes Verfahren mit Wettbewerb '
                || '— wahrscheinlich unkritisch]'
        WHERE rule_id = 'R-02'
          AND contract_id IN (
              SELECT contract_id FROM contracts
              WHERE procedure_type = 'OPEN' AND num_bidders >= 3
          )
    """)
    # Elevate single-bidder awards — the genuine concern.
    con.execute("""
        UPDATE anomalies
        SET severity = 'HIGH',
            description = description
                || ' [Auto-Validierung: nur 1 Bieter — '
                || 'Wettbewerb fehlt, Pruefung empfohlen]'
        WHERE contract_id IN (
            SELECT contract_id FROM contracts WHERE num_bidders = 1
        )
    """)
    # Annotate negotiated procedures.
    con.execute("""
        UPDATE anomalies
        SET description = description || ' [Verhandlungsverfahren]'
        WHERE contract_id IN (
            SELECT contract_id FROM contracts
            WHERE procedure_type = 'NEGOTIATED'
        )
        AND description NOT LIKE '%Verhandlungsverfahren%'
    """)
    log.info("Auto-validation applied to flags")


# ── Orchestrator ───────────────────────────────────────────────────────
def run_all_rules(con: duckdb.DuckDBPyConnection) -> int:
    tag_jurisdiction(con)
    total = (
        run_r01_splitting(con)
        + run_r02_price_outlier(con)
        + run_r03_sole_source(con)
        + run_r04_repeat_direct(con)
    )
    apply_validation(con)
    log.info(f"Detection complete: {total} total flags")
    return total