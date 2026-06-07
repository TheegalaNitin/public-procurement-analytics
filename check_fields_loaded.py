import sys
sys.path.insert(0, '.')
from pipeline.schema import get_connection
con = get_connection()
rows = con.execute("""
    SELECT vendor_name, ROUND(amount_eur), procedure_type, 
           num_bidders, is_framework, is_gpa
    FROM contracts WHERE amount_eur > 1000000 LIMIT 8
""").fetchall()
print(f"{'Vendor':<25} {'Amount':>11} {'Procedure':<12} {'Bid':>4} {'Frame':>6} {'GPA':>5}")
print("-" * 70)
for r in rows:
    print(f"{str(r[0])[:24]:<25} {r[1]:>11,.0f} {str(r[2]):<12} {str(r[3]):>4} {str(r[4]):>6} {str(r[5]):>5}")
con.close()