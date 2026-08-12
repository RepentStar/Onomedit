"""测试公共夹具与辅助。"""

import os
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
FAKE_EDITOR = TESTS_DIR / "fakeditor.py"


def fake_editor_cmd(mode: str = "exit", *args: str, python: str | None = None) -> str:
    """构造假编辑器命令字符串（等价于用户在 config set-editor 里写的内容）。"""
    exe = python or sys.executable
    parts = [exe, str(FAKE_EDITOR), mode, *args]
    return " ".join(f'"{p}"' if " " in p else p for p in parts)


@pytest.fixture
def fake_editor() -> str:
    """返回假编辑器命令工厂。"""
    return fake_editor_cmd


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """把配置/日志目录隔离到临时目录，避免污染用户真实配置。

    注意：只 setenv，不得再 delenv（否则隔离路径被删除，测试会读写真实配置）。
    """
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    else:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return tmp_path
