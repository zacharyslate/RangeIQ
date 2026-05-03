from __future__ import annotations

import time


class ProviderRateLimiter:
    def __init__(self):
        self._last_call: dict[str, float] = {}

    def wait(self, provider_name: str, min_interval_seconds: float) -> None:
        if min_interval_seconds <= 0:
            return

        now = time.monotonic()
        last_called = self._last_call.get(provider_name)
        if last_called is not None:
            elapsed = now - last_called
            if elapsed < min_interval_seconds:
                time.sleep(min_interval_seconds - elapsed)
        self._last_call[provider_name] = time.monotonic()
