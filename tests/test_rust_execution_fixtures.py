"""共享执行 fixture：重命名、日志、冲突与恢复的 Python oracle。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from onomedit.core.logger import ROTATE_BYTES, SEPARATOR, RenameLogger
from onomedit.core.pipeline import DuplicateTargetError, RenameResult, Renamer, restore


FIXTURE_PATH = Path(__file__).parents[1] / "tests-rust" / "fixtures" / "execution.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _build_files(root: Path, files: dict[str, str]) -> None:
    root.mkdir()
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def _relative(root: Path, path: str | Path) -> str:
    return Path(path).relative_to(root).as_posix()


def _absolute_pairs(root: Path, pairs: list[dict]) -> list[tuple[str, str]]:
    return [(str(root / pair["old"]), str(root / pair["new"])) for pair in pairs]


def _normalized_pairs(root: Path, pairs) -> list[dict[str, str]]:
    return [{"old": _relative(root, old), "new": _relative(root, new)} for old, new in pairs]


def _tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _assert_result(root: Path, result, logger: RenameLogger, expected: dict) -> None:
    assert _normalized_pairs(root, result.success) == expected["success"]
    assert [
        {"old": _relative(root, old), "new": _relative(root, new)}
        for old, new, _ in result.failed
    ] == expected["failed"]
    assert [_relative(root, path) for path in result.skipped] == expected["skipped"]
    assert _tree(root) == expected["tree"]
    assert _normalized_pairs(root, logger.read_last()) == expected["last"]
    assert _normalized_pairs(root, logger.read_history()) == expected["history"]
    for path in root.parent.rglob("*"):
        assert "__onomedit_tmp_" not in path.name
    for log_path in (logger.last_path, logger.history_path):
        if log_path.exists():
            assert "__onomedit_tmp_" not in log_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("case", _fixture()["execute_cases"], ids=lambda case: case["name"])
def test_shared_execute_cases(tmp_path, case):
    root = tmp_path / "tree"
    logger = RenameLogger(tmp_path / "log")
    _build_files(root, case["files"])
    logger.begin_session()
    pairs = _absolute_pairs(root, case["pairs"])

    if case.get("duplicate_error"):
        with pytest.raises(DuplicateTargetError):
            Renamer(log=logger).run(pairs)
        result = RenameResult()
    else:
        result = Renamer(log=logger).run(pairs)

    _assert_result(root, result, logger, case["expected"])
    if case.get("error_contains"):
        error = logger.error_path.read_text(encoding="utf-8")
        for fragment in case["error_contains"]:
            assert fragment in error


@pytest.mark.parametrize("case", _fixture()["restore_cases"], ids=lambda case: case["name"])
def test_shared_restore_cases(tmp_path, case):
    root = tmp_path / "tree"
    logger = RenameLogger(tmp_path / "log")
    _build_files(root, case["files"])
    logger.begin_session()
    log_pairs = _absolute_pairs(root, case["log_pairs"])
    for old, new in log_pairs:
        logger.record(old, new)
    if case.get("clear_last_before_restore"):
        logger.begin_session()

    partial_lines = None
    if "partial_indexes" in case:
        partial_lines = [
            f"{log_pairs[index][0]}{SEPARATOR}{log_pairs[index][1]}"
            for index in case["partial_indexes"]
        ]
    result = restore(
        logger,
        all_history=case.get("all_history", False),
        partial_lines=partial_lines,
    )
    _assert_result(root, result, logger, case["expected"])


def test_shared_history_rotation_boundary(tmp_path):
    logger = RenameLogger(tmp_path / "log")
    logger.begin_session()
    logger.history_path.write_bytes(b"x" * (ROTATE_BYTES + 1))
    logger.record("old.txt", "new.txt")

    assert (logger.log_dir / "history.1.log").stat().st_size == ROTATE_BYTES + 1
    assert logger.read_history() == [("old.txt", "new.txt")]
    assert logger.read_last() == [("old.txt", "new.txt")]
