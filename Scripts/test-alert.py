#!/usr/bin/env python3
"""Send a test alert via the Heimdallr Alert API.

This script demonstrates how to send alerts to Heimdallr using HMAC authentication.
Use the same credentials configured for ChatMaster in config.yaml.

Usage:
    python test-alert.py --api-key YOUR_KEY --api-secret YOUR_SECRET

    Or set environment variables:
    export HEIMDALLR_API_KEY=your_key
    export HEIMDALLR_API_SECRET=your_secret
    python test-alert.py

Example from ChatMaster:
    This same signing mechanism can be used by ChatMaster to trigger alerts
    on Heimdallr (e.g., to notify when certain Discord events occur).
"""
import argparse
import hmac
import hashlib
import json
import os
import sys
import time
import urllib.request
import urllib.error


def sign_request(api_secret: str, body: str, timestamp: str) -> str:
    """Generate HMAC-SHA256 signature for the request."""
    message = f"{timestamp}.{body}"
    return hmac.new(
        api_secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()


def send_alert(
    host: str,
    api_key: str,
    api_secret: str,
    service: str,
    priority: str,
    title: str,
    message: str,
    details: dict = None,
) -> dict:
    """Send an alert via the Heimdallr Alert API.

    Args:
        host: API host (e.g., 'http://localhost:8000')
        api_key: API key (same as ChatMaster api_key)
        api_secret: API secret (same as ChatMaster api_secret)
        service: Service name (e.g., 'Heimdallr', 'MyApp')
        priority: Priority level (P1, P2, P3, P4)
        title: Alert title
        message: Alert message
        details: Optional additional details

    Returns:
        Response from the API
    """
    payload = {
        "service": service,
        "priority": priority,
        "title": title,
        "message": message,
        "details": details or {},
    }

    body = json.dumps(payload)
    timestamp = str(int(time.time()))
    signature = sign_request(api_secret, body, timestamp)

    url = f"{host.rstrip('/')}/api/v1/alert/send"

    req = urllib.request.Request(
        url,
        data=body.encode('utf-8'),
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
            "X-Timestamp": timestamp,
            "X-Signature": signature,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {
                "status": resp.status,
                "response": json.loads(resp.read().decode('utf-8')),
            }
    except urllib.error.HTTPError as e:
        return {
            "status": e.code,
            "error": e.read().decode('utf-8'),
        }
    except urllib.error.URLError as e:
        return {
            "status": 0,
            "error": str(e.reason),
        }


def main():
    parser = argparse.ArgumentParser(
        description="Send a test alert to Heimdallr",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("HEIMDALLR_HOST", "http://localhost:8000"),
        help="Heimdallr API host (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("HEIMDALLR_API_KEY", ""),
        help="API key (or set HEIMDALLR_API_KEY env var)",
    )
    parser.add_argument(
        "--api-secret",
        default=os.environ.get("HEIMDALLR_API_SECRET", ""),
        help="API secret (or set HEIMDALLR_API_SECRET env var)",
    )
    parser.add_argument(
        "--service",
        default="TestService",
        help="Service name (default: TestService)",
    )
    parser.add_argument(
        "--priority",
        default="P2",
        choices=["P1", "P2", "P3", "P4"],
        help="Alert priority (default: P2)",
    )
    parser.add_argument(
        "--title",
        default="Test Alert",
        help="Alert title",
    )
    parser.add_argument(
        "--message",
        default="This is a test alert from the test-alert.py script.",
        help="Alert message",
    )

    args = parser.parse_args()

    if not args.api_key or not args.api_secret:
        print("Error: API key and secret are required.")
        print("Use --api-key and --api-secret, or set environment variables:")
        print("  export HEIMDALLR_API_KEY=your_key")
        print("  export HEIMDALLR_API_SECRET=your_secret")
        sys.exit(1)

    print(f"Sending {args.priority} alert to {args.host}...")

    result = send_alert(
        host=args.host,
        api_key=args.api_key,
        api_secret=args.api_secret,
        service=args.service,
        priority=args.priority,
        title=args.title,
        message=args.message,
        details={"source": "test-alert.py"},
    )

    print(f"Status: {result.get('status')}")
    if 'response' in result:
        print(f"Response: {json.dumps(result['response'], indent=2)}")
    if 'error' in result:
        print(f"Error: {result['error']}")

    sys.exit(0 if result.get('status') == 200 else 1)


if __name__ == "__main__":
    main()
