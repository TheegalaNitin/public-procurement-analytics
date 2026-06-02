import requests, json

url = "https://api.ted.europa.eu/v3/notices/search"

# Try the field names that the current TED eForms API uses
body = {
    "query": "place-of-performance=DE501",
    "fields": [
        "publication-number",
        "buyer-name",
        "contract-value-lot",
        "winner-name",
        "classification-cpv",
        "notice-type",
        "publication-date",
        "title-proc",
        "total-value",
    ],
    "limit": 3,
    "page": 1,
    "scope": "ALL"
}

r = requests.post(url, json=body, timeout=60)
print("Status:", r.status_code)
if r.status_code == 200:
    data = r.json()
    notices = data.get("notices", [])
    if notices:
        print("Fields actually returned in first notice:")
        print(json.dumps(notices[0], indent=2, ensure_ascii=False)[:2000])
else:
    print("Error:", r.text[:500])