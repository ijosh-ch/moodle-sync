# CLAUDE.md — Project context for AI assistants

## What this repo is

A fork of [C0D3D3V/Moodle-DL](https://github.com/C0D3D3V/Moodle-DL) maintained by **ijosh-ch**, extended with:

- `canvas_sync.py` — syncs NTU COOL (Canvas LMS) course content into flat `WEEK-<n>_<filename>` files
- `moodle_sync.py` — syncs Moodle courses (multi-site, cookie or token auth) into flat `WEEK-<n>_<filename>` files
- `.env`-driven configuration for Canvas; JSON config (`moodle_sync.json`) for Moodle
- Security fix: `log_response()` now censors `wstoken`, `password`, `privatetoken` before writing to disk

## Owner context

- University: NTU (National Taiwan University) / NTUST
- Active Canvas course: `cool.ntu.edu.tw/courses/57552` — Academic Writing (114 Spring)
  - Sync target: `/Users/ijosh/Library/CloudStorage/OneDrive-國立臺灣科技大學/Courses/114 Spring/NTU - Academic Writing/Moodle`
- Active Moodle course: `moodle2.ntust.edu.tw/course/view.php?id=18505` — LLM and Applications (114 Spring)
  - Sync target: `/Users/ijosh/Library/CloudStorage/OneDrive-國立臺灣科技大學/Courses/114 Spring/LLM and Applications/Moodle`

## Project structure

```text
canvas_sync.py            — Canvas LMS sync (NTU COOL)
moodle_sync.py            — Moodle sync script (multi-site)
moodle_sync.json          — Live Moodle config (gitignored, never commit)
moodle_sync.json.example  — Config template (committed)
moodle_dl/                — Original Moodle-DL Python package (kept intact)
.env                      — Canvas config (gitignored, never commit)
.env.example              — Canvas config template
*_cookies.txt             — Browser session cookies (gitignored, never commit)
.venv/                    — Python 3.13 venv, prompt: (moodle-sync)
```

## Environment / runtime

- Python 3.13 via `.venv`
- Activate: `source .venv/bin/activate`
- Dependencies: `requests`, `python-dotenv`, `beautifulsoup4` (in `.venv`)
- Run Canvas sync: `python canvas_sync.py`
- Run Moodle sync: `python moodle_sync.py`

## Key env vars — Canvas (in `.env`, never commit)

| Var | Purpose |
| --- | --- |
| `CANVAS_URL` | Canvas instance base URL |
| `CANVAS_COURSE_ID` | Numeric course ID from URL |
| `CANVAS_SYNC_PATH` | Absolute path to sync destination |
| `CANVAS_COOKIES_FILE` | Path to Netscape-format cookies file |

## Moodle sync config (`moodle_sync.json`)

Structured as a list of sites, each with courses. Supports two auth modes per site:

```json
{
  "sites": [
    {
      "name": "NTUST Moodle",
      "url": "https://moodle2.ntust.edu.tw",
      "cookies_file": "moodle2.ntust.edu.tw_cookies.txt",
      "verify_ssl": false,
      "courses": [
        {
          "id": 18505,
          "name": "LLM and Applications",
          "sync_path": "/absolute/path/to/folder"
        }
      ]
    }
  ]
}
```

| Field | Purpose |
| --- | --- |
| `token` | Moodle web service token (wstoken) — get from Moodle → Preferences → Security keys |
| `cookies_file` | Netscape cookies file exported from browser (use if no token access) |
| `verify_ssl` | Set `false` for institutional servers with broken/self-signed certs (default: `true`) |

Exactly one of `token` or `cookies_file` must be present per site.

## Authentication model

**Canvas:** browser session cookies only (student accounts have no token access).
Export via "Get cookies.txt LOCALLY" Chrome extension → `cool.ntu.edu.tw_cookies.txt`.
Cookies expire on logout; re-export when sync fails with 401.

**Moodle (token):** wstoken from Moodle → User menu → Preferences → Security keys.
Tokens are long-lived (do not expire unless revoked).

**Moodle (cookies):** same Netscape export approach as Canvas.
Script extracts the `sesskey` from the course page, then calls the Moodle AJAX service
(`/lib/ajax/service.php`) for course contents. Falls back to HTML scraping if the AJAX
web service is disabled on the Moodle instance.
Cookies expire on logout; re-export when sync fails.

## File naming conventions

Both scripts produce **flat output** — no subfolders per week:

| Prefix | Meaning |
| --- | --- |
| `WEEK-1_filename.pdf` | Section 1 (week 1) |
| `WEEK-2_filename.pdf` | Section 2 (week 2) |
| `GENERAL_filename.pdf` | Section 0 (announcements / general) — Moodle only |

External URLs, assignments, discussions → saved as `.url` shortcut files (`[InternetShortcut]` format, opens in any browser on macOS/Windows).
Pages → saved as `.url` shortcuts pointing to the live Moodle/Canvas page.

## Sync behaviour

- **Canvas:** skips files that already exist (idempotent; no server-side change detection).
- **Moodle (token auth):** compares `timemodified` + `filesize` from the API against a local
  cache (`.moodle_sync_meta.json` in each sync folder). Re-downloads if either differs.
- **Moodle (cookie auth):** compares `Last-Modified` + `Content-Length` HTTP headers against
  the same cache. Issues a HEAD request before each download to check for changes.
- Restricted/locked files log a warning and are skipped gracefully.

## Security rules — never break these

1. Never commit `.env`, `*.env`, `*_cookies.txt`, `.venv/`, `config.json`, `moodle_sync.json`
2. Always censor `wstoken`, `password`, `privatetoken` in any log output
3. Never pass credentials as CLI args in examples or scripts (use env vars or config files)
4. Always use HTTPS — only set `verify_ssl: false` in `moodle_sync.json` for known institutional
   servers with broken certs, and never globally

## Common tasks

```bash
# Activate venv
source .venv/bin/activate

# Run Canvas sync (NTU COOL)
python canvas_sync.py

# Run Moodle sync (all sites in moodle_sync.json)
python moodle_sync.py

# Run original Moodle-DL
moodle-dl --init        # first-time setup
moodle-dl               # download

# Install deps after changes to setup.py
pip install -e .
```

## What NOT to do

- Don't modify `moodle_dl/` internals unless fixing a specific bug — it's upstream code
- Don't add any cookies or config file to git even if git asks
- Don't store any plaintext passwords or tokens in any committed file
- Don't create per-week subfolders — both scripts output flat files with `WEEK-<n>_` prefixes
