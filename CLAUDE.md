# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this tool is

A targeted wordlist generator for pentesting on Kali Linux. It fingerprints a target's tech stack and produces wordlists for directory busting tools like dirsearch and ffuf. It has no exploitation capability.

## Running the tool

```bash
python3 wordsmith.py scan <url> [--depth 2] [--provider none|builtwith|wappalyzer] [--session <name>] [--ignore-robots] [--dry-run]
python3 wordsmith.py build <report.json> [--format dirsearch|ffuf|json|prompt] [--confidence low|medium|high] [--output <file>]
python3 wordsmith.py db list
python3 wordsmith.py db validate
```

There are no tests and no build step. Install dependencies with:

```bash
pip3 install requests pyyaml jsonschema beautifulsoup4
```

External provider API keys are read from environment variables: `BUILTWITH_API_KEY`, `WAPPALYZER_API_KEY`.

## Architecture

Data flows in one direction: `scan` → JSON report → `build` → wordlist. These are strictly separate; `build` makes no network requests.

### scan

`wordsmith.py:cmd_scan` orchestrates three phases:
1. **Recon** (`scanner/recon.py`) — HEAD request for header tech detection, robots.txt, sitemap.xml
2. **Crawl** (`scanner/crawler.py`) — BFS link crawl using BeautifulSoup; extracts `<script src>` JS URLs and scrapes them for path strings, which are then passed through the JS filter pipeline in `builder/filters.py`
3. **Provider** (`scanner/providers/`) — optional external API call

Providers are loaded dynamically via `importlib.import_module(f"scanner.providers.{name}")` — the scanner never statically imports a concrete provider. Adding a provider means adding one file to `scanner/providers/` with a class named after the module (e.g. `builtwith.py` → class `Builtwith`), subclassing `TechProvider` from `scanner/providers/__init__.py`.

### scan report (central contract)

Written to `~/.wordsmith/output/<host>_<timestamp>.json`. Schema defined in `schema/scan_report.json`. Every path entry must have `value`, `source`, and `confidence`. Valid source values: `tech_db | js_scrape | crawl | header | robots | sitemap`. Do not change the schema without updating both the JSON schema file and all modules that read or write it.

### build

`builder/build.py:run_build` loads the report, validates it against the schema, looks up each detected technology in `db/technologies/`, merges in tech DB paths (source: `tech_db`), applies confidence filtering, deduplicates by `value` (first occurrence wins), then writes output.

The `--format prompt` output calls `builder/prompt_generator.py:format_llm_prompt`, which generates a context-aware LLM prompt. The two module-level constants to extend are `SITE_CONTEXT_HINTS` (regex → site type label) and `TECH_FOCUS_MAP` (regex → focus list). Both use regex pattern keys. `INFRASTRUCTURE_TECHNOLOGIES` maps infrastructure header names to the platform they indicate (e.g. `pepyaka` → Wix), which redirects the LLM away from guessing at header-specific paths.

### JS filter pipeline

`builder/filters.py` — individual filter functions, each `(s: str, base_url: str) -> bool`. Listed in `FILTER_PIPELINE`. New rules must be added as new functions to the list, not merged into existing ones.

### Tech DB

`db/technologies/` — one YAML per technology, validated against `schema/tech_entry.json`. `db/manager.py:lookup_technology` does case-insensitive name matching. 15 technologies pre-seeded.

### Sessions

`~/.wordsmith/sessions/<name>.yaml` — carries `cookies`, `headers`, and optionally `target`. Loaded into a `requests.Session` before scanning.

## Constraints — do not change without discussion

- Three subcommands only: `scan`, `build`, `db`. Do not merge or add subcommands.
- Dependencies: `requests`, `pyyaml`, `jsonschema`, `argparse`, `beautifulsoup4` only. Flag before adding anything new.
- `from __future__ import annotations` is in every file that uses `X | Y` union syntax — required for compatibility with Python 3.9 on the dev machine (target is 3.10+ on Kali).
- BeautifulSoup crawling does not execute JavaScript. This is a known limitation — do not silently work around it.
- If a change would affect the scan report schema or merge two subcommands, stop and ask first.
