"""Preflight and execute an absolute path rename batch."""

from __future__ import annotations

import errno
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from onomedit.core import pathitem
from onomedit.core.absolute_path import (
    AbsoluteItem,
    DirectoryEntry,
    Identity,
    ParentState,
    SourceEntry,
    entry_identity,
    inspect_parent,
    row_error,
    validate_target,
)
from onomedit.core.logger import RenameLogger
from onomedit.i18n import tr
from onomedit.utils import safename

if TYPE_CHECKING:
    from onomedit.core.pipeline import RenameResult


@dataclass(frozen=True)
class AbsoluteMove:
    line: int
    source: SourceEntry
    target: str
    parent: ParentState
    occupant: Identity | None
    skipped: bool
    case_only: bool

    @property
    def key(self) -> str:
        return self.parent.child_key(self.target)

    def describe(self, error: Exception | str) -> str:
        return row_error(self.line, self.source.path, self.target, error)


def _same_entry(
    source: SourceEntry, target: str, parent: ParentState, occupant: Identity | None
) -> tuple[bool, bool]:
    """Distinguish equivalent spellings, case-only moves and separate hard links."""
    if parent.key != source.parent.key:
        return False, False
    old_name = os.path.basename(source.path)
    new_name = os.path.basename(target)
    if old_name == new_name:
        return True, False
    if occupant != source.identity:
        return False, False
    folded = unicodedata.normalize("NFC", old_name).casefold()
    if folded != unicodedata.normalize("NFC", new_name).casefold():
        return False, False
    with os.scandir(os.path.dirname(source.path)) as entries:
        names = {entry.name for entry in entries}
    if new_name in names:
        return old_name not in names, False
    return False, True


def _require_source(source: SourceEntry, path: str) -> None:
    if entry_identity(path) != source.identity:
        raise OSError(tr("源目录项已变化或不存在: {path}", path=path))


def _protect_logs(log_dir: Path, moves: list[AbsoluteMove]) -> None:
    log_parent = inspect_parent(os.path.abspath(log_dir))
    log_ancestors = log_parent.ancestors()
    log_entries = set()
    if not log_parent.missing:
        log = RenameLogger(log_dir)
        for path in log.last_path, log.history_path, log.error_path:
            identity = entry_identity(str(path))
            if identity is not None:
                log_entries.add(identity)
                if os.path.islink(path) or identity.reparse_tag:
                    log_entries.add(entry_identity(os.path.realpath(path)))
    for move in moves:
        if (
            move.source.key in log_ancestors
            or move.key in log_ancestors
            or log_parent.key in move.source.parent.ancestors()
            or log_parent.key in move.parent.ancestors()
            or move.source.identity in log_entries
            or (move.occupant is not None and move.occupant in log_entries)
        ):
            raise ValueError(move.describe(tr("路径与活动日志目录冲突")))


def build_absolute_moves(
    items: list[AbsoluteItem], pairs: list[tuple[str, str]], log_dir: Path
) -> list[AbsoluteMove]:
    moves = []
    goals: dict[str, AbsoluteMove] = {}
    source_ancestors = set()
    target_ancestors = set()
    for line, (item, (old, target)) in enumerate(zip(items, pairs, strict=True), 1):
        source = item.source
        try:
            if inspect_parent(os.path.dirname(old)) != source.parent:
                raise OSError(tr("源父目录已变化"))
            _require_source(source, old)
            parent = inspect_parent(os.path.dirname(target))
            occupant = entry_identity(target) if not parent.missing else None
            skipped, case_only = _same_entry(source, target, parent, occupant)
            if not skipped and source.parent.device != parent.device:
                raise OSError(tr("跨卷移动需要在同一卷内执行"))
        except OSError as exc:
            raise ValueError(row_error(line, old, target, exc)) from exc

        move = AbsoluteMove(line, source, target, parent, occupant, skipped, case_only)
        moves.append(move)
        source_ancestors.update(source.parent.ancestors())
        if not skipped:
            if conflict := goals.get(move.key):
                reason = tr("检测到目标重名")
                raise ValueError(
                    f"{conflict.describe(reason)}\n{move.describe(reason)}"
                )
            goals[move.key] = move
            target_ancestors.update(parent.ancestors())

    try:
        _protect_logs(log_dir, moves)
    except OSError as exc:
        raise ValueError(
            tr("无法检查活动日志目录 {path}: {error}", path=log_dir, error=exc)
        ) from exc
    ancestors = source_ancestors | target_ancestors
    for move in goals.values():
        if move.key in ancestors or move.source.key in ancestors:
            raise ValueError(move.describe(tr("存在目录依赖，请拆成多次执行")))
    return moves


class AbsoluteRenamer:
    def __init__(self, log: RenameLogger, result: RenameResult):
        self.log = log
        self.result = result
        self._created: dict[str, DirectoryEntry] = {}
        self._reserved: set[str] = set()
        self._tmp_seq = 0

    def run(self, moves: list[AbsoluteMove]) -> RenameResult:
        moving = {move.source.key: move for move in moves if not move.skipped}
        dependencies = {}
        for move in moving.values():
            occupant = move if move.case_only else moving.get(move.key)
            if occupant is not None and move.occupant == occupant.source.identity:
                dependencies[move.line] = occupant.line
        staged_lines = set(dependencies.values())
        staged = {}
        failed = set()
        for move in moves:
            self._reserved.update(
                move.parent.ancestors() | move.source.parent.ancestors()
            )
            self._reserved.update((move.key, move.source.key))

        for move in moving.values():
            if move.line in staged_lines:
                try:
                    staged[move.line] = self._stage(move)
                except (OSError, ValueError) as exc:
                    failed.add(move.line)
                    self._record_failure(move, exc)

        for move in moves:
            if move.skipped:
                self.result.skipped.append(move.source.path)
            elif move.line not in failed:
                temp = staged.get(move.line)
                try:
                    dependency = dependencies.get(move.line)
                    if dependency in failed:
                        raise OSError(tr("待移动的目标占用项暂存失败"))
                    landed = self._place(
                        move, temp or move.source.path, dependency is not None
                    )
                except (OSError, ValueError) as exc:
                    self._record_failure(move, exc, temp)
                else:
                    self.result.success.append((move.source.path, landed))
                    self.log.record(move.source.path, landed)
        return self.result

    def _check_parent(
        self, parent: ParentState, path: str, *, create: bool = False
    ) -> None:
        parent_path = os.path.dirname(path)
        count = len(parent.existing)
        while True:
            current = inspect_parent(parent_path)
            if current.existing[:count] != parent.existing or current.key != parent.key:
                raise OSError(tr("父目录已变化: {path}", path=parent_path))
            for entry in current.existing[count:]:
                real_key = os.path.normcase(os.path.realpath(entry.path, strict=True))
                created = self._created.get(real_key)
                if created is None or (entry.link, entry.directory) != (
                    created.link,
                    created.directory,
                ):
                    raise OSError(tr("父目录已变化: {path}", path=entry.path))
            if not current.missing:
                return
            new_parent = os.path.join(current.existing[-1].path, current.missing[0])
            first_missing_key = current.key
            for _ in current.missing[1:]:
                first_missing_key = os.path.dirname(first_missing_key)
            if first_missing_key in self._created:
                raise OSError(tr("父目录已变化: {path}", path=new_parent))
            if not create:
                return
            os.mkdir(new_parent)
            state = inspect_parent(new_parent)
            entry = state.existing[-1]
            if (
                state.missing
                or state.existing[:-1] != current.existing
                or entry.link.reparse_tag
                or entry.link != entry.directory
            ):
                raise OSError(tr("父目录已变化: {path}", path=new_parent))
            self._created[state.key] = entry

    def _stage(self, move: AbsoluteMove) -> str:
        source = move.source
        self._check_parent(source.parent, source.path)
        self._check_parent(move.parent, move.target)
        parent = source.parent.resolved
        while True:
            self._tmp_seq += 1
            candidate = os.path.join(
                parent, f".__onomedit_tmp_{os.getpid()}_{self._tmp_seq}"
            )
            key = source.parent.child_key(candidate)
            if key in self._reserved or entry_identity(candidate) is not None:
                continue
            self._check_parent(source.parent, source.path)
            _require_source(source, source.path)
            validate_target(candidate, final_name=True)
            try:
                pathitem.rename_no_replace(source.path, candidate)
            except FileExistsError:
                continue
            self._reserved.add(key)
            return candidate

    def _place(self, move: AbsoluteMove, path: str, has_dependency: bool) -> str:
        source = move.source
        self._check_parent(source.parent, source.path)
        _require_source(source, path)
        self._check_parent(move.parent, move.target, create=True)
        target = Path(move.target)
        candidate = move.target
        number = 0
        while True:
            self._check_parent(source.parent, source.path)
            _require_source(source, path)
            self._check_parent(move.parent, candidate)
            key = move.parent.child_key(candidate)
            if (number == 0 or key not in self._reserved) and entry_identity(
                candidate
            ) is None:
                validate_target(candidate, final_name=True)
                try:
                    pathitem.rename_no_replace(path, candidate)
                except OSError as exc:
                    if exc.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                        raise
                else:
                    self._reserved.add(key)
                    return candidate
            if has_dependency:
                raise OSError(tr("待移动的目标占用项已变化: {path}", path=candidate))
            number += 1
            candidate = str(safename.numbered_path(target, number))

    def _record_failure(
        self, move: AbsoluteMove, error: Exception, temp: str | None = None
    ) -> None:
        reason = str(error)
        if isinstance(error, OSError) and (
            error.errno == errno.EXDEV or getattr(error, "winerror", None) == 17
        ):
            reason = tr("跨卷移动需要在同一卷内执行") + f" ({reason})"
        if temp is not None:
            try:
                self._check_parent(move.source.parent, move.source.path)
                _require_source(move.source, temp)
                pathitem.rename_no_replace(temp, move.source.path)
            except OSError as exc:
                reason += "\n" + tr(
                    "暂存恢复失败，恢复路径: {path}；{error}", path=temp, error=exc
                )
        self.result.failed.append((move.source.path, move.target, reason))
        self.log.record_error(move.describe(reason))
