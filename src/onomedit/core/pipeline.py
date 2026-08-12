"""重命名主流程编排：收集 → 编辑器 → 读回 → 应用规则 → 执行 → 日志。"""

from __future__ import annotations

import difflib
import os
from dataclasses import dataclass, field
from pathlib import Path

from onomedit.core import collection, config as config_mod, editor, envvars, rules, tempfile_mgr
from onomedit.core.logger import RenameLogger, parse_line
from onomedit.core.pathitem import PathItem
from onomedit.utils import safename


class PipelineError(RuntimeError):
    """主流程中止级错误（无文件、未配置编辑器、行数校验失败等）。"""


@dataclass
class RenameResult:
    """批量重命名结果：成功 / 失败 / 无变化（跳过）。"""

    success: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str, str]] = field(default_factory=list)  # (old, new, error)
    skipped: list[str] = field(default_factory=list)  # 目标与源相同，无变化

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
    temp_path: str = ""


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
        self._removed: set[str] = set()  # 已被移走的路径（主循环跳过）
        self._moved: dict[str, str] = {}  # 临时名 → 最终目标（第二阶段落位）
        self._tmp_seq = 0

    def run(self, pairs: list[tuple[str, str]]) -> RenameResult:
        seen: dict[str, str] = {}
        clean: list[tuple[str, str]] = []
        for old, new in pairs:
            if new in seen:
                self.result.failed.append((old, new, "目标冲突：与其他文件同名"))
                self._log_error(f"{old} -> {new}: 目标冲突（与其他文件同名）")
                continue
            seen[new] = old
            clean.append((old, new))

        # 第一阶段：移走冲突目标 + 完成无冲突改名
        self._pending = {old: new for old, new in clean}
        for old, new in clean:
            if old in self._removed:
                continue  # 内容已被链处理移走，其落位在第二阶段
            self._do(old, new)

        # 第二阶段：被移走的内容落位到最终目标
        for tmp, target in list(self._moved.items()):
            try:
                if os.path.exists(target):
                    target = str(safename.unique_path(Path(target)))
                os.rename(tmp, target)
                self.result.success.append((tmp, target))
                self._log_record(tmp, target)
            except OSError as e:
                self.result.failed.append((tmp, target, str(e)))
                self._log_error(f"{tmp} -> {target}: {e}")
        return self.result

    # ---- 内部 ----
    def _do(self, old: str, new: str) -> None:
        if old == new:
            self._pending.pop(old, None)
            self.result.skipped.append(old)
            return
        try:
            if os.path.exists(new) and new in self._pending:
                # 链/环：new 是本批次尚未执行的源 → 先把内容移出到临时名
                tmp = self._temp_name(new)
                os.rename(new, tmp)
                self._log_record(new, tmp)
                self._removed.add(new)
                self._moved[tmp] = self._pending.pop(new)
            if os.path.exists(new):
                # 真冲突：目标仍被占用且不属于本批次 → 安全序号化
                new = str(safename.unique_path(Path(new)))
            os.rename(old, new)
            self._pending.pop(old, None)
            self.result.success.append((old, new))
            self._log_record(old, new)
        except OSError as e:
            self._pending.pop(old, None)
            self.result.failed.append((old, new, str(e)))
            self._log_error(f"{old} -> {new}: {e}")

    def _temp_name(self, target: str) -> str:
        self._tmp_seq += 1
        parent = os.path.dirname(target)
        stem, ext = os.path.splitext(os.path.basename(target))
        return os.path.join(
            parent, f".__onomedit_tmp_{os.getpid()}_{self._tmp_seq}_{stem}{ext}"
        )

    def _log_record(self, old: str, new: str) -> None:
        if self.log:
            self.log.record(old, new)

    def _log_error(self, message: str) -> None:
        if self.log:
            self.log.record_error(message)


def restore(logger: RenameLogger, *, all_history: bool = False, partial_lines: list[str] | None = None) -> RenameResult:
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

    def __init__(self, cfg=None, *, temp_dir=None, on_status=None, clipboard_text: str | None = None):
        self.cfg = cfg or config_mod.load_config()
        self.temp_dir = temp_dir or (self.cfg.temp_dir or None)
        self.on_status = on_status or (lambda msg: None)
        self.clipboard_text = clipboard_text

    def prepare(self, raw_paths: list[str] | None = None) -> tuple[list[PathItem], list[str], str]:
        """流程前半：收集 → 展开 → 过滤 → 写临时文件 → 等待编辑 → 读回。

        返回 (items, new_full 列表, 临时文件路径)。行数校验失败抛 LineCountError。
        """
        paths = collection.collect_paths(raw_paths, use_clipboard=self.clipboard_text is None)
        if not paths:
            raise PipelineError("没有可处理的文件（路径不存在或剪贴板为空）")
        items = collection.build_items(paths)
        if self.cfg.expand_subdirs:
            items = collection.expand_subdirs(items, self.cfg.subdirs_depth)
        items = collection.apply_excludes(items, self.cfg.exclude)
        if not items:
            raise PipelineError("应用排除规则后没有可处理的文件")

        temp_path, _ = tempfile_mgr.write_items(items, self.cfg.path_type, temp_dir=self.temp_dir)
        sig = tempfile_mgr.signature(temp_path)

        if self.cfg.open_editor:
            editor_cmd = self.cfg.editor
            if not editor_cmd.strip():
                raise PipelineError(
                    "未配置编辑器，请先运行: onomedit config set-editor <命令>\n"
                    "（或使用 --no-editor 跳过编辑器）"
                )
            self.on_status(
                f"已写入临时文件: {temp_path}\n请在编辑器中修改后保存并退出…"
            )
            editor.launch_and_wait(
                editor_cmd,
                temp_path,
                sig,
                multi_tab=self.cfg.multi_tab,
                timeout=self.cfg.editor_timeout,
                on_status=self.on_status,
            )

        lines = tempfile_mgr.read_lines(temp_path, len(items))  # 行数校验，不一致抛 LineCountError
        new_fulls = [item.with_field(self.cfg.path_type, line) for item, line in zip(items, lines)]
        return items, new_fulls, temp_path

    def plan(self, items: list[PathItem], new_fulls: list[str]) -> list[tuple[str, str]]:
        """应用规则（顺序固定）+ 环境变量展开 + 安全命名，生成 (old, new) 计划对。

        规则顺序：替换/转换/插入（按配置列表顺序）→ 环境变量展开 → 安全命名。
        """
        pairs: list[tuple[str, str]] = []
        env = envvars.EnvVars()
        for item, new_full in zip(items, new_fulls):
            full = new_full
            if self.cfg.apply_rules:
                if self.cfg.enable_auto_rules:
                    for rule in self.cfg.auto_rules:
                        pi = PathItem(full)
                        value = pi.get_field(rule.scope)
                        value = rules.apply_rule(value, rule)
                        full = pi.with_field(rule.scope, value)
                if self.cfg.enable_envvars:
                    # 环境变量作用于 name 段（目录段保持原样）
                    pi = PathItem(full)
                    ctx = envvars.EnvContext(file=item.full, clip_text=self.clipboard_text)
                    new_name = env.expand(pi.name, context=ctx)
                    full = os.path.join(pi.directory, new_name)
            if self.cfg.safety.sanitize:
                pi = PathItem(full)
                full = os.path.join(pi.directory, safename.sanitize_name(pi.name))
            pairs.append((item.full, full))
        return pairs

    def run_editor_mode(
        self,
        raw_paths: list[str] | None = None,
        *,
        dry_run: bool = False,
    ) -> PipelineOutcome:
        """编辑器模式全流程（流程 1）。dry_run 仅预览（差异/距离）不执行。"""
        items, new_fulls, temp_path = self.prepare(raw_paths)
        try:
            pairs = self.plan(items, new_fulls)
        finally:
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

        log = RenameLogger(config_mod.log_dir())
        log.begin_session()
        renamer = Renamer(log=log)
        result = renamer.run(pairs)
        return PipelineOutcome(result=result, pairs=pairs, temp_path=temp_path)

    @staticmethod
    def _cleanup_temp(temp_path: str) -> None:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def preview_rows(items: list[PathItem], pairs: list[tuple[str, str]], cfg) -> list[PreviewRow]:
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
