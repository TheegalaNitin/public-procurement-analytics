import sys
sys.path.insert(0, '.')
from pipeline.schema import get_connection
con = get_connection()

print("=== DATA BY SOURCE AND YEAR ===")
rows = con.execute("""
    SELECT source, 
           EXTRACT(year FROM award_date) AS yr,
           COUNT(*) 
    FROM contracts
    GROUP BY source, yr
    ORDER BY source, yr
""").fetchall()
for r in rows:
    print(f"  {r[0]:<12} {str(r[1]):<6} {r[2]} contracts")

print("\n=== NEWEST CONTRACTS ===")
rows = con.execute("""
    SELECT award_date, source, vendor_name, ROUND(amount_eur)
    FROM contracts
    WHERE award_date IS NOT NULL
    ORDER BY award_date DESC LIMIT 5
""").fetchall()
for r in rows:
    print(f"  {r[0]} [{r[1]}] {str(r[2])[:30]} EUR {r[3]:,.0f}")
con.close()