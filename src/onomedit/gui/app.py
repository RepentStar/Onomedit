"""主窗口：文件收集（拖拽/按钮/剪贴板）→ 后台线程编辑器流程 → 列表窗口确认。

编辑器调用与等待必须在后台线程（避免冻结界面）；完成后经事件循环回主线程。
恢复上次操作是主窗口的快捷按钮。拖拽依赖 tkinterdnd2（可选，缺失时用按钮）。
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

from onomedit.core import collection, config as config_mod
from onomedit.core.collection import display_base
from onomedit.core.logger import RenameLogger
from onomedit.core.pathitem import PathItem
from onomedit.core.pipeline import (
    DuplicateTargetError,
    RenamePipeline,
    Renamer,
    find_duplicate_targets,
    restore,
)
from onomedit.gui.listview import ListWindow
from onomedit.gui.settings import SettingsWindow


class MainWindow:
    def __init__(self, root: tk.Tk, cfg: config_mod.Config | None = None):
        self.root = root
        self.cfg = cfg or config_mod.load_config()
        self.paths: list[str] = []  # 用户添加的原始路径（不展开）
        self._busy = False
        self._build()
        self._setup_dnd()

    # ------------------------------------------------------------ UI 构建
    def _build(self) -> None:
        self.root.title("Onomedit - 批量重命名")
        self.root.geometry("780x560")

        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)

        # 文件列表
        list_frame = ttk.LabelFrame(
            main, text="文件（将按此顺序写入临时文件）", padding=6
        )
        list_frame.pack(fill="both", expand=True)

        self.listbox = tk.Listbox(list_frame, selectmode="extended")
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # 按钮行
        btns = ttk.Frame(main)
        btns.pack(fill="x", pady=(8, 4))
        ttk.Button(btns, text="添加文件…", command=self._pick_files).pack(
            side="left", padx=2
        )
        ttk.Button(btns, text="添加文件夹…", command=self._pick_dir).pack(
            side="left", padx=2
        )
        ttk.Button(btns, text="从剪贴板", command=self._from_clipboard).pack(
            side="left", padx=2
        )
        ttk.Button(btns, text="清空", command=self._clear).pack(side="left", padx=2)
        ttk.Button(btns, text="设置…", command=self._open_settings).pack(
            side="right", padx=2
        )
        ttk.Button(btns, text="恢复上次", command=self._restore_last).pack(
            side="right", padx=2
        )

        # 选项行
        opts = ttk.Frame(main)
        opts.pack(fill="x", pady=4)
        ttk.Label(opts, text="路径类型:").pack(side="left")
        self.path_type_var = tk.StringVar(value=self.cfg.path_type)
        ttk.Combobox(
            opts,
            textvariable=self.path_type_var,
            values=list(config_mod.PATH_TYPES),
            state="readonly",
            width=10,
        ).pack(side="left", padx=4)
        self.subdirs_var = tk.BooleanVar(value=self.cfg.expand_subdirs)
        ttk.Checkbutton(
            opts, text="展开子文件夹", variable=self.subdirs_var, command=self._refresh
        ).pack(side="left", padx=6)
        ttk.Label(opts, text="层级:").pack(side="left")
        self.depth_var = tk.IntVar(value=self.cfg.subdirs_depth)
        self.depth_spin = ttk.Spinbox(
            opts,
            from_=1,
            to=99,
            width=4,
            textvariable=self.depth_var,
            command=self._refresh,
        )
        self.depth_spin.pack(side="left")

        # 执行
        run_frame = ttk.Frame(main)
        run_frame.pack(fill="x", pady=(4, 0))
        ttk.Button(run_frame, text="开始（打开编辑器）", command=self._start).pack(
            side="left"
        )
        ttk.Button(
            run_frame,
            text="直接应用规则（跳过编辑器）",
            command=lambda: self._start(no_editor=True),
        ).pack(side="left", padx=6)
        ttk.Button(
            run_frame,
            text="预览（进入重命名确认）",
            command=lambda: self._start(dry_run=True),
        ).pack(side="left")

        self._status = ttk.Label(main, text="就绪", anchor="w")
        self._status.pack(fill="x", pady=(6, 0))

    def _setup_dnd(self) -> None:
        """可选拖拽：tkinterdnd2 就绪时启用，否则提示并回退按钮。

        root 由 ttkbootstrap 创建（非 TkinterDnD.Tk），须用官方公开 API
        ``TkinterDnD.require(root)`` 挂载 tkdnd。"""
        try:
            from tkinterdnd2 import TkinterDnD

            TkinterDnD.require(self.root)
            self.listbox.drop_target_register("DND_Files")
            self.listbox.dnd_bind("<<Drop>>", self._on_drop)
        except Exception as e:  # noqa: BLE001 - 可选能力
            self._status.configure(text=f"就绪（拖拽不可用: {e}）")

    # ------------------------------------------------------------ 收集
    def _pick_files(self) -> None:
        chosen = filedialog.askopenfilenames(parent=self.root, title="选择文件")
        self._add_paths(list(chosen))

    def _pick_dir(self) -> None:
        chosen = filedialog.askdirectory(parent=self.root, title="选择文件夹")
        if chosen:
            self._add_paths([chosen])

    def _from_clipboard(self) -> None:
        from onomedit.utils import clipboard

        paths = clipboard.get_paths()
        if not paths:
            self._status.configure(text="剪贴板为空或不可读")
            return
        self._add_paths(paths)

    def _on_drop(self, event) -> None:
        files = self.root.tk.splitlist(event.data)
        self._add_paths(list(files))

    def _add_paths(self, paths: list[str]) -> None:
        existing = set(self.paths)
        added = 0
        for p in paths:
            if p and p not in existing and os.path.exists(p):
                self.paths.append(p)
                existing.add(p)
                added += 1
        self._refresh()
        self._status.configure(text=f"已添加 {added} 项，共 {len(self.paths)} 项")

    def _clear(self) -> None:
        self.paths = []
        self._refresh()
        self._status.configure(text="已清空")

    def _refresh(self) -> None:
        """按「展开子文件夹」勾选与层级刷新列表显示，并应用配置的排序。

        勾选时把目录项展开到指定层级（文件/目录都显示），否则原样显示；
        列表显示即最终写入顺序，故展开后统一按 sort_by 排序。
        """
        self.listbox.delete(0, "end")
        depth = int(self.depth_var.get() or 1)
        expand = self.subdirs_var.get()
        shown: list[str] = []
        for p in self.paths:
            if expand and os.path.isdir(p):
                items = collection.expand_subdirs([PathItem(p)], depth)
                shown.extend(it.full for it in items)
            else:
                shown.append(p)
        items = collection.sort_items(
            [PathItem(p) for p in shown], self.cfg.sort_by, reverse=self.cfg.sort_reverse
        )
        for it in items:
            self.listbox.insert("end", it.full)

    # ------------------------------------------------------------ 流程
    def _start(self, *, no_editor: bool = False, dry_run: bool = False) -> None:
        if self._busy:
            return
        paths = list(self.listbox.get(0, "end"))
        if not paths:
            self._status.configure(text="请先添加文件")
            return
        cfg = config_mod.load_config()
        cfg.path_type = self.path_type_var.get()
        # 列表已按勾选状态展开显示；处理时不再重复展开（显示即最终列表）
        cfg.expand_subdirs = False
        cfg.subdirs_depth = int(self.depth_var.get() or 1)
        if no_editor:
            cfg.open_editor = False

        self._busy = True
        self._status.configure(text="后台线程：准备文件并等待编辑器…")
        self.root.configure(cursor="watch")

        def worker() -> None:
            try:
                pipeline = RenamePipeline(
                    cfg,
                    on_status=lambda m: self._ui(
                        lambda: self._status.configure(text=m)
                    ),
                )
                items, new_fulls, temp_path = pipeline.prepare(paths)
                pairs = pipeline.plan(items, new_fulls)
                # 读取编辑结果后立即预检目标重名：发现重名 → 警告并中止（不执行）
                if not dry_run:
                    conflicts = find_duplicate_targets(pairs)
                    if conflicts:
                        raise DuplicateTargetError(conflicts)
                # 基准基于原始输入（展开前），保持「只显示到所选目录」语义
                base = display_base(self.paths)
                self._ui(
                    lambda: self._show_list(
                        pairs,
                        base,
                        dry_run=dry_run,
                        skip_confirmation=cfg.skip_confirmation,
                    )
                )
            except Exception as e:  # noqa: BLE001 - 流程错误统一提示并恢复可操作
                # 注意：except 变量 e 在块结束后即被删除，而 self._ui 是延迟到
                # 主线程执行（root.after），必须在此立即绑定，否则闭包读取 e 时
                # 抛 NameError: free variable 'e'（历史踩坑）。
                self._ui(lambda exc=e: self._finish_with_error(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_with_error(self, exc: Exception) -> None:
        """后台线程出错后的统一收尾：恢复可操作状态并提示。"""
        self._busy = False
        self.root.configure(cursor="")
        if isinstance(exc, DuplicateTargetError):
            self._warn_duplicate_targets(exc)
        else:
            self._status.configure(text=f"出错: {exc}")

    def _warn_duplicate_targets(self, exc: DuplicateTargetError) -> None:
        """目标重名警告：状态栏摘要 + 弹窗详情（路径分行展示，可读性好）。"""
        self._status.configure(text=exc.summary)
        messagebox.showwarning("目标重名，已中止", str(exc), parent=self.root)

    def _show_list(
        self, pairs, base: str, *, dry_run: bool, skip_confirmation: bool = False
    ) -> None:
        self._busy = False
        self.root.configure(cursor="")
        if dry_run:
            self._status.configure(text=f"预览共 {len(pairs)} 项（未执行）")
        if not dry_run and skip_confirmation:
            # 跳过确认模式：编辑保存后直接执行
            log = RenameLogger(config_mod.log_dir())
            log.begin_session()
            try:
                result = Renamer(log=log).run(pairs)
            except DuplicateTargetError as e:
                # 防御性兜底：worker 已预检，此处再触发则警告并中止且不退出
                self._warn_duplicate_targets(e)
                return
            self._status.configure(
                text=f"重命名完成: 成功 {len(result.success)} / 失败 {len(result.failed)}"
                f" / 无变化 {len(result.skipped)}"
            )
            self._maybe_exit_after()
            return
        ListWindow(
            self.root,
            pairs,
            cfg=self.cfg,
            base=base,
            on_done=lambda r: self._ui(lambda: self._on_rename_done(r)),
            on_cancel=lambda: self._ui(
                lambda: self._status.configure(text="重命名确认已取消")
            ),
        )

    def _on_rename_done(self, result) -> None:
        """确认窗口执行完成后的处理（状态栏 + 完成后退出）。"""
        self._status.configure(
            text=f"重命名完成: 成功 {len(result.success)} / 失败 {len(result.failed)}"
            f" / 无变化 {len(result.skipped)}"
        )
        self._maybe_exit_after()

    def _maybe_exit_after(self) -> None:
        """配置「完成后退出」开启时，短暂展示结果后关闭主窗口。"""
        if self.cfg.exit_after:
            self.root.after(600, self.root.destroy)

    def _restore_last(self) -> None:
        log = RenameLogger(config_mod.log_dir())
        try:
            result = restore(log)
        except DuplicateTargetError as e:
            self._warn_duplicate_targets(e)
            return
        self._status.configure(
            text=f"恢复完成: 成功 {len(result.success)} / 失败 {len(result.failed)} / 无变化 {len(result.skipped)}"
        )

    def _open_settings(self) -> None:
        SettingsWindow(self.root, cfg=self.cfg)
        # 保存后刷新本地配置并重排列表（排序依据等变更立即生效）
        self.cfg = config_mod.load_config()
        self._refresh()

    def _ui(self, fn) -> None:
        self.root.after(0, fn)


def main() -> None:
    """GUI 入口（供 CLI 的 gui 子命令调用）。"""
    try:
        import ttkbootstrap as tb

        root = tb.Window(themename="flatly")
    except ImportError:  # pragma: no cover - CLI 已提示安装
        raise
    MainWindow(root)
    root.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
