"""
moodle_sync.py — Sync Moodle course materials to local folders.

Config: moodle_sync.json (copy from moodle_sync.json.example).

Auth — two modes, set per site in the config:
  token:        Moodle web service token (wstoken). Get it from
                Moodle → avatar → Preferences → Security keys.
  cookies_file: Netscape cookies file exported from your browser
                (e.g. via "Get cookies.txt LOCALLY" extension).
                Re-export when sync fails with a 401/redirect-to-login.

Files land flat in each course's sync folder as:
  WEEK-<n>_<filename>     for weekly sections
  GENERAL_<filename>      for section 0 (announcements / general)

Sync behaviour:
  - New files are downloaded.
  - Existing files are re-downloaded if Moodle reports a newer
    timemodified timestamp or a different filesize.
  - Otherwise the file is skipped (no network request).
  - State is tracked in .moodle_sync_meta.json inside each sync folder.
"""

import json
import logging
import re
import sys
from pathlib import Path

import requests
import urllib3

CONFIG_FILE = "moodle_sync.json"
META_FILENAME = ".moodle_sync_meta.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("moodle-sync")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config() -> dict:
    path = Path(CONFIG_FILE)
    if not path.exists():
        log.error(
            "Config not found: %s\n"
            "  → Copy moodle_sync.json.example to moodle_sync.json and fill in your details.",
            CONFIG_FILE,
        )
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def load_cookies(cookies_file: str, verify_ssl: bool = True) -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (moodle-sync/1.0)"
    session.verify = verify_ssl
    with open(cookies_file, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, _, path, _secure, expiry_str, name, value = parts[:7]
            try:
                expiry = int(expiry_str) if expiry_str else 0
            except ValueError:
                expiry = 0
            session.cookies.set(name, value, domain=domain.lstrip("."), path=path)
    return session


def get_sesskey(session: requests.Session, base_url: str, course_id: int) -> str:
    """Extract Moodle sesskey from any course page (needed for AJAX calls)."""
    resp = session.get(f"{base_url}/course/view.php", params={"id": course_id})
    if resp.status_code == 401 or "login/index" in resp.url:
        log.error(
            "Authentication failed — cookies may have expired.\n"
            "  → Re-export cookies from your browser and replace the cookies file."
        )
        sys.exit(1)
    match = re.search(r'"sesskey"\s*:\s*"([^"]+)"', resp.text)
    if not match:
        match = re.search(r'[?&]sesskey=([a-zA-Z0-9]+)', resp.text)
    if not match:
        log.error("Could not extract sesskey from Moodle page — are you logged in?")
        sys.exit(1)
    return match.group(1)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_token(session: requests.Session, base_url: str, token: str, function: str, **params):
    """Call Moodle REST API with a wstoken."""
    resp = session.get(
        f"{base_url}/webservice/rest/server.php",
        params={
            "wstoken": token,
            "wsfunction": function,
            "moodlewsrestformat": "json",
            **params,
        },
    )
    if resp.status_code == 401:
        log.error("Authentication failed (401) — check your token for %s", base_url)
        sys.exit(1)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("exception"):
        raise RuntimeError(f"Moodle API: {data.get('message', data)}")
    return data


def api_cookie(session: requests.Session, base_url: str, sesskey: str, methodname: str, **args):
    """Call Moodle AJAX service with session cookies."""
    resp = session.post(
        f"{base_url}/lib/ajax/service.php",
        params={"sesskey": sesskey, "info": methodname},
        json=[{"index": 0, "methodname": methodname, "args": args}],
        headers={"Content-Type": "application/json"},
    )
    resp.raise_for_status()
    results = resp.json()
    if results[0].get("error"):
        msg = results[0].get("data", {}).get("message", str(results[0]))
        raise RuntimeError(f"Moodle AJAX error: {msg}")
    return results[0]["data"]


# ---------------------------------------------------------------------------
# Sync helpers
# ---------------------------------------------------------------------------

def safe_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name.strip(". ")


def load_meta(sync_path: Path) -> dict:
    meta_file = sync_path / META_FILENAME
    if meta_file.exists():
        try:
            return json.loads(meta_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_meta(sync_path: Path, meta: dict):
    (sync_path / META_FILENAME).write_text(json.dumps(meta, indent=2), encoding="utf-8")


def needs_download(dest: Path, timemodified: int, filesize: int, meta: dict) -> bool:
    if not dest.exists():
        return True
    cached = meta.get(dest.name, {})
    return cached.get("timemodified") != timemodified or cached.get("filesize") != filesize


def download_file(
    session: requests.Session,
    file_url: str,
    dest: Path,
    token: str | None,
    timemodified: int,
    filesize: int,
    meta: dict,
) -> bool:
    if not needs_download(dest, timemodified, filesize, meta):
        log.info("  skip  %s", dest.name)
        return False

    action = "↺" if dest.exists() else "↓"
    log.info("  %s     %s", action, dest.name)

    # Token auth: append token to URL. Cookie auth: session handles it.
    if token and "token=" not in file_url:
        dl_url = f"{file_url}?token={token}"
    else:
        dl_url = file_url

    with session.get(dl_url, stream=True) as resp:
        if resp.status_code in (403, 404):
            log.warning("  access denied or not found: %s", dest.name)
            return False
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                fh.write(chunk)

    meta[dest.name] = {"timemodified": timemodified, "filesize": filesize}
    return True


def save_shortcut(dest: Path, url: str) -> bool:
    if dest.exists():
        log.info("  skip  %s", dest.name)
        return False
    dest.write_text(f"[InternetShortcut]\nURL={url}\n", encoding="utf-8")
    log.info("  link  %s", dest.name)
    return True


# ---------------------------------------------------------------------------
# Sync logic
# ---------------------------------------------------------------------------

def sync_course(
    session: requests.Session,
    base_url: str,
    token: str | None,
    sesskey: str | None,
    course_id: int,
    sync_path: Path,
):
    sync_path.mkdir(parents=True, exist_ok=True)
    meta = load_meta(sync_path)

    if token:
        sections = api_token(session, base_url, token, "core_course_get_contents", courseid=course_id)
    else:
        sections = api_cookie(session, base_url, sesskey, "core_course_get_contents", courseid=course_id)

    for section in sections:
        sec_num = section.get("section", 0)
        sec_name = section.get("name", f"Section {sec_num}")
        modules = section.get("modules", [])
        if not modules:
            continue

        prefix = "GENERAL" if sec_num == 0 else f"WEEK-{sec_num}"
        log.info("[%s — %s]", prefix, sec_name)

        for module in modules:
            modname = module.get("modname", "")
            title = safe_name(module.get("name", "untitled"))
            contents = module.get("contents", [])

            if modname in ("resource", "folder"):
                for content in contents:
                    if content.get("type") != "file":
                        continue
                    filename = safe_name(content.get("filename") or title)
                    dest = sync_path / f"{prefix}_{filename}"
                    download_file(
                        session,
                        content["fileurl"],
                        dest,
                        token,
                        content.get("timemodified", 0),
                        content.get("filesize", 0),
                        meta,
                    )

            elif modname == "url":
                ext_url = contents[0].get("fileurl", "") if contents else ""
                if not ext_url:
                    ext_url = module.get("url", f"{base_url}/mod/url/view.php?id={module['id']}")
                save_shortcut(sync_path / f"{prefix}_{title}.url", ext_url)

            elif modname == "page":
                save_shortcut(
                    sync_path / f"{prefix}_{title}.url",
                    f"{base_url}/mod/page/view.php?id={module['id']}",
                )

            elif modname in ("assign", "quiz", "forum", "choice", "feedback", "workshop"):
                view_url = module.get("url", f"{base_url}/course/view.php?id={course_id}")
                save_shortcut(sync_path / f"{prefix}_{title}.url", view_url)

            elif modname == "label":
                pass  # inline text, nothing to save

            else:
                view_url = module.get("url", "")
                if view_url:
                    save_shortcut(sync_path / f"{prefix}_{title}.url", view_url)

    save_meta(sync_path, meta)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    config = load_config()

    for site in config.get("sites", []):
        base_url = site["url"].rstrip("/")
        log.info("=== %s ===", site.get("name", base_url))

        token = site.get("token")
        cookies_file = site.get("cookies_file")

        if not token and not cookies_file:
            log.error("Site %s has neither 'token' nor 'cookies_file' — skipping.", base_url)
            continue

        verify_ssl = site.get("verify_ssl", True)
        if not verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        if cookies_file:
            if not Path(cookies_file).exists():
                log.error(
                    "Cookies file not found: %s\n"
                    "  → Export cookies from your browser and save as %s",
                    cookies_file, cookies_file,
                )
                continue
            session = load_cookies(cookies_file, verify_ssl=verify_ssl)
        else:
            session = requests.Session()
            session.headers["User-Agent"] = "Mozilla/5.0 (moodle-sync/1.0)"
            session.verify = verify_ssl

        for course in site.get("courses", []):
            course_id = int(course["id"])
            sync_path = Path(course["sync_path"])
            log.info("Course: %s → %s", course.get("name", course_id), sync_path)

            sesskey = None
            if cookies_file:
                sesskey = get_sesskey(session, base_url, course_id)

            try:
                sync_course(session, base_url, token, sesskey, course_id, sync_path)
            except Exception as exc:
                log.error("Failed syncing course %s: %s", course_id, exc)

    log.info("All done.")


if __name__ == "__main__":
    main()
