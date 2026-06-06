from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from shared.config import is_real_value, strict_integrations
from shared.errors import IntegrationNotConfigured


def app_secret() -> str | None:
    secret = os.getenv("APP_SECRET")
    return secret if is_real_value(secret) else None


def sign_token(subject: str, ttl_seconds: int = 86400) -> str | None:
    secret = app_secret()
    if not secret:
        if strict_integrations():
            raise IntegrationNotConfigured("APP_SECRET is required to sign public approval links")
        return None
    payload = {"sub": subject, "exp": int(time.time()) + ttl_seconds}
    raw_payload = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
    signature = hmac.new(secret.encode("utf-8"), raw_payload.encode("ascii"), hashlib.sha256).digest()
    raw_signature = base64.urlsafe_b64encode(signature).decode("ascii")
    return f"{raw_payload}.{raw_signature}"


def verify_token(subject: str, token: str | None) -> bool:
    secret = app_secret()
    if not secret:
        return not strict_integrations()
    if not token or "." not in token:
        return False
    raw_payload, raw_signature = token.rsplit(".", 1)
    expected = base64.urlsafe_b64encode(
        hmac.new(secret.encode("utf-8"), raw_payload.encode("ascii"), hashlib.sha256).digest()
    ).decode("ascii")
    if not hmac.compare_digest(expected, raw_signature):
        return False
    try:
        payload: dict[str, Any] = json.loads(base64.urlsafe_b64decode(raw_payload.encode("ascii")))
    except (ValueError, json.JSONDecodeError):
        return False
    return payload.get("sub") == subject and int(payload.get("exp", 0)) >= int(time.time())


def configured_api_key() -> str | None:
    value = os.getenv("HIVEMIND_API_KEY")
    return value if is_real_value(value) else None


def api_key_matches(value: str | None) -> bool:
    expected = configured_api_key()
    if not expected:
        return True
    return bool(value) and hmac.compare_digest(expected, value)
