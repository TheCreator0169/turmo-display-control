"""Update check (v0.3.4): what the About page's Update button does.

Nothing runs by itself: one HTTPS request to GitHub's public "latest release" address happens only when the user
presses the button. It sends nothing about the user or the PC. The installer is downloaded only from this project's
release address, and its SHA-256 must match the one published in the release's SHA256SUMS.txt (this catches a
corrupted download, not a hijacked account: code signing is what would).
"""
import hashlib
import json
import os
import re
import urllib.request

REPO = "TheCreator0169/turmo-display-control"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
SETUP_RE = re.compile(r"^TURMO-Setup-v\d+\.\d+\.\d+\.exe$")
TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?$")
SUMS_NAME = "SHA256SUMS.txt"
HEADERS = {"User-Agent": "TURMO-update-check", "Accept": "application/vnd.github+json"}


class UpdateError(Exception):
    """A readable reason why the check or the download could not finish."""


class Release:
    def __init__(self, tag, page, setup_name, setup_url, sums_url):
        self.tag, self.page = tag, page
        self.setup_name, self.setup_url, self.sums_url = setup_name, setup_url, sums_url

    def has_installer(self):
        return bool(self.setup_name and self.setup_url and self.sums_url)


def version_tuple(tag):
    """'v0.3.3' -> (0, 3, 3, 0); None when it is not a release tag."""
    m = TAG_RE.match(tag or "")
    return tuple(int(part or 0) for part in m.groups()) if m else None


def is_newer(latest_tag, current_tag):
    latest, current = version_tuple(latest_tag), version_tuple(current_tag)
    return latest is not None and current is not None and latest > current


def _own_url(url):
    return url if isinstance(url, str) and url.startswith(DOWNLOAD_PREFIX) else None


def fetch_latest(urlopen=urllib.request.urlopen, timeout=10):
    """The latest published release (never a draft or a pre-release: GitHub's `latest` skips them)."""
    try:
        with urlopen(urllib.request.Request(API, headers=HEADERS), timeout=timeout) as response:
            data = json.load(response)
    except Exception as e:
        raise UpdateError(f"GitHub did not answer ({e})") from e
    tag = data.get("tag_name", "")
    if version_tuple(tag) is None:
        raise UpdateError("the latest release has no version tag")
    assets = {a.get("name"): _own_url(a.get("browser_download_url")) for a in data.get("assets", [])}
    setup = next((name for name in assets if SETUP_RE.match(name or "")), None)
    return Release(tag, data.get("html_url", ""), setup, assets.get(setup), assets.get(SUMS_NAME))


def parse_sums(text, name):
    """The SHA-256 written for `name` in a SHA256SUMS.txt ('<hash> *<name>' or '<hash>  <name>'), else None."""
    for line in text.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1].lstrip("*").strip() == name and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            return parts[0].lower()
    return None


def fetch_checksum(release, urlopen=urllib.request.urlopen, timeout=15):
    try:
        with urlopen(urllib.request.Request(release.sums_url, headers=HEADERS), timeout=timeout) as response:
            text = response.read(65536).decode("utf-8", "replace")
    except Exception as e:
        raise UpdateError(f"the checksum file could not be read ({e})") from e
    digest = parse_sums(text, release.setup_name)
    if digest is None:
        raise UpdateError("the release has no checksum for its installer")
    return digest


def download(release, folder, expected, progress=None, urlopen=urllib.request.urlopen, timeout=20):
    """Download the installer into `folder`, check its SHA-256 against `expected`; return its path. A file that does not
    match is deleted, never kept. `progress(done, total)` is called while it downloads (from this thread)."""
    final = os.path.join(folder, release.setup_name)
    part = final + ".part"
    digest = hashlib.sha256()
    try:
        with urlopen(urllib.request.Request(release.setup_url, headers=HEADERS), timeout=timeout) as response, \
                open(part, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            for chunk in iter(lambda: response.read(1 << 20), b""):
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except Exception as e:
        _remove(part)
        raise UpdateError(f"the download failed ({e})") from e
    if digest.hexdigest() != expected:
        _remove(part)
        raise UpdateError("the download does not match its checksum and was deleted")
    os.replace(part, final)
    return final


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass  # ok: nothing was written yet, or it is already gone
