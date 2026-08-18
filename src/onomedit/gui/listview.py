"""列表窗口：编辑后确认（原文件名 / 新文件名 / 差异 / 距离，勾选执行）。

默认全选；路径相对基准目录显示，执行仍用完整路径；全部成功后自动关闭。"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk

from onomedit.core import config as config_mod
from onomedit.core.logger import RenameLogger
from onomedit.core.pipeline import DuplicateTargetError, Renamer, diff_text, levenshtein


class ListWindow(tk.Toplevel):
    """展示重命名计划，用户勾选后执行。

    承担"编辑后确认"角色：取消勾选的项目不执行。
    """

    def __init__(
        self,
        master,
        pairs: list[tuple[str, str]],
        cfg=None,
        on_done=None,
        on_cancel=None,
        base: str = "",
    ):
        super().__init__(master)
        self.title("Onomedit - 重命名确认")
        self.geometry("900x560")
        self.pairs = pairs
        self.cfg = cfg or config_mod.load_config()
        self.on_done = on_done
        self.on_cancel = on_cancel
        self.base = base  # 显示基准目录（空 = 显示完整路径）
        self._executed = False  # 是否已执行过（防止执行后关闭再触发取消提示）
        self._build()
        self.transient(master)
        # 强制关闭（点 X）与取消按钮一致：刷新主窗口状态栏
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # 默认全选
        self.tree.selection_set(self.tree.get_children())

    def _build(self) -> None:
        # 列按配置动态生成：差异/距离关闭时直接不显示该列
        cols: list[str] = ["old", "new"]
        headers: list[str] = ["原文件名", "新文件名"]
        if self.cfg.preview.diff:
            cols.append("diff")
            headers.append("差异")
        if self.cfg.preview.distance:
            cols.append("distance")
            headers.append("距离")

        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="extended")
        tree = self.tree
        for col, head in zip(cols, headers):
            tree.heading(col, text=head)
            width = 120 if col in ("old", "new") else 260
            tree.column(col, width=width, anchor="center")

        vsb = ttk.Scrollbar(self, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")

        for i, (old, new) in enumerate(self.pairs):
            d_old, d_new = self._display(old), self._display(new)
            values: list = [d_old, d_new]
            if self.cfg.preview.diff:
                values.append(diff_text(d_old, d_new))
            if self.cfg.preview.distance:
                values.append(levenshtein(d_old, d_new))
            tree.insert("", "end", iid=str(i), values=values)

        btns = ttk.Frame(self)
        btns.pack(side="bottom", fill="x", pady=6)
        ttk.Button(btns, text="全选", command=lambda: self._select_all(True)).pack(side="left", padx=4)
        ttk.Button(btns, text="全不选", command=lambda: self._select_all(False)).pack(side="left", padx=4)
        ttk.Button(btns, text="执行重命名", command=self._execute).pack(side="right", padx=4)
        ttk.Button(btns, text="取消", command=self._on_close).pack(side="right", padx=4)

        self._status = ttk.Label(self, text=f"共 {len(self.pairs)} 项（已全选）")
        self._status.pack(side="bottom", fill="x", padx=8)

        # 双击行切换选中（勾选语义）
        tree.bind("<Double-1>", lambda e: self._toggle(e))

    def _display(self, path: str) -> str:
        """相对基准目录显示；不在基准下或跨盘时原样显示。"""
        if not self.base:
            return path
        try:
            rel = os.path.relpath(path, self.base)
        except ValueError:
            return path
        if rel.startswith(".."):
            return path
        return rel

    def _on_close(self) -> None:
        """取消 / 强制关闭（点 X）：通知主窗口刷新状态栏后销毁。

        已执行过重命名时不再触发取消提示（结果提示已由 on_done 更新）。
        """
        if self.on_cancel and not self._executed:
            self.on_cancel()
        self.destroy()

    # 勾选逻辑：Treeview 无勾选控件，以选中态表示勾选
    def _selected(self) -> list[int]:
        return [int(iid) for iid in self.tree.selection()]

    def _toggle(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        if iid in self.tree.selection():
            self.tree.selection_remove(iid)
        else:
            self.tree.selection_add(iid)

    def _select_all(self, flag: bool) -> None:
        if flag:
            self.tree.selection_set(self.tree.get_children())
        else:
            self.tree.selection_remove(*self.tree.get_children())

    def _execute(self) -> None:
        indexes = self._selected()
        if not indexes:
            self._status.configure(text="未勾选任何项目")
            return
        pairs = [self.pairs[i] for i in indexes]
        log = RenameLogger(config_mod.log_dir())
        log.begin_session()
        try:
            result = Renamer(log=log).run(pairs)
        except DuplicateTargetError as e:
            # 勾选的项目中出现目标重名 → 警告并中止，不执行
            self._status.configure(text=e.summary)
            messagebox.showwarning("目标重名，已中止", str(e), parent=self)
            return
        self._executed = True
        text = (
            f"完成: 成功 {len(result.success)} / 失败 {len(result.failed)}"
            f" / 无变化 {len(result.skipped)}"
        )
        self._status.configure(text=text)
        if self.on_done:
            self.on_done(result)
        if not result.failed:
            self.after(800, self.destroy)
