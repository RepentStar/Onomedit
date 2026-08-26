"""剪贴板读取：文本路径解析（引号/空格/换行）、CF_HDROP 回读、Windows 回环。"""

import ctypes
import os
import struct

import pytest

from onomedit.utils import clipboard

CF_HDROP = 15


def test_parse_quoted_paths_with_spaces():
    text = '"C:\\a b\\x.txt" "C:\\d\\y.txt"'
    assert clipboard._parse_path_text(text) == ["C:\\a b\\x.txt", "C:\\d\\y.txt"]


def test_parse_newline_separated():
    assert clipboard._parse_path_text("C:\\a\\b\nC:\\c\\d") == ["C:\\a\\b", "C:\\c\\d"]


def test_parse_mixed_quoted_and_plain():
    assert clipboard._parse_path_text('C:\\a "C:\\b c\\d"') == ["C:\\a", "C:\\b c\\d"]


def test_parse_backslash_not_escaped():
    # 无引号路径的反斜杠不能被转义（shlex posix=True 的坑）
    assert clipboard._parse_path_text("C:\\plain\\nofile.txt") == [
        "C:\\plain\\nofile.txt"
    ]


def test_parse_single_quoted_path():
    assert clipboard._parse_path_text('"C:\\spaced dir\\f.txt"') == [
        "C:\\spaced dir\\f.txt"
    ]


def test_parse_blank_lines_ignored():
    assert clipboard._parse_path_text("  \nC:\\a\n\n") == ["C:\\a"]


def _clipboard_available() -> bool:
    """剪贴板是否可被当前进程独占（被其他进程占用时测试跳过）。"""
    user32 = ctypes.WinDLL("user32")
    ok = bool(user32.OpenClipboard(None))
    if ok:
        user32.CloseClipboard()
    return ok


def _set_hdrop_clipboard(paths: list[str]) -> None:
    """模拟资源管理器复制文件/文件夹：构造 DROPFILES 写入剪贴板。"""
    user32 = ctypes.WinDLL("user32")
    kernel32 = ctypes.WinDLL("kernel32")
    void_p = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = void_p
    kernel32.GlobalLock.argtypes = [void_p]
    kernel32.GlobalLock.restype = void_p
    kernel32.GlobalUnlock.argtypes = [void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    user32.SetClipboardData.argtypes = [ctypes.c_uint, void_p]
    user32.SetClipboardData.restype = void_p
    user32.OpenClipboard.argtypes = [void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.EmptyClipboard.restype = ctypes.c_bool
    user32.CloseClipboard.restype = ctypes.c_bool

    header = struct.pack(
        "<IIiii", 20, 0, 0, 0, 1
    )  # pFiles=20, pt=(0,0), fNC=0, fWide=1
    body = "".join(p + "\x00" for p in paths) + "\x00"
    raw = header + body.encode("utf-16-le")
    hmem = kernel32.GlobalAlloc(0x0042, len(raw))  # GMEM_MOVEABLE | GMEM_ZEROINIT
    assert hmem
    ptr = kernel32.GlobalLock(hmem)
    assert ptr
    try:
        ctypes.memmove(ptr, raw, len(raw))
    finally:
        kernel32.GlobalUnlock(hmem)
    assert user32.OpenClipboard(None)
    user32.EmptyClipboard()
    assert user32.SetClipboardData(CF_HDROP, hmem)
    user32.CloseClipboard()


def test_win_get_hdrop_multiple_paths():
    """资源管理器复制多文件（含空格/中文路径）→ HDROP 完整还原。"""
    if os.name != "nt":
        pytest.skip("仅 Windows")
    if not _clipboard_available():
        pytest.skip("剪贴板被其他进程占用")
    paths = ["C:\\dir with space\\f1.txt", "D:\\中文目录\\文件.txt"]
    _set_hdrop_clipboard(paths)
    assert clipboard._win_get_hdrop() == paths


def test_win_get_hdrop_prefers_over_text():
    """同时有 HDROP 与文本时，get_paths 返回 HDROP 列表。"""
    if os.name != "nt":
        pytest.skip("仅 Windows")
    if not _clipboard_available():
        pytest.skip("剪贴板被其他进程占用")
    _set_hdrop_clipboard(["C:\\a.txt", "C:\\b.txt"])
    assert clipboard.get_paths() == ["C:\\a.txt", "C:\\b.txt"]


def test_win_clipboard_roundtrip():
    """Windows：tkinter 写入剪贴板 → ctypes 读取，内容一致。"""
    if os.name != "nt":
        pytest.skip("仅 Windows")
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except Exception:  # noqa: BLE001 - 无显示环境
        pytest.skip("无可用显示环境")
    try:
        text = "C:\\a\\b\nD:\\x\\y.txt\n中文路径测试"
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        got = clipboard.get_text()
        assert got is not None, "ctypes 剪贴板读取失败（可能是 restype 截断）"
        assert got.replace("\r\n", "\n").strip() == text
    finally:
        try:
            root.destroy()
        except Exception:  # noqa: BLE001
            pass


def test_get_paths_text_fallback(monkeypatch):
    """无 HDROP 时回退文本解析。"""
    if os.name == "nt":
        monkeypatch.setattr(clipboard, "_win_get_hdrop", lambda: None)
        monkeypatch.setattr(
            clipboard, "_win_get_text", lambda: '"C:\\a b\\x.txt" "C:\\d\\y.txt"'
        )
    else:
        monkeypatch.setattr(
            clipboard, "get_text", lambda: '"C:\\a b\\x.txt" "C:\\d\\y.txt"'
        )
    assert clipboard.get_paths() == ["C:\\a b\\x.txt", "C:\\d\\y.txt"]


def test_get_text_returns_none_when_unavailable(monkeypatch):
    """无可用剪贴板/外部命令时返回 None 而非崩溃。"""
    if os.name == "nt":
        monkeypatch.setattr(clipboard, "_win_get_text", lambda: None)
    else:
        monkeypatch.setattr(clipboard, "_run", lambda args: None)
    assert clipboard.get_text() is None
