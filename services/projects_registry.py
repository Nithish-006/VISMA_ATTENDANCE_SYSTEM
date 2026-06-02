"""Read-only access to the shared VISMA projects registry.

Another app (VISMA) owns the `projects` table in the `visma_financial` MySQL
database. This module is the single source of truth for the project dropdown:
it queries that table live and caches the result for a short window so the UI
always reflects the current registry without hammering the DB.

Canonical project value: the string "{id} - {stem_name}" (e.g. "655 - RCH").
That exact string is what gets stored on the attendance record.
"""
import threading
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from config import Config

# Lazily-created, process-wide engine to the read-only registry DB.
_engine = None
_engine_lock = threading.Lock()

# Cache state, guarded by _cache_lock. `data` is the last good list of project
# dicts; `ts` is the monotonic time it was fetched (0 means never).
_cache_lock = threading.Lock()
_cache = {"data": None, "ts": 0.0}

_QUERY = text("SELECT id, stem_name FROM projects ORDER BY id")


class ProjectsRegistryError(Exception):
    """Raised when the registry can't be reached and no cache is available."""


def canonical_value(project_id, stem_name):
    """Build the canonical "{id} - {stem_name}" string stored on records."""
    return f"{project_id} - {stem_name}"


def _get_engine():
    """Return (creating once) the read-only engine, or None if unconfigured."""
    global _engine
    if not Config.PROJECTS_DB_URL:
        return None
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                # pool_pre_ping recovers transparently from dropped connections
                # (the proxy may idle-close them between the ~60s polls).
                _engine = create_engine(
                    Config.PROJECTS_DB_URL,
                    pool_pre_ping=True,
                    pool_recycle=300,
                )
    return _engine


def _fetch_from_db():
    """Query the registry and return the list of project dicts. Raises on error."""
    engine = _get_engine()
    if engine is None:
        raise ProjectsRegistryError(
            "Projects registry DB is not configured (set PROJECTS_DB_* env vars)."
        )
    with engine.connect() as conn:
        rows = conn.execute(_QUERY).fetchall()
    return [
        {"id": row[0], "value": canonical_value(row[0], row[1])}
        for row in rows
    ]


def get_projects(force_refresh=False):
    """Return the current projects list, refreshing from the DB when stale.

    Returns a dict: {"projects": [...], "stale": bool}.
      - stale=False: the list is fresh (within the TTL or just refetched).
      - stale=True:  the DB was unreachable, so this is the last cached list.

    Raises ProjectsRegistryError only when the DB is unreachable AND there is
    no cached list to fall back to. Never falls back to free text.
    """
    ttl = Config.PROJECTS_CACHE_TTL
    now = time.monotonic()

    with _cache_lock:
        cached = _cache["data"]
        fresh = cached is not None and (now - _cache["ts"]) < ttl
        if fresh and not force_refresh:
            return {"projects": cached, "stale": False}

    # Cache miss/expired (or forced): try the DB outside the lock.
    try:
        data = _fetch_from_db()
    except (SQLAlchemyError, ProjectsRegistryError) as exc:
        with _cache_lock:
            if _cache["data"] is not None:
                # Serve the last known-good list rather than breaking the UI.
                return {"projects": _cache["data"], "stale": True}
        raise ProjectsRegistryError(str(exc))

    with _cache_lock:
        _cache["data"] = data
        _cache["ts"] = time.monotonic()
    return {"projects": data, "stale": False}
