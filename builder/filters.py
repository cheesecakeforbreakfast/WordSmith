"""
JS path filter pipeline.

Each filter is an individual function with signature:
    filter_X(s: str, base_url: str) -> bool

Return True to KEEP the string, False to DISCARD it.

New filter rules must be added as new functions to FILTER_PIPELINE,
not merged into existing filter functions. (CLAUDE.md constraint)
"""

from urllib.parse import urlparse


def filter_node_modules(s: str, base_url: str) -> bool:
    """Discard strings containing 'node_modules'."""
    return "node_modules" not in s


def filter_external_url(s: str, base_url: str) -> bool:
    """Discard absolute HTTP/HTTPS URLs whose domain differs from base_url."""
    if not (s.startswith("http://") or s.startswith("https://")):
        return True
    base_host = urlparse(base_url).netloc
    s_host = urlparse(s).netloc
    return s_host == base_host


def filter_spaces(s: str, base_url: str) -> bool:
    """Discard strings containing spaces."""
    return " " not in s


def filter_length(s: str, base_url: str) -> bool:
    """Discard strings shorter than 3 or longer than 80 characters."""
    return 3 <= len(s) <= 80


def filter_source_maps(s: str, base_url: str) -> bool:
    """Discard source map patterns: strings ending in .map or containing 'webpack://'."""
    if s.endswith(".map"):
        return False
    if "webpack://" in s:
        return False
    return True


def filter_non_path_chars(s: str, base_url: str) -> bool:
    """Discard strings containing characters that indicate non-path content: ( ) ; ="""
    for ch in ("(", ")", ";", "="):
        if ch in s:
            return False
    return True


def filter_must_have_slash_or_dot(s: str, base_url: str) -> bool:
    """Keep only strings that contain at least one '/' or '.'."""
    return "/" in s or "." in s


# Ordered pipeline — strings must pass ALL filters to be kept.
FILTER_PIPELINE = [
    filter_node_modules,
    filter_external_url,
    filter_spaces,
    filter_length,
    filter_source_maps,
    filter_non_path_chars,
    filter_must_have_slash_or_dot,
]


def apply_js_filter_pipeline(strings: list[str], base_url: str) -> list[str]:
    """
    Run all filters in FILTER_PIPELINE against each string.
    Returns only the strings that pass every filter.
    """
    result = []
    for s in strings:
        if all(f(s, base_url) for f in FILTER_PIPELINE):
            result.append(s)
    return result
