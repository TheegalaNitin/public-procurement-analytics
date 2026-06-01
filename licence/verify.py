"""
Licence verifier — the enforcement half of the KILL SWITCH.

Imported by BOTH the pipeline and the dashboard. Every entry point calls
verify_licence() before doing any real work. If the licence is missing,
tampered with, or expired beyond the grace period, the app refuses to run.

Three possible outcomes:
  - VALID    : full access, everything runs
  - GRACE    : expired but within grace window — dashboard is read-only,
               pipeline will NOT refresh data (no new value delivered)
  - LOCKED   : expired beyond grace, or tampered, or missing — hard stop

This design means non-payment degrades gracefully: the customer keeps
read access to what they already have for 30 days (goodwill), but gets
no new data, then loses access entirely.
"""
import hmac
import json
import base64
import hashlib
from enum import Enum
from datetime import date, timedelta
from dataclasses import dataclass

from config.settings import LICENCE_SECRET, LICENCE_PATH, LICENCE_GRACE_DAYS
from config.logging_setup import get_logger

log = get_logger("licence.verify")


class LicenceStatus(Enum):
    VALID = "valid"
    GRACE = "grace"
    LOCKED = "locked"


@dataclass
class LicenceResult:
    status: LicenceStatus
    customer: str | None = None
    expires: str | None = None
    tier: str | None = None
    message: str = ""

    @property
    def can_run_pipeline(self) -> bool:
        # Only a fully valid licence may refresh data.
        return self.status == LicenceStatus.VALID

    @property
    def can_read_dashboard(self) -> bool:
        # Valid and grace can both read; locked cannot.
        return self.status in (LicenceStatus.VALID, LicenceStatus.GRACE)


def _read_token(token_str: str | None) -> str:
    if token_str is not None:
        return token_str.strip()
    if not LICENCE_PATH.exists():
        raise FileNotFoundError("No licence.key file found.")
    return LICENCE_PATH.read_text(encoding="utf-8").strip()


def verify_licence(token_str: str | None = None) -> LicenceResult:
    """
    Verify a licence token. Pass the token string directly (e.g. from
    Streamlit secrets) or leave None to read from the licence.key file.
    """
    # 1. Load the token
    try:
        raw_token = _read_token(token_str)
    except FileNotFoundError:
        log.error("Licence check failed: no token provided and no licence.key")
        return LicenceResult(
            LicenceStatus.LOCKED,
            message="Keine Lizenz gefunden. Bitte kontaktieren Sie den Anbieter.",
        )

    # 2. Decode and split payload from signature
    try:
        decoded = base64.b64decode(raw_token).decode()
        payload_str, signature = decoded.rsplit("|||", 1)
    except Exception:
        log.error("Licence check failed: token malformed")
        return LicenceResult(
            LicenceStatus.LOCKED,
            message="Lizenzdatei beschädigt oder ungültig.",
        )

    # 3. Verify the HMAC signature — this is what makes it tamper-proof.
    #    If the customer edits the expiry date, this check fails.
    expected = hmac.new(
        LICENCE_SECRET.encode(),
        payload_str.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        log.error("Licence check failed: signature mismatch (tampering?)")
        return LicenceResult(
            LicenceStatus.LOCKED,
            message="Lizenz ungültig — Signatur stimmt nicht. "
                    "Die Datei wurde möglicherweise verändert.",
        )

    # 4. Parse the verified payload
    payload = json.loads(payload_str)
    customer = payload.get("customer")
    expires = payload.get("expires")
    tier = payload.get("tier")

    # 5. Evaluate expiry against today, with grace window
    today = date.today()
    expiry_date = date.fromisoformat(expires)
    grace_end = expiry_date + timedelta(days=LICENCE_GRACE_DAYS)

    if today <= expiry_date:
        log.info(f"Licence VALID for {customer} until {expires}")
        return LicenceResult(
            LicenceStatus.VALID, customer, expires, tier,
            message=f"Lizenz gültig bis {expires}.",
        )

    if today <= grace_end:
        days_left = (grace_end - today).days
        log.warning(
            f"Licence in GRACE for {customer} — expired {expires}, "
            f"{days_left} grace days left"
        )
        return LicenceResult(
            LicenceStatus.GRACE, customer, expires, tier,
            message=f"Lizenz abgelaufen am {expires}. Nur-Lese-Zugriff "
                    f"noch {days_left} Tage. Bitte erneuern.",
        )

    log.error(f"Licence LOCKED for {customer} — expired {expires}, grace over")
    return LicenceResult(
        LicenceStatus.LOCKED, customer, expires, tier,
        message=f"Lizenz abgelaufen am {expires}. Zugriff gesperrt. "
                f"Bitte kontaktieren Sie den Anbieter zur Verlängerung.",
    )


def enforce_or_exit(require_pipeline: bool = False) -> LicenceResult:
    """
    Convenience guard for the pipeline. Raises SystemExit on lock.
    Call at the very top of any pipeline entry point.
    """
    result = verify_licence()
    if result.status == LicenceStatus.LOCKED:
        raise SystemExit(f"ACCESS DENIED: {result.message}")
    if require_pipeline and not result.can_run_pipeline:
        raise SystemExit(
            f"PIPELINE BLOCKED: {result.message} "
            f"(data refresh requires an active licence)"
        )
    return result
