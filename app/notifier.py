"""Notification system for alerts and status updates.

Provides:
- Email notifications via AWS SES
- Slack webhook integration
- Discord webhook integration
- Notification templating
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import aiohttp

from app.config import NotificationSettings
from app.alert_manager import Alert, AlertPriority
from app.service_monitor import HealthChange, HealthState

log = logging.getLogger("monitor.notifier")


class NotificationChannel(Enum):
    """Available notification channels."""
    EMAIL = "email"
    SLACK = "slack"
    DISCORD = "discord"


class NotificationPriority(Enum):
    """Notification priority levels."""
    CRITICAL = "critical"  # Immediate attention
    HIGH = "high"          # Within 15 minutes
    NORMAL = "normal"      # Within 1 hour
    LOW = "low"            # Informational


@dataclass
class Notification:
    """A notification to be sent."""
    title: str
    message: str
    priority: NotificationPriority
    channels: List[NotificationChannel]
    service: str
    details: Dict[str, Any]

    def to_email_body(self) -> str:
        """Format notification for email."""
        body = f"""
AWS Monitor Alert

Priority: {self.priority.value.upper()}
Service: {self.service}

{self.title}

{self.message}

Details:
"""
        for key, value in self.details.items():
            body += f"  {key}: {value}\n"

        body += f"\n\nTimestamp: {datetime.now(timezone.utc).isoformat()}"
        body += "\n\n--\nAWS Monitor - Automated Notification"

        return body

    def to_slack_payload(self) -> Dict:
        """Format notification for Slack webhook."""
        color_map = {
            NotificationPriority.CRITICAL: "#FF0000",
            NotificationPriority.HIGH: "#FF6600",
            NotificationPriority.NORMAL: "#FFCC00",
            NotificationPriority.LOW: "#00CC00",
        }

        fields = [
            {"title": key, "value": str(value), "short": True}
            for key, value in self.details.items()
        ][:8]  # Slack limit

        return {
            "attachments": [{
                "color": color_map.get(self.priority, "#808080"),
                "title": self.title,
                "text": self.message,
                "fields": fields,
                "footer": f"AWS Monitor | {self.service}",
                "ts": int(datetime.now(timezone.utc).timestamp()),
            }]
        }

    def to_discord_payload(self) -> Dict:
        """Format notification for Discord webhook."""
        color_map = {
            NotificationPriority.CRITICAL: 16711680,  # Red
            NotificationPriority.HIGH: 16744448,      # Orange
            NotificationPriority.NORMAL: 16763904,    # Yellow
            NotificationPriority.LOW: 52224,          # Green
        }

        fields = [
            {"name": key, "value": str(value)[:1024], "inline": True}
            for key, value in list(self.details.items())[:6]  # Discord limit
        ]

        return {
            "embeds": [{
                "title": self.title,
                "description": self.message[:4096],
                "color": color_map.get(self.priority, 8421504),
                "fields": fields,
                "footer": {"text": f"AWS Monitor | {self.service}"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }]
        }


class Notifier:
    """Sends notifications through multiple channels.

    Features:
    - Multiple channel support (email, Slack, Discord)
    - Priority-based routing
    - Rate limiting to prevent spam
    - Notification templates
    """

    def __init__(self, settings: NotificationSettings):
        """Initialize the notifier.

        Args:
            settings: Notification configuration
        """
        self.settings = settings
        self._http_session: Optional[aiohttp.ClientSession] = None

        # Rate limiting
        self._sent_count: Dict[str, int] = {}  # channel -> count
        self._last_reset = datetime.now(timezone.utc)
        self._rate_limit_per_hour = 50  # Per channel

        # Notification history
        self._history: List[Dict] = []
        self._max_history = 500

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def close(self) -> None:
        """Close HTTP session."""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()

    async def send_notification(self, notification: Notification) -> Dict[str, bool]:
        """Send notification to all specified channels.

        Args:
            notification: Notification to send

        Returns:
            Dict mapping channel to success status
        """
        results = {}

        for channel in notification.channels:
            # Check rate limit
            if not self._check_rate_limit(channel):
                log.warning(f"Rate limit exceeded for {channel.value}")
                results[channel.value] = False
                continue

            try:
                if channel == NotificationChannel.EMAIL:
                    success = await self._send_email(notification)
                elif channel == NotificationChannel.SLACK:
                    success = await self._send_slack(notification)
                elif channel == NotificationChannel.DISCORD:
                    success = await self._send_discord(notification)
                else:
                    success = False

                results[channel.value] = success
                self._record_sent(channel, notification, success)

            except Exception as e:
                log.error(f"Failed to send {channel.value} notification: {e}")
                results[channel.value] = False

        return results

    async def _send_email(self, notification: Notification) -> bool:
        """Send email via AWS SES."""
        if not self.settings.email_enabled:
            return False

        if not self.settings.email_recipients:
            log.warning("No email recipients configured")
            return False

        try:
            # Use aiobotocore for async SES
            from aiobotocore.session import get_session

            session = get_session()
            async with session.create_client("ses", region_name="us-east-1") as ses:
                response = await ses.send_email(
                    Source=self.settings.email_from,
                    Destination={
                        "ToAddresses": self.settings.email_recipients,
                    },
                    Message={
                        "Subject": {
                            "Data": f"[{notification.priority.value.upper()}] {notification.title}",
                        },
                        "Body": {
                            "Text": {"Data": notification.to_email_body()},
                        },
                    },
                )

                message_id = response.get("MessageId")
                log.info(f"Email sent: {message_id}")
                return True

        except Exception as e:
            log.error(f"SES email failed: {e}")
            return False

    async def _send_slack(self, notification: Notification) -> bool:
        """Send notification via Slack webhook."""
        if not self.settings.slack_enabled:
            return False

        if not self.settings.slack_webhook_url:
            log.warning("No Slack webhook URL configured")
            return False

        try:
            session = await self._get_session()
            payload = notification.to_slack_payload()

            async with session.post(
                self.settings.slack_webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    log.info("Slack notification sent")
                    return True
                else:
                    text = await response.text()
                    log.error(f"Slack webhook failed: {response.status} - {text}")
                    return False

        except Exception as e:
            log.error(f"Slack notification failed: {e}")
            return False

    async def _send_discord(self, notification: Notification) -> bool:
        """Send notification via Discord webhook."""
        if not self.settings.discord_enabled:
            return False

        if not self.settings.discord_webhook_url:
            log.warning("No Discord webhook URL configured")
            return False

        try:
            session = await self._get_session()
            payload = notification.to_discord_payload()

            async with session.post(
                self.settings.discord_webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status in {200, 204}:
                    log.info("Discord notification sent")
                    return True
                else:
                    text = await response.text()
                    log.error(f"Discord webhook failed: {response.status} - {text}")
                    return False

        except Exception as e:
            log.error(f"Discord notification failed: {e}")
            return False

    def _check_rate_limit(self, channel: NotificationChannel) -> bool:
        """Check if under rate limit for channel."""
        # Reset counts hourly
        now = datetime.now(timezone.utc)
        if (now - self._last_reset).total_seconds() > 3600:
            self._sent_count.clear()
            self._last_reset = now

        count = self._sent_count.get(channel.value, 0)
        return count < self._rate_limit_per_hour

    def _record_sent(
        self,
        channel: NotificationChannel,
        notification: Notification,
        success: bool,
    ) -> None:
        """Record sent notification."""
        self._sent_count[channel.value] = self._sent_count.get(channel.value, 0) + 1

        self._history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "channel": channel.value,
            "title": notification.title,
            "priority": notification.priority.value,
            "service": notification.service,
            "success": success,
        })

        if len(self._history) > self._max_history:
            self._history.pop(0)

    # Convenience methods for common notifications

    async def notify_alert(self, alert: Alert) -> Dict[str, bool]:
        """Send notification for a new alert."""
        priority_map = {
            AlertPriority.P1: NotificationPriority.CRITICAL,
            AlertPriority.P2: NotificationPriority.HIGH,
            AlertPriority.P3: NotificationPriority.NORMAL,
            AlertPriority.P4: NotificationPriority.LOW,
        }

        # Determine channels based on priority
        channels = [NotificationChannel.EMAIL] if self.settings.email_enabled else []
        if alert.priority in {AlertPriority.P1, AlertPriority.P2}:
            if self.settings.slack_enabled:
                channels.append(NotificationChannel.SLACK)
            if self.settings.discord_enabled:
                channels.append(NotificationChannel.DISCORD)

        notification = Notification(
            title=alert.title,
            message=alert.message,
            priority=priority_map.get(alert.priority, NotificationPriority.NORMAL),
            channels=channels,
            service=alert.source_service,
            details={
                "Alert ID": alert.alert_id,
                "Priority": alert.priority.value,
                "Source": alert.source_type,
                "Status": alert.status.value,
            },
        )

        return await self.send_notification(notification)

    async def notify_health_change(self, change: HealthChange) -> Dict[str, bool]:
        """Send notification for health state change."""
        # Only notify on significant changes
        if change.new_state == HealthState.HEALTHY:
            priority = NotificationPriority.LOW
        elif change.new_state == HealthState.DEGRADED:
            priority = NotificationPriority.NORMAL
        else:
            priority = NotificationPriority.HIGH

        channels = []
        if self.settings.email_enabled:
            channels.append(NotificationChannel.EMAIL)
        if priority in {NotificationPriority.CRITICAL, NotificationPriority.HIGH}:
            if self.settings.slack_enabled:
                channels.append(NotificationChannel.SLACK)

        notification = Notification(
            title=f"Service Health: {change.service_name}",
            message=f"State changed: {change.old_state.value} → {change.new_state.value}\n{change.message}",
            priority=priority,
            channels=channels,
            service=change.service_name,
            details={
                "Service Type": change.service_type,
                "Previous State": change.old_state.value,
                "New State": change.new_state.value,
            },
        )

        return await self.send_notification(notification)

    async def notify_action_result(
        self,
        action_type: str,
        service: str,
        success: bool,
        message: str,
    ) -> Dict[str, bool]:
        """Send notification for action execution result."""
        priority = NotificationPriority.NORMAL if success else NotificationPriority.HIGH

        channels = []
        if self.settings.email_enabled:
            channels.append(NotificationChannel.EMAIL)

        notification = Notification(
            title=f"Action {'Completed' if success else 'Failed'}: {action_type}",
            message=message,
            priority=priority,
            channels=channels,
            service=service,
            details={
                "Action": action_type,
                "Result": "Success" if success else "Failed",
            },
        )

        return await self.send_notification(notification)

    def get_stats(self) -> Dict:
        """Get notifier statistics."""
        return {
            "email_enabled": self.settings.email_enabled,
            "slack_enabled": self.settings.slack_enabled,
            "discord_enabled": self.settings.discord_enabled,
            "sent_this_hour": dict(self._sent_count),
            "rate_limit_per_hour": self._rate_limit_per_hour,
            "total_sent": len(self._history),
        }

    def get_history(self, limit: int = 50) -> List[Dict]:
        """Get notification history."""
        return list(reversed(self._history[-limit:]))
