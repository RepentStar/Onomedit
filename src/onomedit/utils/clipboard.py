"""剪贴板读取（跨平台，纯标准库）。

Windows：
- ``get_paths`` 优先读 **CF_HDROP**（资源管理器复制文件/文件夹产生的格式），
  可靠还原每个路径（含空格、中文等）；
- 无 HDROP 时回退文本（CF_UNICODETEXT），解析支持换行分隔、空格分隔、
  引号包裹的路径列表。

macOS 用 ``pbpaste``；Linux 用 ``xclip`` / ``xsel``。任何失败返回空。

关键点（历史教训）：Win32 句柄/指针必须显式声明 ``restype = c_void_p``，
否则 64 位平台上被截断为 32 位导致读取失败。
"""

from __future__ import annotations

import os
import subprocess
import sys

CF_UNICODETEXT = 13
CF_HDROP = 15


def get_text() -> str | None:
    """返回剪贴板中的纯文本；无法读取时返回 None。"""
    if os.name == "nt":
        return _win_get_text()
    if sys.platform == "darwin":
        return _run(["pbpaste"])
    for cmd in (["xclip", "-o", "-selection", "clipboard"], ["xsel", "-b"]):
        text = _run(cmd)
        if text is not None:
            return text
    return None


def get_paths() -> list[str]:
    """返回剪贴板中的文件/路径列表。

    Windows 优先读 CF_HDROP（资源管理器复制文件/文件夹）；否则解析文本。
    """
    if os.name == "nt":
        hdrop = _win_get_hdrop()
        if hdrop is not None:
            return hdrop
        text = _win_get_text()
        return _parse_path_text(text) if text else []
    text = get_text()
    return _parse_path_text(text) if text else []


def _parse_path_text(text: str) -> list[str]:
    """把剪贴板文本解析为路径列表。

    支持三种形态（可混合）：
    - 换行分隔：``C:\\a\\b\\nC:\\c\\d``
    - 空格分隔：``C:\\a C:\\b``
    - 引号包裹（路径含空格）：``"C:\\a b\\x" "C:\\d\\y"``
    """
    paths: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        paths.extend(_split_quoted(line))
    return paths


def _split_quoted(line: str) -> list[str]:
    """按 Windows 规则拆分路径列表：引号内空格保留，反斜杠不转义。

    ``shlex`` 不可用：``posix=False`` 会保留引号，``posix=True`` 会转义
    无引号路径的反斜杠（``C:\\a`` → ``C:bell``）。此处手写解析。
    """
    parts: list[str] = []
    cur: list[str] = []
    in_quotes = False
    for ch in line:
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == " " and not in_quotes:
            if cur:
                parts.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return parts


def _run(args: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            timeout=5,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


# ---------------------------------------------------------------- Windows
def _win_setup() -> tuple:
    import ctypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32")
    void_p = ctypes.c_void_p

    user32.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]
    user32.IsClipboardFormatAvailable.restype = ctypes.c_bool
    user32.OpenClipboard.argtypes = [void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = void_p
    user32.CloseClipboard.restype = ctypes.c_bool
    kernel32.GlobalLock.argtypes = [void_p]
    kernel32.GlobalLock.restype = void_p
    kernel32.GlobalSize.argtypes = [void_p]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalUnlock.argtypes = [void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    shell32.DragQueryFileW.argtypes = [void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
    shell32.DragQueryFileW.restype = ctypes.c_uint
    return user32, kernel32, shell32, void_p


def _win_get_text() -> str | None:
    """Windows 剪贴板文本读取（UTF-16）。"""
    import ctypes

    user32, kernel32, _shell32, void_p = _win_setup()
    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return None
    if not user32.OpenClipboard(None):
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            size = kernel32.GlobalSize(handle)
            if size <= 0:
                return ""
            n_chars = size // 2
            buf = (ctypes.c_wchar * n_chars).from_address(ptr)
            return "".join(buf).rstrip("\x00")
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _win_get_hdrop() -> list[str] | None:
    """读取 CF_HDROP 文件列表（资源管理器复制文件/文件夹）。

    返回 None 表示剪贴板无该格式；有该格式时返回完整路径列表。
    """
    import ctypes

    user32, _kernel32, shell32, void_p = _win_setup()
    if not user32.IsClipboardFormatAvailable(CF_HDROP):
        return None
    if not user32.OpenClipboard(None):
        return None
    try:
        handle = user32.GetClipboardData(CF_HDROP)
        if not handle:
            return None
        # DragQueryFileW(hDrop, -1, None, 0) → 文件数
        count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
        paths: list[str] = []
        for i in range(count):
            length = shell32.DragQueryFileW(handle, i, None, 0)  # 字符数（不含结尾 \0）
            buf = ctypes.create_unicode_buffer(length + 1)
            shell32.DragQueryFileW(handle, i, buf, length + 1)
            paths.append(buf.value)
        return paths
    finally:
        user32.CloseClipboard()
