#!/usr/bin/env python3
"""WordSmith — targeted wordlist generator for pentesting."""

from __future__ import annotations

import argparse
import importlib
import json
import pathlib
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
import yaml


def load_config() -> dict:
    """Load config.yaml from the same directory as this script. Returns {} on missing file."""
    config_path = pathlib.Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        with config_path.open() as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        print(f"[warn] Failed to parse config.yaml: {exc}", file=sys.stderr)
        return {}


def resolve(args_val, config_key: str, config: dict, default):
    """Return the first non-None value: CLI arg > config file > hardcoded default."""
    if args_val is not None:
        return args_val
    return config.get(config_key, default)


def _build_http_session(config: dict, session_data: dict | None) -> requests.Session:
    """
    Build a requests.Session pre-loaded with User-Agent, and optionally
    cookies and extra headers from a named session file.
    """
    s = requests.Session()
    user_agent = config.get("user_agent", "Mozilla/5.0 (compatible; research)")
    s.headers.update({"User-Agent": user_agent})

    if session_data:
        cookies = session_data.get("cookies", {}) or {}
        headers = session_data.get("headers", {}) or {}
        for k, v in cookies.items():
            s.cookies.set(str(k), str(v))
        s.headers.update({str(k): str(v) for k, v in headers.items()})

    # Do not follow redirects to external domains — handled per-request via hooks
    return s


def _load_provider(name: str):
    """
    Dynamically load a TechProvider implementation by name.

    Each provider module in scanner/providers/ must expose a class whose
    name is the module name capitalised (e.g. builtwith -> Builtwith).
    The scanner never statically imports a concrete provider. (CLAUDE.md constraint)
    """
    try:
        mod = importlib.import_module(f"scanner.providers.{name}")
    except ModuleNotFoundError:
        print(f"[error] Unknown provider: {name}", file=sys.stderr)
        sys.exit(1)
    class_name = name.capitalize()
    cls = getattr(mod, class_name, None)
    if cls is None:
        print(
            f"[error] Provider module scanner.providers.{name} has no class {class_name}",
            file=sys.stderr,
        )
        sys.exit(1)
    return cls()


def _build_report(
    url: str,
    session_name: str | None,
    recon_result: dict,
    crawl_result: dict,
    tech_detections: list[dict],
) -> dict:
    """Assemble the scan report dict from all scan phase results."""
    # Merge technologies: recon header-detected + provider-detected, dedup by name
    all_techs: list[dict] = []
    seen_tech_names: set[str] = set()
    for tech in recon_result.get("technologies", []) + tech_detections:
        name = tech.get("name", "").lower()
        if name and name not in seen_tech_names:
            seen_tech_names.add(name)
            all_techs.append(tech)

    # Merge paths from recon (robots/sitemap) + crawl
    all_paths: list[dict] = (
        recon_result.get("paths", []) + crawl_result.get("paths", [])
    )

    return {
        "target": url,
        "session": session_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "technologies": all_techs,
        "paths": all_paths,
    }


def _write_report(report: dict, output_dir: pathlib.Path, url: str) -> pathlib.Path:
    """Write the scan report JSON to the output directory. Returns the file path."""
    safe_host = urlparse(url).netloc.replace(":", "_").replace("/", "_")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{safe_host}_{timestamp}.json"
    out_path = output_dir / filename
    with out_path.open("w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    return out_path


def cmd_scan(args, config: dict) -> int:
    """Entry point for `wordsmith scan`."""
    from scanner.recon import run_recon
    from scanner.crawler import run_crawl
    from sessions.manager import load_session

    url = args.url.rstrip("/")
    depth = resolve(args.depth, "depth", config, 3)
    confidence = resolve(args.confidence, "confidence", config, "low")
    provider_name = resolve(args.provider, "provider", config, "none")
    output_dir = pathlib.Path(
        config.get("output_dir", "~/.wordsmith/output/")
    ).expanduser()

    # Load session if specified
    session_data: dict | None = None
    if args.session:
        session_data = load_session(args.session, config)

    if args.dry_run:
        print(f"[dry-run] Target: {url}", file=sys.stderr)
        print(f"[dry-run] Depth: {depth}", file=sys.stderr)
        print(f"[dry-run] Confidence: {confidence}", file=sys.stderr)
        print(f"[dry-run] Provider: {provider_name}", file=sys.stderr)
        print(f"[dry-run] Session: {args.session or 'none'}", file=sys.stderr)
        print(f"[dry-run] Output dir: {output_dir}", file=sys.stderr)
        print(f"[dry-run] Ignore robots: {args.ignore_robots}", file=sys.stderr)
        print("[dry-run] No requests will be made.", file=sys.stderr)
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    http_session = _build_http_session(config, session_data)

    # Recon phase
    print(f"[scan] Recon: {url}", file=sys.stderr)
    recon_result = run_recon(
        url, http_session, config, ignore_robots=args.ignore_robots
    )
    techs_found = len(recon_result.get("technologies", []))
    paths_found = len(recon_result.get("paths", []))
    print(
        f"[scan] Recon complete — {techs_found} technologies, {paths_found} paths",
        file=sys.stderr,
    )

    # Crawl phase
    print(f"[scan] Crawling (depth={depth})...", file=sys.stderr)
    crawl_result = run_crawl(url, http_session, config, depth=depth)
    print(
        f"[scan] Crawl complete — {len(crawl_result.get('paths', []))} paths",
        file=sys.stderr,
    )

    # Provider phase
    tech_detections: list[dict] = []
    if provider_name != "none":
        print(f"[scan] Running provider: {provider_name}", file=sys.stderr)
        provider = _load_provider(provider_name)
        tech_detections = provider.detect(url, session_data)
        print(
            f"[scan] Provider detected {len(tech_detections)} technologies",
            file=sys.stderr,
        )

    # Assemble report
    report = _build_report(url, args.session, recon_result, crawl_result, tech_detections)

    # Write report
    out_path = _write_report(report, output_dir, url)
    print(f"[scan] Report written: {out_path}", file=sys.stderr)

    return 0


def cmd_build(args, config: dict) -> int:
    """Entry point for `wordsmith build`."""
    from builder.build import run_build

    confidence = resolve(args.confidence, "confidence", config, "low")
    return run_build(
        scan_report_path=args.scan_report,
        confidence=confidence,
        output_path=args.output,
        fmt=args.format,
    )


def cmd_db_list(args, config: dict) -> int:
    """Entry point for `wordsmith db list`."""
    from db.manager import list_technologies
    return list_technologies()


def cmd_db_validate(args, config: dict) -> int:
    """Entry point for `wordsmith db validate`."""
    from db.manager import validate_technologies
    return validate_technologies()


def build_parser() -> argparse.ArgumentParser:
    """Construct and return the full ArgumentParser tree."""
    parser = argparse.ArgumentParser(
        prog="wordsmith",
        description="WordSmith — targeted wordlist generator for pentesting",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- scan ---
    scan_p = subparsers.add_parser(
        "scan",
        help="Fingerprint a target and produce a scan report",
    )
    scan_p.add_argument("url", help="Target URL to scan")
    scan_p.add_argument("--session", default=None, metavar="NAME",
                        help="Named session to use for authenticated scanning")
    scan_p.add_argument("--depth", type=int, default=None,
                        help="Crawl depth (default: 3)")
    scan_p.add_argument("--confidence", choices=["low", "medium", "high"], default=None,
                        help="Minimum confidence level for included paths")
    scan_p.add_argument("--provider", choices=["builtwith", "wappalyzer", "none"],
                        default=None, help="External tech detection provider")
    scan_p.add_argument("--ignore-robots", action="store_true",
                        help="Ignore robots.txt restrictions during crawl")
    scan_p.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without making any requests")
    scan_p.set_defaults(func=cmd_scan)

    # --- build ---
    build_p = subparsers.add_parser(
        "build",
        help="Build a wordlist from a scan report",
    )
    build_p.add_argument("scan_report", help="Path to scan report JSON file")
    build_p.add_argument("--confidence", choices=["low", "medium", "high"], default=None,
                         help="Minimum confidence level for included paths")
    build_p.add_argument("--output", default=None, metavar="FILE",
                         help="Output file path (default: ~/.wordsmith/output/)")
    build_p.add_argument("--format", choices=["dirsearch", "ffuf", "json"],
                         default="dirsearch", help="Output format (default: dirsearch)")
    build_p.set_defaults(func=cmd_build)

    # --- db ---
    db_p = subparsers.add_parser("db", help="Manage the technology database")
    db_sub = db_p.add_subparsers(dest="db_command")

    db_list_p = db_sub.add_parser("list", help="List all technologies in the database")
    db_list_p.set_defaults(func=cmd_db_list)

    db_val_p = db_sub.add_parser("validate", help="Validate all technology YAML files")
    db_val_p.set_defaults(func=cmd_db_validate)

    return parser


def main() -> None:
    config = load_config()
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args, config))


if __name__ == "__main__":
    main()
