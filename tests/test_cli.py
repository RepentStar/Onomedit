"""CLI：rename 子命令参数解析（含临时排除 --exclude）。"""

import pytest

from onomedit.cli import build_parser
from onomedit.core import config as config_mod


def test_rename_exclude_parses_multi_tags():
    args = build_parser().parse_args(["rename", "a.txt", "--exclude", "f", "h", "--dry-run"])
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
    assert [tag for group in args.exclude for tag in group] == list(config_mod.EXCLUDE_TAGS)


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

    args = build_parser().parse_args(["rename", "a.txt", "--sort-by", SORT_BY_CHOICES[-1]])
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


# ---------------------------------------------------------------- --depth 临时深度
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


# ---------------------------------------------------------------- --reverse 反转顺序
def test_rename_reverse_parses():
    args = build_parser().parse_args(["rename", "a.txt", "--reverse"])
    assert args.reverse is True


def test_rename_reverse_absent_false():
    args = build_parser().parse_args(["rename", "a.txt"])
    assert args.reverse is False


def test_rename_reverse_with_sort_by():
    args = build_parser().parse_args(["rename", "a.txt", "--sort-by", "name", "--reverse"])
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
