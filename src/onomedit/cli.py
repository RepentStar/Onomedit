"""CLI：子命令分发（先于位置参数解析）+ 各子命令实现。

子命令：
    config           查看/设置配置
    config set       按 KEY 设置任意项（点路径 + 类型推断）
    config set-editor 设置编辑器命令
    config reset     重置默认配置
    rename           编辑器模式批量重命名
    restore          恢复上次/全部/部分
    history          查看重命名日志
    gui              启动图形界面
    version          版本信息
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from onomedit import __version__
from onomedit.core import config as config_mod
from onomedit.core import editor, tempfile_mgr
from onomedit.core.logger import SEPARATOR, RenameLogger
from onomedit.core.pipeline import PipelineError, RenamePipeline, restore


def _ensure_utf8() -> None:
    """Windows 控制台中文输出依赖 UTF-8（历史教训：GBK 解码中文会崩溃）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - 尽力而为
            pass


# ---------------------------------------------------------------- 构建解析器
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="onomedit",
        description="结合外部编辑器进行批量文件重命名的工具",
        epilog=(
            "示例:\n"
            "  onomedit help                     查看本帮助\n"
            "  onomedit help rename              查看 rename 子命令帮助\n"
            "  onomedit config set-editor notepad  配置编辑器后即可开始\n"
            "  onomedit rename *.jpg --dry-run   预览（差异/距离），不执行\n"
            "  onomedit restore                  恢复上一次重命名"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    sub = parser.add_subparsers(dest="command", metavar="<子命令>")
    sub.required = True

    # help
    p_help = sub.add_parser("help", help="显示帮助信息（可指定子命令）", add_help=False)
    p_help.add_argument("topic", nargs="?", help="子命令名（如 rename / restore）")
    p_help.set_defaults(handler=_cmd_help)

    # config（默认查看；子操作：set / set-editor / reset）
    p_config = sub.add_parser(
        "config",
        help="查看/设置配置",
        description="查看配置、按 KEY 设置任意项、设置编辑器、重置默认。",
        epilog="示例:\n  onomedit config\n  onomedit config set path_type name\n  onomedit config set exclude.hidden false\n  onomedit config set-editor notepad\n  onomedit config reset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_config.set_defaults(handler=_cmd_config)
    cfg_sub = p_config.add_subparsers(dest="config_command", metavar="<操作>")

    p_set = cfg_sub.add_parser(
        "set",
        help="按 KEY 设置配置项（config set KEY VALUE）",
        description="按 KEY 设置配置项，支持点路径（如 exclude.hidden），值按类型推断。",
        epilog="示例:\n  onomedit config set editor_timeout 60\n  onomedit config set exclude.hidden false\n  onomedit config set auto_rules '[{\"scope\":\"stem\",\"kind\":\"replace\",\"find\":\"a\",\"replace\":\"b\"}]'",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_set.add_argument("key", help="配置键，支持点路径（如 exclude.hidden）")
    p_set.add_argument("value", help="值（按类型推断：true/false、数字、文本、JSON）")
    p_set.set_defaults(handler=_cmd_config_set)

    p_set_editor = cfg_sub.add_parser(
        "set-editor",
        help="设置编辑器命令",
        description="设置外部编辑器命令（可含参数）。多标签编辑器（如 VSCode）可再配合 config set multi_tab true。",
        epilog="示例:\n  onomedit config set-editor notepad\n  onomedit config set-editor code -w\n  onomedit config set-editor \"C:\\Program Files\\Notepad++\\notepad++.exe\"",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_set_editor.add_argument("command", nargs="+", help="编辑器命令（可含参数）")
    p_set_editor.set_defaults(handler=_cmd_set_editor)

    p_reset = cfg_sub.add_parser(
        "reset",
        help="重置默认配置",
        description="把配置恢复为默认值。",
        epilog="示例:\n  onomedit config reset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_reset.set_defaults(handler=_cmd_config_reset)

    # rename
    p_rename = sub.add_parser(
        "rename",
        help="编辑器模式批量重命名",
        description=(
            "把文件名列表写入临时文件并拉起编辑器；用户修改保存后读回并批量重命名。\n"
            "路径可含通配符；不提供路径时从剪贴板读取。"
        ),
        epilog=(
            "示例:\n"
            "  onomedit rename a.txt b.txt\n"
            "  onomedit rename *.jpg --dry-run\n"
            "  onomedit rename --no-editor --path-type name  仅应用规则不拉起编辑器\n"
            "  onomedit rename *.txt --exclude h d --dry-run  临时排除隐藏文件与目录"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_rename.add_argument("paths", nargs="*", help="文件/目录路径（可含通配符）；缺省读剪贴板")
    p_rename.add_argument("--dry-run", action="store_true", help="仅预览（差异/距离），不执行")
    p_rename.add_argument("--no-editor", action="store_true", help="跳过编辑器（直接应用规则）")
    p_rename.add_argument("--path-type", choices=config_mod.PATH_TYPES, help="覆盖路径类型")
    p_rename.add_argument("--multi-tab", action="store_true", help="多标签编辑器：直接轮询等保存")
    p_rename.add_argument("--timeout", type=float, help="编辑器等待超时（秒）")
    p_rename.add_argument(
        "--exclude",
        nargs="+",
        action="append",
        choices=config_mod.EXCLUDE_TAGS,
        metavar="TYPE",
        help=(
            "临时排除路径类型（可多次/多值）：f/file 文件、d/dir 目录、l/link 符号链接、"
            "r/readonly 只读、h/hidden 隐藏、s/system 系统；在现有配置 exclude.* 基础上追加"
        ),
    )
    p_rename.set_defaults(handler=_cmd_rename)

    # restore
    p_restore = sub.add_parser(
        "restore",
        help="恢复重命名",
        description="按日志反向恢复：默认恢复最近一次；--all 恢复全部历史；--partial 在编辑器中筛选日志行。",
        epilog="示例:\n  onomedit restore\n  onomedit restore --all\n  onomedit restore --partial",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_restore.add_argument("--all", action="store_true", help="恢复全部历史")
    p_restore.add_argument("--partial", action="store_true", help="恢复部分（编辑器筛选日志行）")
    p_restore.set_defaults(handler=_cmd_restore)

    # history
    p_history = sub.add_parser(
        "history",
        help="查看重命名日志（最近一次）",
        description="显示重命名记录（旧路径<-->新路径）；--all 显示全部历史。",
        epilog="示例:\n  onomedit history\n  onomedit history --all",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_history.add_argument("--all", action="store_true", help="查看全部历史")
    p_history.set_defaults(handler=_cmd_history)

    # gui
    p_gui = sub.add_parser(
        "gui",
        help="启动图形界面",
        description="启动图形界面（依赖 ttkbootstrap；未安装时给出提示）。",
        epilog="示例:\n  onomedit gui",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_gui.set_defaults(handler=_cmd_gui)

    # version
    p_version = sub.add_parser(
        "version",
        help="版本信息",
        description="显示版本号。",
        epilog="示例:\n  onomedit version",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_version.set_defaults(handler=_cmd_version)

    return parser


# ---------------------------------------------------------------- 子命令实现
def _cmd_help(args) -> int:
    """显示帮助；可指定子命令（``onomedit help rename``）。"""
    parser = build_parser()
    if args.topic:
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                sub = action.choices.get(args.topic)
                if sub is None:
                    print(f"未知子命令: {args.topic}（可执行 onomedit help 查看全部）", file=sys.stderr)
                    return 1
                sub.print_help()
                return 0
    parser.print_help()
    return 0


def _cmd_config(args) -> int:
    cfg = config_mod.load_config()
    print(json.dumps(config_mod.to_dict(cfg), ensure_ascii=False, indent=2))
    print(f"\n配置文件: {config_mod.config_path()}")
    return 0


def _cmd_config_set(args) -> int:
    cfg = config_mod.load_config()
    try:
        desc = config_mod.set_value(cfg, args.key, args.value)
    except KeyError:
        print(f"错误: 未知配置键 {args.key!r}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    config_mod.save_config(cfg)
    print(desc)
    return 0


def _cmd_set_editor(args) -> int:
    cfg = config_mod.load_config()
    cfg.editor = " ".join(args.command)
    config_mod.save_config(cfg)
    print(f"编辑器已设置为: {cfg.editor}")
    return 0


def _cmd_config_reset(args) -> int:
    cfg = config_mod.default_config()
    config_mod.save_config(cfg)
    print("配置已重置为默认值")
    return 0


def _cmd_rename(args) -> int:
    cfg = config_mod.load_config()
    if args.path_type:
        cfg.path_type = args.path_type
    if args.multi_tab:
        cfg.multi_tab = True
    if args.timeout is not None:
        cfg.editor_timeout = args.timeout
    if args.no_editor:
        cfg.open_editor = False
    if args.exclude:
        # 扁平化多组 tag，在现有配置基础上追加（不改配置文件）
        tags = [tag for group in args.exclude for tag in group]
        cfg.exclude = config_mod.merge_exclude_tags(cfg.exclude, tags)

    pipeline = RenamePipeline(cfg, on_status=lambda msg: print(msg, flush=True))
    try:
        outcome = pipeline.run_editor_mode(args.paths, dry_run=args.dry_run)
    except PipelineError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except tempfile_mgr.LineCountError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except editor.EditorError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    if outcome.dry_run:
        if outcome.preview is not None:
            for row in outcome.preview:
                extra = ""
                if row.diff:
                    extra += f"  差异: {row.diff}"
                if row.distance:
                    extra += f"  距离: {row.distance}"
                print(f"{row.old}  →  {row.new}{extra}")
        else:
            for old, new in outcome.pairs:
                print(f"{old}  →  {new}")
        print(f"（dry-run 预览，共 {len(outcome.pairs)} 项，未执行）")
        return 0

    result = outcome.result
    print(
        f"重命名完成: 成功 {len(result.success)} / 失败 {len(result.failed)}"
        f" / 无变化 {len(result.skipped)} / 总计 {result.total}"
    )
    for old, new, err in result.failed:
        print(f"失败: {old} -> {new}: {err}", file=sys.stderr)
    return 0 if not result.failed else 1


def _cmd_restore(args) -> int:
    cfg = config_mod.load_config()
    log = RenameLogger(config_mod.log_dir())
    if args.partial:
        pairs = log.read_last()
        if not pairs:
            print("没有可恢复的记录（最近一次日志为空）", file=sys.stderr)
            return 1
        lines = [f"{old}{SEPARATOR}{new}" for old, new in pairs]
        temp_dir = cfg.temp_dir or None
        import tempfile as _tempfile

        fd, path = _tempfile.mkstemp(prefix="onomedit_restore_", suffix=".txt", dir=temp_dir, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                for line in lines:
                    f.write(line + "\n")
            if not cfg.editor.strip():
                print("未配置编辑器，无法进行部分恢复（先 config set-editor）", file=sys.stderr)
                return 1
            sig = tempfile_mgr.signature(path)
            print(f"请在编辑器中删去不想恢复的行，保存后退出…（{path}）")
            editor.launch_and_wait(
                cfg.editor, path, sig, multi_tab=cfg.multi_tab, timeout=cfg.editor_timeout
            )
            kept = tempfile_mgr.read_lines(path, len(lines))
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        if len(kept) > len(lines):
            print("错误: 筛选后的行数超过原始行数，已中止", file=sys.stderr)
            return 1
        result = restore(log, partial_lines=kept)
    else:
        result = restore(log, all_history=args.all)

    print(
        f"恢复完成: 成功 {len(result.success)} / 失败 {len(result.failed)}"
        f" / 无变化 {len(result.skipped)} / 总计 {result.total}"
    )
    for old, new, err in result.failed:
        print(f"失败: {old} -> {new}: {err}", file=sys.stderr)
    return 0 if not result.failed else 1


def _cmd_history(args) -> int:
    log = RenameLogger(config_mod.log_dir())
    pairs = log.read_history() if args.all else log.read_last()
    if not pairs:
        print("（空）")
        return 0
    for old, new in pairs:
        print(f"{old}{SEPARATOR}{new}")
    return 0


def _cmd_gui(args) -> int:
    try:
        from onomedit.gui.app import main as gui_main
    except ImportError as e:
        print(
            "错误: GUI 依赖 ttkbootstrap 未安装。请安装: uv pip install ttkbootstrap "
            f"（{e}）",
            file=sys.stderr,
        )
        return 1
    gui_main()
    return 0


def _cmd_version(args) -> int:
    print(f"onomedit {__version__}")
    return 0


# ---------------------------------------------------------------- 入口
def main(argv: list[str] | None = None) -> int:
    _ensure_utf8()
    args_list = list(sys.argv[1:] if argv is None else argv)
    if not args_list:
        # 无参数：默认启动 GUI，控制台提示 CLI 用法
        print("启动 Onomedit 图形界面…")
        print("提示: 输入 onomedit help 查看全部子命令与用法；也可直接使用 CLI（如 onomedit rename *.txt --dry-run）")
        return _cmd_gui(None)
    parser = build_parser()
    args = parser.parse_args(args_list)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    try:
        return handler(args) or 0
    except KeyboardInterrupt:
        print("\n已取消", file=sys.stderr)
        return 130
