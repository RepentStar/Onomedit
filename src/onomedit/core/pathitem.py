"""路径封装：单个文件路径四段（全路径/目录/名/扩展名）与序列化/重命名。

路径段拆分必须兼容点开头文件（``.gitignore``）与多扩展名文件（``a.tar.gz``），
序列化与反序列化严格对称。"""

from __future__ import annotations

import os

# 路径类型（四档）
PATH_TYPE_FULL = "full"
PATH_TYPE_NAME = "name"
PATH_TYPE_STEM = "stem"
PATH_TYPE_EXT = "ext"
PATH_TYPES = (PATH_TYPE_FULL, PATH_TYPE_NAME, PATH_TYPE_STEM, PATH_TYPE_EXT)


class PathItem:
    """封装单个文件路径，提供四段惰性属性与段级读写。"""

    __slots__ = ("full",)

    def __init__(self, full: str | os.PathLike):
        self.full = os.fspath(full)

    # ---- 四段（惰性属性） ----
    @property
    def directory(self) -> str:
        return os.path.dirname(self.full)

    @property
    def name(self) -> str:
        return os.path.basename(self.full)

    @property
    def stem(self) -> str:
        return os.path.splitext(self.name)[0]

    @property
    def ext(self) -> str:
        """扩展名（含点，如 ``.txt``；无扩展名为空串）。"""
        return os.path.splitext(self.name)[1]

    # ---- 段级读写 ----
    def get_field(self, scope: str) -> str:
        if scope not in PATH_TYPES:
            raise ValueError(f"未知路径类型: {scope}")
        return getattr(self, scope)

    def with_field(self, scope: str, value: str) -> str:
        """把编辑后的某段写回全路径（序列化/反序列化对称的关键）。

        拼接时保持原路径的分隔符风格（正/反斜杠），不做无谓转换。
        """
        if scope == "full":
            return value
        parent = self.directory
        if scope == "name":
            return self._join(parent, value)
        if scope == "stem":
            return self._join(parent, value + self.ext)
        if scope == "ext":
            return self._join(parent, self.stem + value)
        raise ValueError(f"未知路径类型: {scope}")

    @staticmethod
    def _join(parent: str, value: str) -> str:
        if not parent:
            return value
        sep = "/" if "/" in parent else os.sep
        return parent.rstrip("/\\") + sep + value

    def serialize(self, path_type: str) -> str:
        """按路径类型生成临时文件中的一行。"""
        return self.get_field(path_type)

    def rename(self, target: str | os.PathLike) -> None:
        """执行重命名；失败抛 OSError，由调用方记录。"""
        rename_ensure_parent(self.full, os.fspath(target))

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"PathItem({self.full!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, PathItem) and self.full == other.full

    def __hash__(self) -> int:
        return hash(self.full)


def rename_ensure_parent(old: str, new: str) -> None:
    """执行重命名；目标父目录缺失时先递归创建再重试一次。

    全路径模式支持通过重命名移动文件，目标目录可能尚不存在（如
    ``C:\\data\\new\\file.txt``）；此时创建缺失的父目录后再次尝试。
    仅当源仍存在（排除源缺失导致的 ``FileNotFoundError``）时创建目录；
    其余情况原样抛出 OSError，由调用方决定如何处理（记录失败等）。
    """
    try:
        os.rename(old, new)
        return
    except FileNotFoundError:
        if not os.path.exists(old):
            raise
        parent = os.path.dirname(new)
        if not parent:
            raise
        os.makedirs(parent, exist_ok=True)
        os.rename(old, new)