"""
Webhook helpers for geometry correction job completion notifications.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
from typing import Optional

import requests


logger = logging.getLogger(__name__)


@dataclass
class WebhookConfig:
    url: str
    secret: str = ""
    timeout_s: int = 10


def send_completion_webhook(
    config: WebhookConfig,
    job_id: str,
    status: str,
    result: dict,
    error: Optional[str] = None,
) -> bool:
    """
    Notify an external endpoint when a geometry correction job finishes.
    """
    payload = {
        "job_id": job_id,
        "status": status,
        "result": result,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    headers = {"Content-Type": "application/json"}
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)

    if config.secret:
        digest = hmac.new(
            config.secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers["X-GC-Signature"] = "sha256=" + digest

    try:
        response = requests.post(
            config.url,
            data=body,
            headers=headers,
            timeout=config.timeout_s,
        )
        return 200 <= int(response.status_code) < 300
    except Exception as exc:
        logger.warning("Geometry correction webhook failed: %s", exc)
        return False
