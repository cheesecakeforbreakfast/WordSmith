"""
Offline wordlist builder.

Consumes a scan report JSON, looks up detected technologies in the DB,
merges paths, applies confidence filtering, deduplicates, and writes output.
"""

from __future__ import annotations

import json
import pathlib
import sys

import jsonschema
import yaml

from builder.prompt_generator import format_llm_prompt
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
                f.write(format_llm_prompt(report, technologies, deduplicated))
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


