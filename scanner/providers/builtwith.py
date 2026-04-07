import os
import sys

import requests

from scanner.providers import TechProvider


class Builtwith(TechProvider):
    """BuiltWith Free API technology detection provider."""

    BASE_URL = "https://api.builtwith.com/free1/api.json"

    def detect(self, url: str, session: dict | None) -> list[dict]:
        """
        Call the BuiltWith Free API to detect technologies.

        Requires BUILTWITH_API_KEY environment variable.
        Returns empty list and logs a warning if the key is missing or the
        request fails.
        """
        api_key = os.environ.get("BUILTWITH_API_KEY")
        if not api_key:
            print(
                "[warn] BUILTWITH_API_KEY not set — skipping BuiltWith provider",
                file=sys.stderr,
            )
            return []

        try:
            resp = requests.get(
                self.BASE_URL,
                params={"KEY": api_key, "LOOKUP": url},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            print(f"[warn] BuiltWith API request failed: {exc}", file=sys.stderr)
            return []
        except ValueError as exc:
            print(f"[warn] BuiltWith API returned invalid JSON: {exc}", file=sys.stderr)
            return []

        techs = []
        try:
            results = data.get("Results", [])
            if results:
                paths = results[0].get("Result", {}).get("Paths", [])
                for tech in paths:
                    name = tech.get("SubCategory") or tech.get("Name")
                    if name:
                        techs.append({
                            "name": name,
                            "confidence": "medium",
                            "source": "header",
                        })
        except (KeyError, IndexError, TypeError) as exc:
            print(f"[warn] BuiltWith API response parse error: {exc}", file=sys.stderr)

        return techs
