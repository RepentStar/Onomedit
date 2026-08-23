"""临时文件读写：行序列化、行数校验、文件签名。

行数与文件数不一致必须中止（防错位改名）；临时文件路径可被调用方覆盖（测试隔离/多实例）。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


class LineCountError(ValueError):
    """临时文件行数与文件数不一致。"""


def write_items(items, path_type: str, temp_dir: str | os.PathLike | None = None) -> tuple[Path, list[str]]:
    """把路径对象序列化写入 UTF-8 临时文件。

    返回 (临时文件路径, 原始行列表)。每项一行，尾部换行。
    """
    lines = [it.serialize(path_type) for it in items]
    fd, path = tempfile.mkstemp(prefix="onomedit_", suffix=".txt", dir=temp_dir, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            for line in lines:
                f.write(line + "\n")
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return Path(path), lines


def read_lines(path: str | os.PathLike, expected_count: int) -> list[str]:
    """读回临时文件并校验行数；不一致抛 LineCountError。"""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    if len(lines) != expected_count:
        raise LineCountError(
            f"临时文件行数 {len(lines)} 与文件数 {expected_count} 不一致，已中止（防止错位改名）"
        )
    return lines


def signature(path: str | os.PathLike) -> tuple[float, int]:
    """记录文件签名（修改时间 + 大小），用于检测编辑器是否保存过。"""
    st = os.stat(path)
    return (st.st_mtime, st.st_size)


def changed(sig1: tuple[float, int], sig2: tuple[float, int]) -> bool:
    return sig1 != sig2
