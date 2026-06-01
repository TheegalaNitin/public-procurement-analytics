"""
TED CSV loader — imports real Bremen procurement data from the
TED CSV annual export files into the DuckDB warehouse.

Column mapping is specific to the TED CSV v2 format (2017-2023).
Filter: TAL_LOCATION_NUTS starting with DE50 = Bremen + Bremerhaven.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import duckdb
from config.settings import DB_PATH
from config.logging_setup import get_logger

log = get_logger("extract.ted_csv")

# NUTS codes for Bremen state
# DE501 = Bremen city, DE502 = Bremerhaven
BREMEN_NUTS_PREFIX = "DE50"

# Map TED procedure codes to readable labels
PROCEDURE_MAP = {
    "1": "OPEN",
    "2": "RESTRICTED",
    "3": "NEGOTIATED",
    "4": "DIRECT",
    "6": "NEGOTIATED",
    "9": "OTHER",
}


def load_ted_csv(csv_path: str) -> int:
    """
    Load one TED CSV file, filter to Bremen, insert into contracts table.
    Returns number of rows inserted.
    """
    path = Path(csv_path)
    if not path.exists():
        log.error(f"File not found: {csv_path}")
        return 0

    log.info(f"Reading {path.name} ...")

    # Read in chunks to handle large files without running out of memory
    chunk_size = 50_000
    total_inserted = 0
    con = duckdb.connect(str(DB_PATH))

# Check columns before processing
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
        # ── Filter to Bremen ──────────────────────────────────────────
        bremen = chunk[
            chunk["TAL_LOCATION_NUTS"]
            .fillna("")
            .str.startswith(BREMEN_NUTS_PREFIX)
        ].copy()

        if bremen.empty:
            continue

        # ── Clean and map columns ─────────────────────────────────────
        bremen["procedure_clean"] = (
            bremen["TOP_TYPE"]
            .fillna("9")
            .astype(str)
            .map(PROCEDURE_MAP)
            .fillna("OTHER")
        )

        bremen["cpv_clean"] = (
            bremen["CPV"]
            .fillna("")
            .astype(str)
            .str[:8]           # keep first 8 digits only
            .str.strip()
        )

        bremen["amount_clean"] = pd.to_numeric(
            bremen["VALUE_EURO"], errors="coerce"
        ).fillna(0.0)

        bremen["award_date_clean"] = pd.to_datetime(
            bremen["DT_AWARD"], format="%Y%m%d", errors="coerce"
        ).dt.date

        bremen["vendor_clean"] = (
            bremen["WIN_NAME"]
            .fillna("UNKNOWN")
            .astype(str)
            .str.strip()
            .str.upper()       # normalise for deduplication
        )

        bremen["buyer_clean"] = (
            bremen["CAE_NAME"]
            .fillna("UNKNOWN")
            .astype(str)
            .str.strip()
        )

        # ── Insert into DuckDB ────────────────────────────────────────
        inserted_this_chunk = 0
        for _, row in bremen.iterrows():
            try:
                con.execute("""
                    INSERT OR REPLACE INTO contracts (
                        contract_id, source, buyer_name, buyer_dept,
                        vendor_name, vendor_name_norm,
                        amount_eur, cpv_code, cpv_division,
                        cpv_label, award_date, procedure_type,
                        nuts_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    str(row.get("ID_NOTICE_CAN", ""))
                        + "_" + str(row.get("ID_AWARD", "")),
                    "ted_csv",
                    row["buyer_clean"],
                    row["buyer_clean"],          # use buyer name as dept
                    row["WIN_NAME"] if pd.notna(row.get("WIN_NAME")) else "UNKNOWN",
                    row["vendor_clean"],
                    float(row["amount_clean"]),
                    row["cpv_clean"],
                    row["cpv_clean"][:2] if row["cpv_clean"] else "",
                    "",                          # CPV label added next step
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
            f"Chunk {chunk_num + 1}: "
            f"{len(bremen)} Bremen rows found, "
            f"{inserted_this_chunk} inserted"
        )

    con.close()
    log.info(
        f"Finished loading {path.name}: "
        f"{total_inserted} Bremen contracts inserted"
    )
    return total_inserted


if __name__ == "__main__":
    import glob, os

    # Find all TED CSV files in data/raw/
    csv_files = glob.glob(str(ROOT / "data" / "raw" / "ted_*.csv"))

    if not csv_files:
        print("No TED CSV files found in data/raw/")
        print("Expected files like: ted_awards_2023.csv")
        sys.exit(1)

    for f in sorted(csv_files):
        print(f"\nLoading: {f}")
        n = load_ted_csv(f)
        print(f"Inserted: {n} Bremen contracts")

    # Show what we have
    con = duckdb.connect(str(DB_PATH))
    total = con.execute(
        "SELECT COUNT(*) FROM contracts WHERE source='ted_csv'"
    ).fetchone()[0]
    print(f"\nTotal real Bremen contracts in database: {total}")

    print("\nSample — top 5 buyers by contract count:")
    rows = con.execute("""
        SELECT buyer_dept, COUNT(*) as n, ROUND(SUM(amount_eur)) as total_eur
        FROM contracts
        WHERE source = 'ted_csv'
        GROUP BY buyer_dept
        ORDER BY n DESC
        LIMIT 5
    """).fetchall()
    for r in rows:
        print(f"  {r[0][:50]:50s}  {r[1]:4d} contracts  €{r[2]:>12,.0f}")

    con.close()