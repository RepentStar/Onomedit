"""验证剪贴板读取：HDROP（多文件/文件夹复制）、引号/空格路径文本解析、纯文本。"""

import ctypes
import struct
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import tkinter as tk

from onomedit.utils import clipboard

CF_HDROP = 15


def set_hdrop_clipboard(paths: list[str]) -> None:
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
    assert hmem, "GlobalAlloc 失败"
    ptr = kernel32.GlobalLock(hmem)
    assert ptr, "GlobalLock 失败"
    try:
        ctypes.memmove(ptr, raw, len(raw))
    finally:
        kernel32.GlobalUnlock(hmem)
    assert user32.OpenClipboard(None)
    user32.EmptyClipboard()
    assert user32.SetClipboardData(CF_HDROP, hmem), "SetClipboardData(CF_HDROP) 失败"
    user32.CloseClipboard()


def check(desc: str, ok: bool) -> None:
    print(("✔ " if ok else "✘ ") + desc)
    if not ok:
        sys.exit(1)


def main() -> int:
    # 1) 文本路径解析：引号包裹 / 换行分隔 / 混合
    p = clipboard._parse_path_text('"C:\\a b\\x.txt" "C:\\d\\y.txt"')
    check("引号包裹空格路径", p == ["C:\\a b\\x.txt", "C:\\d\\y.txt"])
    p = clipboard._parse_path_text("C:\\a\\b\nC:\\c\\d")
    check("换行分隔", p == ["C:\\a\\b", "C:\\c\\d"])
    p = clipboard._parse_path_text('C:\\a "C:\\b c\\d"')
    check("混合", p == ["C:\\a", "C:\\b c\\d"])

    root = tk.Tk()
    root.withdraw()
    try:
        # 2) HDROP：资源管理器复制多文件（含空格、中文路径）
        set_hdrop_clipboard(["C:\\dir with space\\f1.txt", "D:\\中文目录\\文件.txt"])
        got = clipboard.get_paths()
        print("HDROP 读到:", got)
        check(
            "HDROP 多文件（含空格/中文）",
            got == ["C:\\dir with space\\f1.txt", "D:\\中文目录\\文件.txt"],
        )

        # 3) 纯文本路径（不带引号）
        root.clipboard_clear()
        root.clipboard_append("C:\\plain\\nofile.txt")
        root.update()
        got = clipboard.get_paths()
        print("文本读到:", got)
        check("纯文本单路径", got == ["C:\\plain\\nofile.txt"])

        # 4) 引号包裹的文本路径
        root.clipboard_clear()
        root.clipboard_append('"C:\\spaced dir\\f.txt"')
        root.update()
        got = clipboard.get_paths()
        print("引号文本读到:", got)
        check("引号文本单路径", got == ["C:\\spaced dir\\f.txt"])
    finally:
        try:
            root.destroy()
        except Exception:
            pass
    print("剪贴板验证全部通过 ✔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
