"""
Central configuration for the Bremen Procurement Anomaly Detector.

Every tunable value lives here — no magic numbers scattered through the code.
This is a data engineering principle: configuration is explicit, versioned,
and lives in one place.
"""
import os
from pathlib import Path

# ── Project paths ─────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_STAGING = ROOT / "data" / "staging"
DB_PATH = ROOT / "procurement.db"
LOG_PATH = ROOT / "pipeline.log"

# Ensure data directories exist (idempotent)
DATA_RAW.mkdir(parents=True, exist_ok=True)
DATA_STAGING.mkdir(parents=True, exist_ok=True)

# ── TED (Tenders Electronic Daily) ────────────────────────────────────
# The Search API requires NO authentication — it is built for data reusers.
TED_SEARCH_API = "https://api.ted.europa.eu/v3/notices/search"

# NUTS region code for Bremen. DE501 = Bremen, Kreisfreie Stadt.
# DE502 = Bremerhaven. We capture both with the DE50 prefix.
BREMEN_NUTS_PREFIX = "DE50"

# How many notices to request per API page (max 250 for TED).
TED_PAGE_SIZE = 100

# ── vergabe.bremen.de (below-threshold contracts) ─────────────────────
# Bremen's regional procurement portal. No bulk export — we scrape.
VERGABE_BREMEN_BASE = "https://vergabe.bremen.de"

# ── Detection rule thresholds ─────────────────────────────────────────
# These are the tunable knobs of the detection engine. Keeping them here
# means you can adjust sensitivity per customer without touching SQL.

# R-01 Contract splitting: N+ awards to same vendor/buyer/CPV-division
#      within this many days, summing above the direct-award threshold.
SPLITTING_WINDOW_DAYS = 30
SPLITTING_MIN_CONTRACTS = 2
DIRECT_AWARD_THRESHOLD_EUR = 25_000  # Bremen direct-award limit (approx)

# R-02 Price outlier: contract amount more than N× the median for its
#      CPV code. Only consider contracts above a floor to avoid noise.
PRICE_OUTLIER_MULTIPLE = 3.0
PRICE_OUTLIER_FLOOR_EUR = 10_000

# R-03 Sole-source concentration: a single vendor receiving more than
#      this fraction of a department's spend via non-open procedures.
SOLE_SOURCE_SHARE = 0.40
SOLE_SOURCE_MIN_EUR = 50_000

# R-04 Repeat direct awards: same vendor + department + year, more than
#      this many direct awards.
REPEAT_DIRECT_MAX = 3

# ── Licence / kill switch ─────────────────────────────────────────────
# The HMAC secret signs licence tokens. NEVER commit the real value.
# In production it is read from an environment variable (Streamlit Cloud
# secrets). The default here is only a placeholder for local dev.
LICENCE_SECRET = os.environ.get(
    "LICENCE_SECRET",
    "DEV_ONLY_PLACEHOLDER_replace_in_production"
)
LICENCE_PATH = ROOT / "licence.key"

# Grace period: after expiry, historical data stays readable this many
# days before the hard lock. Set to 0 for immediate lock.
LICENCE_GRACE_DAYS = 30

# ── Logging ───────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
