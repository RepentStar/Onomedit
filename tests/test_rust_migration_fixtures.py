"""Python v0.1.6 持久化快照必须继续由 Python oracle 正常读取。"""

import json
from pathlib import Path

from onomedit.core.config import from_dict
from onomedit.core.logger import RenameLogger


FIXTURE_ROOT = Path(__file__).parents[1] / "tests-rust" / "fixtures" / "v0_1_6"


def test_python_v0_1_6_persistence_snapshot():
    config = from_dict(json.loads((FIXTURE_ROOT / "config.json").read_text(encoding="utf-8")))
    assert config.editor == '"C:\\Program Files\\Notepad++\\notepad++.exe" -multiInst'
    assert config.path_type == "name"
    assert config.sort_by == "mtime"
    assert config.preview.diff is True
    assert config.exclude.hidden is False
    assert config.auto_rules[0].find == "旧"

    logger = RenameLogger(FIXTURE_ROOT / "log")
    assert logger.read_history() == [
        (r"C:\资料\old.txt", r"D:\归档\new.txt"),
        (r"C:\资料\old<-->part.txt", r"D:\归档\newer.txt"),
        (r"\\server\share\旧.txt", r"\\server\share\新.txt"),
    ]
    assert logger.read_last() == [(r"\\server\share\旧.txt", r"\\server\share\新.txt")]
