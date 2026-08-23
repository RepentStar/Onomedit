"""文件属性位判断。

Windows 用系统属性位（st_file_attributes，纯标准库）；其他平台按约定降级
（如点开头视为隐藏）。避免跨平台行为不一致的假设。
"""

from __future__ import annotations

import os

# Windows FILE_ATTRIBUTE_* 位
_FILE_ATTRIBUTE_READONLY = 0x1
_FILE_ATTRIBUTE_HIDDEN = 0x2
_FILE_ATTRIBUTE_SYSTEM = 0x4


def _win_attributes(path: str | os.PathLike) -> int:
    try:
        st = os.stat(path)
        return int(getattr(st, "st_file_attributes", 0) or 0)
    except OSError:
        return 0


def is_readonly(path: str | os.PathLike) -> bool:
    if os.name == "nt":
        return bool(_win_attributes(path) & _FILE_ATTRIBUTE_READONLY)
    # POSIX 降级：无写权限视为只读
    return not os.access(path, os.W_OK)


def is_hidden(path: str | os.PathLike) -> bool:
    if os.name == "nt":
        return bool(_win_attributes(path) & _FILE_ATTRIBUTE_HIDDEN)
    # POSIX 降级：点开头视为隐藏
    return os.path.basename(os.fspath(path)).startswith(".")


def is_system(path: str | os.PathLike) -> bool:
    if os.name == "nt":
        return bool(_win_attributes(path) & _FILE_ATTRIBUTE_SYSTEM)
    return False
