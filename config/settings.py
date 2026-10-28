"""Central configuration: paths, network limits and the news source list."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = PROJECT_ROOT / "config" / "news_sources.json"
APP_DIR_NAME = "AfricanPulseOasis"

REQUEST_TIMEOUT_SECONDS = 15
MAX_FEED_BYTES = 5 * 1024 * 1024
MAX_SUMMARY_CHARS = 600
USER_AGENT = "AfricanPulseOasis/0.1 (BOS Communications feed reader)"


class ConfigError(Exception):
    """Raised when the news source configuration is missing or invalid."""


@dataclass(frozen=True)
class FeedSource:
    name: str
    feed_url: str
    enabled: bool = True


def default_data_dir() -> Path:
    """Per user application data folder (%LOCALAPPDATA% on Windows)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_DIR_NAME


def get_database_path() -> Path:
    """Database location. APOASIS_DB_PATH overrides the default."""
    override = os.environ.get("APOASIS_DB_PATH")
    if override:
        return Path(override).expanduser()
    return default_data_dir() / "africanpulse.db"


def load_sources(path: Path = SOURCES_FILE) -> list[FeedSource]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise ConfigError(f"News source file not found: {path}")
    except json.JSONDecodeError as exc:
        raise ConfigError(f"News source file is not valid JSON: {exc}")

    entries = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ConfigError('News source file must contain a "sources" list.')

    sources: list[FeedSource] = []
    seen_urls: set[str] = set()
    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ConfigError(f"Source #{position} must be an object.")
        name = str(entry.get("name", "")).strip()
        url = str(entry.get("url", "")).strip()
        if not name or not url.lower().startswith(("http://", "https://")):
            raise ConfigError(f"Source #{position} needs a name and an http(s) url.")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        sources.append(FeedSource(name, url, bool(entry.get("enabled", True))))
    return sources


HOST = os.environ.get("APOASIS_HOST", "127.0.0.1")  # localhost only by default
PORT = int(os.environ.get("APOASIS_PORT", "5000"))


def allow_private_feeds() -> bool:
    """Feed URLs pointing at localhost or private networks are rejected unless enabled."""
    return os.environ.get("APOASIS_ALLOW_PRIVATE_FEEDS", "").strip() == "1"


def load_or_create_secret_key() -> str:
    """Session signing key from the environment, else a generated key kept beside the database."""
    env_key = os.environ.get("APOASIS_SECRET_KEY")
    if env_key:
        return env_key
    import secrets

    key_file = get_database_path().parent / "secret_key"
    try:
        if key_file.exists():
            return key_file.read_text(encoding="utf-8").strip()
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_hex(32)
        key_file.write_text(key, encoding="utf-8")
        return key
    except OSError:
        return secrets.token_hex(32)  # sessions then reset on restart
