"""Test setup: point the app at a throwaway database.

pytest runs this file before it imports the tests (and therefore main.py),
so main.py picks up this DATABASE_URL and your real database.db is never touched.
"""

import os
import tempfile
from pathlib import Path

TEST_DB = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
