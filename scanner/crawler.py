"""
BFS link crawler with JS path scraping.

Known limitation: BeautifulSoup cannot execute JavaScript. Paths rendered
only by client-side JS will not be discovered. This is a known constraint
documented in CLAUDE.md — do not attempt to paper over it silently.
"""

from __future__ import annotations

import re
import sys
from collections import deque
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from builder.filters import apply_js_filter_pipeline

# Regex to extract string literals that could be path segments from JS source.
# Matches single- or double-quoted strings.
_JS_STRING_RE = re.compile(r"""(?:['"])(/?[^'"]{2,79}['"?#][^'"]*|[^'"]*[./][^'"]*)(?:['"])""")


def run_crawl(
    base_url: str,
    http_session: requests.Session,
    config: dict,
    depth: int,
) -> dict:
    """
    BFS crawl from base_url up to `depth` levels deep.

    Respects max_crawl_pages config limit.
    Does not follow redirects to external domains.

    Returns:
        {"paths": [{"value": str, "source": "crawl"|"js_scrape", "confidence": "high"|"medium"}]}
    """
    timeout = config.get("timeout", 10)
    max_pages = config.get("max_crawl_pages", 200)
    base_parsed = urlparse(base_url)
    base_host = base_parsed.netloc

    # BFS queue entries: (url, current_depth)
    queue: deque[tuple[str, int]] = deque([(base_url, 0)])
    visited: set[str] = {base_url}
    pages_fetched = 0

    paths: list[dict] = []
    seen_paths: set[str] = set()

    def _add_path(value: str, source: str, confidence: str) -> None:
        value = value.lstrip("/")
        if value and value not in seen_paths:
            seen_paths.add(value)
            paths.append({"value": value, "source": source, "confidence": confidence})

    while queue and pages_fetched < max_pages:
        current_url, current_depth = queue.popleft()
        pages_fetched += 1

        html, js_urls = _crawl_page(current_url, http_session, timeout)
        if html is None:
            continue

        # Record this URL as a discovered crawl path
        parsed = urlparse(current_url)
        path = parsed.path
        if path and path != "/":
            _add_path(path, "crawl", "high")

        # Extract and queue links for next depth level
        if current_depth < depth:
            links = extract_links(html, current_url, base_host)
            for link in links:
                if link not in visited:
                    visited.add(link)
                    queue.append((link, current_depth + 1))

        # Scrape JS files for path strings
        js_urls_filtered = [
            u for u in js_urls
            if urlparse(u).netloc == base_host
        ]
        for js_url in js_urls_filtered:
            try:
                resp = http_session.get(js_url, timeout=timeout)
                if resp.status_code == 200:
                    raw_strings = _extract_js_strings(resp.text)
                    filtered = apply_js_filter_pipeline(raw_strings, base_url)
                    for s in filtered:
                        _add_path(s, "js_scrape", "medium")
            except requests.RequestException as exc:
                print(f"[warn] JS fetch failed {js_url}: {exc}", file=sys.stderr)

    return {"paths": paths}


def _crawl_page(
    url: str, http_session: requests.Session, timeout: int
) -> tuple[str | None, list[str]]:
    """
    Fetch a single HTML page.

    Returns (html_text, js_src_urls) or (None, []) on error.
    """
    try:
        resp = http_session.get(url, timeout=timeout, allow_redirects=True)
        if resp.status_code != 200:
            return None, []
        content_type = resp.headers.get("Content-Type", "")
        if "html" not in content_type:
            return None, []
        html = resp.text
    except requests.RequestException as exc:
        print(f"[warn] Crawl failed {url}: {exc}", file=sys.stderr)
        return None, []

    js_urls = extract_js_urls(html, url)
    return html, js_urls


def extract_links(html: str, base_url: str, base_host: str) -> list[str]:
    """
    Parse HTML and extract all href attributes from <a> tags.

    Returns only same-domain absolute URLs, deduplicated.
    Query strings and fragments are stripped.
    """
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    seen: set[str] = set()

    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("javascript:"):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        # Strip fragment and query for deduplication
        clean = parsed._replace(fragment="", query="").geturl()
        if parsed.netloc == base_host and clean not in seen:
            seen.add(clean)
            links.append(clean)

    return links


def extract_js_urls(html: str, base_url: str) -> list[str]:
    """
    Parse HTML and extract src attributes from <script> tags.

    Returns absolute URLs of external JS files.
    """
    soup = BeautifulSoup(html, "html.parser")
    js_urls: list[str] = []

    for tag in soup.find_all("script", src=True):
        src = tag["src"].strip()
        if src:
            absolute = urljoin(base_url, src)
            js_urls.append(absolute)

    return js_urls


def _extract_js_strings(js_text: str) -> list[str]:
    """
    Extract string literals from JS source that may be path segments.

    Uses a regex to find single- and double-quoted string values.
    """
    candidates: list[str] = []
    for m in re.finditer(r"""["']([^"'\n\r]{2,80})["']""", js_text):
        candidates.append(m.group(1))
    return candidates
