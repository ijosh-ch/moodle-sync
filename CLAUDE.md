# CLAUDE.md — Project context for AI assistants

## What this repo is

A fork of [C0D3D3V/Moodle-DL](https://github.com/C0D3D3V/Moodle-DL) maintained by **ijosh-ch**, extended with:
- `canvas_sync.py` — syncs NTU COOL (Canvas LMS) course content into local week-based folders
- `.env`-driven configuration (no credentials on the CLI)
- Security fix: `log_response()` now censors `wstoken`, `password`, `privatetoken` before writing to disk

## Owner context

- University: NTU (National Taiwan University) / NTUST
- Active course synced: `cool.ntu.edu.tw/courses/57552` — Academic Writing (114 Spring)
- Sync target: `/Users/ijosh/Library/CloudStorage/OneDrive-國立臺灣科技大學/Courses/114 Spring/NTU - Academic Writing/Moodle`

## Project structure

```
canvas_sync.py          — Main Canvas sync script (the primary tool)
moodle_dl/              — Original Moodle-DL Python package (kept intact)
.env                    — Local config (gitignored, never commit)
.env.example            — Template to copy from
*_cookies.txt           — Browser session cookies (gitignored, never commit)
.venv/                  — Python 3.13 venv, prompt: (moodle-sync)
```

## Environment / runtime

- Python 3.13 via `.venv`
- Activate: `source .venv/bin/activate`
- Dependencies: `requests`, `python-dotenv` (in `.venv`)
- Run sync: `python canvas_sync.py`

## Key env vars (in `.env`, never commit)

| Var | Purpose |
|---|---|
| `CANVAS_URL` | Canvas instance base URL |
| `CANVAS_COURSE_ID` | Numeric course ID from URL |
| `CANVAS_SYNC_PATH` | Absolute path to sync destination |
| `CANVAS_COOKIES_FILE` | Path to Netscape-format cookies file |
| `MOODLE_SYNC_PATH` | Path for original Moodle-DL downloads |
| `MOODLE_TOKEN` | Moodle API token (optional) |
| `MOODLE_USERNAME` / `MOODLE_PASSWORD` | Moodle credentials (optional, headless only) |

## Authentication model

Canvas uses **browser session cookies** (no API token — student accounts don't have token generation access).  
Export cookies from Chrome via "Get cookies.txt LOCALLY" extension → save as `cool.ntu.edu.tw_cookies.txt`.  
Cookies expire on logout; re-export when sync fails with 401.

## Security rules — never break these

1. Never commit `.env`, `*.env`, `*_cookies.txt`, `.venv/`, `config.json`
2. Always censor `wstoken`, `password`, `privatetoken` in any log output
3. Never pass credentials as CLI args in examples or scripts (use env vars)
4. Always use HTTPS — do not set `use_http=True` or `skip_cert_verify=True` unless explicitly asked

## Canvas sync behaviour

- One folder per module (week): `01 - Week 1 - 02_24/`, `02 - Week 2 - 03_03/`, …
- Files already present are **skipped** (idempotent — safe to re-run)
- Restricted/locked files log a warning and are skipped gracefully
- External URLs, assignments, discussions → saved as `.url` shortcut files
- Pages → saved as `.html` files

## Common tasks

```bash
# Activate venv
source .venv/bin/activate

# Run Canvas sync
python canvas_sync.py

# Run original Moodle-DL
moodle-dl --init        # first-time setup
moodle-dl               # download

# Install deps after changes to setup.py
pip install -e .
```

## What NOT to do

- Don't modify `moodle_dl/` internals unless fixing a specific bug — it's upstream code
- Don't add the cookies file to git even if git asks
- Don't store any plaintext passwords in any committed file
