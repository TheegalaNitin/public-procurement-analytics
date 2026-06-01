import sys
sys.path.insert(0, '.')
from pipeline.schema import get_connection

con = get_connection()

print('=== R-01 CONTRACT SPLITTING ===')
rows = con.execute("""
    SELECT a.description, c.buyer_dept, c.vendor_name, ROUND(a.risk_eur)
    FROM anomalies a JOIN contracts c ON c.contract_id = a.contract_id
    WHERE a.rule_id = 'R-01'
""").fetchall()
for r in rows:
    print('  Buyer: ', r[1])
    print('  Vendor:', r[2])
    print('  Risk:  ', r[3])
    print('  Detail:', r[0])
    print()

print('=== R-02 PRICE OUTLIERS (top 5) ===')
rows = con.execute("""
    SELECT a.description, c.buyer_dept, c.vendor_name,
           ROUND(c.amount_eur), ROUND(a.risk_eur)
    FROM anomalies a JOIN contracts c ON c.contract_id = a.contract_id
    WHERE a.rule_id = 'R-02'
    ORDER BY a.risk_eur DESC LIMIT 5
""").fetchall()
for r in rows:
    print('  Buyer: ', r[1])
    print('  Vendor:', r[2])
    print('  Amount: EUR', r[3])
    print('  Risk:   EUR', r[4])
    print('  Detail:', r[0])
    print()

print('=== R-03 SOLE SOURCE ===')
rows = con.execute("""
    SELECT a.description, c.buyer_dept, c.vendor_name, ROUND(a.risk_eur)
    FROM anomalies a JOIN contracts c ON c.contract_id = a.contract_id
    WHERE a.rule_id = 'R-03'
""").fetchall()
for r in rows:
    print('  Buyer: ', r[1])
    print('  Vendor:', r[2])
    print('  Risk:  ', r[3])
    print('  Detail:', r[0])
    print()

print('=== R-04 REPEAT DIRECT AWARDS ===')
rows = con.execute("""
    SELECT a.description, c.buyer_dept, c.vendor_name, ROUND(a.risk_eur)
    FROM anomalies a JOIN contracts c ON c.contract_id = a.contract_id
    WHERE a.rule_id = 'R-04'
""").fetchall()
for r in rows:
    print('  Buyer: ', r[1])
    print('  Vendor:', r[2])
    print('  Risk:  ', r[3])
    print('  Detail:', r[0])
    print()

con.close()