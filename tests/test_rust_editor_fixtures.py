"""共享外部编辑器 fixture：Python 等待状态机 oracle。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import fake_editor_cmd
from onomedit.core import editor, tempfile_mgr


FIXTURE_PATH = Path(__file__).parents[1] / "tests-rust" / "fixtures" / "editor.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _fixture()["launch_cases"], ids=lambda case: case["name"])
def test_shared_editor_launch_cases(tmp_path, case):
    edit_path = tmp_path / "names.txt"
    edit_path.write_text(case["initial"], encoding="utf-8", newline="\n")
    original = tempfile_mgr.signature(edit_path)
    statuses = []
    command = fake_editor_cmd(case["mode"], *case.get("args", []))

    editor.launch_and_wait(
        command,
        edit_path,
        original,
        multi_tab=case["multi_tab"],
        timeout=case["timeout_ms"] / 1000,
        on_status=statuses.append,
    )

    changed = tempfile_mgr.changed(original, tempfile_mgr.signature(edit_path))
    assert changed is case["expected_changed"]
    if "expected_content" in case:
        assert edit_path.read_text(encoding="utf-8") == case["expected_content"]
    for fragment in case["expected_status_contains"]:
        assert any(fragment in status for status in statuses)
