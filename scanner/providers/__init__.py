from __future__ import annotations

from abc import ABC, abstractmethod


class TechProvider(ABC):
    """Abstract interface for technology detection providers."""

    @abstractmethod
    def detect(self, url: str, session: dict | None) -> list[dict]:
        """
        Detect technologies for the given URL.

        Args:
            url: Target URL string.
            session: Optional session dict from sessions/manager.py
                     (may contain cookies and headers).

        Returns:
            List of dicts, each with keys:
                name (str): Technology display name, e.g. "WordPress"
                confidence (str): "low" | "medium" | "high"
                source (str): One of the allowed source values.
        """
        ...
