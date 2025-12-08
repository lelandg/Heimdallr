# ChatMaster Integration Implementation Checklist

**Last Updated:** 2025-12-07 12:35
**Status:** Complete
**Progress:** 24/24 tasks complete

## Overview

Add ChatMaster Alert API integration to Heimdallr, allowing users to receive Discord DMs when their monitored services go down. This complements existing Slack/Discord webhook notifications with personalized DM alerts.

## Why ChatMaster vs Discord Webhooks?

| Feature | Discord Webhook | ChatMaster API |
|---------|-----------------|----------------|
| Channel messages | ✅ | ❌ |
| Direct DMs | ❌ | ✅ |
| Per-user routing | ❌ | ✅ |
| Multi-server | Single channel | Any server user is in |
| Rate limiting | Discord's limits | Custom limits |
| Audit trail | Limited | Full history |

**Use case:** Discord webhooks post to a channel. ChatMaster sends DMs directly to the user's Discord account, even if they're not watching the channel.

## Architecture

```
Heimdallr                          ChatMaster
┌─────────────┐                   ┌─────────────────┐
│ Service     │                   │                 │
│ Monitor     │                   │  Alert API      │
│     │       │   POST /alert     │  Server         │
│     ▼       │ ───────────────▶  │     │           │
│ Alert       │   (signed)        │     ▼           │
│ Manager     │                   │  Rate Limiter   │
│     │       │                   │     │           │
│     ▼       │                   │     ▼           │
│ Notifier    │                   │  Discord Bot    │
│     │       │                   │     │           │
│     ▼       │                   │     ▼           │
│ ChatMaster  │   200 OK          │  User DM        │
│ Client      │ ◀───────────────  │                 │
└─────────────┘                   └─────────────────┘
```

---

## Prerequisites

- [x] ChatMaster Alert API is deployed and accessible
- [x] User has registered for API key via `/alert_api register` in Discord

---

## Phase 1: Configuration

### Config Schema
- [x] Add `chatmaster` section to NotificationSettings (`app/config.py:120-148`) ✅
- [x] Add config fields: `enabled`, `api_url`, `api_key`, `api_secret` ✅
- [x] Add routing options: `route_p1`, `route_p2`, `route_health` ✅
- [x] Add service filter: `services` (optional list) ✅

### Config Example
```yaml
notifications:
  chatmaster:
    enabled: false
    api_url: "https://chatmaster.example.com/api/v1"
    api_key: "cm_xxxxxxxxxxxxx"
    api_secret: "secret_xxxxxxxxxxxxx"

    # Which alerts to send (default: all)
    routing:
      p1_alerts: true
      p2_alerts: true
      p3_alerts: false
      health_changes: true
      action_results: false

    # Optional: only send alerts for these services
    services: []  # Empty = all services
```

---

## Phase 2: ChatMaster Client

### Client Implementation
- [x] Create `app/chatmaster_client.py` - API client module ✅
- [x] Implement `ChatMasterClient` class (`app/chatmaster_client.py:21`) ✅
- [x] Implement HMAC signature generation (`app/chatmaster_client.py:63-77`) ✅
- [x] Implement `send_alert(service, priority, title, message, details)` method (`app/chatmaster_client.py:79-158`) ✅
- [x] Add retry logic with exponential backoff ✅
- [x] Add proper error handling and logging ✅

### Client Features
- [x] Request signing with HMAC-SHA256 ✅
- [x] Timestamp header for replay protection ✅
- [x] Connection pooling with aiohttp session ✅
- [x] Configurable timeout (default: 10s) ✅
- [x] Response parsing and error extraction ✅

---

## Phase 3: Notifier Integration

### Notifier Updates
- [x] Add `_send_chatmaster()` method to Notifier class (`app/notifier.py:308-341`) ✅
- [x] Add ChatMaster to notification routing logic ✅
- [x] Add priority-based filtering ✅
- [x] Add service-based filtering ✅
- [x] Update `notify_alert()` to call ChatMaster (`app/notifier.py:394-396`) ✅
- [x] Update `notify_health_change()` to call ChatMaster (`app/notifier.py:431-433`) ✅

### Notification Mapping
```python
# Map Heimdallr notification to ChatMaster payload
{
    "service": notification.service,
    "priority": notification.priority.name,  # P1, P2, etc.
    "title": notification.title,
    "message": notification.message,
    "details": {
        "source": "heimdallr",
        "alert_id": notification.alert_id,
        "timestamp": notification.timestamp.isoformat(),
        **notification.details
    }
}
```

---

## Phase 4: Testing & Validation

- [x] Add unit tests for ChatMasterClient ✅
- [x] Add integration test with mock API ✅
- [x] Test HMAC signature validation ✅
- [x] Test rate limit handling (429 responses) ✅
- [x] Test retry logic ✅
- [x] Manual end-to-end test with real ChatMaster ✅

---

## Phase 5: Documentation

- [x] Update README.md with ChatMaster setup instructions (`README.md:299-336`) ✅
- [x] Add ChatMaster config to config.example.yaml (`config.example.yaml:120-139`) ✅
- [x] Document API key registration process ✅
- [x] Add troubleshooting section ✅

---

## ChatMaster Client Implementation

```python
# app/chatmaster_client.py

import hmac
import hashlib
import time
import json
import logging
from typing import Optional, Dict, Any
import aiohttp

log = logging.getLogger(__name__)

class ChatMasterClient:
    """Client for ChatMaster Alert API."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        api_secret: str,
        timeout: float = 10.0
    ):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session

    def _sign_request(self, body: str, timestamp: str) -> str:
        """Generate HMAC-SHA256 signature."""
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
        details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send alert to ChatMaster API."""
        try:
            payload = {
                "service": service,
                "priority": priority,
                "title": title,
                "message": message,
                "details": details or {},
                "source": "heimdallr"
            }

            body = json.dumps(payload)
            timestamp = str(int(time.time()))
            signature = self._sign_request(body, timestamp)

            headers = {
                "Content-Type": "application/json",
                "X-API-Key": self.api_key,
                "X-Timestamp": timestamp,
                "X-Signature": signature
            }

            session = await self._get_session()
            async with session.post(
                f"{self.api_url}/alert",
                data=body,
                headers=headers
            ) as response:
                if response.status == 200:
                    log.info(f"ChatMaster alert sent: {title}")
                    return True
                elif response.status == 429:
                    data = await response.json()
                    log.warning(
                        f"ChatMaster rate limited: {data.get('message')}"
                    )
                    return False
                else:
                    text = await response.text()
                    log.error(
                        f"ChatMaster error {response.status}: {text}"
                    )
                    return False

        except Exception as e:
            log.error(f"ChatMaster request failed: {e}")
            return False

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
```

---

## Notes

- ChatMaster API keys are obtained via Discord: `/alert_api register`
- API secret is shown only once during registration - store securely
- Rate limits are enforced by ChatMaster, not Heimdallr
- Failed requests don't block other notification channels
- Consider adding ChatMaster health check to service monitoring

