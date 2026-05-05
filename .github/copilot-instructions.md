# GitHub Copilot instructions for ijosh-ch/moodle-sync

## Project summary

This repo has two tools:
1. `canvas_sync.py` — syncs NTU COOL (Canvas LMS) course files into local week-based folders using browser cookies
2. `moodle_dl/` — the original Moodle-DL downloader (Moodle Mobile API)

Owner is a student at NTU/NTUST. Config lives in `.env` (gitignored).

## Code style

- Python 3.13, line length 120 (black), `snake_case` everywhere
- No type annotations needed on new code unless the surrounding code already has them
- Prefer `pathlib.Path` over `os.path` for new file operations
- Log with `logging` module, not `print`

## Security — always enforce

- `wstoken`, `password`, `privatetoken` must be censored to `'censored'` before any log/file write
- Credentials come from `.env` only — never hardcode, never pass as CLI args in generated examples
- All HTTP requests must use HTTPS
- `.env`, `*_cookies.txt`, `config.json` are gitignored — never suggest adding them to git

## canvas_sync.py conventions

- Sync is idempotent: skip files that already exist on disk
- Folder names: `{idx:02d} - {module_name}` (zero-padded index)
- Filenames sanitised with `safe_name()` — strips `<>:"/\|?*` and control chars
- Auth: Netscape cookies file parsed manually (not `MozillaCookieJar`) to handle session cookies with expiry=0
- On 401: tell user to re-export cookies, then `sys.exit(1)`

## Environment

- venv at `.venv/`, prompt `(moodle-sync)`
- Activate: `source .venv/bin/activate`
- Run: `python canvas_sync.py`
