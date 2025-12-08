"""ChatMaster Alert API client.

Sends alerts directly to Discord DMs via the ChatMaster Alert API.
This complements webhook notifications by allowing personalized DM alerts.
"""
from __future__ import annotations

import hmac
import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional

import aiohttp

from app.config import ChatMasterSettings

log = logging.getLogger("heimdallr.chatmaster")


class ChatMasterClient:
    """Client for ChatMaster Alert API.

    Features:
    - HMAC-SHA256 request signing
    - Timestamp-based replay protection
    - Connection pooling with aiohttp
    - Retry logic with exponential backoff
    """

    def __init__(self, settings: ChatMasterSettings, timeout: float = 10.0):
        """Initialize the ChatMaster client.

        Args:
            settings: ChatMaster configuration
            timeout: Request timeout in seconds
        """
        self.settings = settings
        self.api_url = settings.api_url.rstrip("/")
        self.api_key = settings.api_key
        self.api_secret = settings.api_secret
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def is_configured(self) -> bool:
        """Check if ChatMaster is properly configured."""
        return bool(
            self.settings.enabled
            and self.api_url
            and self.api_key
            and self.api_secret
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session with connection pooling."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session

    def _sign_request(self, body: str, timestamp: str) -> str:
        """Generate HMAC-SHA256 signature for request authentication.

        Args:
            body: JSON request body
            timestamp: Unix timestamp string

        Returns:
            Hex-encoded HMAC signature
        """
        message = f"{timestamp}.{body}"
        return hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

    async def send_alert(
        self,
        service: str,
        priority: str,
        title: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        max_retries: int = 2,
    ) -> bool:
        """Send alert to ChatMaster API.

        Args:
            service: Service name (e.g., "ChameleonLabs", "WebServer")
            priority: Priority level (P1, P2, P3, P4)
            title: Alert title
            message: Alert message body
            details: Optional additional details
            max_retries: Maximum retry attempts on failure

        Returns:
            True if alert was sent successfully
        """
        if not self.is_configured:
            log.debug("ChatMaster not configured, skipping alert")
            return False

        payload = {
            "service": service,
            "priority": priority,
            "title": title,
            "message": message,
            "details": details or {},
            "source": "heimdallr",
        }

        body = json.dumps(payload)
        retry_delay = 1.0

        for attempt in range(max_retries + 1):
            try:
                timestamp = str(int(time.time()))
                signature = self._sign_request(body, timestamp)

                headers = {
                    "Content-Type": "application/json",
                    "X-API-Key": self.api_key,
                    "X-Timestamp": timestamp,
                    "X-Signature": signature,
                }

                session = await self._get_session()
                async with session.post(
                    f"{self.api_url}/alert",
                    data=body,
                    headers=headers,
                ) as response:
                    if response.status == 200:
                        log.info(f"ChatMaster alert sent: {title}")
                        return True

                    elif response.status == 429:
                        # Rate limited
                        data = await response.json()
                        retry_after = data.get("retry_after", 60)
                        log.warning(
                            f"ChatMaster rate limited: {data.get('message')}. "
                            f"Retry after {retry_after}s"
                        )
                        return False

                    elif response.status >= 500 and attempt < max_retries:
                        # Server error - retry
                        text = await response.text()
                        log.warning(
                            f"ChatMaster server error {response.status}: {text}. "
                            f"Retrying in {retry_delay}s..."
                        )
                        await self._sleep(retry_delay)
                        retry_delay *= 2
                        continue

                    else:
                        # Client error or final server error
                        text = await response.text()
                        log.error(f"ChatMaster error {response.status}: {text}")
                        return False

            except aiohttp.ClientError as e:
                if attempt < max_retries:
                    log.warning(f"ChatMaster request failed: {e}. Retrying...")
                    await self._sleep(retry_delay)
                    retry_delay *= 2
                    continue
                log.error(f"ChatMaster request failed after {max_retries + 1} attempts: {e}")
                return False

            except Exception as e:
                log.error(f"ChatMaster unexpected error: {e}")
                return False

        return False

    async def _sleep(self, seconds: float) -> None:
        """Async sleep helper for testing."""
        import asyncio
        await asyncio.sleep(seconds)

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def should_send_for_priority(self, priority: str) -> bool:
        """Check if alerts should be sent for given priority.

        Args:
            priority: Priority level (P1, P2, P3, P4)

        Returns:
            True if routing config allows this priority
        """
        routing = self.settings.routing
        priority_map = {
            "P1": routing.p1_alerts,
            "P2": routing.p2_alerts,
            "P3": routing.p3_alerts,
            "P4": False,  # P4 never sent via ChatMaster
        }
        return priority_map.get(priority, False)

    def should_send_for_service(self, service: str) -> bool:
        """Check if alerts should be sent for given service.

        Args:
            service: Service name

        Returns:
            True if service filter allows this service
        """
        # Empty list means all services
        if not self.settings.services:
            return True
        return service in self.settings.services
