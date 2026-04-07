import os
import sys

import requests

from scanner.providers import TechProvider


class Wappalyzer(TechProvider):
    """Wappalyzer API technology detection provider."""

    BASE_URL = "https://api.wappalyzer.com/v2/lookup/"

    def detect(self, url: str, session: dict | None) -> list[dict]:
        """
        Call the Wappalyzer API to detect technologies.

        Requires WAPPALYZER_API_KEY environment variable.
        Returns empty list and logs a warning if the key is missing or the
        request fails.
        """
        api_key = os.environ.get("WAPPALYZER_API_KEY")
        if not api_key:
            print(
                "[warn] WAPPALYZER_API_KEY not set — skipping Wappalyzer provider",
                file=sys.stderr,
            )
            return []

        try:
            resp = requests.get(
                self.BASE_URL,
                params={"urls": url},
                headers={"x-api-key": api_key},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            print(f"[warn] Wappalyzer API request failed: {exc}", file=sys.stderr)
            return []
        except ValueError as exc:
            print(f"[warn] Wappalyzer API returned invalid JSON: {exc}", file=sys.stderr)
            return []

        techs = []
        try:
            for entry in data:
                for tech in entry.get("technologies", []):
                    name = tech.get("name")
                    if name:
                        techs.append({
                            "name": name,
                            "confidence": "medium",
                            "source": "header",
                        })
        except (KeyError, TypeError) as exc:
            print(f"[warn] Wappalyzer API response parse error: {exc}", file=sys.stderr)

        return techs
