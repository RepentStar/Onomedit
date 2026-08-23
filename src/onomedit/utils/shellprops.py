"""Shell 扩展属性读取（Windows 专属，可选依赖 pywin32）。

非 Windows / 未安装 pywin32 时返回空 dict；绝不因此阻塞主流程。
"""

from __future__ import annotations

import os

# 常用属性名（配置 shell_props 中可按需引用）
KNOWN_PROPS = ("size", "created", "modified", "attributes", "dimensions")


def get_shell_props(path: str | os.PathLike) -> dict:
    """读取文件的 Shell 扩展属性。

    返回 dict[str, str]；任何失败都返回空 dict。
    """
    if os.name != "nt":
        return {}
    try:
        import win32api  # noqa: F401
        import win32con  # noqa: F401
    except ImportError:
        return {}
    return _read_props(os.fspath(path))


def _read_props(path: str) -> dict:
    try:
        import win32api
        import win32con
    except ImportError:  # pragma: no cover - 由 get_shell_props 兜底
        return {}
    props: dict = {}
    try:
        st = os.stat(path)
        props["size"] = str(st.st_size)
        props["created"] = st.st_ctime
        props["modified"] = st.st_mtime
        attrs = win32api.GetFileAttributes(path)
        flags = []
        if attrs & win32con.FILE_ATTRIBUTE_READONLY:
            flags.append("readonly")
        if attrs & win32con.FILE_ATTRIBUTE_HIDDEN:
            flags.append("hidden")
        if attrs & win32con.FILE_ATTRIBUTE_SYSTEM:
            flags.append("system")
        props["attributes"] = ",".join(flags)
    except OSError:
        return {}
    except Exception:  # noqa: BLE001 - 可选能力，任何异常都降级
        return {}
    return props
