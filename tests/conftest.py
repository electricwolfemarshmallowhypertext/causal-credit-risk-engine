from __future__ import annotations

import os
from pathlib import Path
import tempfile

import pytest


@pytest.fixture(scope="session", autouse=True)
def _force_repo_local_tempdir() -> None:
    """
    Force tempfile usage into the repository so tests are writable in restricted
    Windows sandbox environments where %LOCALAPPDATA%\\Temp is not writable.
    """
    repo_root = Path(__file__).resolve().parents[1]
    temp_root = repo_root / ".tmp_pytest"
    temp_root.mkdir(parents=True, exist_ok=True)

    previous_temp = os.environ.get("TEMP")
    previous_tmp = os.environ.get("TMP")
    previous_tempdir = tempfile.tempdir

    os.environ["TEMP"] = str(temp_root)
    os.environ["TMP"] = str(temp_root)
    tempfile.tempdir = str(temp_root)
    try:
        yield
    finally:
        if previous_temp is None:
            os.environ.pop("TEMP", None)
        else:
            os.environ["TEMP"] = previous_temp

        if previous_tmp is None:
            os.environ.pop("TMP", None)
        else:
            os.environ["TMP"] = previous_tmp

        tempfile.tempdir = previous_tempdir
