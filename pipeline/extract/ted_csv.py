"""
TED CSV loader — imports real Bremen procurement data from the
TED CSV annual export files into the DuckDB warehouse.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import duckdb
from config.settings import DB_PATH, DATA_RAW
from config.logging_setup import get_logger

log = get_logger("extract.ted_csv")

RAW_TED = DATA_RAW / "ted"
RAW_TED.mkdir(parents=True, exist_ok=True)

BREMEN_NUTS_PREFIX = "DE50"

PROCEDURE_MAP = {
    "1": "OPEN", "2": "RESTRICTED", "3": "NEGOTIATED",
    "4": "DIRECT", "6": "NEGOTIATED", "9": "OTHER",
}

CPV_LABELS = {
    "03": "Land- und Forstwirtschaft", "09": "Energie und Kraftstoffe",
    "14": "Bergbauerzeugnisse", "15": "Nahrungsmittel",
    "16": "Landmaschinen", "18": "Bekleidung", "19": "Leder und Textilien",
    "22": "Druckerzeugnisse", "24": "Chemische Erzeugnisse",
    "30": "Büromaschinen und EDV", "31": "Elektrische Maschinen",
    "32": "Telekommunikation", "33": "Medizinische Geräte",
    "34": "Transportausrüstung", "35": "Sicherheitsausrüstung",
    "37": "Musikinstrumente und Sport", "38": "Laborgeräte",
    "39": "Möbel und Einrichtung", "41": "Wasser",
    "42": "Industriemaschinen", "43": "Bergbaumaschinen",
    "44": "Baumaterialien", "45": "Bauarbeiten",
    "48": "Softwareprodukte", "50": "Reparatur und Wartung",
    "51": "Installationsarbeiten", "55": "Hoteldienstleistungen",
    "60": "Transportdienstleistungen", "63": "Hilfsdienstleistungen",
    "64": "Post und Telekommunikation", "65": "Versorgungsleistungen",
    "66": "Finanzdienstleistungen", "70": "Immobiliendienstleistungen",
    "71": "Architektur und Ingenieurleistungen", "72": "IT-Dienstleistungen",
    "73": "Forschung und Entwicklung", "75": "Öffentliche Verwaltung",
    "76": "Dienstleistungen Öl und Gas", "77": "Forstwirtschaft",
    "79": "Unternehmensdienstleistungen", "80": "Bildung und Ausbildung",
    "85": "Gesundheitswesen", "90": "Abwasser und Abfall",
    "92": "Freizeit und Kultur", "98": "Sonstige Dienstleistungen",
}


def get_cpv_label(cpv_code: str) -> str:
    if not cpv_code or str(cpv_code) == "nan":
        return ""
    division = str(cpv_code).strip()[:2]
    return CPV_LABELS.get(division, "")


def load_ted_csv(csv_path: str) -> int:
    path = Path(csv_path)
    if not path.exists():
        log.error(f"File not found: {csv_path}")
        return 0

    log.info(f"Reading {path.name} ...")
    chunk_size = 50_000
    total_inserted = 0
    con = duckdb.connect(str(DB_PATH))

    # Probe columns first
    probe = pd.read_csv(csv_path, nrows=1, low_memory=False,
                        encoding="utf-8", on_bad_lines="skip")
    required = {"DT_AWARD", "WIN_NAME", "VALUE_EURO", "TAL_LOCATION_NUTS"}
    if not required.issubset(set(probe.columns)):
        log.warning(
            f"Skipping {path.name} — missing award columns "
            f"(this is a contract notices file, not an awards file)"
        )
        con.close()
        return 0

    for chunk_num, chunk in enumerate(
        pd.read_csv(csv_path, chunksize=chunk_size,
                    low_memory=False, encoding="utf-8",
                    on_bad_lines="skip")
    ):
        bremen = chunk[
            chunk["TAL_LOCATION_NUTS"]
            .fillna("")
            .str.startswith(BREMEN_NUTS_PREFIX)
        ].copy()

        if bremen.empty:
            continue

        bremen["procedure_clean"] = (
            bremen["TOP_TYPE"].fillna("9").astype(str)
            .map(PROCEDURE_MAP).fillna("OTHER")
        )
        bremen["cpv_clean"] = (
            bremen["CPV"].fillna("").astype(str)
            .str.replace(".0", "", regex=False).str[:8].str.strip()
        )
        bremen["amount_clean"] = pd.to_numeric(
            bremen["VALUE_EURO"], errors="coerce"
        ).fillna(0.0)
        bremen["award_date_clean"] = pd.to_datetime(
            bremen["DT_AWARD"], format="%d/%m/%y", errors="coerce"
        ).dt.date
        bremen["vendor_clean"] = (
            bremen["WIN_NAME"].fillna("UNKNOWN").astype(str)
            .str.strip().str.upper()
        )
        bremen["buyer_clean"] = (
            bremen["CAE_NAME"].fillna("UNKNOWN").astype(str).str.strip()
        )

        inserted_this_chunk = 0
        for _, row in bremen.iterrows():
            try:
                con.execute("""
                    INSERT OR IGNORE INTO contracts (
                        contract_id, source, buyer_name, buyer_dept,
                        vendor_name, vendor_name_norm,
                        amount_eur, cpv_code, cpv_division,
                        cpv_label, award_date, procedure_type, nuts_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    str(row.get("ID_NOTICE_CAN", ""))
                        + "_" + str(row.get("ID_AWARD", "")),
                    "ted_csv",
                    row["buyer_clean"],
                    row["buyer_clean"],
                    row["WIN_NAME"] if pd.notna(row.get("WIN_NAME")) else "UNKNOWN",
                    row["vendor_clean"],
                    float(row["amount_clean"]),
                    row["cpv_clean"],
                    row["cpv_clean"][:2] if row["cpv_clean"] else "",
                    get_cpv_label(row["cpv_clean"]),
                    row["award_date_clean"],
                    row["procedure_clean"],
                    str(row.get("TAL_LOCATION_NUTS", "DE50")),
                ])
                inserted_this_chunk += 1
            except Exception as e:
                log.debug(f"Skipped row: {e}")
                continue

        total_inserted += inserted_this_chunk
        log.info(
            f"Chunk {chunk_num + 1}: {len(bremen)} Bremen rows found, "
            f"{inserted_this_chunk} inserted"
        )

    con.close()
    log.info(f"Finished loading {path.name}: {total_inserted} inserted")
    return total_inserted


if __name__ == "__main__":
    import glob
    csv_files = glob.glob(str(ROOT / "data" / "raw" / "ted_*.csv"))
    if not csv_files:
        print("No TED CSV files found in data/raw/")
        sys.exit(1)
    for f in sorted(csv_files):
        print(f"\nLoading: {f}")
        n = load_ted_csv(f)
        print(f"Inserted: {n} Bremen contracts")
    con = duckdb.connect(str(DB_PATH))
    total = con.execute(
        "SELECT COUNT(*) FROM contracts WHERE source='ted_csv'"
    ).fetchone()[0]
    print(f"\nTotal real Bremen contracts: {total}")
    con.close()