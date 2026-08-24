"""共享文件树 fixture：收集、临时编辑文件与计划阶段的 Python oracle。"""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path

import pytest

from onomedit.core import config as config_mod
from onomedit.core import tempfile_mgr
from onomedit.core.pipeline import PipelineError, RenamePipeline
from onomedit.utils import fileattr


FIXTURE_PATH = Path(__file__).parents[1] / "tests-rust" / "fixtures" / "filesystem.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _set_windows_attributes(path: Path, attributes: list[str]) -> None:
    if os.name != "nt":
        return
    import ctypes

    masks = {"readonly": 0x1, "hidden": 0x2, "system": 0x4}
    value = sum(masks[name] for name in attributes)
    if not ctypes.windll.kernel32.SetFileAttributesW(str(path), value or 0x80):
        raise ctypes.WinError()


def _reset_tree_attributes(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        try:
            if os.name == "nt":
                _set_windows_attributes(path, [])
            elif path.is_file():
                path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


def _build_tree(root: Path, tree: dict) -> bool:
    root.mkdir()
    for relative in tree["directories"]:
        (root / relative).mkdir(parents=True, exist_ok=True)
    for file in tree["files"]:
        if delay := file.get("delay_before_ms"):
            time.sleep(delay / 1000)
        path = root / file["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(file["content"], encoding="utf-8", newline="\n")
        if mtime := file.get("mtime"):
            os.utime(path, (mtime, mtime))
        attributes = file.get("attributes", [])
        if "readonly" in attributes and os.name != "nt":
            path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        _set_windows_attributes(path, attributes)

    symlinks_ready = True
    for link in tree.get("symlinks", []):
        path = root / link["path"]
        try:
            os.symlink(
                root / link["target"],
                path,
                target_is_directory=link["kind"] == "dir",
            )
        except (OSError, NotImplementedError):
            symlinks_ready = False
            break
    return symlinks_ready


def _relative(root: Path, value: str | os.PathLike) -> str:
    return Path(os.path.relpath(value, root)).as_posix()


@pytest.mark.parametrize("case", _fixture()["cases"], ids=lambda case: case["name"])
def test_shared_filesystem_prepare_and_plan(tmp_path, case, request):
    root = tmp_path / "tree"
    scratch = tmp_path / "scratch"
    symlinks_ready = _build_tree(root, _fixture()["tree"])
    request.addfinalizer(lambda: _reset_tree_attributes(root))
    if case.get("requires_symlinks") and not symlinks_ready:
        pytest.skip("当前平台不允许创建测试所需的符号链接")
    if case.get("requires_readonly_enforcement") and not fileattr.is_readonly(
        root / "attributes" / "readonly.txt"
    ):
        pytest.skip("当前用户仍可写只读权限文件，无法验证只读排除")
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
