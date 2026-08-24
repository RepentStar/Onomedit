"""编辑器等待策略：单实例/启动器型/多标签/超时/命令解析。"""

import os
import sys
import threading

import pytest

from onomedit.core import editor, tempfile_mgr
from conftest import fake_editor_cmd


def _write(tmp_path, name="names.txt", content="line1\n"):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8", newline="\n")
    return p


def test_split_command_plain():
    assert editor.split_command("notepad") == ["notepad"]
    assert editor.split_command("code -w") == ["code", "-w"]


def test_split_command_empty_raises():
    with pytest.raises(editor.EditorError):
        editor.split_command("   ")


def test_editor_not_found(tmp_path):
    p = _write(tmp_path)
    sig = tempfile_mgr.signature(p)
    with pytest.raises(editor.EditorError):
        editor.launch_and_wait("definitely_not_a_real_editor_xyz", p, sig, timeout=0.5)


@pytest.mark.skipif(os.name != "nt", reason="Windows 专属：.cmd 批处理启动")
def test_batch_file_editor_launches(tmp_path):
    """Windows：code 等 .cmd 批处理须经 cmd /c 启动（WinError 2 回归）。

    直接 CreateProcess 无法执行 .cmd/.bat（[WinError 2] 系统找不到指定的文件），
    但用户在终端手动执行没问题——必须回退 shell 启动。
    """
    p = _write(tmp_path)
    sig = tempfile_mgr.signature(p)
    batch = tmp_path / "fake_code.cmd"
    batch.write_text(
        "@echo off\r\necho saved>> %1\r\n",
        encoding="utf-8",
    )
    editor.launch_and_wait(str(batch), p, sig, timeout=5)
    assert tempfile_mgr.changed(sig, tempfile_mgr.signature(p))


def test_save_editor_exits_after_modify(tmp_path):
    """单实例型：编辑器修改文件后退出 → 正常继续。"""
    p = _write(tmp_path)
    sig = tempfile_mgr.signature(p)
    cmd = fake_editor_cmd("save")
    editor.launch_and_wait(cmd, p, sig, timeout=5)
    assert tempfile_mgr.changed(sig, tempfile_mgr.signature(p))


def test_launcher_type_triggers_poll_and_save(tmp_path):
    """启动器型：立即退出且文件未改 → 轮询等待保存。"""
    p = _write(tmp_path)
    sig = tempfile_mgr.signature(p)

    def modify_later():
        import time

        time.sleep(0.4)
        with open(p, "a", encoding="utf-8") as f:
            f.write("saved")

    threading.Thread(target=modify_later, daemon=True).start()
    cmd = fake_editor_cmd("launcher")
    editor.launch_and_wait(cmd, p, sig, timeout=5)
    assert tempfile_mgr.changed(sig, tempfile_mgr.signature(p))  # 轮询捕获保存


def test_launcher_type_timeout_continues(tmp_path):
    """启动器型超时：轮询等待超时后继续（不抛异常）。"""
    p = _write(tmp_path)
    sig = tempfile_mgr.signature(p)
    cmd = fake_editor_cmd("launcher")  # 退出且不改文件
    statuses = []
    editor.launch_and_wait(cmd, p, sig, timeout=0.8, on_status=statuses.append)
    assert any("启动器" in s for s in statuses)
    assert any("超时" in s for s in statuses)


def test_running_editor_timeout_continues(tmp_path):
    """编辑器进程持续存活：达到总等待超时后按当前内容继续。"""
    p = _write(tmp_path)
    sig = tempfile_mgr.signature(p)
    statuses = []
    cmd = fake_editor_cmd("sleep", "0.5")

    editor.launch_and_wait(cmd, p, sig, timeout=0.15, on_status=statuses.append)

    assert not tempfile_mgr.changed(sig, tempfile_mgr.signature(p))
    assert any("等待编辑器超时" in status for status in statuses)


def test_multi_tab_polls_save(tmp_path):
    """多标签型：不依赖进程退出，直接轮询等待保存。"""
    p = _write(tmp_path)
    sig = tempfile_mgr.signature(p)
    cmd = fake_editor_cmd("delay", "0.3")  # 0.3s 后保存
    editor.launch_and_wait(cmd, p, sig, multi_tab=True, timeout=5)
    assert tempfile_mgr.changed(sig, tempfile_mgr.signature(p))


def test_multi_tab_timeout_continues(tmp_path):
    p = _write(tmp_path)
    sig = tempfile_mgr.signature(p)
    cmd = fake_editor_cmd("launcher")
    editor.launch_and_wait(cmd, p, sig, multi_tab=True, timeout=0.5)
    # 不抛异常即通过


def test_status_callback_receives_messages(tmp_path):
    p = _write(tmp_path)
    sig = tempfile_mgr.signature(p)
    messages = []
    cmd = fake_editor_cmd("launcher")
    editor.launch_and_wait(cmd, p, sig, multi_tab=True, timeout=0.5, on_status=messages.append)
    assert messages  # 多标签模式启动时有状态提示
