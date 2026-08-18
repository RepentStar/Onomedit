"""配置管理：JSON 读写、默认值填充、损坏回退、按 KEY 设置（点路径 + 类型推断）。"""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from onomedit.core.pathitem import PATH_TYPES, PATH_TYPE_EXT, PATH_TYPE_FULL, PATH_TYPE_NAME, PATH_TYPE_STEM  # noqa: F401
from onomedit.core.rules import rule_from_dict, rule_to_dict

CONFIG_VERSION = 1


@dataclass
class ExcludeOptions:
    files: bool = False
    dirs: bool = False
    symlinks: bool = True
    readonly: bool = False
    hidden: bool = True
    system: bool = True


# ``rename --exclude`` 命令行 tag → ExcludeOptions 字段映射（别名成对）
EXCLUDE_TAG_MAP: dict[str, str] = {
    "f": "files",
    "file": "files",
    "d": "dirs",
    "dir": "dirs",
    "l": "symlinks",
    "link": "symlinks",
    "r": "readonly",
    "readonly": "readonly",
    "h": "hidden",
    "hidden": "hidden",
    "s": "system",
    "system": "system",
}
# argparse choices 用：全部合法 tag
EXCLUDE_TAGS: tuple[str, ...] = tuple(EXCLUDE_TAG_MAP)


def merge_exclude_tags(base: ExcludeOptions, tags: Iterable[str]) -> ExcludeOptions:
    """把 ``--exclude`` 的 tag 合并进排除配置：在 base 基础上打开对应位。

    返回新的 ExcludeOptions，不改动 base（保证"临时排除"不影响持久化配置）；
    未列出的排除位沿用 base 的当前值。
    """
    merged = ExcludeOptions(**vars(base))
    for tag in tags:
        setattr(merged, EXCLUDE_TAG_MAP[tag], True)
    return merged


@dataclass
class PreviewOptions:
    diff: bool = False
    distance: bool = False


@dataclass
class SafetyOptions:
    sanitize: bool = True


@dataclass
class Config:
    version: int = CONFIG_VERSION
    # 编辑器（主/备用）与等待
    editor: str = ""
    editor_alt: str = ""
    editor_timeout: float = 120.0
    multi_tab: bool = False
    # 两个独立开关：是否打开编辑器 / 是否应用规则
    open_editor: bool = True
    apply_rules: bool = True
    # 路径类型（四档之一，默认"不带扩展名"）
    path_type: str = PATH_TYPE_STEM
    # 重命名顺序（default 原顺序 / name / path / mtime / ctime / size）
    sort_by: str = "default"
    # 环境变量与自动替换
    enable_envvars: bool = True
    enable_auto_rules: bool = True
    # 子文件夹展开（默认开启，层级 10 ≈ 全递归）
    expand_subdirs: bool = True
    subdirs_depth: int = 10
    # 排除 / 预览 / 安全
    exclude: ExcludeOptions = field(default_factory=ExcludeOptions)
    preview: PreviewOptions = field(default_factory=PreviewOptions)
    safety: SafetyOptions = field(default_factory=SafetyOptions)
    # GUI：完成后退出 / 跳过重命名确认
    exit_after: bool = True
    skip_confirmation: bool = True
    # Shell 属性 / 自动替换规则 / 临时目录（空 = 系统临时）
    shell_props: list = field(default_factory=list)
    auto_rules: list = field(default_factory=list)
    temp_dir: str = ""


def config_dir() -> Path:
    """跨平台配置目录：Windows %APPDATA%，macOS Application Support，其他 XDG。"""
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(base) / "Onomedit"


def config_path() -> Path:
    return config_dir() / "config.json"


def log_dir() -> Path:
    return config_dir() / "log"


def default_config() -> Config:
    return Config()


def detect_default_editor() -> str:
    """按系统探测可用的默认编辑器命令（首次启动自动配置，避免 editor 为空报错）。"""
    if os.name == "nt":
        return _detect_win_editor()
    if sys.platform == "darwin":
        return _detect_macos_editor()
    return _detect_linux_editor()


def _detect_win_editor() -> str:
    # 1) 系统自带记事本（优先，Windows 必定存在）
    if shutil.which("notepad"):
        return "notepad"
    # 2) VSCode（-w 等待文件关闭）
    if shutil.which("code"):
        return "code -w"
    return ""


def _detect_macos_editor() -> str:
    if os.path.exists("/System/Applications/TextEdit.app"):
        return "open -W -a TextEdit"
    for name in ("subl", "code"):
        if shutil.which(name):
            return f"{name} -w"
    return shutil.which("vim") or ""


def _detect_linux_editor() -> str:
    for name in ("nano", "vi", "kate"):
        if shutil.which(name):
            return name
    return os.environ.get("EDITOR", "")


def _ensure_default_editor(cfg: Config) -> None:
    """editor 为空时探测系统默认编辑器并填入（探测失败保持空）。"""
    if not cfg.editor.strip():
        detected = detect_default_editor()
        if detected:
            cfg.editor = detected


def _rule_default() -> list:
    return []


def to_dict(cfg: Config) -> dict:
    """Config → 可 JSON 序列化的 dict。"""
    data = {}
    for f in cfg.__dataclass_fields__:  # type: ignore[attr-defined]
        value = getattr(cfg, f)
        if isinstance(value, (ExcludeOptions, PreviewOptions, SafetyOptions)):
            data[f] = value.__dict__.copy()
        elif f == "auto_rules":
            data[f] = [rule_to_dict(r) for r in value]
        else:
            data[f] = value
    return data


def from_dict(data: dict) -> Config:
    """dict → Config，缺失键用默认值填充；未知键忽略。"""
    base = default_config()
    flat = {f: getattr(base, f) for f in base.__dataclass_fields__}  # type: ignore[attr-defined]
    flat.update({k: v for k, v in data.items() if k in flat})
    for key in ("exclude", "preview", "safety"):
        sub = flat.get(key)
        if isinstance(sub, dict):
            cls = {"exclude": ExcludeOptions, "preview": PreviewOptions, "safety": SafetyOptions}[key]
            defaults = cls()
            merged = {f: sub.get(f, getattr(defaults, f)) for f in defaults.__dict__}
            flat[key] = cls(**merged)
    rules = []
    for item in flat.get("auto_rules") or []:
        try:
            rules.append(rule_from_dict(item))
        except (KeyError, ValueError, TypeError):
            continue
    flat["auto_rules"] = rules
    return Config(**flat)


def load_config() -> Config:
    """读取配置；缺失/损坏时回退默认值（损坏时先备份原文件）并写回。

    首次启动（缺失/损坏/editor 为空）时自动探测系统默认编辑器，
    避免 editor 为空导致重命名流程报错。
    """
    path = config_path()
    if not path.exists():
        cfg = default_config()
        _ensure_default_editor(cfg)
        save_config(cfg)
        return cfg
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("config root is not an object")
        cfg = from_dict(raw)
        # 版本迁移
        cfg = migrate(cfg)
        # editor 为空（旧配置/被清空）：探测并补写
        if not cfg.editor.strip():
            _ensure_default_editor(cfg)
            save_config(cfg)
        return cfg
    except (OSError, ValueError, json.JSONDecodeError):
        # 损坏回退：备份后写回默认
        try:
            backup = path.with_suffix(".json.bak")
            os.replace(path, backup)
        except OSError:
            pass
        cfg = default_config()
        _ensure_default_editor(cfg)
        save_config(cfg)
        return cfg


def save_config(cfg: Config) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(to_dict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def migrate(cfg: Config) -> Config:
    """配置版本迁移；当前仅版本 1。"""
    if cfg.version < CONFIG_VERSION:
        cfg.version = CONFIG_VERSION
        save_config(cfg)
    return cfg


def _coerce(raw: str, current) -> object:
    """按目标字段当前值类型推断输入。"""
    if isinstance(current, bool):
        low = raw.strip().lower()
        if low in ("true", "1", "yes", "on"):
            return True
        if low in ("false", "0", "no", "off"):
            return False
        raise ValueError("需要布尔值（true/false/1/0）")
    if isinstance(current, int):
        return int(raw.strip())
    if isinstance(current, float):
        return float(raw.strip())
    if isinstance(current, (list, dict)):
        return json.loads(raw)
    return raw


def set_value(cfg: Config, dotted_path: str, raw: str) -> str:
    """按点路径设置配置项（如 ``exclude.hidden``），返回描述信息。

    类型按当前值推断（bool/int/float/str/list/dict）。找不到路径抛 KeyError。
    """
    parts = dotted_path.split(".")
    obj: object = cfg
    for part in parts[:-1]:
        if isinstance(obj, (Config, ExcludeOptions, PreviewOptions, SafetyOptions)):
            try:
                obj = getattr(obj, part)
            except AttributeError:
                raise KeyError(dotted_path) from None
        elif isinstance(obj, dict):
            if part not in obj:
                raise KeyError(dotted_path)
            obj = obj[part]
        else:
            raise KeyError(dotted_path)
    try:
        current = (
            getattr(obj, parts[-1])
            if isinstance(obj, (Config, ExcludeOptions, PreviewOptions, SafetyOptions))
            else obj[parts[-1]]
        )
    except (AttributeError, KeyError):
        raise KeyError(dotted_path) from None
    value = _coerce(raw, current)
    # auto_rules 走规则反序列化
    if dotted_path == "auto_rules" and isinstance(value, list):
        value = [rule_from_dict(item) for item in value]
    if isinstance(obj, (Config, ExcludeOptions, PreviewOptions, SafetyOptions)):
        setattr(obj, parts[-1], value)
    else:
        obj[parts[-1]] = value
    return f"{dotted_path} = {json.dumps(value, ensure_ascii=False, default=str)}"
