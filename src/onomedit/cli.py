"""CLI：子命令分发（先于位置参数解析）+ 各子命令实现。

子命令：config / rename / restore / history / gui / version / help / completion。"""

from __future__ import annotations

import argparse
import json
import os
import sys

from onomedit import __version__
from onomedit.core import collection, completion, editor, tempfile_mgr
from onomedit.core import config as config_mod
from onomedit.core.logger import SEPARATOR, RenameLogger
from onomedit.core.pipeline import PipelineError, RenamePipeline, restore
from onomedit.i18n import choose, set_language, tr


def _ensure_utf8() -> None:
    """Windows 控制台中文输出依赖 UTF-8（历史教训：GBK 解码中文会崩溃）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - 尽力而为
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="onomedit",
        description=tr("结合外部编辑器进行批量文件重命名的工具"),
        epilog=choose(
            "示例:\n"
            "  onomedit help                     查看本帮助\n"
            "  onomedit help rename              查看 rename 子命令帮助\n"
            "  onomedit config set-editor notepad  配置编辑器后即可开始\n"
            "  onomedit rename *.jpg --dry-run   预览（差异/距离），不执行\n"
            "  onomedit restore                  恢复上一次重命名",
            "Examples:\n"
            "  onomedit help                     Show this help\n"
            "  onomedit help rename              Show help for rename\n"
            "  onomedit config set-editor notepad  Configure an editor\n"
            "  onomedit rename *.jpg --dry-run   Preview without applying\n"
            "  onomedit restore                  Restore the latest rename",
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    sub = parser.add_subparsers(dest="command", metavar=tr("<子命令>"))
    sub.required = True

    p_help = sub.add_parser(
        "help", help=tr("显示帮助信息（可指定子命令）"), add_help=False
    )
    p_help.add_argument("topic", nargs="?", help=tr("子命令名（如 rename / restore）"))
    p_help.set_defaults(handler=_cmd_help)

    # config（默认查看；子操作：set / set-editor / reset）
    p_config = sub.add_parser(
        "config",
        help=tr("查看/设置配置"),
        description=tr("查看配置、按 KEY 设置任意项、设置编辑器、重置默认。"),
        epilog="示例:\n  onomedit config\n  onomedit config set path_type name\n  onomedit config set exclude.hidden false\n  onomedit config set-editor notepad\n  onomedit config reset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_config.set_defaults(handler=_cmd_config)
    cfg_sub = p_config.add_subparsers(dest="config_command", metavar=tr("<操作>"))

    p_set = cfg_sub.add_parser(
        "set",
        help=tr("按 KEY 设置配置项（config set KEY VALUE）"),
        description=tr(
            "按 KEY 设置配置项，支持点路径（如 exclude.hidden），值按类型推断。"
        ),
        epilog='示例:\n  onomedit config set editor_timeout 60\n  onomedit config set exclude.hidden false\n  onomedit config set auto_rules \'[{"scope":"stem","kind":"replace","find":"a","replace":"b"}]\'',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_set.add_argument("key", help=tr("配置键，支持点路径（如 exclude.hidden）"))
    p_set.add_argument(
        "value", help=tr("值（按类型推断：true/false、数字、文本、JSON）")
    )
    p_set.set_defaults(handler=_cmd_config_set)

    p_set_editor = cfg_sub.add_parser(
        "set-editor",
        help=tr("设置编辑器命令"),
        description=tr(
            "设置外部编辑器命令（可含参数）。多标签编辑器（如 VSCode）可再配合 config set multi_tab true。"
        ),
        epilog='示例:\n  onomedit config set-editor notepad\n  onomedit config set-editor code -w\n  onomedit config set-editor "C:\\Program Files\\Notepad++\\notepad++.exe"',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_set_editor.add_argument("command", nargs="+", help=tr("编辑器命令（可含参数）"))
    p_set_editor.set_defaults(handler=_cmd_set_editor)

    p_reset = cfg_sub.add_parser(
        "reset",
        help=tr("重置默认配置"),
        description=tr("把配置恢复为默认值。"),
        epilog="示例:\n  onomedit config reset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_reset.set_defaults(handler=_cmd_config_reset)

    p_rename = sub.add_parser(
        "rename",
        help=tr("编辑器模式批量重命名"),
        description=choose(
            "把文件名列表写入临时文件并拉起编辑器；用户修改保存后读回并批量重命名。\n"
            "路径可含通配符；不提供路径时从剪贴板读取；若 stdin 来自管道则读其行作路径。",
            "Write names to an edit file, open it in your editor, then apply the saved names.\n"
            "Paths may include globs; input defaults to the clipboard or piped stdin.",
        ),
        epilog=choose(
            "示例:\n"
            "  onomedit rename a.txt b.txt\n"
            "  onomedit rename *.jpg --dry-run\n"
            "  onomedit rename --no-editor --path-type name  仅应用规则不拉起编辑器\n"
            "  onomedit rename *.txt --exclude h d --dry-run  临时排除隐藏文件与目录\n"
            "  dir /b *.jpg | onomedit rename  从管道读入路径（编辑模式下重命名）",
            "Examples:\n"
            "  onomedit rename a.txt b.txt\n"
            "  onomedit rename *.jpg --dry-run\n"
            "  onomedit rename --no-editor --path-type name  Apply rules without an editor\n"
            "  onomedit rename *.txt --exclude h d --dry-run  Exclude hidden files and folders\n"
            "  dir /b *.jpg | onomedit rename  Read paths from stdin",
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_rename.add_argument(
        "paths",
        nargs="*",
        help=tr("文件/目录路径（可含通配符）；缺省读剪贴板或 stdin 管道"),
    )
    p_rename.add_argument(
        "--dry-run", action="store_true", help=tr("仅预览（差异/距离），不执行")
    )
    p_rename.add_argument(
        "--no-editor", action="store_true", help=tr("跳过编辑器（直接应用规则）")
    )
    p_rename.add_argument(
        "--path-type", choices=config_mod.PATH_TYPES, help=tr("覆盖路径类型")
    )
    p_rename.add_argument(
        "--multi-tab", action="store_true", help=tr("多标签编辑器：直接轮询等保存")
    )
    p_rename.add_argument("--timeout", type=float, help=tr("编辑器等待超时（秒）"))
    p_rename.add_argument(
        "--sort-by",
        choices=collection.SORT_BY_CHOICES,
        metavar="KEY",
        help=choose(
            "临时重命名顺序："
            "default 原顺序、name 名称、path 路径、mtime 修改时间、ctime 创建时间、size 大小",
            "Temporary rename order: default, name, path, mtime, ctime, or size",
        ),
    )
    p_rename.add_argument(
        "--reverse",
        action="store_true",
        help=choose(
            "临时反转重命名顺序：与 --sort-by 组合时按排序键降序，否则反转原顺序",
            "Reverse the input order, or sort descending when used with --sort-by",
        ),
    )
    p_rename.add_argument(
        "--depth",
        type=int,
        metavar="N",
        help=choose(
            "临时目录搜索深度：1 = 直接子项，0 = 不展开；指定时临时开启子文件夹展开",
            "Temporary folder depth: 1 = direct children, 0 = do not expand",
        ),
    )
    p_rename.add_argument(
        "--exclude",
        nargs="+",
        action="append",
        choices=config_mod.EXCLUDE_TAGS,
        metavar="TYPE",
        help=choose(
            "临时排除路径类型（可多次/多值）：f/file 文件、d/dir 目录、l/link 符号链接、"
            "r/readonly 只读、h/hidden 隐藏、s/system 系统；在现有配置 exclude.* 基础上追加",
            "Temporarily exclude types (repeatable): f/file, d/dir, l/link, r/readonly, h/hidden, s/system",
        ),
    )
    p_rename.set_defaults(handler=_cmd_rename)

    p_restore = sub.add_parser(
        "restore",
        help=tr("恢复重命名"),
        description=choose(
            "按日志反向恢复：默认恢复最近一次；--all 恢复全部历史；--partial 在编辑器中筛选日志行。",
            "Restore renames from the log. Use --all for all history or --partial to filter entries in an editor.",
        ),
        epilog="示例:\n  onomedit restore\n  onomedit restore --all\n  onomedit restore --partial",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_restore.add_argument("--all", action="store_true", help=tr("恢复全部历史"))
    p_restore.add_argument(
        "--partial", action="store_true", help=tr("恢复部分（编辑器筛选日志行）")
    )
    p_restore.set_defaults(handler=_cmd_restore)

    p_history = sub.add_parser(
        "history",
        help=tr("查看重命名日志（最近一次）"),
        description=choose(
            "显示重命名记录（旧路径<-->新路径）；--all 显示全部历史。",
            "Show rename records (old path <--> new path); --all shows all history.",
        ),
        epilog="示例:\n  onomedit history\n  onomedit history --all",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_history.add_argument("--all", action="store_true", help=tr("查看全部历史"))
    p_history.set_defaults(handler=_cmd_history)

    p_gui = sub.add_parser(
        "gui",
        help=tr("启动图形界面"),
        description=tr("启动图形界面（依赖 ttkbootstrap；未安装时给出提示）。"),
        epilog="示例:\n  onomedit gui",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_gui.set_defaults(handler=_cmd_gui)

    p_version = sub.add_parser(
        "version",
        help=tr("版本信息"),
        description=tr("显示版本号。"),
        epilog="示例:\n  onomedit version",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_version.set_defaults(handler=_cmd_version)

    p_comp = sub.add_parser(
        "completion",
        help=tr("生成 shell 补全脚本（pipe 到文件后配置）"),
        description=choose(
            "输出指定 shell 的补全脚本到 stdout；把 stdout 重定向到文件后配置到 shell。\n"
            f"支持: {', '.join(completion.supported_shells())}。",
            "Write a completion script to stdout and redirect it to your shell's completion directory.\n"
            f"Supported shells: {', '.join(completion.supported_shells())}.",
        ),
        epilog=completion.completion_usage(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    p_comp.add_argument(
        "shell",
        choices=completion.supported_shells(),
        help=tr("目标 shell（bash / zsh / pwsh / fish）"),
    )
    p_comp.set_defaults(handler=_cmd_completion)

    return parser


def _cmd_help(args) -> int:
    """显示帮助；可指定子命令（``onomedit help rename``）。"""
    parser = build_parser()
    if args.topic:
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                sub = action.choices.get(args.topic)
                if sub is None:
                    print(
                        tr(
                            "未知子命令: {topic}（可执行 onomedit help 查看全部）",
                            topic=args.topic,
                        ),
                        file=sys.stderr,
                    )
                    return 1
                sub.print_help()
                return 0
    parser.print_help()
    return 0


def _cmd_config(args) -> int:
    cfg = config_mod.load_config()
    print(json.dumps(config_mod.to_dict(cfg), ensure_ascii=False, indent=2))
    print("\n" + tr("配置文件: {path}", path=config_mod.config_path()))
    return 0


def _cmd_config_set(args) -> int:
    cfg = config_mod.load_config()
    try:
        desc = config_mod.set_value(cfg, args.key, args.value)
    except KeyError:
        print(tr("错误: 未知配置键 {key}", key=repr(args.key)), file=sys.stderr)
        return 1
    except ValueError as e:
        print(tr("错误: {error}", error=e), file=sys.stderr)
        return 1
    config_mod.save_config(cfg)
    if args.key == "language":
        set_language(cfg.language)
    print(desc)
    return 0


def _cmd_set_editor(args) -> int:
    cfg = config_mod.load_config()
    cfg.editor = " ".join(args.command)
    config_mod.save_config(cfg)
    print(tr("编辑器已设置为: {editor}", editor=cfg.editor))
    return 0


def _cmd_config_reset(args) -> int:
    cfg = config_mod.default_config()
    config_mod.save_config(cfg)
    print(tr("配置已重置为默认值"))
    return 0


def _pipe_hint() -> str:
    """管道场景路径解析失败时的跨平台提示（Windows vs POSIX 语法各异）。

    根因跨 shell 一致：管道里的相对路径按当前工作目录查找，程序无法从裸文件名
    推断其所在目录。POSIX 的 `ls` 管道输出本就干净（每行一个裸名），无表格问题；
    Windows PowerShell 直接传文件对象会被渲染成带表头的表格，额外提醒。
    """
    if os.name == "nt":
        return choose(
            "\n提示: 管道里的路径解析失败——相对路径会按当前目录查找。\n"
            "  · 提供完整路径：Get-ChildItem C:\\dir | ForEach-Object FullName | onomedit rename …\n"
            "  · 或先 cd 到目标目录：cd C:\\dir; Get-ChildItem -Name | onomedit rename …\n"
            "  · 直接用 Get-ChildItem C:\\dir | onomedit（不加参数）会把文件对象渲染成带表头表格，无法解析",
            "\nTip: piped relative paths are resolved from the current directory.\n"
            "  · Pipe full paths: Get-ChildItem C:\\dir | ForEach-Object FullName | onomedit rename …\n"
            "  · Or change directory first: cd C:\\dir; Get-ChildItem -Name | onomedit rename …\n"
            "  · Do not pipe PowerShell file objects directly; their table formatting cannot be parsed",
        )
    return choose(
        "\n提示: 管道里的路径解析失败——相对路径会按当前目录查找，程序无法从裸文件名推断其目录。\n"
        "  · 提供完整路径(逐行进管道)：find /some/dir -maxdepth 1 | onomedit rename …\n"
        "    (需要仅文件可加 -type f；find 输出以 /some/dir 开头的完整路径，可直接解析)\n"
        "  · 或先 cd 到目标目录：cd /some/dir; ls | onomedit rename …",
        "\nTip: piped relative paths are resolved from the current directory.\n"
        "  · Pipe full paths: find /some/dir -maxdepth 1 | onomedit rename …\n"
        "  · Or change directory first: cd /some/dir; ls | onomedit rename …",
    )


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
    if args.sort_by:
        cfg.sort_by = args.sort_by
    if args.reverse:
        cfg.sort_reverse = True
    if args.depth is not None:
        # 临时深度：覆盖层级并开启展开（用户显式指定深度即隐含要展开）
        cfg.subdirs_depth = args.depth
        cfg.expand_subdirs = True
    if args.exclude:
        # 扁平化多组 tag，在现有配置基础上追加（不改配置文件）
        tags = [tag for group in args.exclude for tag in group]
        cfg.exclude = config_mod.merge_exclude_tags(cfg.exclude, tags)

    pipeline = RenamePipeline(cfg, on_status=lambda msg: print(msg, flush=True))

    # 未提供路径且 stdin 来自管道时，把管道输出当作路径列表（优先于剪贴板）
    raw_paths = args.paths
    from_pipe = False
    if not raw_paths and not sys.stdin.isatty():
        from_pipe = True
        raw_paths = collection.read_stream_paths()
        if not raw_paths:
            # 空管道：明确无输入，不回退剪贴板（避免管道场景误读剪贴板）
            print(tr("错误: 管道未提供任何路径"), file=sys.stderr)
            return 1
    try:
        outcome = pipeline.run_editor_mode(raw_paths, dry_run=args.dry_run)
    except PipelineError as e:
        print(tr("错误: {error}", error=e), file=sys.stderr)
        if from_pipe:
            # 管道路径解析失败：补一道管场景特有的可操作提示（按平台给出语法）
            print(_pipe_hint(), file=sys.stderr)
        return 1
    except tempfile_mgr.LineCountError as e:
        print(tr("错误: {error}", error=e), file=sys.stderr)
        return 1
    except editor.EditorError as e:
        print(tr("错误: {error}", error=e), file=sys.stderr)
        return 1

    if outcome.dry_run:
        if outcome.preview is not None:
            for row in outcome.preview:
                extra = ""
                if row.diff:
                    extra += tr("  差异: {diff}", diff=row.diff)
                if row.distance:
                    extra += tr("  距离: {distance}", distance=row.distance)
                print(f"{row.old}  →  {row.new}{extra}")
        else:
            for old, new in outcome.pairs:
                print(f"{old}  →  {new}")
        print(tr("（dry-run 预览，共 {count} 项，未执行）", count=len(outcome.pairs)))
        return 0

    result = outcome.result
    print(
        tr(
            "重命名完成: 成功 {success} / 失败 {failed} / 无变化 {skipped} / 总计 {total}",
            success=len(result.success),
            failed=len(result.failed),
            skipped=len(result.skipped),
            total=result.total,
        )
    )
    for old, new, err in result.failed:
        print(
            tr("失败: {old} -> {new}: {error}", old=old, new=new, error=err),
            file=sys.stderr,
        )
    return 0 if not result.failed else 1


def _cmd_restore(args) -> int:
    cfg = config_mod.load_config()
    log = RenameLogger(config_mod.log_dir())
    if args.partial:
        pairs = log.read_last()
        if not pairs:
            print(tr("没有可恢复的记录（最近一次日志为空）"), file=sys.stderr)
            return 1
        lines = [f"{old}{SEPARATOR}{new}" for old, new in pairs]
        temp_dir = cfg.temp_dir or None
        import tempfile as _tempfile

        fd, path = _tempfile.mkstemp(
            prefix="onomedit_restore_", suffix=".txt", dir=temp_dir, text=True
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                for line in lines:
                    f.write(line + "\n")
            if not cfg.editor.strip():
                print(
                    tr("未配置编辑器，无法进行部分恢复（先 config set-editor）"),
                    file=sys.stderr,
                )
                return 1
            sig = tempfile_mgr.signature(path)
            print(tr("请在编辑器中删去不想恢复的行，保存后退出…（{path}）", path=path))
            editor.launch_and_wait(
                cfg.editor,
                path,
                sig,
                multi_tab=cfg.multi_tab,
                timeout=cfg.editor_timeout,
            )
            kept = tempfile_mgr.read_lines(path, len(lines))
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        if len(kept) > len(lines):
            print(tr("错误: 筛选后的行数超过原始行数，已中止"), file=sys.stderr)
            return 1
        try:
            result = restore(log, partial_lines=kept)
        except PipelineError as e:
            print(tr("错误: {error}", error=e), file=sys.stderr)
            return 1
    else:
        try:
            result = restore(log, all_history=args.all)
        except PipelineError as e:
            print(tr("错误: {error}", error=e), file=sys.stderr)
            return 1

    print(
        tr(
            "恢复完成: 成功 {success} / 失败 {failed} / 无变化 {skipped} / 总计 {total}",
            success=len(result.success),
            failed=len(result.failed),
            skipped=len(result.skipped),
            total=result.total,
        )
    )
    for old, new, err in result.failed:
        print(
            tr("失败: {old} -> {new}: {error}", old=old, new=new, error=err),
            file=sys.stderr,
        )
    return 0 if not result.failed else 1


def _cmd_history(args) -> int:
    log = RenameLogger(config_mod.log_dir())
    pairs = log.read_history() if args.all else log.read_last()
    if not pairs:
        print(tr("（空）"))
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


def _cmd_completion(args) -> int:
    """把指定 shell 的补全脚本写到 stdout，供用户重定向到文件。

    用 buffer 二进制写以保证行尾恒为 LF：Windows 文本模式下 \n 会被转成
    CRLF，破坏 bash/zsh 脚本解析。
    """
    data = completion.completion_for(args.shell).encode("utf-8")
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8()
    set_language(config_mod.load_config().language)
    args_list = list(sys.argv[1:] if argv is None else argv)
    if not args_list:
        # 无参数：默认启动 GUI，控制台提示 CLI 用法
        print(tr("启动 Onomedit 图形界面…"))
        print(
            tr(
                "提示: 输入 onomedit help 查看全部子命令与用法；也可直接使用 CLI（如 onomedit rename *.txt --dry-run）"
            )
        )
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
        print("\n" + tr("已取消"), file=sys.stderr)
        return 130
