"""Path syntax and directory-entry identities for absolute editing."""

from __future__ import annotations

import errno
import ntpath
import os
import posixpath
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from onomedit.core.logger import SEPARATOR
from onomedit.core.pathitem import PathItem
from onomedit.i18n import tr
from onomedit.utils.safename import WINDOWS_RESERVED

_LINE_BREAKS = frozenset("\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029")
_WINDOWS_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_DEVICES = (
    WINDOWS_RESERVED
    | {"CONIN$", "CONOUT$"}
    | {prefix + digit for prefix in ("COM", "LPT") for digit in "¹²³"}
)


def row_error(line: int, source: str, target: str, error: Exception | str) -> str:
    def display(path: str) -> str:
        if any(ch in _LINE_BREAKS or ch == "\0" for ch in path):
            return repr(path)
        return f'"{path}"'

    return tr(
        "第 {line} 行: {source} -> {target}: {error}",
        line=line,
        source=display(source),
        target=display(target),
        error=error,
    )


def validate_text(path: str) -> None:
    if any(ch in _LINE_BREAKS or ch == "\0" for ch in path):
        raise ValueError(tr("路径包含行分隔符或 NUL"))
    if SEPARATOR in path:
        raise ValueError(tr("路径包含日志分隔符 {separator}", separator=SEPARATOR))
    try:
        path.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(tr("路径无法编码为 UTF-8")) from exc


def _validate_windows_name(name: str) -> None:
    device = name.split(".", 1)[0].rstrip(" ").upper()
    if (
        name.endswith((".", " "))
        or device in _WINDOWS_DEVICES
        or _WINDOWS_ILLEGAL.search(name)
    ):
        raise ValueError(tr("无效的 Windows 路径段 {name!r}", name=name))


def _windows_root(path: str) -> tuple[str, str]:
    path = path.replace("/", "\\")
    if path.startswith(("\\\\.\\", "\\\\?\\")):
        raise ValueError(tr("路径使用了 Windows 设备或扩展命名空间"))
    drive, rest = ntpath.splitdrive(path)
    if drive.startswith("\\\\"):
        server_share = drive[2:].split("\\")
        if len(server_share) != 2 or any(not part for part in server_share):
            raise ValueError(tr("UNC 路径必须包含服务器和共享名"))
        for part in server_share:
            _validate_windows_name(part)
    elif not re.fullmatch(r"[A-Za-z]:", drive):
        raise ValueError(tr("请填写完整的绝对路径和名称"))
    if ":" in rest:
        raise ValueError(tr("路径包含 Windows 备用数据流分隔符"))
    return drive, rest


def validate_target(
    path: str, *, final_name: bool = False, windows: bool | None = None
) -> str:
    """Validate the spelling before normalization, optionally check the cleaned name."""
    validate_text(path)
    windows = os.name == "nt" if windows is None else windows
    if windows:
        drive, rest = _windows_root(path)
        sep = "\\"
        normalize = ntpath.normpath
    else:
        drive, rest = "", path
        sep = "/"
        normalize = posixpath.normpath
    if not rest.startswith(sep) or rest.endswith(sep):
        raise ValueError(tr("请填写完整的绝对路径和名称"))
    parts = rest.split(sep)
    if ".." in parts or parts[-1] == ".":
        raise ValueError(tr("路径包含 .. 段或以 . 结尾"))
    if windows:
        for part in parts[1:-1]:
            if part and part != ".":
                _validate_windows_name(part)
        if final_name:
            _validate_windows_name(parts[-1])
    return normalize(drive + rest)


def validate_name_segment(value: str) -> None:
    validate_text(value)
    if os.sep in value or (os.altsep and os.altsep in value):
        raise ValueError(tr("名称段包含路径分隔符"))


class Identity(NamedTuple):
    device: int
    inode: int
    kind: int
    reparse_tag: int


def _identity(st: os.stat_result) -> Identity:
    return Identity(
        st.st_dev, st.st_ino, stat.S_IFMT(st.st_mode), getattr(st, "st_reparse_tag", 0)
    )


def entry_identity(path: str) -> Identity | None:
    try:
        return _identity(os.lstat(path))
    except FileNotFoundError:
        return None


def source_path(path: str, cwd: str) -> str:
    """Make a collected path absolute while keeping its final directory entry."""
    validate_text(path)
    raw = os.path.join(cwd, path)
    if os.name == "nt":
        raw = raw.replace("/", "\\")
        drive, _ = _windows_root(raw)
        # Keep the separator on a drive or UNC root for the root check below.
        raw = raw.rstrip("\\") or raw
        if raw == drive:
            raw += "\\"
    else:
        raw = raw.rstrip("/") or raw
    normalized = os.path.abspath(raw)
    validate_text(normalized)
    name = os.path.basename(normalized)
    if not name:
        raise ValueError(tr("根目录不能作为移动源"))
    if os.name == "nt":
        validate_target(normalized, final_name=True)

    raw_name = os.path.basename(raw)
    if raw_name in (".", ".."):
        # A final dot segment denotes a directory. A link at the normalized
        # final position would move the link rather than that directory.
        selected = _identity(os.stat(raw))
        if selected.kind != stat.S_IFDIR or entry_identity(normalized) != selected:
            raise ValueError(tr("无法确认规范化前后的源目录项相同"))
    elif raw != normalized:
        if (
            raw_name != name
            or _identity(os.stat(os.path.dirname(raw)))
            != _identity(os.stat(os.path.dirname(normalized)))
            or entry_identity(raw) != entry_identity(normalized)
        ):
            raise ValueError(tr("无法确认规范化前后的源目录项相同"))
    return normalized


def ancestor_keys(key: str) -> set[str]:
    ancestors = set()
    parent = os.path.dirname(key)
    while parent != key:
        ancestors.add(parent)
        key, parent = parent, os.path.dirname(parent)
    return ancestors


@dataclass(frozen=True)
class DirectoryEntry:
    path: str
    link: Identity
    directory: Identity


@dataclass(frozen=True)
class ParentState:
    existing: tuple[DirectoryEntry, ...]
    missing: tuple[str, ...]
    resolved: str
    aliases: frozenset[str]

    @property
    def key(self) -> str:
        return os.path.normcase(self.resolved)

    @property
    def device(self) -> int:
        return self.existing[-1].directory.device

    def child_key(self, path: str) -> str:
        return os.path.join(self.key, os.path.normcase(os.path.basename(path)))

    def ancestors(self) -> set[str]:
        keys = ancestor_keys(self.key) | self.aliases | {self.key}
        for alias in self.aliases:
            keys.update(ancestor_keys(alias))
        return keys


def inspect_parent(parent: str) -> ParentState:
    existing = []
    aliases = set()
    parts = Path(parent).parts
    current = parts[0]
    for index, part in enumerate(parts):
        if index:
            current = os.path.join(current, part)
        link = entry_identity(current)
        if link is None:
            if not existing:
                raise FileNotFoundError(
                    errno.ENOENT, os.strerror(errno.ENOENT), current
                )
            break
        directory = link
        if link.kind == stat.S_IFLNK or link.reparse_tag:
            directory = _identity(os.stat(current))
            if index:
                previous = os.path.realpath(existing[-1].path, strict=True)
                aliases.add(os.path.normcase(os.path.join(previous, part)))
        if directory.kind != stat.S_IFDIR:
            raise NotADirectoryError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), current)
        existing.append(DirectoryEntry(current, link, directory))
    missing = parts[len(existing) :]
    resolved = os.path.realpath(existing[-1].path, strict=True)
    return ParentState(
        tuple(existing), missing, os.path.join(resolved, *missing), frozenset(aliases)
    )


@dataclass(frozen=True)
class SourceEntry:
    path: str
    identity: Identity
    parent: ParentState

    @classmethod
    def read(cls, path: str) -> SourceEntry:
        parent = inspect_parent(os.path.dirname(path))
        identity = entry_identity(path)
        if identity is None:
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path)
        return cls(path, identity, parent)

    @property
    def key(self) -> str:
        return self.parent.child_key(self.path)


class AbsoluteItem(PathItem):
    __slots__ = ("source",)

    def __init__(self, source: SourceEntry, *, is_dir: bool):
        super().__init__(source.path, is_dir=is_dir)
        self.source = source
