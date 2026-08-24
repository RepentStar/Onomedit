"""共享外部编辑器 fixture：Python 等待状态机 oracle。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from conftest import fake_editor_cmd
from onomedit.core import editor, tempfile_mgr


FIXTURE_PATH = Path(__file__).parents[1] / "tests-rust" / "fixtures" / "editor.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _fixture()["split_cases"], ids=lambda case: case["name"])
def test_shared_editor_split_cases(case):
    assert editor.split_command(case["command"]) == case["expected"]


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


@pytest.mark.skipif(os.name != "nt", reason="Windows editor command compatibility")
@pytest.mark.parametrize(
    "case", _fixture()["windows_launch_cases"], ids=lambda case: case["name"]
)
def test_shared_windows_editor_command_cases(tmp_path, monkeypatch, case):
    edit_path = tmp_path / "names with spaces.txt"
    edit_path.write_text("line1\n", encoding="utf-8", newline="\n")
    original = tempfile_mgr.signature(edit_path)
    tools_dir = tmp_path / "editor tools"
    tools_dir.mkdir()
    script = tools_dir / f'{case["executable"]}.{case["extension"]}'
    script.write_text(
        '@echo off\r\necho saved>> "%~1"\r\n',
        encoding="utf-8",
    )

    if case["lookup"] == "direct":
        command = f'"{script}"'
    else:
        monkeypatch.setenv("PATH", str(tools_dir) + os.pathsep + os.environ["PATH"])
        monkeypatch.setenv("PATHEXT", case["pathext"])
        command = case["executable"]

    editor.launch_and_wait(command, edit_path, original, timeout=5)

    assert tempfile_mgr.changed(original, tempfile_mgr.signature(edit_path))
