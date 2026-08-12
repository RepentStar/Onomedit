"""日志：记录、轮转、读取、恢复方向解析。"""

from pathlib import Path

import pytest

from onomedit.core.logger import RenameLogger, parse_line


@pytest.fixture
def logger(tmp_path):
    return RenameLogger(tmp_path)


def test_begin_session_clears_last(logger):
    logger.begin_session()
    logger.record("a", "b")
    logger.begin_session()  # 新会话清空最近一次
    assert logger.read_last() == []


def test_record_appends_both(logger):
    logger.begin_session()
    logger.record("a.txt", "b.txt")
    logger.record("c.txt", "d.txt")
    assert logger.read_last() == [("a.txt", "b.txt"), ("c.txt", "d.txt")]
    assert logger.read_history() == [("a.txt", "b.txt"), ("c.txt", "d.txt")]


def test_record_error(logger):
    logger.record_error("boom")
    assert "boom" in logger.error_path.read_text(encoding="utf-8")


def test_parse_line_roundtrip(logger):
    logger.begin_session()
    logger.record("旧 名<-->.txt", "新 名.txt")
    pairs = logger.read_last()
    assert pairs == [("旧 名<-->.txt", "新 名.txt")]  # 路径内含分隔符从右分割
    old, new = parse_line("a<-->b<-->c")
    assert (old, new) == ("a<-->b", "c")


def test_parse_line_invalid():
    with pytest.raises(ValueError):
        parse_line("no separator")


def test_rotation(logger, monkeypatch):
    import onomedit.core.logger as logger_mod

    monkeypatch.setattr(logger_mod, "ROTATE_BYTES", 20)
    logger.begin_session()
    for i in range(10):
        logger.record(f"old{i}.txt", f"new{i}.txt")
    assert logger.history_path.exists()
    # 轮转后至少产生 history.1.log
    assert (logger.log_dir / "history.1.log").exists() or logger.history_path.stat().st_size <= 20


def test_read_empty(logger):
    assert logger.read_last() == []
    assert logger.read_history() == []


def test_missing_files_no_error(logger):
    assert logger.read_last() == []
    logger.record_error("x")  # 不崩
