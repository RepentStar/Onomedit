"""数据管理：文件收集、子文件夹展开、排除过滤。"""

import os

import pytest

from onomedit.core import collection
from onomedit.core.collection import display_base
from onomedit.core.config import ExcludeOptions
from onomedit.core.pathitem import PathItem


class _Stream:
    """模拟管道 stdout（delimiter 分隔）：含 Windows CRLF 与空行。"""

    def __init__(self, content):
        self._data = iter(content.split("\n"))

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._data)


def test_read_stream_paths_strips_and_skips_empty():
    stream = _Stream(" a.txt\n\nb.txt \r\nc.txt\n")
    assert collection.read_stream_paths(stream) == ["a.txt", "b.txt", "c.txt"]


def test_read_stream_paths_empty():
    assert collection.read_stream_paths(_Stream("\n\n")) == []


def _make_tree(root):
    (root / "a.txt").write_text("1", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "b.txt").write_text("2", encoding="utf-8")
    (root / "sub" / "deep").mkdir()
    (root / "sub" / "deep" / "c.txt").write_text("3", encoding="utf-8")


def test_collect_filters_nonexistent(tmp_path):
    p1 = tmp_path / "exists.txt"
    p1.write_text("x", encoding="utf-8")
    got = collection.collect_paths([str(p1), str(tmp_path / "nope.txt")])
    assert got == [str(p1)]


def test_collect_glob(tmp_path):
    (tmp_path / "g1.txt").write_text("1", encoding="utf-8")
    (tmp_path / "g2.txt").write_text("2", encoding="utf-8")
    (tmp_path / "g3.md").write_text("3", encoding="utf-8")
    got = collection.collect_paths([str(tmp_path / "*.txt")])
    assert sorted(os.path.basename(p) for p in got) == ["g1.txt", "g2.txt"]


def test_collect_clipboard(monkeypatch, tmp_path):
    p = tmp_path / "clip.txt"
    p.write_text("x", encoding="utf-8")
    import onomedit.utils.clipboard as cb

    monkeypatch.setattr(cb, "get_paths", lambda: [str(p), str(tmp_path / "ghost.txt")])
    got = collection.collect_paths(None, use_clipboard=True)
    assert got == [str(p)]  # 不存在的路径被过滤


def test_expand_subdirs_depth1(tmp_path):
    _make_tree(tmp_path)
    items = [PathItem(str(tmp_path))]
    expanded = collection.expand_subdirs(items, 1)
    names = sorted(os.path.basename(i.full) for i in expanded)
    assert "a.txt" in names and "sub" in names
    assert "b.txt" not in names  # 第 2 层文件（sub 内）不展开
    assert "c.txt" not in names  # 第 3 层不展开


def test_expand_subdirs_depth2(tmp_path):
    _make_tree(tmp_path)
    items = [PathItem(str(tmp_path))]
    expanded = collection.expand_subdirs(items, 2)
    names = sorted(os.path.basename(i.full) for i in expanded)
    assert "a.txt" in names and "sub" in names
    assert "b.txt" in names and "deep" in names  # 第 2 层内容
    assert "c.txt" not in names  # 第 3 层不展开


def test_expand_subdirs_depth3(tmp_path):
    _make_tree(tmp_path)
    items = [PathItem(str(tmp_path))]
    expanded = collection.expand_subdirs(items, 3)
    names = sorted(os.path.basename(i.full) for i in expanded)
    assert "a.txt" in names and "sub" in names
    assert "b.txt" in names and "deep" in names
    assert "c.txt" in names  # 第 3 层内容


def test_expand_subdirs_zero_keeps_dir(tmp_path):
    _make_tree(tmp_path)
    items = [PathItem(str(tmp_path))]
    expanded = collection.expand_subdirs(items, 0)
    assert len(expanded) == 1 and expanded[0].full == str(tmp_path)


def test_dedupe_items_removes_exact_duplicates(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("x", encoding="utf-8")
    other = tmp_path / "b.txt"
    other.write_text("y", encoding="utf-8")
    items = [PathItem(str(p)), PathItem(str(p)), PathItem(str(other))]
    got = collection.dedupe_items(items)
    assert [i.full for i in got] == [str(p), str(other)]


def test_dedupe_items_case_insensitive(tmp_path):
    """Windows 大小写不敏感：不同写法的同一路径视为重复（首个保留）。"""
    p = tmp_path / "A.TXT"
    p.write_text("x", encoding="utf-8")
    items = [PathItem(str(p)), PathItem(str(tmp_path / "a.txt"))]
    got = collection.dedupe_items(items)
    assert [i.full for i in got] == [str(p)]


def test_dedupe_items_relative_alias(tmp_path):
    """相对/带 . 的路径与绝对路径指向同一文件：视为重复。"""
    p = tmp_path / "a.txt"
    p.write_text("x", encoding="utf-8")
    items = [PathItem(str(p)), PathItem(os.path.join(str(tmp_path), ".", "a.txt"))]
    got = collection.dedupe_items(items)
    assert len(got) == 1


def test_dedupe_items_keeps_distinct(tmp_path):
    p1 = tmp_path / "a.txt"
    p2 = tmp_path / "b.txt"
    p1.write_text("1", encoding="utf-8")
    p2.write_text("2", encoding="utf-8")
    got = collection.dedupe_items([PathItem(str(p1)), PathItem(str(p2))])
    assert len(got) == 2


def test_exclude_files(tmp_path):
    _make_tree(tmp_path)
    items = [PathItem(str(tmp_path / "a.txt")), PathItem(str(tmp_path / "sub"))]
    ex = ExcludeOptions(files=True)
    kept = collection.apply_excludes(items, ex)
    assert [i.full for i in kept] == [str(tmp_path / "sub")]


def test_exclude_dirs(tmp_path):
    _make_tree(tmp_path)
    items = [PathItem(str(tmp_path / "a.txt")), PathItem(str(tmp_path / "sub"))]
    ex = ExcludeOptions(dirs=True)
    kept = collection.apply_excludes(items, ex)
    assert [i.full for i in kept] == [str(tmp_path / "a.txt")]


def test_display_base_single_dir(tmp_path):
    d = tmp_path / "a" / "b"
    d.mkdir(parents=True)
    # 单目录输入 → 基准向上取一级（显示 b\...）
    assert display_base([str(d)]) == str(d.parent)


def test_display_base_multi_files(tmp_path):
    f1 = tmp_path / "x" / "1.txt"
    f2 = tmp_path / "x" / "2.txt"
    f1.parent.mkdir(parents=True)
    f1.write_text("1", encoding="utf-8")
    f2.write_text("2", encoding="utf-8")
    assert display_base([str(f1), str(f2)]) == str(tmp_path / "x")


def test_display_base_empty_and_missing(tmp_path):
    assert display_base([]) == ""
    assert display_base([str(tmp_path / "nope.txt")]) == str(tmp_path)


def test_exclude_symlink(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("x", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("当前平台不支持符号链接")
    items = [PathItem(str(target)), PathItem(str(link))]
    ex = ExcludeOptions(symlinks=True)
    kept = collection.apply_excludes(items, ex)
    assert [i.full for i in kept] == [str(target)]


def test_sort_items_default_keeps_order(tmp_path):
    _make_tree(tmp_path)
    items = [PathItem(str(tmp_path / "sub")), PathItem(str(tmp_path / "a.txt"))]
    got = collection.sort_items(items, "default")
    assert got is items  # 不排序：原列表直接返回


def test_sort_items_by_name_case_insensitive(tmp_path):
    (tmp_path / "z.txt").write_text("1", encoding="utf-8")
    (tmp_path / "A.txt").write_text("2", encoding="utf-8")
    items = [PathItem(str(tmp_path / "z.txt")), PathItem(str(tmp_path / "A.txt"))]
    got = collection.sort_items(items, "name")
    assert [i.name for i in got] == ["A.txt", "z.txt"]  # normcase：A 排在 z 前


def test_sort_items_by_path(tmp_path):
    _make_tree(tmp_path)
    items = [
        PathItem(str(tmp_path / "sub" / "b.txt")),
        PathItem(str(tmp_path / "a.txt")),
    ]
    got = collection.sort_items(items, "path")
    assert [i.full for i in got] == [
        str(tmp_path / "a.txt"),
        str(tmp_path / "sub" / "b.txt"),
    ]


def test_sort_items_by_mtime(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("1", encoding="utf-8")
    b.write_text("2", encoding="utf-8")
    past = 1_000_000_000
    os.utime(a, (past, past))
    os.utime(b, (past + 10, past + 10))
    items = [PathItem(str(b)), PathItem(str(a))]  # 输入顺序：b 在前
    got = collection.sort_items(items, "mtime")
    assert [i.name for i in got] == ["a.txt", "b.txt"]  # 修改时间早的在前


def test_sort_items_by_size(tmp_path):
    small = tmp_path / "small.txt"
    big = tmp_path / "big.txt"
    small.write_text("x", encoding="utf-8")
    big.write_text("x" * 100, encoding="utf-8")
    items = [PathItem(str(big)), PathItem(str(small))]
    got = collection.sort_items(items, "size")
    assert [i.name for i in got] == ["small.txt", "big.txt"]


def test_sort_items_unknown_key_keeps_order(tmp_path):
    items = [PathItem(str(tmp_path / "b.txt")), PathItem(str(tmp_path / "a.txt"))]
    got = collection.sort_items(items, "bogus")
    assert got is items  # 未知值安全回退原顺序


def test_sort_items_default_reverse_reverses_order(tmp_path):
    """default + reverse：反转收集顺序。"""
    items = [PathItem(str(tmp_path / "a.txt")), PathItem(str(tmp_path / "b.txt"))]
    got = collection.sort_items(items, "default", reverse=True)
    assert [i.name for i in got] == ["b.txt", "a.txt"]
    assert got is not items  # 反转产生新列表


def test_sort_items_reverse_name_descending(tmp_path):
    (tmp_path / "z.txt").write_text("1", encoding="utf-8")
    (tmp_path / "A.txt").write_text("2", encoding="utf-8")
    items = [PathItem(str(tmp_path / "A.txt")), PathItem(str(tmp_path / "z.txt"))]
    got = collection.sort_items(items, "name", reverse=True)
    assert [i.name for i in got] == ["z.txt", "A.txt"]  # 降序


def test_sort_items_reverse_mtime_descending(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("1", encoding="utf-8")
    b.write_text("2", encoding="utf-8")
    past = 1_000_000_000
    os.utime(a, (past, past))
    os.utime(b, (past + 10, past + 10))
    items = [PathItem(str(a)), PathItem(str(b))]
    got = collection.sort_items(items, "mtime", reverse=True)
    assert [i.name for i in got] == ["b.txt", "a.txt"]  # 修改时间新的在前
