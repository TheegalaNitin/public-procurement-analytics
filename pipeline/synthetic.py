"""
Synthetic data generator — realistic Bremen contracts with PLANTED anomalies.

Why this matters: the TED API rate-limits, and you cannot demo on an empty
database. This generates believable Bremen procurement data AND deliberately
injects each of the four anomaly types so you can:
  1. Prove the detection rules actually fire (testing)
  2. Show a compelling demo with real-looking flagged cases

Every planted anomaly is tagged in the description so you can verify the
detector catches exactly what was planted — no more, no less.
"""
import random
import uuid
from datetime import date, timedelta

from config.logging_setup import get_logger
from pipeline.schema import get_connection
from config.settings import DIRECT_AWARD_THRESHOLD_EUR

log = get_logger("synthetic")

random.seed(42)  # deterministic — same demo data every run

BREMEN_DEPTS = [
    "Senator fuer Finanzen", "Senator fuer Inneres",
    "Senatorin fuer Wirtschaft", "Immobilien Bremen",
    "Senatorin fuer Umwelt", "Bremer Stadtreinigung",
    "Senatorin fuer Soziales", "Gesundheitsamt Bremen",
]

VENDORS = [
    "Nordbau GmbH", "Hanse IT Solutions GmbH", "Weser Consulting AG",
    "Bremer Bürobedarf KG", "TechnikPartner GmbH", "BauWerk Nord GmbH",
    "Digitalis Software UG", "Reinigung Plus GmbH", "MediTech Bremen GmbH",
    "Logistik Weser GmbH", "GreenEnergy Nord GmbH", "ProConsult Partner AG",
]

# (cpv_code, label, typical_median_eur) — realistic categories
CPV_CATALOG = [
    ("45000000", "Bauarbeiten", 180_000),
    ("72000000", "IT-Dienstleistungen", 95_000),
    ("79400000", "Unternehmensberatung", 60_000),
    ("30192000", "Bürobedarf", 8_000),
    ("90910000", "Reinigungsdienste", 45_000),
    ("33100000", "Medizinische Geräte", 120_000),
    ("60100000", "Strassentransport", 30_000),
    ("09310000", "Elektrizität", 75_000),
]

PROCEDURES = ["OPEN", "RESTRICTED", "NEGOTIATED", "DIRECT"]


def _rand_date(days_back_max: int = 365) -> date:
    return date.today() - timedelta(days=random.randint(0, days_back_max))


def generate(n_normal: int = 400) -> None:
    con = get_connection()
    con.execute("DELETE FROM contracts")  # idempotent reset for demo
    con.execute("DELETE FROM cpv_reference")

    # Load CPV reference
    for code, label, _ in CPV_CATALOG:
        con.execute(
            "INSERT OR REPLACE INTO cpv_reference VALUES (?, ?)",
            [code, label],
        )

    rows = []

    # ── Normal background contracts ──────────────────────────────────
    for _ in range(n_normal):
        cpv_code, cpv_label, median = random.choice(CPV_CATALOG)
        # amounts cluster around the median (log-normal-ish)
        amount = round(median * random.uniform(0.5, 1.8), 2)
        rows.append({
            "contract_id": f"NORM-{uuid.uuid4().hex[:10]}",
            "buyer_dept": random.choice(BREMEN_DEPTS),
            "vendor_name": random.choice(VENDORS),
            "amount_eur": amount,
            "cpv_code": cpv_code,
            "cpv_label": cpv_label,
            "award_date": _rand_date(),
            "procedure_type": random.choices(
                PROCEDURES, weights=[50, 20, 20, 10])[0],
        })

    # ── PLANT R-01: contract splitting ───────────────────────────────
    # One vendor gets 4 direct awards to one dept, same CPV division,
    # all within 20 days, each just under the threshold.
    split_date = _rand_date(100)
    for i in range(4):
        rows.append({
            "contract_id": f"SPLIT-{i}-{uuid.uuid4().hex[:6]}",
            "buyer_dept": "Immobilien Bremen",
            "vendor_name": "BauWerk Nord GmbH",
            "amount_eur": DIRECT_AWARD_THRESHOLD_EUR - 1_500,  # just under
            "cpv_code": "45000000",
            "cpv_label": "Bauarbeiten",
            "award_date": split_date + timedelta(days=i * 5),
            "procedure_type": "DIRECT",
        })

    # ── PLANT R-02: price outlier ────────────────────────────────────
    # One office-supply contract at 6x the median (8k -> 48k).
    rows.append({
        "contract_id": f"OUTLIER-{uuid.uuid4().hex[:8]}",
        "buyer_dept": "Senator fuer Inneres",
        "vendor_name": "Bremer Bürobedarf KG",
        "amount_eur": 48_000,  # median is ~8k
        "cpv_code": "30192000",
        "cpv_label": "Bürobedarf",
        "award_date": _rand_date(60),
        "procedure_type": "DIRECT",
    })

    # ── PLANT R-03: sole-source concentration ────────────────────────
    # One vendor takes >40% of a dept's negotiated spend.
    for i in range(6):
        rows.append({
            "contract_id": f"SOLE-{i}-{uuid.uuid4().hex[:6]}",
            "buyer_dept": "Gesundheitsamt Bremen",
            "vendor_name": "MediTech Bremen GmbH",
            "amount_eur": round(random.uniform(40_000, 80_000), 2),
            "cpv_code": "33100000",
            "cpv_label": "Medizinische Geräte",
            "award_date": _rand_date(300),
            "procedure_type": "NEGOTIATED",
        })

    # ── PLANT R-04: repeat direct awards ─────────────────────────────
    # Same vendor, same dept, 5 direct awards in one year.
    for i in range(5):
        rows.append({
            "contract_id": f"REPEAT-{i}-{uuid.uuid4().hex[:6]}",
            "buyer_dept": "Senatorin fuer Wirtschaft",
            "vendor_name": "ProConsult Partner AG",
            "amount_eur": round(random.uniform(15_000, 23_000), 2),
            "cpv_code": "79400000",
            "cpv_label": "Unternehmensberatung",
            "award_date": _rand_date(330),
            "procedure_type": "DIRECT",
        })

    # ── Insert all rows ──────────────────────────────────────────────
    for r in rows:
        con.execute("""
            INSERT OR REPLACE INTO contracts
            (contract_id, source, buyer_name, buyer_dept, vendor_name,
             vendor_name_norm, amount_eur, cpv_code, cpv_division,
             cpv_label, award_date, procedure_type, nuts_code)
            VALUES (?, 'synthetic', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DE501')
        """, [
            r["contract_id"], r["buyer_dept"], r["buyer_dept"],
            r["vendor_name"], r["vendor_name"].upper().strip(),
            r["amount_eur"], r["cpv_code"], r["cpv_code"][:2],
            r["cpv_label"], r["award_date"], r["procedure_type"],
        ])

    total = con.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
    log.info(f"Generated {total} synthetic contracts "
             f"({n_normal} normal + planted anomalies)")
    con.close()


if __name__ == "__main__":
    generate()
    print("Synthetic data generated. Planted anomalies:")
    print("  R-01: 4 split contracts (Immobilien Bremen / BauWerk Nord)")
    print("  R-02: 1 price outlier (Bürobedarf at 6x median)")
    print("  R-03: sole-source concentration (Gesundheitsamt / MediTech)")
    print("  R-04: 5 repeat direct awards (Wirtschaft / ProConsult)")
