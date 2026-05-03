from __future__ import annotations


def validate_payload(payload: str) -> list[str]:
    stripped = payload.strip()
    if not stripped:
        return ["Payload is empty."]
    if not (stripped.startswith("{") or "|" in stripped):
        return ["Payload format is unsupported."]
    return []
