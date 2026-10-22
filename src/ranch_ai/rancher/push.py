"""Web Push for the messenger: the phone buzzes when a message arrives, even with RangeIQ closed.

The server signs each push with its own VAPID key pair (RFC 8292), made the first time it's needed and kept in the app
database, never in the repo. Message text is encrypted for each phone (RFC 8291), so the push services (Google, Apple,
Mozilla) only pass on an encrypted blob. Phones whose subscription has expired (HTTP 404/410) are dropped.
iPhones get pushes only when RangeIQ was added to the Home Screen (iOS 16.4+).
"""

from __future__ import annotations

import base64
import json
import threading
from typing import Any

VAPID_KEY = "vapid_private_pem"
CONTACT = "mailto:admin@rangeiq.org"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def vapid_private_pem(store) -> str:
    pem = store.app_value(VAPID_KEY)
    if pem:
        return pem
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    return store.set_app_value_once(VAPID_KEY, pem)


def vapid_public_key(store) -> str:
    """The key phones need to subscribe (applicationServerKey): the uncompressed P-256 point, base64url."""
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_private_key(vapid_private_pem(store).encode(), password=None)
    raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return _b64url(raw)


def send(store, user_ids: list[str], payload: dict[str, Any], *, sender=None) -> dict[str, int]:
    """Send one notification to every phone of these people. Returns counts; never raises."""
    subs = store.push_subs_for(user_ids)
    if not subs:
        return {"sent": 0, "dropped": 0, "failed": 0}
    if sender is None:
        try:
            from pywebpush import WebPushException, webpush
        except ImportError:                          # library missing on this server: report, don't crash
            print("[push] pywebpush is not installed; notifications are off", flush=True)
            return {"sent": 0, "dropped": 0, "failed": len(subs)}

        def sender(info, data, private_pem):        # noqa: E306
            try:
                webpush(subscription_info=info, data=data, vapid_private_key=private_pem, vapid_claims={"sub": CONTACT},
                        ttl=24 * 3600, timeout=10)
                return 201
            except WebPushException as exc:
                return getattr(exc.response, "status_code", 0) or 0
    pem = vapid_private_pem(store)
    from cryptography.hazmat.primitives import serialization
    # pywebpush wants the key as base64url DER (or a file path); give it DER.
    der = serialization.load_pem_private_key(pem.encode(), password=None).private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    key_arg = _b64url(der)
    data = json.dumps(payload)
    counts = {"sent": 0, "dropped": 0, "failed": 0}
    for s in subs:
        info = {"endpoint": s["endpoint"], "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}}
        try:
            status = sender(info, data, key_arg)
        except Exception:  # noqa: BLE001 - a bad phone must not stop the others
            status = 0
        if status in (404, 410):                    # the phone unsubscribed or the subscription expired
            store.delete_push_sub(s["endpoint"]); counts["dropped"] += 1
        elif 200 <= status < 300:
            counts["sent"] += 1
        else:
            counts["failed"] += 1
    return counts


def send_in_background(store, user_ids: list[str], payload: dict[str, Any]) -> None:
    threading.Thread(target=send, args=(store, user_ids, payload), daemon=True).start()
