from __future__ import annotations

from typing import Any


class PayloadValidationError(ValueError):
    pass


def bounded_text(payload: dict[str, Any], field: str, *, required: bool = True, max_length: int = 12000) -> str:
    value = payload.get(field, "")
    if value is None:
        value = ""
    text = str(value).strip()
    if required and not text:
        raise PayloadValidationError(f"{field} is required")
    if len(text) > max_length:
        raise PayloadValidationError(f"{field} exceeds {max_length} characters")
    return text


def bounded_tags(value: Any, *, max_items: int = 20, max_length: int = 60) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise PayloadValidationError("tags must be a list")
    tags = []
    for item in value[:max_items]:
        text = str(item).strip()
        if text:
            tags.append(text[:max_length])
    return tags
