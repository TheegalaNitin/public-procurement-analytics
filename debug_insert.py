import sys
sys.path.insert(0, '.')
import pandas as pd
from pipeline.schema import get_connection

con = get_connection()

# Check the actual schema columns
cols = con.execute("PRAGMA table_info(contracts)").fetchall()
print("=== CONTRACTS TABLE COLUMNS ===")
for c in cols:
    print(f"  {c[1]} ({c[2]})")

print("\n=== TRYING ONE INSERT TO SEE THE REAL ERROR ===")
df = pd.read_csv('data/raw/ted_awards_2023.csv', low_memory=False, nrows=200)
bremen = df[df["TAL_LOCATION_NUTS"].fillna("").str.startswith("DE50")]
print(f"Bremen rows in first 200: {len(bremen)}")

if len(bremen) > 0:
    row = bremen.iloc[0]
    try:
        con.execute("""
            INSERT OR IGNORE INTO contracts (
                contract_id, source, buyer_name, buyer_dept,
                vendor_name, vendor_name_norm, amount_eur,
                cpv_code, cpv_division, cpv_label, award_date,
                procedure_type, nuts_code, is_framework,
                num_bidders, is_gpa
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, ["TEST-1", "test", "buyer", "buyer", "vendor", "VENDOR",
              1000.0, "45000000", "45", "Bauarbeiten", None,
              "OPEN", "DE501", False, 3, True])
        print("INSERT SUCCESS - schema is fine")
    except Exception as e:
        print(f"INSERT FAILED with error:\n  {e}")

con.close()