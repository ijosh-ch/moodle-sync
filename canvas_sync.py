"""
canvas_sync.py — Download NTU COOL (Canvas) course content into week-based folders.

Authentication: browser cookies (no API token required).
  1. Log in to cool.ntu.edu.tw in Chrome/Firefox.
  2. Install the "Get cookies.txt LOCALLY" extension (Chrome) or
     "cookies.txt" extension (Firefox).
  3. Export cookies for cool.ntu.edu.tw → save as cookies.txt in this folder.
  4. Run:  .venv/bin/python canvas_sync.py

Configuration is read from .env (see .env.example).
"""

import os
import re
import sys
import logging
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CANVAS_URL = os.environ.get("CANVAS_URL", "").rstrip("/")
COURSE_ID  = os.environ.get("CANVAS_COURSE_ID", "")
SYNC_PATH  = os.environ.get("CANVAS_SYNC_PATH", "")
COOKIES_FILE = os.environ.get("CANVAS_COOKIES_FILE", "cookies.txt")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("canvas-sync")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def check_config():
    missing = [k for k, v in {
        "CANVAS_URL": CANVAS_URL,
        "CANVAS_COURSE_ID": COURSE_ID,
        "CANVAS_SYNC_PATH": SYNC_PATH,
    }.items() if not v]
    if missing:
        log.error("Missing required env vars: %s", ", ".join(missing))
        sys.exit(1)
    if not Path(COOKIES_FILE).exists():
        log.error(
            "Cookie file not found: %s\n"
            "  → Log in to %s in your browser, export cookies as\n"
            "    Netscape/cookies.txt format, and save it here.",
            COOKIES_FILE, CANVAS_URL,
        )
        sys.exit(1)


def make_session() -> requests.Session:
    session = requests.Session()
    # Parse the Netscape cookies file manually so session cookies (expiry=0)
    # are not skipped by MozillaCookieJar's strict loader.
    with open(COOKIES_FILE, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, _, path, secure, expiry_str, name, value = parts[:7]
            try:
                expiry = int(expiry_str) if expiry_str else 0
            except ValueError:
                expiry = 0
            session.cookies.set(
                name, value,
                domain=domain.lstrip("."),
                path=path,
            )
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (canvas-sync/1.0)",
        "Accept": "application/json",
    })
    return session


def get_all(session: requests.Session, url: str, params: dict = None) -> list:
    """Fetch every page of a paginated Canvas API endpoint."""
    results = []
    params = {**(params or {}), "per_page": 100}
    while url:
        resp = session.get(url, params=params)
        if resp.status_code == 401:
            log.error(
                "Authentication failed (HTTP 401). Your cookies may have expired.\n"
                "  → Re-export cookies from your browser and replace cookies.txt."
            )
            sys.exit(1)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "errors" in data:
            log.error("Canvas API error: %s", data["errors"])
            sys.exit(1)
        results.extend(data)
        # Follow Link: <...>; rel="next" pagination
        url = None
        params = {}
        for part in resp.headers.get("Link", "").split(","):
            part = part.strip()
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
    return results


def safe_name(name: str) -> str:
    """Strip characters that are invalid in file/folder names on macOS/Windows."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name.strip(". ")


def download_file(session: requests.Session, url: str, dest: Path):
    """Stream-download a file, skipping if it already exists."""
    if dest.exists():
        log.info("  skip  %s", dest.name)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    log.info("  ↓     %s", dest.name)
    with session.get(url, stream=True) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                fh.write(chunk)


def save_url_shortcut(dest: Path, target_url: str, title: str):
    """Save an external URL as a .url shortcut file (works on macOS/Windows)."""
    if dest.exists():
        log.info("  skip  %s", dest.name)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(f"[InternetShortcut]\nURL={target_url}\n", encoding="utf-8")
    log.info("  link  %s → %s", title, target_url)


# ---------------------------------------------------------------------------
# Main sync logic
# ---------------------------------------------------------------------------
def sync_course(session: requests.Session):
    base = f"{CANVAS_URL}/api/v1"
    course_path = Path(SYNC_PATH)
    course_path.mkdir(parents=True, exist_ok=True)

    # Fetch course info
    course = session.get(f"{base}/courses/{COURSE_ID}").json()
    course_name = course.get("name", f"Course {COURSE_ID}")
    log.info("Syncing course: %s", course_name)

    # Fetch all modules (one module = one week)
    modules = get_all(session, f"{base}/courses/{COURSE_ID}/modules")
    if not modules:
        log.warning("No modules found. The course may be unpublished or restricted.")
        return

    for idx, module in enumerate(modules, start=1):
        folder_name = safe_name(f"{idx:02d} - {module['name']}")
        module_path = course_path / folder_name
        module_path.mkdir(parents=True, exist_ok=True)
        log.info("[%s]", folder_name)

        items = get_all(session, f"{base}/courses/{COURSE_ID}/modules/{module['id']}/items")

        for item in items:
            item_type = item.get("type")
            title = safe_name(item.get("title", "untitled"))

            if item_type == "File":
                # Resolve the actual file download URL
                file_url = item.get("url")
                if not file_url:
                    continue
                file_info = session.get(file_url)
                if file_info.status_code != 200:
                    log.warning("  cannot fetch file info for %s", title)
                    continue
                fdata = file_info.json()
                dl_url = fdata.get("url", "")
                if not dl_url:
                    log.warning("  no download URL for %s (may be restricted)", title)
                    continue
                filename = safe_name(fdata.get("filename") or fdata.get("display_name") or title)
                download_file(session, dl_url, module_path / filename)

            elif item_type == "ExternalUrl":
                ext_url = item.get("external_url", "")
                dest = module_path / f"{title}.url"
                save_url_shortcut(dest, ext_url, title)

            elif item_type == "Page":
                page_url = item.get("url")
                if not page_url:
                    continue
                page_resp = session.get(f"{base}/courses/{COURSE_ID}/pages/{page_url}")
                if page_resp.status_code != 200:
                    continue
                page_body = page_resp.json().get("body") or ""
                dest = module_path / f"{title}.html"
                if not dest.exists():
                    dest.write_text(
                        f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
                        f"<title>{title}</title></head><body>{page_body}</body></html>",
                        encoding="utf-8",
                    )
                    log.info("  page  %s", title)
                else:
                    log.info("  skip  %s.html", title)

            else:
                # Assignment, Discussion, Quiz, SubHeader — save as shortcut
                content_id = item.get("content_id") or item.get("id")
                html_url = item.get("html_url") or f"{CANVAS_URL}/courses/{COURSE_ID}"
                dest = module_path / f"{title}.url"
                save_url_shortcut(dest, html_url, title)

    log.info("Sync complete → %s", SYNC_PATH)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    check_config()
    session = make_session()
    sync_course(session)
