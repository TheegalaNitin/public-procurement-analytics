"""
Licence generator — the KILL SWITCH control panel.

YOU run this script to mint a licence token after a customer pays.
You NEVER ship this file to the customer. The HMAC secret it uses lives
only on your machine (and in Streamlit Cloud secrets for the hosted app).

How the kill switch works:
  1. You generate a token with an expiry date and email it / paste it
     into the hosted app's secrets.
  2. The app verifies the token's signature on every startup and every
     pipeline run (see licence/verify.py).
  3. If the customer stops paying, you simply do not issue a new token.
     When the current one expires, the app locks itself.
  4. The customer cannot forge or extend a token because they do not
     have your secret key. Editing the expiry date breaks the signature.

Usage:
    python -m licence.generate "Rechnungshof Bremen" 2026-12-31 annual
"""
import sys
import hmac
import json
import base64
import hashlib
from datetime import date

# Import the secret from settings so dev/prod share one source of truth.
from config.settings import LICENCE_SECRET


def generate_licence(customer: str, expires: str, tier: str) -> str:
    """
    Create a signed licence token.

    customer : human-readable customer name (stored in token)
    expires  : ISO date string 'YYYY-MM-DD' — the kill date
    tier     : 'pilot' | 'annual' | 'perpetual'
    """
    # Validate the expiry is a real date before signing.
    date.fromisoformat(expires)

    payload = json.dumps(
        {
            "customer": customer,
            "expires": expires,
            "tier": tier,
            "issued": date.today().isoformat(),
        },
        sort_keys=True,  # deterministic — same input, same signature
    )

    signature = hmac.new(
        LICENCE_SECRET.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    token = base64.b64encode(f"{payload}|||{signature}".encode()).decode()
    return token


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        print("\nError: need exactly 3 arguments.")
        print('Example: python -m licence.generate "Rechnungshof Bremen" '
              '2026-12-31 annual')
        sys.exit(1)

    if LICENCE_SECRET.startswith("DEV_ONLY"):
        print("WARNING: you are using the DEV placeholder secret.")
        print("Set a real LICENCE_SECRET environment variable before "
              "generating production tokens.\n")

    customer, expires, tier = sys.argv[1], sys.argv[2], sys.argv[3]
    token = generate_licence(customer, expires, tier)

    print("=" * 64)
    print("LICENCE TOKEN GENERATED")
    print("=" * 64)
    print(f"Customer : {customer}")
    print(f"Expires  : {expires}  (kill date)")
    print(f"Tier     : {tier}")
    print("-" * 64)
    print("Token (paste into licence.key or Streamlit secrets):")
    print(token)
    print("=" * 64)
