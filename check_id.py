import sys
sys.path.insert(0, '.')
from pipeline.schema import get_connection
con = get_connection()
rows = con.execute("""
    SELECT contract_id, vendor_name, ROUND(amount_eur)
    FROM contracts WHERE amount_eur > 1000000 LIMIT 5
""").fetchall()
for r in rows:
    print(f"ID: {r[0]}  |  {r[1][:30]}  |  EUR {r[2]:,.0f}")
    print(f"   Link: https://ted.europa.eu/en/notice/-/detail/{r[0]}")
con.close()