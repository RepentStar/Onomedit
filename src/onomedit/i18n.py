"""Small, dependency-free localization layer for Onomedit."""

from __future__ import annotations

from contextvars import ContextVar

ZH_CN = "zh-CN"
EN_US = "en-US"
SUPPORTED_LANGUAGES = (ZH_CN, EN_US)
LANGUAGE_NAMES = {ZH_CN: "简体中文", EN_US: "English"}

_language: ContextVar[str] = ContextVar("onomedit_language", default=ZH_CN)


def normalize_language(language: str | None) -> str:
    """Return a supported BCP-47 language tag, falling back to Chinese."""
    value = (language or "").strip().replace("_", "-").lower()
    if value in {"en", "en-us"}:
        return EN_US
    if value in {"zh", "zh-cn", "zh-hans"}:
        return ZH_CN
    return ZH_CN


def set_language(language: str | None) -> str:
    normalized = normalize_language(language)
    _language.set(normalized)
    return normalized


def get_language() -> str:
    return _language.get()


def tr(message: str, /, **values: object) -> str:
    """Translate a source-language message and interpolate named values."""
    translated = _EN_US.get(message, message) if get_language() == EN_US else message
    return translated.format(**values) if values else translated


def choose(zh_cn: str, en_us: str) -> str:
    """Choose one of two longer localized text blocks."""
    return en_us if get_language() == EN_US else zh_cn


_EN_US = {
    # Shared
    "错误: {error}": "Error: {error}",
    "失败: {old} -> {new}: {error}": "Failed: {old} -> {new}: {error}",
    "取消": "Cancel",
    "保存": "Save",
    "重置默认": "Reset defaults",
    "（空）": "(empty)",
    # Main window
    "Onomedit - 批量重命名": "Onomedit - Batch Rename",
    "文件（将按此顺序写入临时文件）": "Files (written to the edit file in this order)",
    "添加文件…": "Add files…",
    "添加文件夹…": "Add folder…",
    "从剪贴板": "From clipboard",
    "清空": "Clear",
    "设置…": "Settings…",
    "恢复上次": "Restore last",
    "路径类型:": "Path type:",
    "展开子文件夹": "Expand subfolders",
    "层级:": "Depth:",
    "开始（打开编辑器）": "Start (open editor)",
    "直接应用规则（跳过编辑器）": "Apply rules directly (skip editor)",
    "预览（进入重命名确认）": "Preview (review rename plan)",
    "就绪": "Ready",
    "就绪（拖拽不可用: {error}）": "Ready (drag and drop unavailable: {error})",
    "选择文件": "Select files",
    "选择文件夹": "Select folder",
    "剪贴板为空或不可读": "The clipboard is empty or unreadable",
    "已添加 {added} 项，共 {total} 项": "Added {added} items; {total} total",
    "已清空": "Cleared",
    "请先添加文件": "Add files first",
    "后台线程：准备文件并等待编辑器…": "Preparing files and waiting for the editor…",
    "出错: {error}": "Error: {error}",
    "目标重名，已中止": "Duplicate targets; operation cancelled",
    "预览共 {count} 项（未执行）": "Preview: {count} items (not applied)",
    "重命名完成: 成功 {success} / 失败 {failed} / 无变化 {skipped}": "Rename complete: {success} succeeded / {failed} failed / {skipped} unchanged",
    "重命名确认已取消": "Rename confirmation cancelled",
    "恢复完成: 成功 {success} / 失败 {failed} / 无变化 {skipped}": "Restore complete: {success} succeeded / {failed} failed / {skipped} unchanged",
    # Settings
    "Onomedit 设置": "Onomedit Settings",
    "界面": "Interface",
    "语言（重启后生效）": "Language (takes effect after restart)",
    "编辑器": "Editor",
    "主编辑器命令": "Primary editor command",
    "备用编辑器命令": "Fallback editor command",
    "等待超时（秒）": "Wait timeout (seconds)",
    "多标签编辑器（直接轮询等待保存）": "Multi-tab editor (poll for saves)",
    "重命名": "Rename",
    "排序依据:": "Sort by:",
    "反转顺序（配合排序依据：降序/倒序）": "Reverse order (descending/reversed)",
    "展开层级（1 = 直接子项）": "Expansion depth (1 = direct children)",
    "行为": "Behavior",
    "打开编辑器": "Open editor",
    "应用规则": "Apply rules",
    "环境变量替换（<n> <d> 等）": "Expand variables (<n>, <d>, etc.)",
    "自动替换规则": "Automatic replacement rules",
    "跳过重命名确认（编辑保存后直接执行）": "Skip confirmation (apply after saving)",
    "完成后退出": "Exit when finished",
    "排除": "Exclude",
    "文件": "Files",
    "目录": "Folders",
    "符号链接": "Symbolic links",
    "只读": "Read-only",
    "隐藏": "Hidden",
    "系统": "System",
    "排除{label}": "Exclude {label}",
    "预览与安全": "Preview and safety",
    "显示差异": "Show differences",
    "显示距离": "Show distance",
    "安全命名（非法字符/保留名/序号）": "Safe names (invalid characters/reserved names/suffixes)",
    # Confirmation window
    "Onomedit - 重命名确认": "Onomedit - Confirm Rename",
    "原文件名": "Original name",
    "新文件名": "New name",
    "差异": "Difference",
    "距离": "Distance",
    "全选": "Select all",
    "全不选": "Select none",
    "执行重命名": "Rename selected",
    "共 {count} 项（已全选）": "{count} items (all selected)",
    "未勾选任何项目": "No items selected",
    "完成: 成功 {success} / 失败 {failed} / 无变化 {skipped}": "Complete: {success} succeeded / {failed} failed / {skipped} unchanged",
    # CLI help
    "结合外部编辑器进行批量文件重命名的工具": "Batch rename files with your external editor",
    "<子命令>": "<command>",
    "<操作>": "<action>",
    "显示帮助信息（可指定子命令）": "Show help (optionally for a command)",
    "子命令名（如 rename / restore）": "Command name (for example rename or restore)",
    "查看/设置配置": "View or change configuration",
    "查看配置、按 KEY 设置任意项、设置编辑器、重置默认。": "View configuration, set any key, configure the editor, or reset defaults.",
    "按 KEY 设置配置项（config set KEY VALUE）": "Set a configuration value (config set KEY VALUE)",
    "按 KEY 设置配置项，支持点路径（如 exclude.hidden），值按类型推断。": "Set a configuration value by key; dotted paths are supported and values are type-inferred.",
    "配置键，支持点路径（如 exclude.hidden）": "Configuration key; dotted paths are supported",
    "值（按类型推断：true/false、数字、文本、JSON）": "Value (true/false, number, text, or JSON)",
    "设置编辑器命令": "Set the editor command",
    "设置外部编辑器命令（可含参数）。多标签编辑器（如 VSCode）可再配合 config set multi_tab true。": "Set the external editor command and optional arguments. For multi-tab editors, also set multi_tab to true.",
    "编辑器命令（可含参数）": "Editor command and optional arguments",
    "重置默认配置": "Reset configuration defaults",
    "把配置恢复为默认值。": "Restore the default configuration.",
    "编辑器模式批量重命名": "Batch rename in editor mode",
    "文件/目录路径（可含通配符）；缺省读剪贴板或 stdin 管道": "File/folder paths (globs allowed); defaults to clipboard or stdin",
    "仅预览（差异/距离），不执行": "Preview differences/distance without applying",
    "跳过编辑器（直接应用规则）": "Skip the editor and apply rules directly",
    "覆盖路径类型": "Override the path type",
    "多标签编辑器：直接轮询等保存": "Multi-tab editor: poll for saves",
    "编辑器等待超时（秒）": "Editor wait timeout (seconds)",
    "恢复重命名": "Restore renames",
    "恢复全部历史": "Restore all history",
    "恢复部分（编辑器筛选日志行）": "Restore selected entries (filter in editor)",
    "查看重命名日志（最近一次）": "View rename history (latest operation)",
    "查看全部历史": "View all history",
    "启动图形界面": "Start the graphical interface",
    "启动图形界面（依赖 ttkbootstrap；未安装时给出提示）。": "Start the graphical interface (requires ttkbootstrap).",
    "版本信息": "Version information",
    "显示版本号。": "Show the version.",
    "生成 shell 补全脚本（pipe 到文件后配置）": "Generate a shell completion script",
    "目标 shell（bash / zsh / pwsh / fish）": "Target shell (bash / zsh / pwsh / fish)",
    # CLI output
    "未知子命令: {topic}（可执行 onomedit help 查看全部）": "Unknown command: {topic} (run onomedit help to list commands)",
    "配置文件: {path}": "Configuration file: {path}",
    "错误: 未知配置键 {key}": "Error: unknown configuration key {key}",
    "编辑器已设置为: {editor}": "Editor set to: {editor}",
    "配置已重置为默认值": "Configuration reset to defaults",
    "错误: 管道未提供任何路径": "Error: stdin did not provide any paths",
    "  差异: {diff}": "  Difference: {diff}",
    "  距离: {distance}": "  Distance: {distance}",
    "（dry-run 预览，共 {count} 项，未执行）": "(dry-run preview: {count} items; not applied)",
    "重命名完成: 成功 {success} / 失败 {failed} / 无变化 {skipped} / 总计 {total}": "Rename complete: {success} succeeded / {failed} failed / {skipped} unchanged / {total} total",
    "没有可恢复的记录（最近一次日志为空）": "Nothing to restore (the latest log is empty)",
    "未配置编辑器，无法进行部分恢复（先 config set-editor）": "An editor is required for partial restore (run config set-editor first)",
    "请在编辑器中删去不想恢复的行，保存后退出…（{path}）": "Delete entries you do not want to restore, then save and close the editor… ({path})",
    "错误: 筛选后的行数超过原始行数，已中止": "Error: the filtered list has more entries than the original; operation cancelled",
    "恢复完成: 成功 {success} / 失败 {failed} / 无变化 {skipped} / 总计 {total}": "Restore complete: {success} succeeded / {failed} failed / {skipped} unchanged / {total} total",
    "启动 Onomedit 图形界面…": "Starting the Onomedit graphical interface…",
    "提示: 输入 onomedit help 查看全部子命令与用法；也可直接使用 CLI（如 onomedit rename *.txt --dry-run）": "Tip: run onomedit help for commands and usage, or use the CLI directly (for example onomedit rename *.txt --dry-run)",
    "已取消": "Cancelled",
    "未知路径类型: {scope}": "Unknown path type: {scope}",
    "需要布尔值（true/false/1/0）": "expected a boolean (true/false/1/0)",
    "编辑器命令为空，请先配置（config set-editor / config set editor）": "The editor command is empty; configure it with config set-editor or config set editor",
    "找不到可执行文件 {executable}，请检查 PATH 或配置编辑器完整路径": "Executable {executable} was not found; check PATH or configure the full editor path",
    "无法启动编辑器 {command}: {error}": "Could not start editor {command}: {error}",
    "编辑器已启动（多标签模式），等待文件保存…": "Editor started in multi-tab mode; waiting for the file to be saved…",
    "检测到启动器型编辑器，等待文件保存（超时后放弃）…": "The editor launcher exited; waiting for the file to be saved…",
    "等待编辑器超时（{timeout}s），按当前内容继续": "Editor wait timed out after {timeout}s; continuing with the current contents",
    "等待保存超时，继续处理": "Save wait timed out; continuing",
    "临时文件行数 {actual} 与文件数 {expected} 不一致，已中止（防止错位改名）": "The edit file has {actual} lines for {expected} files; operation cancelled to prevent mismatched renames",
    "检测到目标重名，已中止（未执行任何重命名）:": "Duplicate targets detected; operation cancelled before any rename:",
    "  目标: {target}": "  Target: {target}",
    "检测到目标重名，已中止（未执行任何重命名）: {groups} 组目标、涉及 {files} 个文件": "Duplicate targets detected; operation cancelled: {groups} target groups involving {files} files",
    "没有可处理的文件（路径不存在或剪贴板为空）": "No files to process (paths do not exist or the clipboard is empty)",
    "应用排除规则后没有可处理的文件": "No files remain after applying exclusion rules",
    "未配置编辑器，请先运行: onomedit config set-editor <命令>\n（或使用 --no-editor 跳过编辑器）": "No editor is configured. Run: onomedit config set-editor <command>\n(or use --no-editor to skip the editor)",
    "已写入临时文件: {path}\n请在编辑器中修改后保存并退出…": "Edit file created: {path}\nEdit it, save, and close the editor…",
}
