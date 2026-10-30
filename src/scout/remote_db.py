"""Fetch the listings DB that the daily workflow publishes to the repo's ``data`` branch.

The app keeps a local SQLite copy and re-downloads it when it is older than ``MAX_AGE_S``.
Does nothing when ``DATABASE_URL`` is set (an external DB wins) and never raises: a failed
download leaves the existing local copy in place.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import requests

from .config import REPO_ROOT, get_settings

logger = logging.getLogger(__name__)

REPO = os.environ.get("DATA_REPO", "Am015-dev/Test")
URL = f"https://raw.githubusercontent.com/{REPO}/data/listings.db"
MAX_AGE_S = 6 * 3600


def ensure_local_db(max_age_s: int = MAX_AGE_S, url: str = URL) -> bool:
    """Download the published DB if the local copy is missing or stale. True if refreshed."""
    s = get_settings()
    if s.database_url:
        return False
    path = Path(s.db_path)
    if not path.is_absolute():
        path = REPO_ROOT / path
    if path.exists() and time.time() - path.stat().st_mtime < max_age_s:
        return False
    try:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".download")
        tmp.write_bytes(r.content)
        os.replace(tmp, path)
    except Exception as e:  # no data branch yet, offline, ...: keep whatever we have
        logger.warning("data download failed: %s", e)
        return False
    from . import db

    if db._engine is not None:
        db._engine.dispose()  # drop pooled connections to the replaced file
    return True
