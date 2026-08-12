"""路径封装：四段拆分（含点开头/多扩展名）、序列化对称、重命名。"""

import os
from pathlib import Path

import pytest

from onomedit.core.pathitem import PATH_TYPES, PathItem


def test_four_segments():
    p = PathItem("C:/x/y/report.tar.gz")
    assert p.directory == "C:/x/y"
    assert p.name == "report.tar.gz"
    assert p.stem == "report.tar"
    assert p.ext == ".gz"


def test_dotfile_segments():
    p = PathItem("/home/u/.gitignore")
    assert p.name == ".gitignore"
    assert p.stem == ".gitignore"
    assert p.ext == ""


def test_serialize_roundtrip_symmetric():
    for path in ("/d/a.b.txt", "/d/.hidden", "/d/noext", "/d/x"):
        for ptype in PATH_TYPES:
            item = PathItem(path)
            line = item.serialize(ptype)
            back = item.with_field(ptype, line)
            assert Path(back) == Path(path), f"{ptype} 往返不一致: {path!r}"


def test_with_field_segments():
    p = PathItem("/d/report.tar.gz")
    # stem 档 = 去掉最后一个扩展名（a.tar）；替换后保留 .gz
    assert Path(p.with_field("stem", "notes")) == Path("/d/notes.gz")
    assert Path(p.with_field("name", "full.txt")) == Path("/d/full.txt")
    assert Path(p.with_field("ext", ".md")) == Path("/d/report.tar.md")
    assert p.with_field("full", "/elsewhere/x") == "/elsewhere/x"


def test_with_field_empty_parent():
    p = PathItem("plain.txt")
    assert p.with_field("name", "new.txt") == "new.txt"


def test_invalid_scope():
    p = PathItem("/d/a.txt")
    with pytest.raises(ValueError):
        p.get_field("bogus")
    with pytest.raises(ValueError):
        p.with_field("bogus", "x")


def test_rename_executes(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("hello", encoding="utf-8")
    item = PathItem(str(src))
    target = str(tmp_path / "b.txt")
    item.rename(target)
    assert (tmp_path / "b.txt").exists()
    assert not src.exists()


def test_equality_and_hash():
    assert PathItem("/a/x") == PathItem("/a/x")
    assert PathItem("/a/x") != PathItem("/a/y")
    assert len({PathItem("/a/x"), PathItem("/a/x")}) == 1
