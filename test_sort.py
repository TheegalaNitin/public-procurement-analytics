import requests

url = "https://api.ted.europa.eu/v3/notices/search"

# TED expert query with SORT BY inside the query string itself
queries = [
    "place-of-performance IN (DE501 DE502) AND notice-type=can-standard SORT BY publication-number DESC",
    "place-of-performance IN (DE501 DE502) AND notice-type=can-standard SORT BY dispatch-date DESC",
]

for q in queries:
    print("=" * 50)
    print("Query:", q[-40:])
    body = {
        "query": q,
        "fields": ["publication-number", "dispatch-date"],
        "limit": 5, "page": 1, "scope": "ALL",
    }
    r = requests.post(url, json=body, timeout=60)
    print("Status:", r.status_code)
    if r.status_code == 200:
        for n in r.json().get("notices", []):
            print("  ", n.get("dispatch-date"), "-", n.get("publication-number"))
    else:
        print("  ", r.text[:200])