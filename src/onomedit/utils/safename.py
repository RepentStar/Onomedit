"""安全命名：非法字符替换、保留名处理、重名序号。

保证生成的名字在目标平台上可创建；Windows 语义（保留名、结尾点/空格）统一适用，
因为跨平台可移植性优先（重命名的文件可能在任何地方被打开）。
"""

from __future__ import annotations

import re
from pathlib import Path

# Windows 保留设备名（不区分大小写，忽略扩展名）
WINDOWS_RESERVED = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
)

# 文件名非法字符：Windows 保留字符 + 控制字符
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_name(name: str, *, replace: str = "_") -> str:
    """清理文件名中的非法内容。

    - 非法字符（含控制字符）替换为 ``replace``
    - 首尾空白清理，结尾点/空格清理（Windows 规则）
    - Windows 保留名（CON/PRN/AUX/NUL/COM1-9/LPT1-9）加 ``_`` 前缀保护

    注意：只处理文件名（name 段），不处理路径分隔符。
    """
    if not name:
        return name
    name = _ILLEGAL_CHARS.sub(replace, name)
    name = name.strip()
    name = name.rstrip(". ")
    stem, dot, ext = name.partition(".")
    if stem.upper() in WINDOWS_RESERVED:
        name = "_" + stem + dot + ext
    return name


def unique_path(target: Path) -> Path:
    """目标路径已存在时追加序号 ``名 (1).扩展名``（2、3 …递增）。

    仅用于与文件系统真实存在的文件冲突的场景；批次内部冲突由执行器处理。
    """
    if not target.exists():
        return target
    parent = target.parent
    stem = target.stem
    suffix = target.suffix
    n = 1
    while True:
        candidate = parent / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1
