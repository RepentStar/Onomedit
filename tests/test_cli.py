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
