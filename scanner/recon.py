"""
Passive reconnaissance: HTTP header analysis, robots.txt, and sitemap.xml.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

import requests


# Maps header names to (tech_name, confidence) tuples.
# Values are substring-matched (case-insensitive) against the header value.
HEADER_TECH_MAP: dict[str, dict[str, tuple[str, str]]] = {
    "server": {
        "nginx": ("Nginx", "high"),
        "apache": ("Apache", "high"),
        "microsoft-iis": ("IIS", "high"),
        "iis": ("IIS", "high"),
        "tomcat": ("Tomcat", "high"),
        "gunicorn": ("Gunicorn", "high"),
        "waitress": ("Waitress", "medium"),
        "jetty": ("Jetty", "high"),
        "lighttpd": ("Lighttpd", "high"),
        "caddy": ("Caddy", "high"),
    },
    "x-powered-by": {
        "php": ("PHP", "high"),
        "asp.net": ("ASP.NET", "high"),
        "express": ("Express", "high"),
        "next.js": ("Next.js", "high"),
        "mono": ("Mono", "medium"),
        "servlet": ("Java Servlet", "medium"),
    },
}

# Headers whose presence alone signals a technology.
PRESENCE_HEADER_MAP: dict[str, tuple[str, str]] = {
    "x-generator":        ("", "high"),       # value used as-is for tech name
    "x-drupal-cache":     ("Drupal", "high"),
    "x-drupal-dynamic-cache": ("Drupal", "high"),
    "x-pingback":         ("WordPress", "high"),
    "x-aspnet-version":   ("ASP.NET", "high"),
    "x-aspnetmvc-version": ("ASP.NET MVC", "high"),
}

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def run_recon(
    url: str,
    http_session: requests.Session,
    config: dict,
    ignore_robots: bool = False,
) -> dict:
    """
    Orchestrate header parsing, robots.txt fetch, and sitemap.xml fetch.

    Returns:
        {
            "technologies": [{"name": str, "confidence": str, "source": "header"}],
            "paths": [{"value": str, "source": "robots"|"sitemap", "confidence": "high"}]
        }
    """
    timeout = config.get("timeout", 10)
    technologies: list[dict] = []
    paths: list[dict] = []

    # Headers
    response = fetch_headers(url, http_session, timeout)
    if response is not None:
        technologies.extend(parse_tech_headers(dict(response.headers)))

    # robots.txt
    if not ignore_robots:
        paths.extend(fetch_robots(url, http_session, timeout))

    # sitemap.xml
    paths.extend(fetch_sitemap(url, http_session, timeout))

    return {"technologies": technologies, "paths": paths}


def fetch_headers(
    url: str, http_session: requests.Session, timeout: int
) -> requests.Response | None:
    """
    Send a HEAD request to the target URL.
    Falls back to GET if the server doesn't support HEAD.
    Returns the Response object, or None on failure.
    """
    for method in ("HEAD", "GET"):
        try:
            resp = http_session.request(method, url, timeout=timeout, allow_redirects=True)
            return resp
        except requests.RequestException as exc:
            print(f"[warn] {method} {url} failed: {exc}", file=sys.stderr)
            if method == "GET":
                return None
    return None


def parse_tech_headers(headers: dict) -> list[dict]:
    """
    Inspect HTTP response headers for technology signals.

    Returns list of {"name": str, "confidence": str, "source": "header"}.
    """
    techs: list[dict] = []
    seen: set[str] = set()

    def _add(name: str, confidence: str) -> None:
        if name and name.lower() not in seen:
            seen.add(name.lower())
            techs.append({"name": name, "confidence": confidence, "source": "header"})

    headers_lower = {k.lower(): v for k, v in headers.items()}

    for header_name, tech_map in HEADER_TECH_MAP.items():
        value = headers_lower.get(header_name, "")
        if not value:
            continue
        value_lower = value.lower()
        matched = False
        for pattern, (tech_name, confidence) in tech_map.items():
            if pattern in value_lower:
                _add(tech_name, confidence)
                matched = True
                break
        if not matched:
            # Use the raw header value as tech name if no specific match
            _add(value.split("/")[0].strip(), "medium")

    for header_name, (tech_name, confidence) in PRESENCE_HEADER_MAP.items():
        value = headers_lower.get(header_name, "")
        if not value:
            continue
        if tech_name:
            _add(tech_name, confidence)
        else:
            # x-generator: use the header value directly as the tech name
            _add(value.split(" ")[0].strip(), confidence)

    return techs


def fetch_robots(
    url: str, http_session: requests.Session, timeout: int
) -> list[dict]:
    """
    Fetch and parse /robots.txt.

    Returns list of {"value": str, "source": "robots", "confidence": "high"}.
    Returns [] on any error.
    """
    robots_url = urljoin(url.rstrip("/") + "/", "robots.txt")
    try:
        resp = http_session.get(robots_url, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200:
            return []
    except requests.RequestException as exc:
        print(f"[warn] robots.txt fetch failed: {exc}", file=sys.stderr)
        return []

    paths: list[dict] = []
    for line in resp.text.splitlines():
        # Strip inline comments
        line = line.split("#")[0].strip()
        if not line:
            continue
        for directive in ("Disallow:", "Allow:"):
            if line.startswith(directive):
                path = line[len(directive):].strip()
                # Strip leading slash and skip empty or root-only entries
                path = path.lstrip("/")
                if path and path != "*":
                    paths.append({
                        "value": path,
                        "source": "robots",
                        "confidence": "high",
                    })
                break

    return paths


def fetch_sitemap(
    url: str, http_session: requests.Session, timeout: int
) -> list[dict]:
    """
    Fetch and parse /sitemap.xml.

    Returns list of {"value": str, "source": "sitemap", "confidence": "high"}.
    Returns [] on any error or if not XML.
    """
    sitemap_url = urljoin(url.rstrip("/") + "/", "sitemap.xml")
    try:
        resp = http_session.get(sitemap_url, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200:
            return []
        content_type = resp.headers.get("Content-Type", "")
        if "xml" not in content_type and not resp.text.strip().startswith("<"):
            return []
    except requests.RequestException as exc:
        print(f"[warn] sitemap.xml fetch failed: {exc}", file=sys.stderr)
        return []

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        print(f"[warn] sitemap.xml parse error: {exc}", file=sys.stderr)
        return []

    base_parsed = urlparse(url)
    base_prefix = f"{base_parsed.scheme}://{base_parsed.netloc}"

    paths: list[dict] = []
    # Handle both namespaced and non-namespaced <loc> elements
    for tag in (f"{{{SITEMAP_NS}}}loc", "loc"):
        for loc in root.iter(tag):
            text = (loc.text or "").strip()
            if not text:
                continue
            # Convert absolute URLs to relative paths
            if text.startswith(base_prefix):
                text = text[len(base_prefix):]
            elif text.startswith("http"):
                # External URL — skip
                continue
            text = text.lstrip("/")
            if text:
                paths.append({
                    "value": text,
                    "source": "sitemap",
                    "confidence": "high",
                })

    return paths
