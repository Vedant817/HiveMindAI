from __future__ import annotations

from shared.security import api_key_matches, configured_api_key

try:
    from fastapi import Header, HTTPException
except Exception:  # pragma: no cover
    Header = HTTPException = None


if Header:
    async def require_api_key(x_hivemind_api_key: str | None = Header(default=None)) -> None:
        if configured_api_key() and not api_key_matches(x_hivemind_api_key):
            raise HTTPException(status_code=401, detail="Invalid or missing HiveMindAI API key")
else:  # pragma: no cover
    async def require_api_key(x_hivemind_api_key: str | None = None) -> None:
        return None
