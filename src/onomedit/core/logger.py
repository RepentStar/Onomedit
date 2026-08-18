"""日志与恢复：三份文件（全部历史/最近一次/错误），格式兼容原版。

行格式：``旧路径<-->新路径``；解析时从右向左分割，避免路径内含分隔符。
恢复方向恒为反向（新 → 旧），倒序执行避免改名链依赖冲突。
"""

from __future__ import annotations

import os
from pathlib import Path

SEPARATOR = "<-->"

# 历史日志轮转阈值（字节）
ROTATE_BYTES = 1024 * 1024
# 保留的轮转份数
ROTATE_KEEP = 5


def parse_line(line: str) -> tuple[str, str]:
    """解析单行日志 ``旧<-->新``；无法解析抛 ValueError。"""
    old, sep, new = line.rstrip("\n").rpartition(SEPARATOR)
    if not sep:
        raise ValueError(f"无法解析日志行: {line!r}")
    return old, new


class RenameLogger:
    def __init__(self, log_dir: Path):
        self.log_dir = Path(log_dir)
        self.history_path = self.log_dir / "history.log"
        self.last_path = self.log_dir / "last.log"
        self.error_path = self.log_dir / "error.log"
        self._session_open = False

    def begin_session(self) -> None:
        """开始一次重命名会话：清空"最近一次"日志。"""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.last_path.write_text("", encoding="utf-8")
        except OSError:
            pass
        self._session_open = True

    def record(self, old: str, new: str) -> None:
        """记录一次成功重命名（追加历史 + 最近一次）。"""
        line = f"{old}{SEPARATOR}{new}\n"
        self._append_history(line)
        self._append(self.last_path, line)

    def record_error(self, message: str) -> None:
        self._append(self.error_path, message.rstrip("\n") + "\n")

    def read_last(self) -> list[tuple[str, str]]:
        return self._read_pairs(self.last_path)

    def read_history(self) -> list[tuple[str, str]]:
        return self._read_pairs(self.history_path)

    def _append(self, path: Path, text: str) -> None:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            pass

    def _append_history(self, line: str) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        if self.history_path.exists() and self.history_path.stat().st_size > ROTATE_BYTES:
            self._rotate()
        self._append(self.history_path, line)

    def _rotate(self) -> None:
        for i in range(ROTATE_KEEP - 1, 0, -1):
            src = self.log_dir / f"history.{i}.log"
            dst = self.log_dir / f"history.{i + 1}.log"
            try:
                if src.exists():
                    if dst.exists():
                        dst.unlink()
                    src.rename(dst)
            except OSError:
                pass
        try:
            self.history_path.rename(self.log_dir / "history.1.log")
        except OSError:
            pass

    @staticmethod
    def _read_pairs(path: Path) -> list[tuple[str, str]]:
        if not path.exists():
            return []
        pairs: list[tuple[str, str]] = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if not line:
                        continue
                    old, _, new = line.rpartition(SEPARATOR)
                    if _:
                        pairs.append((old, new))
        except (OSError, UnicodeDecodeError):
            return []
        return pairs
