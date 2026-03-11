from __future__ import annotations

import os
import pytest


@pytest.fixture
def trail_home(tmp_path):
    old = os.environ.get("TRAIL_HOME")
    os.environ["TRAIL_HOME"] = str(tmp_path)
    yield tmp_path
    if old is None:
        os.environ.pop("TRAIL_HOME", None)
    else:
        os.environ["TRAIL_HOME"] = old
