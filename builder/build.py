"""
Offline wordlist builder.

Consumes a scan report JSON, looks up detected technologies in the DB,
merges paths, applies confidence filtering, deduplicates, and writes output.
"""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime

import jsonschema
import yaml

from db.manager import lookup_technology

CONFIDENCE_ORDER = {"low": 0, "medium": 1, "high": 2}
SCHEMA_PATH = pathlib.Path(__file__).parent.parent / "schema" / "scan_report.json"


def run_build(
    scan_report_path: str,
    confidence: str,
    output_path: str | None,
    fmt: str,
) -> int:
    """
    Build a wordlist from a scan report.

    Args:
        scan_report_path: Path to the scan report JSON file.
        confidence: Minimum confidence level to include ("low", "medium", "high").
        output_path: Output file path. If None, auto-generated in output dir.
        fmt: Output format ("dirsearch", "ffuf", or "json").

    Returns:
        Exit code (0 = success, 1 = error).
    """
    report_path = pathlib.Path(scan_report_path).expanduser()
    if not report_path.exists():
        print(f"[error] Scan report not found: {report_path}", file=sys.stderr)
        return 1

    # Load report
    try:
        with report_path.open() as f:
            report = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[error] Failed to read scan report: {exc}", file=sys.stderr)
        return 1

    # Validate against schema
    try:
        with SCHEMA_PATH.open() as f:
            schema = json.load(f)
        jsonschema.validate(instance=report, schema=schema)
    except jsonschema.ValidationError as exc:
        print(f"[error] Scan report validation failed: {exc.message}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[warn] Could not load schema for validation: {exc}", file=sys.stderr)

    # Collect all paths from the report
    all_paths: list[dict] = list(report.get("paths", []))

    # Look up each detected technology in the DB and merge its paths
    technologies = report.get("technologies", [])
    for tech in technologies:
        tech_name = tech.get("name", "")
        tech_data = lookup_technology(tech_name)
        if tech_data is None:
            print(
                f"[warn] No DB entry for technology: {tech_name}",
                file=sys.stderr,
            )
            continue
        for path_entry in tech_data.get("paths", []):
            all_paths.append({
                "value": path_entry["value"],
                "source": "tech_db",
                "technology": tech_name,
                "confidence": path_entry.get("confidence", "medium"),
            })

    # Apply confidence filter
    min_level = CONFIDENCE_ORDER.get(confidence, 0)
    filtered = [
        p for p in all_paths
        if CONFIDENCE_ORDER.get(p.get("confidence", "low"), 0) >= min_level
    ]

    # Deduplicate by value (first occurrence wins)
    seen: set[str] = set()
    deduplicated: list[dict] = []
    for p in filtered:
        val = p.get("value", "")
        if val and val not in seen:
            seen.add(val)
            deduplicated.append(p)

    if not deduplicated:
        print("[warn] No paths matched the confidence filter.", file=sys.stderr)

    # Determine output path
    if output_path is None:
        ext = "json" if fmt == "json" else "txt"  # prompt, dirsearch, ffuf all get .txt
        output_dir = pathlib.Path("~/.wordsmith/output/").expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = report_path.stem
        output_path = str(output_dir / f"{stem}_wordlist.{ext}")

    output_file = pathlib.Path(output_path).expanduser()
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    try:
        with output_file.open("w") as f:
            if fmt == "json":
                json.dump(deduplicated, f, indent=2)
                f.write("\n")
            elif fmt == "prompt":
                f.write(_format_llm_prompt(report, technologies, deduplicated))
            else:
                # dirsearch and ffuf: flat text, one path per line
                for p in deduplicated:
                    f.write(p["value"] + "\n")
    except OSError as exc:
        print(f"[error] Failed to write output: {exc}", file=sys.stderr)
        return 1

    print(
        f"[info] Wrote prompt to {output_file}" if fmt == "prompt"
        else f"[info] Wrote {len(deduplicated)} paths to {output_file} (format: {fmt})",
        file=sys.stderr,
    )
    return 0


def _format_llm_prompt(
    report: dict,
    technologies: list[dict],
    all_paths: list[dict],
) -> str:
    """
    Build a concise LLM-ready prompt summarising the scan findings.

    The output is designed to be pasted into any LLM and asks it to generate
    an expanded wordlist based on the detected tech stack.
    """
    target = report.get("target", "unknown")

    # Tech stack summary — group by confidence
    tech_lines: list[str] = []
    for tech in technologies:
        name = tech.get("name", "")
        conf = tech.get("confidence", "unknown")
        source = tech.get("source", "")
        tech_lines.append(f"  - {name} ({conf} confidence, detected via {source})")
    tech_block = "\n".join(tech_lines) if tech_lines else "  - None detected"

    # Paths already found — cap at 30 to keep the prompt tight
    # Prefer high-confidence and non-tech_db paths for context value
    sorted_paths = sorted(
        all_paths,
        key=lambda p: (
            {"high": 0, "medium": 1, "low": 2}.get(p.get("confidence", "low"), 2),
            0 if p.get("source") != "tech_db" else 1,
        ),
    )
    sample = sorted_paths[:30]
    path_lines = [f"  {p['value']}" for p in sample]
    if len(all_paths) > 30:
        path_lines.append(f"  ... and {len(all_paths) - 30} more")
    path_block = "\n".join(path_lines) if path_lines else "  (none found)"

    # Unique tech names for the ask
    tech_names = [t.get("name", "") for t in technologies if t.get("name")]
    tech_list_str = ", ".join(tech_names) if tech_names else "unknown technologies"

    prompt = f"""I am performing an authorised penetration test against: {target}

The following tech stack was detected:
{tech_block}

WordSmith has already identified these paths on the target:
{path_block}

Based on the detected tech stack ({tech_list_str}), generate an expanded list of additional paths and filenames that are likely to exist on this server and would be valuable for directory busting.

Focus on:
- Admin panels and management interfaces
- Configuration and environment files
- Backup and temporary files
- API endpoints and versioned routes
- Framework-specific routes and assets
- Known vulnerable or sensitive endpoints for the detected technologies
- Common development and debug paths

Output one path per line with no additional commentary, headers, or explanation. Do not repeat paths already listed above.
"""
    return prompt
