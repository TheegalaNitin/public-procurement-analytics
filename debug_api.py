import sys
sys.path.insert(0, '.')
import requests
from pipeline.schema import get_connection
from pipeline.refresh_from_api import fetch, _text
from pipeline.extract.ted_csv import get_cpv_label

notices = fetch()
print(f"Fetched {len(notices)} notices")

con = get_connection()
n = notices[0]
print("\nFirst notice fields:", list(n.keys()))

# Try one insert and show the real error
try:
    pub = _text(n.get("publication-number"))
    buyer = _text(n.get("buyer-name")) or "UNKNOWN"
    winner = _text(n.get("winner-name")) or "UNKNOWN"
    cpv = str(_text(n.get("classification-cpv")) or "")[:8]
    date = (str(_text(n.get("dispatch-date")) or "").replace("Z","") or None)
    nuts = str(_text(n.get("place-of-performance")) or "DE50")
    con.execute("""
        INSERT OR IGNORE INTO contracts (
            contract_id, source, buyer_name, buyer_dept,
            vendor_name, vendor_name_norm, amount_eur,
            cpv_code, cpv_division, cpv_label,
            award_date, procedure_type, nuts_code, is_framework
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, [f"TED_{pub}", "ted_api", str(buyer), str(buyer),
          str(winner), str(winner).upper(), 0.0,
          cpv, cpv[:2] if cpv else "", get_cpv_label(cpv),
          date, "OTHER", nuts, False])
    print("\nINSERT worked")
except Exception as e:
    print(f"\nREAL ERROR: {e}")
con.close()