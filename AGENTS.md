# AGENTS.md — Agent instructions for this repository

## Identity

Repo: `ijosh-ch/moodle-sync` (GitHub)  
Owner: ijosh-ch (student, NTU/NTUST)  
Primary tool: `canvas_sync.py` — downloads NTU COOL course files into OneDrive

## Before you do anything

1. Read `CLAUDE.md` for full project context
2. Check `.env.example` to understand all config keys
3. Run `source .venv/bin/activate` before any Python commands

## Absolute rules

- **Never commit** `.env`, `*_cookies.txt`, `config.json`, `.venv/`
- **Never log credentials** — `wstoken`, `password`, `privatetoken` must always be censored
- **Never use HTTP** for Moodle/Canvas requests
- **Always run** `git check-ignore -v <file>` before committing any sensitive-looking file

## How to run the sync

```bash
cd /Users/ijosh/Documents/GitHub/ijosh-Moodle-DL
source .venv/bin/activate
python canvas_sync.py
```

## How to install/update dependencies

```bash
source .venv/bin/activate
pip install -e .                  # installs moodle-dl package
pip install requests python-dotenv  # canvas_sync.py deps
```

## Testing a change to canvas_sync.py

There are no automated tests. Verify manually:
1. Run `python canvas_sync.py`
2. Check that previously downloaded files show `skip` (idempotency)
3. Check that no credentials appear in terminal output

## Repo layout cheat-sheet

```
canvas_sync.py      ← touch this for Canvas-related changes
moodle_dl/main.py   ← touch this for CLI/Moodle-DL changes
moodle_dl/moodle/request_helper.py  ← network + credential handling
.env                ← local secrets (gitignored)
.env.example        ← committed template
CLAUDE.md           ← full project context
```
