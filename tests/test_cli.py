"""CLI：rename 子命令参数解析（含临时排除 --exclude）。"""

import pytest

from onomedit.cli import build_parser
from onomedit.core import config as config_mod


def test_rename_exclude_parses_multi_tags():
    args = build_parser().parse_args(
        ["rename", "a.txt", "--exclude", "f", "h", "--dry-run"]
    )
    assert args.exclude == [["f", "h"]]
    assert args.dry_run is True


def test_rename_exclude_repeated_group_accumulates():
    args = build_parser().parse_args(
        ["rename", "a.txt", "--exclude", "d", "--exclude", "readonly"]
    )
    assert args.exclude == [["d"], ["readonly"]]


def test_rename_exclude_invalid_tag_rejected():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["rename", "a.txt", "--exclude", "zzz"])


def test_rename_exclude_all_choices_are_valid():
    # 全部合法 tag 都能通过解析
    args = build_parser().parse_args(
        ["rename", "a.txt", "--exclude", *config_mod.EXCLUDE_TAGS]
    )
    assert [tag for group in args.exclude for tag in group] == list(
        config_mod.EXCLUDE_TAGS
    )


def test_rename_without_exclude_keeps_none():
    args = build_parser().parse_args(["rename", "a.txt"])
    assert args.exclude is None


def test_rename_sort_by_parses():
    args = build_parser().parse_args(["rename", "a.txt", "--sort-by", "mtime"])
    assert args.sort_by == "mtime"


def test_rename_sort_by_invalid_rejected():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["rename", "a.txt", "--sort-by", "zzz"])


def test_rename_sort_by_absent_none():
    args = build_parser().parse_args(["rename", "a.txt"])
    assert args.sort_by is None


def test_rename_sort_by_all_choices_are_valid():
    from onomedit.core.collection import SORT_BY_CHOICES

    args = build_parser().parse_args(
        ["rename", "a.txt", "--sort-by", SORT_BY_CHOICES[-1]]
    )
    assert args.sort_by == SORT_BY_CHOICES[-1]


def test_cmd_rename_sort_by_overrides_cfg(monkeypatch, isolated_config):
    """--sort-by 临时覆盖配置 sort_by（不改配置文件）。"""
    import onomedit.cli as cli_mod

    captured = {}

    class _Result:
        success = []
        failed = []
        skipped = []
        total = 0

    class FakeOutcome:
        dry_run = False
        result = _Result()
        pairs = []
        preview = None

    class FakePipeline:
        def __init__(self, cfg, **kw):
            captured["cfg"] = cfg

        def run_editor_mode(self, paths, dry_run=False):
            captured["paths"] = paths
            return FakeOutcome()

    monkeypatch.setattr(cli_mod, "RenamePipeline", FakePipeline)
    args = build_parser().parse_args(["rename", "a.txt", "--sort-by", "mtime"])
    cli_mod._cmd_rename(args)
    assert captured["cfg"].sort_by == "mtime"


def test_rename_depth_parses():
    args = build_parser().parse_args(["rename", "folder", "--depth", "3"])
    assert args.depth == 3


def test_rename_depth_zero_allowed():
    """0 = 不展开（与配置 subdirs_depth 语义一致）。"""
    args = build_parser().parse_args(["rename", "folder", "--depth", "0"])
    assert args.depth == 0


def test_rename_depth_absent_none():
    args = build_parser().parse_args(["rename", "folder"])
    assert args.depth is None


def test_rename_depth_invalid_rejected():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["rename", "folder", "--depth", "abc"])


def test_cmd_rename_depth_overrides_cfg(monkeypatch, isolated_config):
    """--depth 临时覆盖 subdirs_depth 并临时开启子文件夹展开（不改配置文件）。"""
    import onomedit.cli as cli_mod

    captured = {}

    class _Result:
        success = []
        failed = []
        skipped = []
        total = 0

    class FakeOutcome:
        dry_run = False
        result = _Result()
        pairs = []
        preview = None

    class FakePipeline:
        def __init__(self, cfg, **kw):
            captured["cfg"] = cfg

        def run_editor_mode(self, paths, dry_run=False):
            captured["paths"] = paths
            return FakeOutcome()

    monkeypatch.setattr(cli_mod, "RenamePipeline", FakePipeline)
    args = build_parser().parse_args(["rename", "folder", "--depth", "2"])
    cli_mod._cmd_rename(args)
    assert captured["cfg"].subdirs_depth == 2
    assert captured["cfg"].expand_subdirs is True  # 指定深度隐含展开


def test_rename_reverse_parses():
    args = build_parser().parse_args(["rename", "a.txt", "--reverse"])
    assert args.reverse is True


def test_rename_reverse_absent_false():
    args = build_parser().parse_args(["rename", "a.txt"])
    assert args.reverse is False


def test_rename_reverse_with_sort_by():
    args = build_parser().parse_args(
        ["rename", "a.txt", "--sort-by", "name", "--reverse"]
    )
    assert args.sort_by == "name"
    assert args.reverse is True


def test_cmd_rename_reverse_overrides_cfg(monkeypatch, isolated_config):
    """--reverse 临时开启顺序反转（不改配置文件）。"""
    import onomedit.cli as cli_mod

    captured = {}

    class _Result:
        success = []
        failed = []
        skipped = []
        total = 0

    class FakeOutcome:
        dry_run = False
        result = _Result()
        pairs = []
        preview = None

    class FakePipeline:
        def __init__(self, cfg, **kw):
            captured["cfg"] = cfg

        def run_editor_mode(self, paths, dry_run=False):
            captured["paths"] = paths
            return FakeOutcome()

    monkeypatch.setattr(cli_mod, "RenamePipeline", FakePipeline)
    args = build_parser().parse_args(["rename", "a.txt", "--reverse"])
    cli_mod._cmd_rename(args)
    assert captured["cfg"].sort_reverse is True


def test_cmd_rename_stdin_non_tty_reads_stream(monkeypatch, isolated_config):
    """未提供路径且 stdin 来自管道时，从 stdin 读取路径（优先于剪贴板）。"""
    import onomedit.cli as cli_mod
    from onomedit.core import collection

    captured = {}

    class _Result:
        success = []
        failed = []
        skipped = []
        total = 0

    class FakeOutcome:
        dry_run = False
        result = _Result()
        pairs = []
        preview = None

    class FakePipeline:
        def __init__(self, cfg, **kw):
            pass

        def run_editor_mode(self, paths, dry_run=False):
            captured["paths"] = paths
            return FakeOutcome()

    class FakeStdin:
        def isatty(self):
            return False  # 模拟管道重定向（非终端）

    monkeypatch.setattr(cli_mod, "RenamePipeline", FakePipeline)
    monkeypatch.setattr(cli_mod.sys, "stdin", FakeStdin())
    monkeypatch.setattr(
        collection, "read_stream_paths", lambda stream=None: ["pipe1.txt", "pipe2.txt"]
    )
    args = build_parser().parse_args(["rename"])
    cli_mod._cmd_rename(args)
    assert captured["paths"] == ["pipe1.txt", "pipe2.txt"]


def test_cmd_rename_tty_without_paths_keeps_empty(monkeypatch, isolated_config):
    """stdin 为终端且未提供路径时，不读管道（原逻辑：走剪贴板）。"""
    import onomedit.cli as cli_mod

    captured = {}

    class _Result:
        success = []
        failed = []
        skipped = []
        total = 0

    class FakeOutcome:
        dry_run = False
        result = _Result()
        pairs = []
        preview = None

    class FakePipeline:
        def __init__(self, cfg, **kw):
            pass

        def run_editor_mode(self, paths, dry_run=False):
            captured["paths"] = paths
            return FakeOutcome()

    class FakeStdin:
        def isatty(self):
            return True  # 终端：不读管道

    monkeypatch.setattr(cli_mod, "RenamePipeline", FakePipeline)
    monkeypatch.setattr(cli_mod.sys, "stdin", FakeStdin())
    args = build_parser().parse_args(["rename"])
    cli_mod._cmd_rename(args)
    assert captured["paths"] == []  # 保持原逻辑（读剪贴板）


def test_cmd_rename_stdin_empty_pipe_aborts(monkeypatch, isolated_config):
    """空管道：报错且不回退剪贴板（不调用 pipeline）。"""
    import onomedit.cli as cli_mod
    from onomedit.core import collection

    called = {"run": False}

    class FakePipeline:
        def __init__(self, cfg, **kw):
            pass

        def run_editor_mode(self, paths, dry_run=False):
            called["run"] = True
            raise AssertionError("空管道不应进入 pipeline")

    class FakeStdin:
        def isatty(self):
            return False

    monkeypatch.setattr(cli_mod, "RenamePipeline", FakePipeline)
    monkeypatch.setattr(cli_mod.sys, "stdin", FakeStdin())
    monkeypatch.setattr(collection, "read_stream_paths", lambda stream=None: [])

    args = build_parser().parse_args(["rename"])
    code = cli_mod._cmd_rename(args)
    assert code == 1
    assert called["run"] is False


def test_rename_path_type_parses():
    args = build_parser().parse_args(["rename", "a.txt", "--path-type", "name"])
    assert args.path_type == "name"


def test_rename_path_type_invalid_rejected():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["rename", "a.txt", "--path-type", "zzz"])


def test_rename_path_type_absent_none():
    args = build_parser().parse_args(["rename", "a.txt"])
    assert args.path_type is None


def test_rename_path_type_all_choices_are_valid():
    args = build_parser().parse_args(
        ["rename", "a.txt", "--path-type", config_mod.PATH_TYPES[-1]]
    )
    assert args.path_type == config_mod.PATH_TYPES[-1]


def test_cmd_rename_path_type_overrides_cfg(monkeypatch, isolated_config):
    """--path-type 临时覆盖配置 path_type（不改配置文件）。"""
    import onomedit.cli as cli_mod

    captured = {}

    class _Result:
        success = []
        failed = []
        skipped = []
        total = 0

    class FakeOutcome:
        dry_run = False
        result = _Result()
        pairs = []
        preview = None

    class FakePipeline:
        def __init__(self, cfg, **kw):
            captured["cfg"] = cfg

        def run_editor_mode(self, paths, dry_run=False):
            captured["paths"] = paths
            return FakeOutcome()

    monkeypatch.setattr(cli_mod, "RenamePipeline", FakePipeline)
    args = build_parser().parse_args(["rename", "a.txt", "--path-type", "full"])
    cli_mod._cmd_rename(args)
    assert captured["cfg"].path_type == "full"


def test_pipe_hint_windows_mentions_powershell(monkeypatch):
    """Windows 平台提示给出 PowerShell 语法，并提醒对象渲染成表格的坑。"""
    import onomedit.cli as cli_mod

    monkeypatch.setattr(cli_mod.os, "name", "nt")
    hint = cli_mod._pipe_hint()
    assert "Get-ChildItem" in hint and "cd" in hint
    assert "表头" in hint  # 仅 Windows 有对象渲染问题


def test_pipe_hint_posix_mentions_bash(monkeypatch):
    """POSIX 平台提示给出 bash/zsh 语法（find/cd），不含 PowerShell 表格提醒。"""
    import onomedit.cli as cli_mod

    monkeypatch.setattr(cli_mod.os, "name", "posix")
    hint = cli_mod._pipe_hint()
    assert "find" in hint and "cd /some/dir" in hint
    assert "Get-ChildItem" not in hint  # POSIX 无 PowerShell 表格问题
