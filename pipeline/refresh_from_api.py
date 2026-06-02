"""
Live TED API refresh — pulls latest Bremen contract AWARD notices from the
TED v3 Search API and loads them into DuckDB. Run by GitHub Actions weekly.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests
from config.logging_setup import get_logger
from pipeline.schema import get_connection
from pipeline.extract.ted_csv import get_cpv_label

log = get_logger("pipeline.refresh")

TED_URL = "https://api.ted.europa.eu/v3/notices/search"

# can-standard = Contract Award Notice (has winner + value).
# We only want award notices since those are what the rules analyse.
QUERY = "place-of-performance IN (DE501 DE502) AND notice-type=can-standard"

FIELDS = [
    "publication-number", "buyer-name", "winner-name",
    "total-value", "classification-cpv", "dispatch-date",
    "notice-type", "place-of-performance",
]


def _text(value):
    """Unwrap the nested TED structure: {'deu': ['x']} -> 'x', ['x'] -> 'x'."""
    if value is None:
        return None
    if isinstance(value, dict):
        # language-keyed: prefer German, then any
        for lang in ("deu", "eng"):
            if lang in value:
                return _text(value[lang])
        return _text(next(iter(value.values()), None))
    if isinstance(value, list):
        return _text(value[0]) if value else None
    return value


def fetch(limit=200):
    body = {"query": QUERY, "fields": FIELDS,
            "limit": limit, "page": 1, "scope": "ALL"}
    try:
        r = requests.post(TED_URL, json=body, timeout=60)
        r.raise_for_status()
        notices = r.json().get("notices", [])
        log.info(f"TED API returned {len(notices)} Bremen award notices")
        return notices
    except requests.RequestException as e:
        log.error(f"TED API request failed: {e}")
        return []


def load(notices):
    con = get_connection()
    inserted = 0
    for n in notices:
        try:
            pub = _text(n.get("publication-number"))
            if not pub:
                continue
            buyer = _text(n.get("buyer-name")) or "UNKNOWN"
            winner = _text(n.get("winner-name")) or "UNKNOWN"
            cpv = str(_text(n.get("classification-cpv")) or "")[:8]
            date = (str(_text(n.get("dispatch-date")) or "")
                    .replace("Z", "") or None)
            nuts = str(_text(n.get("place-of-performance")) or "DE50")
            try:
                amount = float(_text(n.get("total-value")) or 0)
            except (ValueError, TypeError):
                amount = 0.0

            con.execute("""
                INSERT OR IGNORE INTO contracts (
                    contract_id, source, buyer_name, buyer_dept,
                    vendor_name, vendor_name_norm, amount_eur,
                    cpv_code, cpv_division, cpv_label,
                    award_date, procedure_type, nuts_code
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, [
                f"TED_{pub}", "ted_api", str(buyer), str(buyer),
                str(winner), str(winner).upper().strip(), amount,
                cpv, cpv[:2] if cpv else "", get_cpv_label(cpv),
                date, "OTHER", nuts,
            ])
            inserted += 1
        except Exception as e:
            log.debug(f"Skipped: {e}")
    con.close()
    log.info(f"Loaded {inserted} award notices")
    return inserted


def run_refresh():
    log.info("=== TED API refresh started ===")
    notices = fetch()
    if not notices:
        log.warning("No award notices returned. Data unchanged.")
        return 0
    n = load(notices)
    log.info(f"=== Refresh complete: {n} processed ===")
    return n


if __name__ == "__main__":
    run_refresh()