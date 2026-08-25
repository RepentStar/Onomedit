"""设置窗口：编辑并保存配置。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from onomedit.core import collection
from onomedit.core import config as config_mod
from onomedit.core.pathitem import PATH_TYPES
from onomedit.i18n import LANGUAGE_NAMES, SUPPORTED_LANGUAGES, set_language, tr


class SettingsWindow(tk.Toplevel):
    """配置编辑对话框（保存后写回配置文件）。"""

    def __init__(self, master=None, cfg: config_mod.Config | None = None):
        super().__init__(master)
        self.cfg = cfg or config_mod.load_config()
        set_language(self.cfg.language)
        self.title(tr("Onomedit 设置"))
        self.resizable(False, False)
        self._vars: dict[str, tk.Variable] = {}
        self._build()
        self.transient(master)
        self.grab_set()

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)

        locale_row = ttk.LabelFrame(body, text=tr("界面"), padding=8)
        locale_row.pack(fill="x", **pad)
        ttk.Label(locale_row, text=tr("语言（重启后生效）")).grid(
            row=0, column=0, sticky="w", pady=2
        )
        language_values = [
            f"{LANGUAGE_NAMES[tag]} ({tag})" for tag in SUPPORTED_LANGUAGES
        ]
        language_var = tk.StringVar(
            value=f"{LANGUAGE_NAMES[self.cfg.language]} ({self.cfg.language})"
        )
        ttk.Combobox(
            locale_row,
            textvariable=language_var,
            values=language_values,
            state="readonly",
            width=20,
        ).grid(row=0, column=1, sticky="w", pady=2)
        self._vars["language"] = language_var

        row = ttk.LabelFrame(body, text=tr("编辑器"), padding=8)
        row.pack(fill="x", **pad)
        self._entry("editor", tr("主编辑器命令"), row)
        self._entry("editor_alt", tr("备用编辑器命令"), row)
        self._entry("editor_timeout", tr("等待超时（秒）"), row)
        self._check("multi_tab", tr("多标签编辑器（直接轮询等待保存）"), row)

        row2 = ttk.LabelFrame(body, text=tr("重命名"), padding=8)
        row2.pack(fill="x", **pad)
        ttk.Label(row2, text=tr("路径类型:")).grid(row=0, column=0, sticky="w", pady=2)
        path_var = tk.StringVar(value=self.cfg.path_type)
        ttk.Combobox(
            row2,
            textvariable=path_var,
            values=list(PATH_TYPES),
            state="readonly",
            width=20,
        ).grid(row=0, column=1, sticky="w", pady=2)
        self._vars["path_type"] = path_var
        ttk.Label(row2, text=tr("排序依据:")).grid(row=1, column=0, sticky="w", pady=2)
        sort_var = tk.StringVar(value=self.cfg.sort_by)
        ttk.Combobox(
            row2,
            textvariable=sort_var,
            values=list(collection.SORT_BY_CHOICES),
            state="readonly",
            width=20,
        ).grid(row=1, column=1, sticky="w", pady=2)
        self._vars["sort_by"] = sort_var
        self._check("sort_reverse", tr("反转顺序（配合排序依据：降序/倒序）"), row2)
        self._check("expand_subdirs", tr("展开子文件夹"), row2)
        self._entry("subdirs_depth", tr("展开层级（1 = 直接子项）"), row2)

        row3 = ttk.LabelFrame(body, text=tr("行为"), padding=8)
        row3.pack(fill="x", **pad)
        self._check("open_editor", tr("打开编辑器"), row3)
        self._check("apply_rules", tr("应用规则"), row3)
        self._check("enable_envvars", tr("环境变量替换（<n> <d> 等）"), row3)
        self._check("enable_auto_rules", tr("自动替换规则"), row3)
        self._check(
            "skip_confirmation", tr("跳过重命名确认（编辑保存后直接执行）"), row3
        )
        self._check("exit_after", tr("完成后退出"), row3)

        row4 = ttk.LabelFrame(body, text=tr("排除"), padding=8)
        row4.pack(fill="x", **pad)
        for key, label in (
            ("files", "文件"),
            ("dirs", "目录"),
            ("symlinks", "符号链接"),
            ("readonly", "只读"),
            ("hidden", "隐藏"),
            ("system", "系统"),
        ):
            self._check(f"exclude.{key}", tr("排除{label}", label=tr(label)), row4)

        row5 = ttk.LabelFrame(body, text=tr("预览与安全"), padding=8)
        row5.pack(fill="x", **pad)
        self._check("preview.diff", tr("显示差异"), row5)
        self._check("preview.distance", tr("显示距离"), row5)
        self._check("safety.sanitize", tr("安全命名（非法字符/保留名/序号）"), row5)

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(8, 0))
        ttk.Button(btns, text=tr("保存"), command=self._save).pack(side="right", padx=4)
        ttk.Button(btns, text=tr("重置默认"), command=self._reset).pack(
            side="right", padx=4
        )
        ttk.Button(btns, text=tr("取消"), command=self.destroy).pack(
            side="right", padx=4
        )

    def _entry(self, key: str, label: str, parent: ttk.Frame) -> None:
        row = len(parent.grid_slaves()) // 2
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        var = tk.StringVar(value=str(getattr(self.cfg, key)))
        ttk.Entry(parent, textvariable=var, width=40).grid(
            row=row, column=1, sticky="we", pady=2
        )
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

    def _save(self) -> None:
        cfg = self.cfg
        for dotted, var in self._vars.items():
            obj = cfg
            parts = dotted.split(".")
            for p in parts[:-1]:
                obj = getattr(obj, p)
            raw = var.get()
            if dotted == "language":
                raw = str(raw).rsplit("(", 1)[-1].rstrip(")")
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
