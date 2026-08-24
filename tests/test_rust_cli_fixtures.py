"""共享 CLI golden 与文件系统 E2E 的 Python oracle。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


FIXTURE_PATH = Path(__file__).parents[1] / "tests-rust" / "fixtures" / "cli.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _run(args: list[str], config_root: Path, stdin: str | None = None):
    env = os.environ.copy()
    env["APPDATA"] = str(config_root)
    env["XDG_CONFIG_HOME"] = str(config_root)
    return subprocess.run(
        [sys.executable, "-m", "onomedit", *args],
        input=None if stdin is None else stdin.encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )


@pytest.mark.parametrize("case", _fixture()["cases"], ids=lambda case: case["name"])
def test_shared_cli_golden(tmp_path, case):
    result = _run(case["args"], tmp_path / "config", case.get("stdin"))
    expected_stdout = case.get("stdout_windows", case.get("stdout")) if os.name == "nt" else case.get("stdout")
    expected_stderr = case.get("stderr_windows", case.get("stderr")) if os.name == "nt" else case.get("stderr")
    stdout = result.stdout.decode("utf-8")
    stderr = result.stderr.decode("utf-8")
    assert result.returncode == case["exit_code"]
    if expected_stdout is not None:
        assert stdout == expected_stdout
    if expected_stderr is not None:
        assert stderr == expected_stderr
    for value in case.get("stdout_contains", []):
        assert value in stdout
    for value in case.get("stderr_contains", []):
        assert value in stderr


def test_python_cli_rename_history_restore_workflow(tmp_path):
    config_root = tmp_path / "config"
    source = tmp_path / "a.txt"
    renamed = tmp_path / "renamed.txt"
    source.write_text("payload", encoding="utf-8")

    settings = [
        ("open_editor", "false"),
        ("expand_subdirs", "false"),
        ("exclude.hidden", "false"),
        (
            "auto_rules",
            '[{"scope":"stem","kind":"replace","find":"a","replace":"renamed"}]',
        ),
    ]
    for key, value in settings:
        assert _run(["config", "set", key, value], config_root).returncode == 0

    renamed_result = _run(["rename", str(source), "--no-editor"], config_root)
    assert renamed_result.returncode == 0
    assert renamed_result.stdout.decode("utf-8").replace("\r\n", "\n") == (
        "重命名完成: 成功 1 / 失败 0 / 无变化 0 / 总计 1\n"
    )
    assert not source.exists() and renamed.read_text(encoding="utf-8") == "payload"

    history = _run(["history"], config_root)
    assert history.returncode == 0
    assert history.stdout.decode("utf-8").strip() == f"{source}<-->{renamed}"

    restored = _run(["restore"], config_root)
    assert restored.returncode == 0
    assert restored.stdout.decode("utf-8").replace("\r\n", "\n") == (
        "恢复完成: 成功 1 / 失败 0 / 无变化 0 / 总计 1\n"
    )
    assert source.read_text(encoding="utf-8") == "payload" and not renamed.exists()

    preview = _run(["rename", str(source), "--no-editor", "--dry-run"], config_root)
    assert preview.returncode == 0
    assert "（dry-run 预览，共 1 项，未执行）" in preview.stdout.decode("utf-8")
    assert source.exists() and not renamed.exists()
