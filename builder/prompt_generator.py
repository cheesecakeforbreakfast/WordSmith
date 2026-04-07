"""
Dynamic, context-aware LLM prompt generator for wordlist expansion.

SITE_CONTEXT_HINTS and TECH_FOCUS_MAP are module-level constants — add new
entries here to extend site-type inference and per-technology focus lists.
Keys in both constants are treated as regex patterns, not literal strings.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Module-level constants — extend these to broaden inference coverage
# ---------------------------------------------------------------------------

# Maps regex patterns (matched against discovered path values) to a plain-
# English description of the likely site purpose. Keys are pipe-delimited
# alternations compiled as regex at match time.
SITE_CONTEXT_HINTS: dict[str, str] = {
    r"shop|product|cart|checkout|order|inventory": "e-commerce platform",
    r"blog|post|article|category|author|feed": "content or publishing site",
    r"api|v1|v2|graphql|rest|webhook": "API-heavy application",
    r"admin|dashboard|manage|cms|editor": "content managed site",
    r"course|lesson|student|enroll|curriculum": "education platform",
    r"booking|appointment|schedule|availability": "booking or scheduling service",
    r"clinical|consultation|therapy|patient|health": "healthcare or medical service",
    r"gallery|portfolio|exhibit|showcase": "portfolio or creative site",
}

# Maps regex patterns (matched against technology names) to an ordered list of
# focus areas for the LLM. Keys are matched case-insensitively against the
# technology name from the scan report.
TECH_FOCUS_MAP: dict[str, list[str]] = {
    r"wordpress": [
        "WordPress-specific admin and plugin paths",
        "wp-config and backup file variants",
        "REST API endpoints under /wp-json/",
        "Xmlrpc and legacy endpoints",
        "Upload directory enumeration",
    ],
    r"wix|pepyaka": [
        "Wix _api/ endpoint enumeration",
        "Wix Data collection endpoints",
        "Velo backend function routes",
        "Member and booking service endpoints",
        "Gallery and media API paths",
    ],
    r"django": [
        "Django admin panel paths",
        "Debug toolbar and __debug__ endpoints",
        "Static and media file roots",
        "Common Django app route patterns",
        "REST framework browsable API paths",
    ],
    r"laravel": [
        "Laravel telescope and horizon endpoints",
        "Storage and public disk paths",
        ".env and config file variants",
        "Artisan-generated route patterns",
        "Laravel API versioning patterns",
    ],
    r"spring|springboot|spring boot": [
        "Spring Boot actuator endpoints",
        "Actuator sub-endpoints: env, beans, mappings, heapdump",
        "Spring security default paths",
        "Swagger and API docs endpoints",
        "Management port paths",
    ],
    r"jenkins": [
        "Jenkins script console and CLI paths",
        "Job and build API endpoints",
        "Plugin management paths",
        "Credential and configuration endpoints",
        "Jenkins REST API paths",
    ],
    r"drupal": [
        "Drupal admin and user paths",
        "Module and theme directory paths",
        "Drupal REST and JSON:API endpoints",
        "Configuration export paths",
        "Update and install script paths",
    ],
    r"joomla": [
        "Joomla administrator panel paths",
        "Component and plugin paths",
        "Joomla API endpoints",
        "Configuration and backup file variants",
        "Installation directory remnants",
    ],
    r"tomcat": [
        "Tomcat manager and host-manager paths",
        "Default application paths",
        "Status and server-info endpoints",
        "Example application paths",
        "JMX proxy paths",
    ],
    r"rails": [
        "Rails admin and ActiveAdmin paths",
        "Sidekiq and background job endpoints",
        "Rails API versioning patterns",
        "Asset pipeline paths",
        "Rails engine mount points",
    ],
    r"express|node\.?js": [
        "Common Express middleware paths",
        "Node.js debug and inspect endpoints",
        "NPM and package metadata paths",
        "Environment and config file variants",
        "Common Express API patterns",
    ],
    r"asp\.?net": [
        "ASP.NET handler and ashx paths",
        "Elmah error log paths",
        "Trace.axd and WebResource.axd",
        "ViewState and ScriptResource paths",
        "Web.config and backup variants",
    ],
    r"nginx": [
        "Nginx status endpoint",
        "Default page and config remnants",
        "Common reverse proxy path patterns",
        "Nginx error page paths",
    ],
    r"apache": [
        "Apache server-status and server-info",
        "mod_status and mod_info endpoints",
        "htaccess and htpasswd file variants",
        "Apache default page paths",
        "Common Apache module paths",
    ],
    r"flask": [
        "Flask debug toolbar and Werkzeug console paths",
        "Static file directory variants",
        "Common Flask blueprint route patterns",
        "Environment and config file variants",
        "Flask-Admin and Flask-Login paths",
    ],
    r"phpmyadmin": [
        "phpMyAdmin panel and setup paths",
        "Database management endpoint variants",
        "Configuration file paths",
        "Theme and library directory paths",
    ],
}

_GENERIC_FOCUS = [
    "Admin panel and management interface paths",
    "Configuration and environment file variants",
    "Backup and temporary file patterns",
    "API endpoint and versioned route patterns",
]

_PATH_FORMAT_BLOCK = """\
Output format:

One path per line
No leading slash
Use * as a wildcard where a dynamic segment is expected
Trailing slash for directories, no trailing slash for files
No query strings unless the parameter name itself is the finding
No explanations, headers, or commentary
Do not repeat any path already listed in the known paths section"""

_KNOWN_PATHS_PREAMBLE = (
    "The following paths were already discovered on this target. Analyse them\n"
    "for naming conventions, structural patterns, and site purpose before\n"
    "generating suggestions. Do not repeat them in your output."
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _infer_site_context(paths: list[dict]) -> str | None:
    """
    Infer the likely site purpose by matching discovered path values against
    SITE_CONTEXT_HINTS regex patterns.

    Iterates every key in SITE_CONTEXT_HINTS as a compiled regex and counts
    how many path values match. Returns the label for the category with the
    highest match count, or None if no pattern matches any path.

    If multiple categories tie, the first one encountered wins.

    Args:
        paths: List of path dicts from the scan report (must have a "value" key).

    Returns:
        A plain-English site-type string (e.g. "e-commerce platform"), or None.
    """
    path_values = [p.get("value", "").lower() for p in paths]
    best_label: str | None = None
    best_count = 0

    for pattern, label in SITE_CONTEXT_HINTS.items():
        compiled = re.compile(pattern, re.IGNORECASE)
        count = sum(1 for v in path_values if compiled.search(v))
        if count > best_count:
            best_count = count
            best_label = label

    return best_label if best_count > 0 else None


def _confidence_instruction(name: str, confidence: str) -> str:
    """
    Return a confidence-weighted instruction line for a single technology.

    Args:
        name: Display name of the technology (e.g. "WordPress").
        confidence: One of "high", "medium", or "low".

    Returns:
        A single instruction string tailored to the confidence level.
    """
    if confidence == "high":
        return (
            f"- {name} (high confidence): Generate specific known paths for {name}. "
            "Prioritise documented endpoints, known admin interfaces, and CVE-referenced paths."
        )
    elif confidence == "medium":
        return (
            f"- {name} (medium confidence): Detection confidence is medium. "
            f"Generate a broader set of paths plausible for {name} but note that some may "
            "not apply if detection is incorrect."
        )
    else:
        return (
            f"- {name} (low confidence): Detection confidence is low. "
            f"Generate conservative, widely-applicable paths only. "
            f"Do not assume {name}-specific structure."
        )


def _get_tech_focus(tech_name: str) -> list[str]:
    """
    Return the focus list for a technology by matching its name against
    TECH_FOCUS_MAP regex keys (case-insensitive).

    Falls back to _GENERIC_FOCUS if no pattern matches.

    Args:
        tech_name: Technology name string from the scan report.

    Returns:
        A list of focus-area strings for the LLM prompt.
    """
    name_lower = tech_name.lower()
    for pattern, focus_list in TECH_FOCUS_MAP.items():
        if re.search(pattern, name_lower, re.IGNORECASE):
            return focus_list
    return _GENERIC_FOCUS


def _quantity_guidance(n_known: int) -> str:
    """
    Return a quantity and prioritisation instruction block scaled to how many
    paths are already known.

    Thresholds:
        < 5 known paths  → min 40, max 80
        5–15 known paths → min 30, max 60
        > 15 known paths → min 20, max 40

    Args:
        n_known: Total number of known/discovered paths in the scan report.

    Returns:
        A multi-line instruction string.
    """
    if n_known < 5:
        min_p, max_p = 40, 80
    elif n_known <= 15:
        min_p, max_p = 30, 60
    else:
        min_p, max_p = 20, 40

    return (
        f"Generate between {min_p} and {max_p} paths. Prioritise:\n\n"
        "Paths specific to the detected technology stack\n"
        "Paths consistent with the inferred site type if identified\n"
        "Paths consistent with naming conventions observed in the known paths above\n"
        "Generic high-value paths last\n\n"
        "Quality over quantity — a shorter focused list is preferable to a long generic one."
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def format_llm_prompt(
    report: dict,
    technologies: list[dict],
    all_paths: list[dict],
) -> str:
    """
    Build a dynamic, context-aware LLM prompt from scan report data.

    The prompt structure follows this order:
        1. Engagement context line (with inferred site type if detected)
        2. Detected technologies block (confidence-weighted per technology)
        3. Known paths section (with inference instruction prepended)
        4. Stack-specific focus list (per detected technology, deduped)
        5. Path format instructions
        6. Quantity and prioritisation guidance

    Args:
        report:       Parsed scan report dict (must contain "target").
        technologies: List of detected technology dicts from the scan report,
                      each with "name", "confidence", and "source" keys.
        all_paths:    Full deduplicated path list after confidence filtering
                      (used for site-context inference, display sample, and
                      quantity guidance).

    Returns:
        A plain-text prompt string ready to paste into any LLM.
    """
    # -- 1. Engagement context -----------------------------------------------
    site_type = _infer_site_context(all_paths)
    context_line = "I am performing an authorised penetration test against my client's website."
    if site_type:
        context_line += f" The site appears to be a {site_type} — weight suggestions accordingly."

    # -- 2. Technologies block (confidence-weighted) -------------------------
    tech_lines: list[str] = []
    for tech in technologies:
        name = tech.get("name", "")
        confidence = tech.get("confidence", "low")
        if name:
            tech_lines.append(_confidence_instruction(name, confidence))
    tech_block = (
        "\n".join(tech_lines)
        if tech_lines
        else "No technologies detected."
    )

    # -- 3. Known paths (inference instruction + capped sample) --------------
    # Sort: higher confidence first, discovered paths before tech_db
    sorted_paths = sorted(
        all_paths,
        key=lambda p: (
            {"high": 0, "medium": 1, "low": 2}.get(p.get("confidence", "low"), 2),
            0 if p.get("source") != "tech_db" else 1,
        ),
    )
    sample = sorted_paths[:30]
    path_lines = [p["value"] for p in sample]
    if len(all_paths) > 30:
        path_lines.append(f"... and {len(all_paths) - 30} more")
    path_block = "\n".join(path_lines) if path_lines else "(none found)"

    # -- 4. Stack-specific focus list (deduped across all detected techs) ----
    seen_focus: set[str] = set()
    focus_items: list[str] = []
    for tech in technologies:
        name = tech.get("name", "")
        if not name:
            continue
        for item in _get_tech_focus(name):
            if item not in seen_focus:
                seen_focus.add(item)
                focus_items.append(f"- {item}")
    focus_block = "\n".join(focus_items) if focus_items else "- High-value paths for the detected stack"

    # -- 5 & 6. Format instructions + quantity guidance ----------------------
    quantity_block = _quantity_guidance(len(all_paths))

    # -- Assemble ------------------------------------------------------------
    sections = [
        context_line,
        f"Detected technologies:\n{tech_block}",
        f"{_KNOWN_PATHS_PREAMBLE}\n\n{path_block}",
        f"Focus on:\n{focus_block}",
        _PATH_FORMAT_BLOCK,
        quantity_block,
    ]
    return "\n\n".join(sections) + "\n"
