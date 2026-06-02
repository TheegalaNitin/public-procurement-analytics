import sys
sys.path.insert(0, '.')
from pipeline.schema import get_connection

con = get_connection()

print('=== SAMPLE CONTRACTS WITH CPV AND DATE ===')
rows = con.execute("""
    SELECT buyer_dept, vendor_name, cpv_label, 
           award_date, amount_eur, procedure_type
    FROM contracts
    WHERE amount_eur > 100000
    ORDER BY amount_eur DESC
    LIMIT 8
""").fetchall()

for r in rows:
    print(f'  Buyer:     {str(r[0])[:50]}')
    print(f'  Vendor:    {str(r[1])[:50]}')
    print(f'  CPV label: {r[2]}')
    print(f'  Date:      {r[3]}')
    print(f'  Amount:    EUR {r[4]:,.0f}')
    print(f'  Procedure: {r[5]}')
    print()

con.close()