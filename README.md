# WordSmith

A targeted wordlist generator for pentesting. WordSmith fingerprints a target site's tech stack and produces wordlists tuned to that stack for use with directory busting tools like [dirsearch](https://github.com/maurosoria/dirsearch) and [ffuf](https://github.com/ffuf/ffuf).

## How it works

```
wordsmith scan <url>   →   scan_report.json   →   wordsmith build   →   wordlist.txt
```

1. **scan** — hits the target, parses HTTP headers, robots.txt, and sitemap.xml, crawls links, and scrapes JS files for path strings. Produces a JSON report.
2. **build** — reads the report, looks up each detected technology in the local DB, merges all known paths, applies a confidence filter, deduplicates, and writes the wordlist.
3. **db** — inspects and validates the local technology database.

## Requirements

- Python 3.10+
- `pip install requests pyyaml jsonschema beautifulsoup4`

## Quickstart

```bash
# Scan a target
python wordsmith.py scan https://target.example.com

# Build a wordlist from the report
python wordsmith.py build ~/.wordsmith/output/<report>.json

# Use with dirsearch
dirsearch -u https://target.example.com -w ~/.wordsmith/output/<report>_wordlist.txt

# Use with ffuf
ffuf -u https://target.example.com/FUZZ -w ~/.wordsmith/output/<report>_wordlist.txt
```

## Commands

### `scan`

Fingerprints a target and writes a scan report to `~/.wordsmith/output/`.

```
python wordsmith.py scan <url> [options]
```

| Option | Description |
|---|---|
| `--session <name>` | Use a saved session (cookies/headers) for authenticated scanning |
| `--depth <int>` | Crawl depth (default: 3) |
| `--confidence <low\|medium\|high>` | Minimum confidence for included paths (default: low) |
| `--provider <builtwith\|wappalyzer\|none>` | External tech detection API (default: none) |
| `--ignore-robots` | Ignore robots.txt during crawl |
| `--dry-run` | Print what would be done without making any requests |

**Examples**

```bash
# Basic scan
python wordsmith.py scan https://target.example.com

# Authenticated scan using a saved session
python wordsmith.py scan https://target.example.com --session admin

# Deep scan with BuiltWith tech detection
python wordsmith.py scan https://target.example.com --depth 5 --provider builtwith

# Preview without sending requests
python wordsmith.py scan https://target.example.com --dry-run
```

### `build`

Builds a wordlist from a scan report. Purely offline — no network requests.

```
python wordsmith.py build <scan_report.json> [options]
```

| Option | Description |
|---|---|
| `--confidence <low\|medium\|high>` | Minimum confidence to include (default: low) |
| `--output <file>` | Output path (default: `~/.wordsmith/output/<stem>_wordlist.txt`) |
| `--format <dirsearch\|ffuf\|json>` | Output format (default: dirsearch) |

**Confidence levels**

| Level | Includes |
|---|---|
| `low` | All paths |
| `medium` | Medium and high confidence paths |
| `high` | High confidence paths only |

**Examples**

```bash
# Default output (dirsearch format, all confidence levels)
python wordsmith.py build ~/.wordsmith/output/target_20240101T120000Z.json

# High confidence only, ffuf format
python wordsmith.py build report.json --confidence high --format ffuf

# Full metadata as JSON
python wordsmith.py build report.json --format json --output paths.json
```

### `db`

Manage the local technology database.

```bash
# List all technologies in the database
python wordsmith.py db list

# Validate all technology YAML files against the schema
python wordsmith.py db validate
```

## Sessions

Sessions let you scan authenticated targets by supplying cookies and custom headers. Session files live in `~/.wordsmith/sessions/<name>.yaml`.

```yaml
# ~/.wordsmith/sessions/admin.yaml
name: admin
target: https://target.example.com
cookies:
  session: abc123
  remember_token: xyz
headers:
  X-Auth-Token: supersecret
  Authorization: Bearer eyJ...
```

```bash
python wordsmith.py scan https://target.example.com --session admin
```

## External providers

WordSmith can call external APIs to improve technology detection. API keys are read from environment variables — never stored on disk.

| Provider | Env var |
|---|---|
| BuiltWith | `BUILTWITH_API_KEY` |
| Wappalyzer | `WAPPALYZER_API_KEY` |

```bash
export BUILTWITH_API_KEY=your_key_here
python wordsmith.py scan https://target.example.com --provider builtwith
```

If a key is not set, the provider is skipped with a warning and the scan continues using header-based detection only.

## Technology database

The DB lives in `db/technologies/` — one YAML file per technology. WordSmith ships with entries for:

WordPress, Laravel, Django, Flask, Rails, Nginx, Apache, Tomcat, Jenkins, phpMyAdmin, Drupal, Joomla, Spring Boot, Express, ASP.NET

**Adding a technology**

Create a new YAML file following this format:

```yaml
name: MyFramework
paths:
  - value: admin/
    confidence: high
  - value: config.php
    confidence: high
  - value: changelog.txt
    confidence: medium
  - value: debug.log
    confidence: low
```

Run `python wordsmith.py db validate` to confirm it passes schema validation.

## Configuration

Default settings are in `config.yaml`:

```yaml
depth: 3                              # crawl depth
confidence: low                       # minimum confidence for build output
output_dir: ~/.wordsmith/output/
sessions_dir: ~/.wordsmith/sessions/
user_agent: "Mozilla/5.0 (compatible; research)"
timeout: 10                           # HTTP request timeout in seconds
max_crawl_pages: 200                  # hard cap on pages crawled
provider: none                        # builtwith | wappalyzer | none
```

CLI flags always override config file values.

## Output formats

| Format | Description |
|---|---|
| `dirsearch` | Flat `.txt`, one path per line |
| `ffuf` | Flat `.txt`, one path per line (same as dirsearch) |
| `json` | Full path objects with `value`, `source`, `confidence`, and `technology` fields |

## Notes

- BeautifulSoup is used for crawling — JS-rendered content is not executed. Paths that only appear after JavaScript runs will not be discovered via crawling (they may still appear via JS source scraping).
- The crawler does not follow redirects to external domains.
- All HTTP errors and timeouts are logged and skipped — the scan will not crash on a single bad URL.
- robots.txt is respected by default. Use `--ignore-robots` to disable this.
