import sys
sys.path.insert(0, '.')
from pipeline.schema import get_connection
con = get_connection()
rows = con.execute("""
    SELECT nuts_code, COUNT(*) 
    FROM contracts 
    GROUP BY nuts_code 
    ORDER BY COUNT(*) DESC
""").fetchall()
print("Contracts by NUTS region:")
for r in rows:
    print(f"  {r[0]}: {r[1]}")
con.close()