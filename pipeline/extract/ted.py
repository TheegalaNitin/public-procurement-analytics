"""
TED extractor — pulls Bremen procurement notices from the TED Search API.

The TED Search API is openly accessible (no authentication) and is the
official channel for data reusers. We query it with an expert query
filtering to Bremen's NUTS region, then cache each page to data/raw/ as
an immutable timestamped file (raw zone is sacred — we never overwrite).

If the API is unreachable (offline dev, rate limit), the loader falls back
to any cached files already on disk, so you can develop without a live
connection once you have pulled data once.
"""
import json
import time
from datetime import date
from pathlib import Path

import requests

from config.settings import (
    TED_SEARCH_API, BREMEN_NUTS_PREFIX, TED_PAGE_SIZE, DATA_RAW
)
from config.logging_setup import get_logger

log = get_logger("extract.ted")

RAW_TED = DATA_RAW / "ted"
RAW_TED.mkdir(parents=True, exist_ok=True)


def _expert_query() -> str:
    """
    TED expert query string. Filters to award notices in Bremen.
    'place-of-performance' uses the NUTS code; we match the DE50 prefix.
    """
    # TED expert query syntax: field=value with wildcards
    return f"(place-of-performance IN ({BREMEN_NUTS_PREFIX}*))"


def fetch_ted_notices(max_pages: int = 5) -> list[dict]:
    """
    Fetch Bremen notices from TED, caching each page to disk.
    Returns the combined list of notice dicts.
    """
    today = date.today().isoformat()
    all_notices: list[dict] = []

    for page in range(1, max_pages + 1):
        cache_file = RAW_TED / f"{today}_page_{page}.json"

        # Cache hit — load from disk, skip the API entirely (idempotent)
        if cache_file.exists():
            log.info(f"Cache hit: {cache_file.name}")
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            all_notices.extend(data.get("notices", []))
            continue

        body = {
            "query": _expert_query(),
            "fields": [
                "publication-number", "buyer-name", "contract-value",
                "classification-cpv", "winner-name", "notice-type",
                "publication-date", "procedure-type",
                "place-of-performance",
            ],
            "page": page,
            "limit": TED_PAGE_SIZE,
            "scope": "ALL",
        }

        try:
            resp = requests.post(TED_SEARCH_API, json=body, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            log.warning(f"TED API request failed on page {page}: {e}")
            log.warning("Falling back to any cached data on disk.")
            break

        notices = data.get("notices", [])
        if not notices:
            log.info(f"No more notices at page {page}; stopping.")
            break

        # Write raw to disk — immutable cache
        cache_file.write_text(json.dumps(data, ensure_ascii=False),
                              encoding="utf-8")
        all_notices.extend(notices)
        log.info(f"Fetched TED page {page}: {len(notices)} notices")
        time.sleep(0.5)  # be polite to the API

    log.info(f"TED extract complete: {len(all_notices)} notices total")
    return all_notices


def load_cached_ted() -> list[dict]:
    """Load all cached TED notices from disk (offline mode)."""
    notices = []
    for f in sorted(RAW_TED.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        notices.extend(data.get("notices", []))
    log.info(f"Loaded {len(notices)} cached TED notices from disk")
    return notices
