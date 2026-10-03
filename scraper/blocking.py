"""Block detection across consecutive requests.

Empty or unparseable responses are held as "pending" until a real result
arrives. If the streak reaches the threshold, the run is treated as blocked and
the pending legs are discarded, so they are never recorded as "no flights".
"""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class BlockedError(Exception):
    """The data source is refusing us (captcha, consent wall, or too many empty replies)."""


class BlockDetector(Generic[T]):
    def __init__(self, threshold: int = 10):
        self.threshold = threshold
        self.pending: list[T] = []

    def ok(self) -> list[T]:
        """A real result arrived; returns pending items that can now be trusted as empty."""
        confirmed, self.pending = self.pending, []
        return confirmed

    def empty(self, item: T) -> bool:
        """Record an empty/unparseable reply. Returns True when the streak means we are blocked."""
        self.pending.append(item)
        return len(self.pending) >= self.threshold

    def discard(self) -> list[T]:
        dropped, self.pending = self.pending, []
        return dropped
