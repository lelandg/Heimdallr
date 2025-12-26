"""API authentication for Heimdallr endpoints.

Provides HMAC-SHA256 signature verification for secure API access.
Uses the same signing scheme as ChatMaster for interoperability.
"""
from __future__ import annotations

import hmac
import hashlib
import logging
import time
from typing import Optional

from fastapi import HTTPException, Request

log = logging.getLogger("heimdallr.api_auth")

# Maximum age for timestamps (5 minutes) to prevent replay attacks
MAX_TIMESTAMP_AGE_S = 300


def verify_signature(
    api_secret: str,
    body: str,
    timestamp: str,
    signature: str,
) -> bool:
    """Verify HMAC-SHA256 signature.

    The signature is computed as: HMAC-SHA256(secret, f"{timestamp}.{body}")
    This matches the signing scheme used by ChatMaster.

    Args:
        api_secret: The shared secret key
        body: The raw request body (JSON string)
        timestamp: Unix timestamp string from X-Timestamp header
        signature: Hex-encoded signature from X-Signature header

    Returns:
        True if signature is valid
    """
    message = f"{timestamp}.{body}"
    expected = hmac.new(
        api_secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


def validate_timestamp(timestamp: str) -> bool:
    """Validate timestamp is recent enough to prevent replay attacks.

    Args:
        timestamp: Unix timestamp string

    Returns:
        True if timestamp is within acceptable range
    """
    try:
        ts = int(timestamp)
        now = int(time.time())
        age = abs(now - ts)
        return age <= MAX_TIMESTAMP_AGE_S
    except (ValueError, TypeError):
        return False


class APIAuthenticator:
    """FastAPI dependency for API authentication.

    Usage:
        auth = APIAuthenticator(api_key="...", api_secret="...")

        @app.post("/api/v1/alert/send")
        async def send_alert(request: Request, _=Depends(auth)):
            ...
    """

    def __init__(self, api_key: str, api_secret: str):
        """Initialize authenticator with credentials.

        Args:
            api_key: Expected API key
            api_secret: Secret for HMAC verification
        """
        self.api_key = api_key
        self.api_secret = api_secret

    @property
    def is_configured(self) -> bool:
        """Check if authentication is properly configured."""
        return bool(self.api_key and self.api_secret)

    async def __call__(self, request: Request) -> bool:
        """Verify request authentication.

        Args:
            request: FastAPI request object

        Returns:
            True if authenticated

        Raises:
            HTTPException: If authentication fails
        """
        # Check if auth is configured
        if not self.is_configured:
            log.warning("API authentication not configured - rejecting request")
            raise HTTPException(
                status_code=503,
                detail="API authentication not configured",
            )

        # Extract headers from request
        x_api_key = request.headers.get("x-api-key")
        x_timestamp = request.headers.get("x-timestamp")
        x_signature = request.headers.get("x-signature")

        # Validate required headers
        if not x_api_key:
            raise HTTPException(
                status_code=401,
                detail="Missing X-API-Key header",
            )

        if not x_timestamp:
            raise HTTPException(
                status_code=401,
                detail="Missing X-Timestamp header",
            )

        if not x_signature:
            raise HTTPException(
                status_code=401,
                detail="Missing X-Signature header",
            )

        # Verify API key
        if not hmac.compare_digest(x_api_key, self.api_key):
            log.warning(f"Invalid API key: {x_api_key[:8]}...")
            raise HTTPException(
                status_code=401,
                detail="Invalid API key",
            )

        # Validate timestamp freshness
        if not validate_timestamp(x_timestamp):
            log.warning(f"Stale timestamp: {x_timestamp}")
            raise HTTPException(
                status_code=401,
                detail="Timestamp too old or invalid",
            )

        # Get request body for signature verification
        body = await request.body()
        body_str = body.decode("utf-8") if body else ""

        # Verify signature
        if not verify_signature(self.api_secret, body_str, x_timestamp, x_signature):
            log.warning("Invalid signature")
            raise HTTPException(
                status_code=401,
                detail="Invalid signature",
            )

        log.debug("API authentication successful")
        return True
