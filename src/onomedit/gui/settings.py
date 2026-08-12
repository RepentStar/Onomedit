"""设置窗口：编辑并保存配置。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from onomedit.core import config as config_mod
from onomedit.core.pathitem import PATH_TYPES


class SettingsWindow(tk.Toplevel):
    """配置编辑对话框（保存后写回配置文件）。"""

    def __init__(self, master=None, cfg: config_mod.Config | None = None):
        super().__init__(master)
        self.title("Onomedit 设置")
        self.cfg = cfg or config_mod.load_config()
        self.resizable(False, False)
        self._vars: dict[str, tk.Variable] = {}
        self._build()
        self.transient(master)
        self.grab_set()

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)

        # 编辑器
        row = ttk.LabelFrame(body, text="编辑器", padding=8)
        row.pack(fill="x", **pad)
        self._entry("editor", "主编辑器命令", row)
        self._entry("editor_alt", "备用编辑器命令", row)
        self._entry("editor_timeout", "等待超时（秒）", row)
        self._check("multi_tab", "多标签编辑器（直接轮询等待保存）", row)

        # 重命名
        row2 = ttk.LabelFrame(body, text="重命名", padding=8)
        row2.pack(fill="x", **pad)
        ttk.Label(row2, text="路径类型:").grid(row=0, column=0, sticky="w", pady=2)
        path_var = tk.StringVar(value=self.cfg.path_type)
        ttk.Combobox(row2, textvariable=path_var, values=list(PATH_TYPES), state="readonly", width=20).grid(
            row=0, column=1, sticky="w", pady=2
        )
        self._vars["path_type"] = path_var
        self._check("expand_subdirs", "展开子文件夹", row2)
        self._entry("subdirs_depth", "展开层级（1 = 直接子项）", row2)

        # 开关组
        row3 = ttk.LabelFrame(body, text="行为", padding=8)
        row3.pack(fill="x", **pad)
        self._check("open_editor", "打开编辑器", row3)
        self._check("apply_rules", "应用规则", row3)
        self._check("enable_envvars", "环境变量替换（<n> <d> 等）", row3)
        self._check("enable_auto_rules", "自动替换规则", row3)
        self._check("skip_confirmation", "跳过重命名确认（编辑保存后直接执行）", row3)
        self._check("exit_after", "完成后退出", row3)

        # 排除
        row4 = ttk.LabelFrame(body, text="排除", padding=8)
        row4.pack(fill="x", **pad)
        for key, label in (
            ("files", "文件"),
            ("dirs", "目录"),
            ("symlinks", "符号链接"),
            ("readonly", "只读"),
            ("hidden", "隐藏"),
            ("system", "系统"),
        ):
            self._check(f"exclude.{key}", f"排除{label}", row4)

        # 预览与安全
        row5 = ttk.LabelFrame(body, text="预览与安全", padding=8)
        row5.pack(fill="x", **pad)
        self._check("preview.diff", "显示差异", row5)
        self._check("preview.distance", "显示距离", row5)
        self._check("safety.sanitize", "安全命名（非法字符/保留名/序号）", row5)

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text="保存", command=self._save).pack(side="right", padx=4)
        ttk.Button(btns, text="重置默认", command=self._reset).pack(side="right", padx=4)
        ttk.Button(btns, text="取消", command=self.destroy).pack(side="right", padx=4)

    # ---- 控件辅助 ----
    def _entry(self, key: str, label: str, parent: ttk.Frame) -> None:
        row = len(parent.grid_slaves()) // 2
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        var = tk.StringVar(value=str(getattr(self.cfg, key)))
        ttk.Entry(parent, textvariable=var, width=40).grid(row=row, column=1, sticky="we", pady=2)
        self._vars[key] = var

    def _check(self, dotted: str, label: str, parent: ttk.Frame) -> None:
        obj = self.cfg
        parts = dotted.split(".")
        for p in parts[:-1]:
            obj = getattr(obj, p)
        var = tk.BooleanVar(value=bool(getattr(obj, parts[-1])))
        ttk.Checkbutton(parent, text=label, variable=var).grid(
            row=len(parent.grid_slaves()), column=0, columnspan=2, sticky="w", pady=1
        )
        self._vars[dotted] = var

    # ---- 动作 ----
    def _save(self) -> None:
        cfg = self.cfg
        for dotted, var in self._vars.items():
            obj = cfg
            parts = dotted.split(".")
            for p in parts[:-1]:
                obj = getattr(obj, p)
            raw = var.get()
            if isinstance(getattr(obj, parts[-1]), bool):
                setattr(obj, parts[-1], bool(raw))
            elif isinstance(getattr(obj, parts[-1]), (int, float)):
                try:
                    value = type(getattr(obj, parts[-1]))(raw)
                except ValueError:
                    continue
                setattr(obj, parts[-1], value)
            else:
                setattr(obj, parts[-1], str(raw))
        config_mod.save_config(cfg)
        self.destroy()

    def _reset(self) -> None:
        self.cfg = config_mod.default_config()
        self.destroy()
