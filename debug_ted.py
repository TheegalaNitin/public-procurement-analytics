import requests, json

url = "https://api.ted.europa.eu/v3/notices/search"

# Try several query formats to find what the API accepts
tests = [
    {
        "name": "Test 1 - simple buyer-country",
        "body": {
            "query": "buyer-country=DEU",
            "fields": ["publication-number"],
            "limit": 3, "page": 1, "scope": "ALL"
        }
    },
    {
        "name": "Test 2 - place-of-performance simple",
        "body": {
            "query": "place-of-performance=DE501",
            "fields": ["publication-number"],
            "limit": 3, "page": 1, "scope": "ALL"
        }
    },
    {
        "name": "Test 3 - no SORT, IN syntax",
        "body": {
            "query": "place-of-performance IN (DE501 DE502)",
            "fields": ["publication-number"],
            "limit": 3, "page": 1, "scope": "ALL"
        }
    },
    {
        "name": "Test 4 - minimal",
        "body": {
            "query": "buyer-country=DEU",
            "fields": ["publication-number"],
            "limit": 3
        }
    },
]

for t in tests:
    print("=" * 60)
    print(t["name"])
    print("Query:", t["body"]["query"])
    try:
        r = requests.post(url, json=t["body"], timeout=60)
        print("Status:", r.status_code)
        if r.status_code == 200:
            data = r.json()
            print("SUCCESS — keys:", list(data.keys()))
            notices = data.get("notices", data.get("results", []))
            print("Notices returned:", len(notices))
            if notices:
                print("First notice keys:", list(notices[0].keys()))
        else:
            print("Error body:", r.text[:400])
    except Exception as e:
        print("Exception:", e)
    print()