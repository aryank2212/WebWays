"""On-disk configuration: settings.json, the local API token, and state directories."""
from __future__ import annotations

import json
import os
import secrets
import stat
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


IS_WINDOWS = sys.platform == "win32"


def default_config_dir() -> Path:
    """Settings, token, publisher key and resume data. Override with WEBWAYS_CONFIG_DIR.

    Windows: %LOCALAPPDATA%\\WebWays (per-user and not roamed, so resume data and secrets stay on this PC).
    Elsewhere: $XDG_CONFIG_HOME/webways or ~/.config/webways.
    """
    if os.environ.get("WEBWAYS_CONFIG_DIR"):
        return Path(os.environ["WEBWAYS_CONFIG_DIR"])
    if IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "WebWays"
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "webways"


def default_download_dir() -> Path:
    return Path.home() / "Downloads" / ("WebWays" if IS_WINDOWS else "webways")


def default_ui_dir() -> Path:
    """Where the built web UI lives: next to the source tree, or inside a PyInstaller bundle."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "ui" / "dist"
    return Path(__file__).resolve().parents[2] / "ui" / "dist"


def normalize_source_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("source must be an http(s) URL without credentials")
    return f"{parts.scheme}://{parts.netloc}{parts.path}".rstrip("/")


@dataclass
class Settings:
    download_dir: str = field(default_factory=lambda: str(default_download_dir()))
    listen_port: int = 6881
    encryption: str = "enabled"     # "enabled" = prefer encrypted, allow plain; "forced" = encrypted only
    download_limit: int = 0         # bytes/s, 0 = unlimited
    upload_limit: int = 0
    # Index sources. Empty on first run: the software ships with no index and no default source.
    sources: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Settings":
        s = cls()
        if path.exists():
            for k, v in json.loads(path.read_text()).items():
                if hasattr(s, k):
                    setattr(s, k, v)
        return s

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2))
        tmp.replace(path)

    def validate(self) -> None:
        if self.encryption not in ("enabled", "forced"):
            raise ValueError("encryption must be 'enabled' or 'forced'")
        if not 0 <= self.listen_port <= 65535 or self.download_limit < 0 or self.upload_limit < 0:
            raise ValueError("invalid port or rate limit")


def load_token(config_dir: Path) -> str:
    path = config_dir / "token"
    if path.exists():
        return path.read_text().strip()
    config_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w") as fh:
        fh.write(token + "\n")
    return token
