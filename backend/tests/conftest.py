"""Test bootstrap.

Points the app at a throwaway SQLite file *before* `app.config` is imported, so
running the suite never touches the development database. Must stay import-order
sensitive: nothing from `app.*` may be imported above the env assignment.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP_DB = Path(tempfile.gettempdir()) / "aivoa_test.db"
_TMP_DB.unlink(missing_ok=True)

os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_TMP_DB.as_posix()}"
# Force the deterministic path so the suite needs no network and no secrets.
os.environ["GROQ_API_KEY"] = ""


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    from app.db.session import engine

    engine.dispose()
    _TMP_DB.unlink(missing_ok=True)
