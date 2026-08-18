"""数据管理：文件数组构建、子文件夹展开、排除过滤、重命名排序。"""

from __future__ import annotations

import glob
import os

from onomedit.core.pathitem import PathItem
from onomedit.utils import clipboard as clipboard_util
from onomedit.utils import fileattr

# 重命名顺序可选项目（默认不排序）
SORT_BY_DEFAULT = "default"
SORT_BY_NAME = "name"
SORT_BY_PATH = "path"
SORT_BY_MTIME = "mtime"
SORT_BY_CTIME = "ctime"
SORT_BY_SIZE = "size"
SORT_BY_CHOICES: tuple[str, ...] = (
    SORT_BY_DEFAULT,
    SORT_BY_NAME,
    SORT_BY_PATH,
    SORT_BY_MTIME,
    SORT_BY_CTIME,
    SORT_BY_SIZE,
)


def collect_paths(raw_paths: list[str] | None, *, use_clipboard: bool = True) -> list[str]:
    """收集文件路径：参数优先，否则读剪贴板；过滤不存在的路径。

    Windows 上 shell 不展开通配符，程序内主动展开（glob）。
    """
    paths: list[str] = []
    if raw_paths:
        paths.extend(raw_paths)
    elif use_clipboard:
        # 剪贴板：优先 CF_HDROP（资源管理器复制文件/文件夹），否则解析文本路径
        paths.extend(clipboard_util.get_paths())
    expanded: list[str] = []
    for p in paths:
        if glob.has_magic(p):
            expanded.extend(glob.glob(p))
        else:
            expanded.append(p)
    return [p for p in expanded if os.path.exists(p)]


def build_items(paths: list[str]) -> list[PathItem]:
    return [PathItem(p) for p in paths]


def expand_subdirs(items: list[PathItem], depth: int) -> list[PathItem]:
    """把目录项展开为其（限层级）子内容：depth=1 为直接子项，depth=2 再含下一层；
    depth<=0 不展开；展开后的目录项本身不再保留。"""
    if depth <= 0:
        return items
    out: list[PathItem] = []
    for item in items:
        p = item.full
        if not os.path.isdir(p):
            out.append(item)
            continue
        for root, dirs, files in os.walk(p):
            rel = os.path.relpath(root, p)
            level = 0 if rel == "." else rel.count(os.sep) + 1
            if level >= depth:
                # 到达层级边界：剪枝（其内容属于更深层级），本层内容不加入
                dirs[:] = []
                continue
            for d in dirs:
                out.append(PathItem(os.path.join(root, d)))
            for f in files:
                out.append(PathItem(os.path.join(root, f)))
    return out


def display_base(paths: list[str]) -> str:
    """确认窗口显示基准：输入路径的公共父目录。

    单目录输入再向上取一级（选 ``C:\\a\\b`` 展开 → 显示 ``b\\...``）；
    无法计算（不同盘符等）时返回空串。"""
    if not paths:
        return ""
    abs_paths = [os.path.abspath(p) for p in paths]
    try:
        common = os.path.commonpath(abs_paths)
    except ValueError:
        return ""
    if len(paths) == 1:
        # 单个输入：取目录；目录输入则再向上取一级（显示 b\... 而非完整路径）
        common = os.path.dirname(common)
    return common


def sort_items(items: list[PathItem], sort_by: str = SORT_BY_DEFAULT) -> list[PathItem]:
    """按指定项目排序重命名顺序；default 或未知值保持原顺序（不复制列表）。

    名称/路径排序用 ``normcase`` 保证 Windows 上大小写不敏感且结果可预测；
    时间/大小排序取 stat 值，stat 失败（权限等）时按 0 处理不中断流程。
    """
    if sort_by == SORT_BY_DEFAULT or sort_by not in SORT_BY_CHOICES:
        return items
    if sort_by == SORT_BY_NAME:
        key = lambda i: os.path.normcase(i.name)
    elif sort_by == SORT_BY_PATH:
        key = lambda i: os.path.normcase(i.full)
    elif sort_by == SORT_BY_MTIME:
        key = lambda i: _stat_attr(i.full, "st_mtime")
    elif sort_by == SORT_BY_CTIME:
        key = lambda i: _stat_attr(i.full, "st_ctime")
    else:  # SORT_BY_SIZE
        key = lambda i: _stat_attr(i.full, "st_size")
    return sorted(items, key=key)


def _stat_attr(path: str, attr: str):
    try:
        return getattr(os.stat(path), attr)
    except OSError:
        return 0.0


def apply_excludes(items: list[PathItem], exclude) -> list[PathItem]:
    """应用六类排除开关（文件/目录/符号链接/只读/隐藏/系统）。

    符号链接用 ``islink`` 而非存在性；隐藏/系统/只读 Windows 按属性位，
    其他平台由 fileattr 降级。
    """
    out: list[PathItem] = []
    for item in items:
        p = item.full
        if exclude.files and os.path.isfile(p):
            continue
        if exclude.dirs and os.path.isdir(p):
            continue
        if exclude.symlinks and os.path.islink(p):
            continue
        if exclude.readonly and fileattr.is_readonly(p):
            continue
        if exclude.hidden and fileattr.is_hidden(p):
            continue
        if exclude.system and fileattr.is_system(p):
            continue
        out.append(item)
    return out
