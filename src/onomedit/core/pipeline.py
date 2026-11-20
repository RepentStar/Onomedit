"""重命名主流程编排：收集 → 编辑器 → 读回 → 应用规则 → 执行 → 日志。"""

from __future__ import annotations

import difflib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from onomedit.core import collection, editor, envvars, pathitem, rules, tempfile_mgr
from onomedit.core import config as config_mod
from onomedit.core.absolute_path import (
    AbsoluteItem,
    row_error,
    validate_name_segment,
    validate_target,
)
from onomedit.core.absolute_rename import AbsoluteRenamer, build_absolute_moves
from onomedit.core.logger import RenameLogger, parse_line
from onomedit.core.pathitem import PathItem, rename_ensure_parent
from onomedit.i18n import tr
from onomedit.utils import safename


class PipelineError(RuntimeError):
    """主流程中止级错误（无文件、未配置编辑器、行数校验失败等）。"""


class DuplicateTargetError(PipelineError):
    """目标重名：编辑结果中多个文件指向同一目标路径，中止执行（不执行任何重命名）。"""

    def __init__(self, conflicts: list[tuple[str, list[str]]]):
        self.conflicts = conflicts
        lines = [tr("检测到目标重名，已中止（未执行任何重命名）:")]
        for new, olds in conflicts:
            lines.append(tr("  目标: {target}", target=new))
            for old in olds:
                lines.append(f"    <- {old}")
        super().__init__("\n".join(lines))

    @property
    def summary(self) -> str:
        """状态栏用的一句话摘要。"""
        groups = len(self.conflicts)
        involved = sum(len(olds) for _, olds in self.conflicts)
        return tr(
            "检测到目标重名，已中止（未执行任何重命名）: {groups} 组目标、涉及 {files} 个文件",
            groups=groups,
            files=involved,
        )


def find_duplicate_targets(pairs: list[tuple[str, str]]) -> list[tuple[str, list[str]]]:
    """找出目标重名组：不同源文件最终指向同一目标路径。

    - Windows 文件系统大小写不敏感：``same.txt`` 与 ``SAME.TXT`` 视为同一目标。
    - 无变化项（``old == new``，保持原名）不算"重命名到重名目标"，不参与判定。

    返回 ``[(目标路径, [源路径, ...]), ...]``，按目标首次出现顺序，仅含重复组。
    """
    groups: dict[str, list[str]] = {}
    first: dict[str, str] = {}
    for old, new in pairs:
        if old == new:
            continue
        key = os.path.normcase(new)
        first.setdefault(key, new)
        groups.setdefault(key, []).append(old)
    return [(first[key], groups[key]) for key in groups if len(groups[key]) > 1]


@dataclass
class RenameResult:
    """批量重命名结果：成功 / 失败 / 无变化（跳过）。"""

    success: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.success) + len(self.failed) + len(self.skipped)

    @property
    def changed(self) -> int:
        return len(self.success) + len(self.failed)


@dataclass
class PreviewRow:
    """列表窗口/预览用：原文件名、新文件名、差异、距离。"""

    old: str
    new: str
    diff: str
    distance: int


@dataclass
class PipelineOutcome:
    result: RenameResult = field(default_factory=RenameResult)
    pairs: list[tuple[str, str]] = field(default_factory=list)
    preview: list[PreviewRow] | None = None
    dry_run: bool = False
    temp_path: str | Path = ""


def levenshtein(a: str, b: str) -> int:
    """编辑距离（单行内存版）。"""
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def diff_text(a: str, b: str) -> str:
    """单行字符级差异标注：删除 [-x-] 插入 [+y+]。"""
    sm = difflib.SequenceMatcher(None, a, b)
    parts: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            parts.append(a[i1:i2])
        elif tag == "delete":
            parts.append(f"[-{a[i1:i2]}-]")
        elif tag == "insert":
            parts.append(f"[+{b[j1:j2]}+]")
        else:  # replace
            parts.append(f"[-{a[i1:i2]}-][+{b[j1:j2]}+]")
    return "".join(parts)


class Renamer:
    """批量重命名执行器：目标重复预检、真冲突序号化、链/环两阶段解环、单文件失败不中断。"""

    def __init__(self, log: RenameLogger | None = None):
        self.log = log
        self.result = RenameResult()
        self._pending: dict[str, str] = {}
        self._removed: set[str] = set()
        self._moved: dict[str, tuple[str, str]] = {}
        self._tmp_seq = 0

    def run(self, pairs: list[tuple[str, str]]) -> RenameResult:
        conflicts = find_duplicate_targets(pairs)
        if conflicts:
            raise DuplicateTargetError(conflicts)

        # 第一阶段：移走冲突目标 + 完成无冲突改名
        self._pending = {old: new for old, new in pairs}
        for old, new in pairs:
            if old in self._removed:
                continue
            self._do(old, new)

        # 第二阶段：被移走的内容落位到最终目标
        for tmp, (old, target) in list(self._moved.items()):
            try:
                if os.path.exists(target):
                    target = str(safename.unique_path(Path(target)))
                rename_ensure_parent(tmp, target)
                self.result.success.append((old, target))
                self._log_record(old, target)
            except OSError as e:
                self.result.failed.append((old, target, str(e)))
                self._log_error(f"{old} -> {target}: {e}")
        return self.result

    def _do(self, old: str, new: str) -> None:
        if old == new:
            self._pending.pop(old, None)
            self.result.skipped.append(old)
            return
        try:
            if os.path.exists(new) and new in self._pending:
                # 链/环：new 是本批次尚未执行的源 → 先把内容移出到临时名
                tmp = self._temp_name(new)
                rename_ensure_parent(new, tmp)
                self._removed.add(new)
                self._moved[tmp] = (new, self._pending.pop(new))
            if os.path.exists(new):
                # 真冲突：目标仍被占用且不属于本批次 → 安全序号化
                new = str(safename.unique_path(Path(new)))
            rename_ensure_parent(old, new)
            self._pending.pop(old, None)
            self.result.success.append((old, new))
            self._log_record(old, new)
        except OSError as e:
            self._pending.pop(old, None)
            self.result.failed.append((old, new, str(e)))
            self._log_error(f"{old} -> {new}: {e}")

    def _temp_name(self, target: str) -> str:
        parent = os.path.dirname(target)
        stem, ext = os.path.splitext(os.path.basename(target))
        while True:
            self._tmp_seq += 1
            candidate = os.path.join(
                parent, f".__onomedit_tmp_{os.getpid()}_{self._tmp_seq}_{stem}{ext}"
            )
            if not os.path.lexists(candidate):
                return candidate

    def _log_record(self, old: str, new: str) -> None:
        if self.log:
            self.log.record(old, new)

    def _log_error(self, message: str) -> None:
        if self.log:
            self.log.record_error(message)


def restore(
    logger: RenameLogger,
    *,
    all_history: bool = False,
    partial_lines: list[str] | None = None,
) -> RenameResult:
    """恢复流程：反向执行（新 → 旧），倒序避免改名链依赖冲突。"""
    if partial_lines is not None:
        pairs = [parse_line(line) for line in partial_lines]
    elif all_history:
        pairs = logger.read_history()
    else:
        pairs = logger.read_last()
    if not pairs:
        return RenameResult()
    reverse = [(new, old) for old, new in reversed(pairs)]
    renamer = Renamer(log=logger)
    return renamer.run(reverse)


class RenamePipeline:
    """主流程编排。所有阶段可被调用方注入（测试/多实例隔离）。"""

    def __init__(
        self,
        cfg=None,
        *,
        temp_dir=None,
        on_status=None,
        clipboard_text: str | None = None,
        recursive: bool = False,
        absolute: bool = False,
    ):
        self.cfg = cfg or config_mod.load_config()
        self.temp_dir = temp_dir or (self.cfg.temp_dir or None)
        self.on_status = on_status or (lambda msg: None)
        self.clipboard_text = clipboard_text
        self.recursive = recursive
        self.absolute = absolute

    def prepare(
        self, raw_paths: list[str] | None = None
    ) -> tuple[list[PathItem], list[str], str | Path]:
        """流程前半：收集 → 展开 → 过滤 → 写临时文件 → 等待编辑 → 读回。

        返回 (items, new_full 列表, 临时文件路径)。行数校验失败抛 LineCountError。
        """
        if self.absolute and self.cfg.path_type != pathitem.PATH_TYPE_FULL:
            raise PipelineError(tr("--absolute 仅适用于 full 路径类型"))
        cwd = os.getcwd() if self.absolute else ""
        paths = collection.collect_paths(
            raw_paths,
            use_clipboard=self.clipboard_text is None,
            recursive=self.recursive,
        )
        if not paths:
            raise PipelineError(tr("没有可处理的文件（路径不存在或剪贴板为空）"))
        items = collection.build_items(paths)
        if self.cfg.expand_subdirs:
            items = collection.expand_subdirs(items, self.cfg.subdirs_depth)
        items = collection.apply_excludes(
            items, self.cfg.exclude, absolute=self.absolute
        )
        if self.absolute:
            try:
                items = collection.absolute_items(items, cwd)
            except ValueError as exc:
                raise PipelineError(str(exc)) from exc
        else:
            items = collection.dedupe_items(items)
        items = collection.sort_items(
            items, self.cfg.sort_by, reverse=self.cfg.sort_reverse
        )
        if not items:
            raise PipelineError(tr("应用排除规则后没有可处理的文件"))
        if self.absolute and not self.cfg.open_editor:
            return items, [item.full for item in items], ""

        temp_path, _ = tempfile_mgr.write_items(
            items, self.cfg.path_type, temp_dir=self.temp_dir
        )
        try:
            lines = self._edit_items(temp_path, len(items))
        except BaseException:
            self._cleanup_temp(temp_path)
            raise
        new_fulls = [
            item.with_field(self.cfg.path_type, line)
            for item, line in zip(items, lines)
        ]
        return items, new_fulls, temp_path

    def _edit_items(self, temp_path: Path, count: int) -> list[str]:
        sig = tempfile_mgr.signature(temp_path)
        if self.cfg.open_editor:
            editor_cmd = self.cfg.editor
            if not editor_cmd.strip():
                raise PipelineError(
                    tr(
                        "未配置编辑器，请先运行: onomedit config set-editor <命令>\n"
                        "（或使用 --no-editor 跳过编辑器）"
                    )
                )
            self.on_status(
                tr(
                    "已写入临时文件: {path}\n请在编辑器中修改后保存并退出…",
                    path=temp_path,
                )
            )
            editor.launch_and_wait(
                editor_cmd,
                temp_path,
                sig,
                multi_tab=self.cfg.multi_tab,
                timeout=self.cfg.editor_timeout,
                on_status=self.on_status,
            )

        try:
            return tempfile_mgr.read_lines(temp_path, count, absolute=self.absolute)
        except UnicodeDecodeError as exc:
            raise PipelineError(tr("编辑文件必须使用 UTF-8 编码")) from exc

    def plan(
        self, items: list[PathItem], new_fulls: list[str]
    ) -> list[tuple[str, str]]:
        """应用规则（顺序固定）+ 环境变量展开 + 安全命名，生成 (old, new) 计划对。

        规则顺序：替换/转换/插入（按配置列表顺序）→ 环境变量展开 → 安全命名。
        """
        pairs: list[tuple[str, str]] = []
        env = envvars.EnvVars()
        for line, (item, new_full) in enumerate(zip(items, new_fulls), 1):
            full = new_full
            try:
                if self.absolute:
                    validate_target(full)
                if self.cfg.apply_rules:
                    if self.cfg.enable_auto_rules:
                        for rule in self.cfg.auto_rules:
                            pi = PathItem(full, is_dir=item.is_dir)
                            value = rules.apply_rule(pi.get_field(rule.scope), rule)
                            if self.absolute and rule.scope != pathitem.PATH_TYPE_FULL:
                                validate_name_segment(value)
                            full = pi.with_field(
                                rule.scope, value, native=self.absolute
                            )
                            if self.absolute:
                                validate_target(full)
                    if self.cfg.enable_envvars:
                        pi = PathItem(full, is_dir=item.is_dir)
                        ctx = envvars.EnvContext(
                            file=item.full, clip_text=self.clipboard_text
                        )
                        new_name = env.expand(pi.name, context=ctx)
                        if self.absolute:
                            validate_name_segment(new_name)
                            if new_name in ("", ".", ".."):
                                raise ValueError(tr("请填写完整的绝对路径和名称"))
                        join = pathitem.join_name if self.absolute else os.path.join
                        full = join(pi.directory, new_name)
                if self.cfg.safety.sanitize:
                    pi = PathItem(full, is_dir=item.is_dir)
                    full = os.path.join(pi.directory, safename.sanitize_name(pi.name))
                if self.absolute:
                    full = validate_target(full, final_name=True)
            except ValueError as exc:
                if not self.absolute:
                    raise
                raise PipelineError(row_error(line, item.full, full, exc)) from exc
            pairs.append((item.full, full))
        return pairs

    def run_editor_mode(
        self,
        raw_paths: list[str] | None = None,
        *,
        dry_run: bool = False,
    ) -> PipelineOutcome:
        """编辑器模式全流程（流程 1）。dry_run 仅预览（差异/距离）不执行。"""
        try:
            items, new_fulls, temp_path = self.prepare(raw_paths)
        except OSError as exc:
            if not self.absolute:
                raise
            raise PipelineError(str(exc)) from exc
        try:
            pairs = self.plan(items, new_fulls)
            if self.absolute:
                log_dir = config_mod.log_dir()
                try:
                    moves = build_absolute_moves(
                        cast(list[AbsoluteItem], items), pairs, log_dir
                    )
                except ValueError as exc:
                    raise PipelineError(str(exc)) from exc
        finally:
            if temp_path:
                self._cleanup_temp(temp_path)

        if dry_run:
            rows = (
                preview_rows(items, pairs, self.cfg)
                if self.cfg.preview.diff or self.cfg.preview.distance
                else None
            )
            return PipelineOutcome(
                pairs=pairs, preview=rows, dry_run=True, temp_path=temp_path
            )

        if self.absolute:
            log = RenameLogger(log_dir)
            try:
                if any(not move.skipped for move in moves):
                    pathitem.require_rename_no_replace()
                log.begin_session()
            except OSError as exc:
                raise PipelineError(str(exc)) from exc
            result = AbsoluteRenamer(log, RenameResult()).run(moves)
        else:
            log = RenameLogger(config_mod.log_dir())
            log.begin_session()
            result = Renamer(log=log).run(pairs)
        return PipelineOutcome(result=result, pairs=pairs, temp_path=temp_path)

    @staticmethod
    def _cleanup_temp(temp_path: str | Path) -> None:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def preview_rows(
    items: list[PathItem], pairs: list[tuple[str, str]], cfg
) -> list[PreviewRow]:
    """生成列表窗口/预览所需行（差异 / 距离按配置开关）。"""
    rows: list[PreviewRow] = []
    for item, (old, new) in zip(items, pairs):
        rows.append(
            PreviewRow(
                old=old,
                new=new,
                diff=diff_text(old, new) if cfg.preview.diff else "",
                distance=levenshtein(old, new) if cfg.preview.distance else 0,
            )
        )
    return rows
