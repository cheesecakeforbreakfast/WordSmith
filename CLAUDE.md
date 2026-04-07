# Wordsmith — Claude Code Context

## What this tool is
A targeted wordlist generator for professional pentesting use on Kali Linux.
It fingerprints a target's tech stack and produces wordlists for directory
busting tools like dirsearch and ffuf. It has no exploitation capability.

## Architecture decisions — do not change without discussion

### Three subcommands only: scan, build, db
- scan handles all live target interaction (recon + crawl combined)
- build is purely offline — it consumes a scan report and produces a wordlist
- db manages the local technology YAML database

### The scan report is the central contract
- Defined in schema/scan_report.json
- Every path entry must carry: value, source, confidence, and optionally technology
- No module should alter this schema without updating the JSON schema file
  and all modules that read or write it
- Source values are strictly: tech_db | js_scrape | crawl | header | robots | sitemap

### Provider abstraction
- scanner/providers/__init__.py defines the abstract base class TechProvider
- Adding a new tech detection API means adding one file to providers/
- The scanner must never import a concrete provider directly — always go
  through the base class interface

### Filter pipeline (builder/filters.py)
- Filters are individual functions, each taking a path string and returning
  bool (keep) or str (normalised value)
- Do not refactor into a monolithic filter function
- New filter rules are added to the pipeline list, not merged into existing functions

## Key constraints
- Python 3.10+ only
- Dependencies: requests, pyyaml, jsonschema, argparse, beautifulsoup4
- Do not add new dependencies without flagging it first
- All output goes to ~/.wordsmith/output/ unless overridden
- Sessions live in ~/.wordsmith/sessions/
- BeautifulSoup crawling does not handle JS-rendered content — this is a
  known limitation, do not attempt to paper over it silently

## What to do when uncertain
- If a change would affect the scan report schema, stop and ask
- If a change would merge two subcommands, stop and ask
- If a new dependency seems necessary, flag it before adding it

## Current development state
[ update this section as you go ]
- scan: complete (recon + crawl + provider abstraction)
- build: complete (confidence filter, dedup, dirsearch/ffuf/json formats)
- db: complete (list, validate, lookup; 15 technologies pre-seeded)
