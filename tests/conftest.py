import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def make_tree(tmp_path):
    """Build a file tree under tmp_path from a {relative_path: content} mapping."""

    def _make(files: dict[str, str]) -> Path:
        for rel, content in files.items():
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return tmp_path

    return _make
