"""共享文件树 fixture：收集、临时编辑文件与计划阶段的 Python oracle。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from onomedit.core import config as config_mod
from onomedit.core import tempfile_mgr
from onomedit.core.pipeline import PipelineError, RenamePipeline


FIXTURE_PATH = Path(__file__).parents[1] / "tests-rust" / "fixtures" / "filesystem.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _build_tree(root: Path, tree: dict) -> None:
    root.mkdir()
    for relative in tree["directories"]:
        (root / relative).mkdir(parents=True, exist_ok=True)
    for file in tree["files"]:
        path = root / file["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(file["content"], encoding="utf-8", newline="\n")


def _relative(root: Path, value: str | os.PathLike) -> str:
    return Path(os.path.relpath(value, root)).as_posix()


@pytest.mark.parametrize("case", _fixture()["cases"], ids=lambda case: case["name"])
def test_shared_filesystem_prepare_and_plan(tmp_path, case):
    root = tmp_path / "tree"
    scratch = tmp_path / "scratch"
    _build_tree(root, _fixture()["tree"])
    scratch.mkdir()

    cfg = config_mod.from_dict(case["config"])
    cfg.temp_dir = str(scratch)
    inputs = [str(root / relative) for relative in case["inputs"]]
    pipeline = RenamePipeline(cfg)
    if case.get("expected_error") == "no_files":
        with pytest.raises(PipelineError, match="没有可处理的文件"):
            pipeline.prepare(inputs)
        return
    if case.get("expected_error") == "no_files_after_exclude":
        with pytest.raises(PipelineError, match="应用排除规则后没有可处理的文件"):
            pipeline.prepare(inputs)
        return

    items, prepared_fulls, temp_path = pipeline.prepare(inputs)
    try:
        raw_edit_file = Path(temp_path).read_bytes()
        assert b"\r\n" not in raw_edit_file
        edit_lines = raw_edit_file.decode("utf-8").splitlines()

        if "edited_lines" in case:
            Path(temp_path).write_text(
                "".join(f"{line}\n" for line in case["edited_lines"]),
                encoding="utf-8",
                newline="\n",
            )
            if case.get("expected_error") == "line_count":
                with pytest.raises(tempfile_mgr.LineCountError):
                    tempfile_mgr.read_lines(temp_path, len(items))
                return
            lines = tempfile_mgr.read_lines(temp_path, len(items))
            edited_fulls = [
                item.with_field(cfg.path_type, line) for item, line in zip(items, lines)
            ]
        else:
            edited_fulls = prepared_fulls

        pairs = pipeline.plan(items, edited_fulls)
    finally:
        Path(temp_path).unlink(missing_ok=True)

    expected = case.get("expected_windows", case["expected"]) if os.name == "nt" else case["expected"]
    assert [_relative(root, item.full) for item in items] == expected["items"]
    assert edit_lines == expected["edit_lines"]
    assert [
        {"old": _relative(root, old), "new": _relative(root, new)} for old, new in pairs
    ] == expected["pairs"]
