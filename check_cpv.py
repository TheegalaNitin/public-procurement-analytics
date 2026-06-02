import sys
sys.path.insert(0, '.')
from pipeline.schema import get_connection

con = get_connection()
rows = con.execute("""
    SELECT DISTINCT cpv_code, cpv_division, cpv_label
    FROM contracts
    WHERE amount_eur > 100000
    LIMIT 15
""").fetchall()

for r in rows:
    print(f'  code="{r[0]}"  division="{r[1]}"  label="{r[2]}"')

con.close()