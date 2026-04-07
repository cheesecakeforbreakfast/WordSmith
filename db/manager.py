from __future__ import annotations

import pathlib
import sys

import jsonschema
import yaml


def _get_db_dir() -> pathlib.Path:
    """Return the path to db/technologies/ relative to this file."""
    return pathlib.Path(__file__).parent / "technologies"


def _get_schema_dir() -> pathlib.Path:
    """Return the path to the schema/ directory relative to this package."""
    return pathlib.Path(__file__).parent.parent / "schema"


def list_technologies(db_dir: pathlib.Path | None = None) -> int:
    """Print sorted list of technology names from all YAML files. Returns exit code."""
    db_dir = db_dir or _get_db_dir()
    yaml_files = sorted(db_dir.glob("*.yaml"))

    if not yaml_files:
        print("[warn] No technology files found in database.", file=sys.stderr)
        return 0

    names = []
    for f in yaml_files:
        try:
            with f.open() as fh:
                data = yaml.safe_load(fh)
            if data and "name" in data:
                names.append(data["name"])
        except (yaml.YAMLError, OSError) as exc:
            print(f"[warn] Could not read {f.name}: {exc}", file=sys.stderr)

    for name in sorted(names):
        print(name)

    return 0


def validate_technologies(
    db_dir: pathlib.Path | None = None,
    schema_path: pathlib.Path | None = None,
) -> int:
    """
    Validate each YAML file against schema/tech_entry.json.
    Prints pass/fail per file. Returns 0 if all pass, 1 if any fail.
    """
    db_dir = db_dir or _get_db_dir()
    schema_path = schema_path or (_get_schema_dir() / "tech_entry.json")

    import json

    try:
        with schema_path.open() as f:
            schema = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[error] Could not load schema {schema_path}: {exc}", file=sys.stderr)
        return 1

    yaml_files = sorted(db_dir.glob("*.yaml"))
    if not yaml_files:
        print("[warn] No technology files found in database.", file=sys.stderr)
        return 0

    all_passed = True
    for f in yaml_files:
        try:
            with f.open() as fh:
                data = yaml.safe_load(fh)
            jsonschema.validate(instance=data, schema=schema)
            print(f"  [pass] {f.name}")
        except yaml.YAMLError as exc:
            print(f"  [fail] {f.name} — YAML parse error: {exc}")
            all_passed = False
        except jsonschema.ValidationError as exc:
            print(f"  [fail] {f.name} — {exc.message}")
            all_passed = False
        except OSError as exc:
            print(f"  [fail] {f.name} — Could not read file: {exc}")
            all_passed = False

    return 0 if all_passed else 1


def lookup_technology(name: str, db_dir: pathlib.Path | None = None) -> dict | None:
    """
    Case-insensitive lookup of a technology by name in the DB.

    Returns the parsed YAML dict if found, or None if not found.
    """
    db_dir = db_dir or _get_db_dir()
    name_lower = name.lower()

    for f in db_dir.glob("*.yaml"):
        try:
            with f.open() as fh:
                data = yaml.safe_load(fh)
            if data and data.get("name", "").lower() == name_lower:
                return data
        except (yaml.YAMLError, OSError):
            continue

    return None
