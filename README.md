# Bremen Procurement Anomaly Detector

A data engineering tool that ingests public procurement data, detects
anomalies (contract splitting, price outliers, sole-source concentration,
repeat direct awards), and presents prioritised findings to auditors.

Built to be sold to the Rechnungshof Bremen and similar audit bodies.

## What's in this scaffold (Phase 1–3 complete)

```
config/          central settings, logging
licence/         the kill switch — generate.py (you) + verify.py (enforced)
pipeline/
  extract/ted.py TED Search API extractor (no auth needed)
  schema.py      DuckDB warehouse schema
  synthetic.py   demo data with planted anomalies
  detect.py      THE FOUR DETECTION RULES — core product IP
dashboard/       Streamlit app (Phase 4 — next)
tests/           unit tests (Phase 4 — next)
```

## Quick start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Set your kill-switch secret (keep this private!)
export LICENCE_SECRET="your-long-random-secret-here"

# 3. Generate a licence for yourself to develop with
python -m licence.generate "Dev Test" 2026-12-31 annual
# copy the token into a file named licence.key

# 4. Generate demo data and run detection
python -m pipeline.synthetic
python -c "from pipeline.schema import get_connection; \
           from pipeline.detect import run_all_rules; \
           run_all_rules(get_connection())"

# 5. (Phase 4) Run the dashboard
streamlit run dashboard/app.py
```

## The kill switch — how it protects your revenue

The licence system uses HMAC-SHA256 signing. You hold the secret key;
the customer never does.

- `licence/generate.py` — YOU run this to mint a token after payment.
  Never ship this file or the secret to the customer.
- `licence/verify.py` — imported by the pipeline and dashboard. Checks
  the token on every run.

Three states:
- VALID  — full access
- GRACE  — expired but within 30 days: dashboard read-only, no data
  refresh (configurable via LICENCE_GRACE_DAYS)
- LOCKED — expired beyond grace, tampered, or missing: hard stop

Because you host on Streamlit Cloud, the customer never holds the code,
so the lock is effectively absolute. To stop service for non-payment,
you simply stop issuing new tokens — the app locks itself on expiry.

## Detection rules (config/settings.py to tune thresholds)

| Rule | What it catches | Default threshold |
|------|-----------------|-------------------|
| R-01 | Contract splitting | 2+ direct awards, same vendor/dept/CPV, 30 days, sum > €25k |
| R-02 | Price outlier | amount > 3x CPV median, floor €10k |
| R-03 | Sole-source concentration | one vendor > 40% of dept non-open spend, > €50k |
| R-04 | Repeat direct awards | > 3 direct awards, same vendor/dept/year |

## Data sources

- TED Search API — above-threshold EU contracts, no auth. Filtered to
  Bremen via NUTS DE50 prefix.
- vergabe.bremen.de — below-threshold contracts (Phase 4 scraper).
- CPV reference — EU procurement category codes (loaded from synthetic
  catalog for now; swap for full CSV in production).

## Deployment (Phase 5)

Host on Streamlit Community Cloud (free). Put LICENCE_SECRET and the
customer's token in Streamlit secrets. Schedule the pipeline with GitHub
Actions (weekly cron). The customer gets a private URL with password auth.

## Next phases

- Phase 4: Streamlit dashboard + vergabe.bremen.de scraper + unit tests
- Phase 5: GitHub Actions scheduling + deploy + pitch
