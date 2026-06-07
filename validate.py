import sys
sys.path.insert(0, '.')
from pipeline.schema import get_connection
con = get_connection()

print("=== TOP FINDINGS TO VALIDATE ===\n")
rows = con.execute("""
    SELECT a.rule_id, c.buyer_dept, c.vendor_name, 
           ROUND(c.amount_eur) as amount, c.cpv_label,
           c.contract_id, a.description
    FROM anomalies a
    JOIN contracts c ON c.contract_id = a.contract_id
    WHERE a.rule_id = 'R-02'
    ORDER BY a.risk_eur DESC
    LIMIT 5
""").fetchall()

for r in rows:
    print(f"Vendor:  {r[2]}")
    print(f"Buyer:   {r[1]}")
    print(f"Amount:  EUR {r[3]:,.0f}")
    print(f"Type:    {r[4]}")
    print(f"ID:      {r[5]}")
    notice_id = r[5].replace("TED_", "").split("_")[0]
    if "-" in notice_id:
        print(f"CHECK:   https://ted.europa.eu/en/notice/{notice_id}/pdf")
    print()

con.close()