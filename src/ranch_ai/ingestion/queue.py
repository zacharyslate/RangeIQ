from __future__ import annotations

from collections import deque


class MemoryPacketQueue:
    def __init__(self) -> None:
        self._queue: deque = deque()

    def enqueue(self, item) -> None:
        self._queue.append(item)

    def dequeue(self):
        return self._queue.popleft() if self._queue else None

    def size(self) -> int:
        return len(self._queue)
