"""Absolute CLI editing, batch preflight and exclusive filesystem moves."""

from __future__ import annotations

import errno
import io
import os
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from onomedit import cli, i18n
from onomedit.core import (
    absolute_rename,
    collection,
    completion,
    config,
    editor,
    pathitem,
    tempfile_mgr,
)
from onomedit.core.absolute_path import validate_target
from onomedit.core.logger import RenameLogger
from onomedit.core.pipeline import PipelineError, RenamePipeline
from onomedit.core.rules import Rule


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path / "settings")
    previous_language = i18n.get_language()
    i18n.set_language("zh-CN")
    yield
    i18n.set_language(previous_language)


@pytest.fixture
def cfg():
    settings = config.Config(path_type="full", expand_subdirs=False, editor="fake")
    return settings


@pytest.fixture
def edit(monkeypatch):
    def setup(*targets, before_save=None):
        captured = {}

        def save(_command, temp_path, _signature, **_kwargs):
            captured["path"] = temp_path
            captured["lines"] = temp_path.read_text(encoding="utf-8").splitlines()
            if before_save is not None:
                before_save()
            temp_path.write_bytes(
                ("\r\n".join(map(str, targets)) + "\r\n").encode("utf-8")
            )

        monkeypatch.setattr(editor, "launch_and_wait", save)
        return captured

    return setup


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def seed_log() -> RenameLogger:
    log = RenameLogger(config.log_dir())
    log.begin_session()
    log.record("older", "record")
    return log


def symlink(path: Path, target: Path, *, directory=False) -> None:
    try:
        path.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        if os.name == "nt" and exc.winerror == 1314:
            pytest.skip("Windows symlink creation requires Developer Mode or privilege")
        raise


def test_absolute_cli_preview_execute_and_restore(
    tmp_path, monkeypatch, capsys, cfg, fake_editor
):
    monkeypatch.chdir(tmp_path)
    source = write(tmp_path / "原 图.jpg", "original photo")
    target = tmp_path / "归档" / "旅行" / source.name
    log = seed_log()
    cfg.editor = fake_editor("set", "1", str(target))
    cfg.path_type = "stem"
    config.save_config(cfg)
    args = ["rename", "--absolute", "--path-type", "full", "*.jpg"]

    assert cli.main([*args, "--dry-run"]) == 0
    assert f"{source}  →  {target}" in capsys.readouterr().out
    assert source.read_text(encoding="utf-8") == "original photo"
    assert not target.parent.exists()
    assert log.read_last() == [("older", "record")]
    assert config.load_config().path_type == "stem"

    assert cli.main(args) == 0
    assert not source.exists()
    assert target.read_text(encoding="utf-8") == "original photo"
    assert log.read_last() == [(str(source), str(target))]
    assert log.read_history()[-1] == (str(source), str(target))
    monkeypatch.chdir(target.parent)
    assert cli.main(["restore"]) == 0
    assert source.read_text(encoding="utf-8") == "original photo"
    assert not target.exists()


@pytest.mark.parametrize("mode", ["name", "stem", "ext"])
def test_cli_rejects_non_full_before_input(monkeypatch, cfg, capsys, mode):
    config.save_config(cfg)

    def unexpected(*_args, **_kwargs):
        pytest.fail("invalid arguments must stop before input collection")

    monkeypatch.setattr(collection, "read_stream_paths", unexpected)
    monkeypatch.setattr(cli, "RenamePipeline", unexpected)
    assert cli.main(["rename", "--absolute", "--path-type", mode]) == 2
    assert "--absolute" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("language", "help_text"),
    [
        ("zh-CN", "本次使用绝对路径编辑"),
        ("en-US", "Edit absolute paths for this run"),
    ],
)
def test_help_and_shell_completions(cfg, capsys, language, help_text):
    cfg.language = language
    config.save_config(cfg)
    assert cli.main(["help", "rename"]) == 0
    help_output = capsys.readouterr().out
    assert "--absolute" in help_output
    assert help_text in help_output
    for shell in completion.supported_shells():
        spelling = "-l absolute" if shell == "fish" else "--absolute"
        assert spelling in completion.completion_for(shell)


def test_absolute_stdin_and_clipboard(tmp_path, monkeypatch, capsys, cfg):
    monkeypatch.chdir(tmp_path)
    source = write(tmp_path / "with spaces.txt", "source")
    config.save_config(cfg)
    monkeypatch.setattr(sys, "stdin", io.StringIO(source.name + "\n"))
    assert cli.main(["rename", "--absolute", "--no-editor", "--dry-run"]) == 0
    assert str(source) in capsys.readouterr().out
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(collection.clipboard_util, "get_paths", lambda: [source.name])
    assert cli.main(["rename", "--absolute", "--no-editor", "--dry-run"]) == 0
    assert str(source) in capsys.readouterr().out


def test_absolute_sources_are_sorted_deduplicated_and_keep_directory_items(
    tmp_path, monkeypatch, cfg, edit
):
    folder = tmp_path / "root"
    nested = folder / "nested"
    nested.mkdir(parents=True)
    top = write(folder / "a.txt", "A")
    bottom = write(nested / "b.txt", "B")
    monkeypatch.chdir(tmp_path)
    cfg.expand_subdirs = True
    cfg.subdirs_depth = 1
    cfg.sort_by = "path"
    ordered = sorted([str(top), str(nested), str(bottom)], key=os.path.normcase)
    captured = edit(*ordered)
    outcome = RenamePipeline(cfg, absolute=True, recursive=True).run_editor_mode(
        [os.path.join("root", "*.txt"), str(top), "root"]
    )
    assert captured["lines"] == ordered == outcome.result.skipped
    assert not captured["path"].exists()


def test_no_editor_rules_keep_collection_order_and_can_move(tmp_path, monkeypatch, cfg):
    a = write(tmp_path / "a.txt", "A")
    b = write(tmp_path / "b.txt", "B")
    dest = tmp_path / "out"
    cfg.open_editor = False
    cfg.auto_rules = [
        Rule(scope="full", find=str(tmp_path), replace=str(dest)),
        Rule(scope="stem", kind="insert", insert="<n>1;2;1;_"),
    ]
    monkeypatch.chdir(tmp_path)
    outcome = RenamePipeline(cfg, absolute=True).run_editor_mode([b.name, a.name])
    assert outcome.result.success == [
        (str(b), str(dest / "01_b.txt")),
        (str(a), str(dest / "02_a.txt")),
    ]
    assert (dest / "01_b.txt").read_text(encoding="utf-8") == "B"
    assert (dest / "02_a.txt").read_text(encoding="utf-8") == "A"


@pytest.mark.parametrize(
    "kind",
    [
        "relative",
        "blank",
        "root",
        "trailing",
        "parent",
        "nul",
        "unicode_break",
        "log_separator",
        "duplicate",
        "log_target",
        "log_source",
    ],
)
@pytest.mark.parametrize("dry_run", [True, False])
def test_invalid_batch_preserves_source_target_tree_and_previous_log(
    tmp_path, cfg, edit, kind, dry_run
):
    log = seed_log()
    a = write(tmp_path / "a", "A")
    b = write(tmp_path / "b", "B")
    dest = tmp_path / "new" / "a"
    candidates = {
        "relative": "relative.txt",
        "blank": "   ",
        "root": tmp_path.anchor,
        "trailing": str(tmp_path / "name") + os.sep,
        "parent": os.path.join(str(tmp_path), "new", "..", "name"),
        "nul": str(tmp_path / "bad\0name"),
        "unicode_break": str(tmp_path / "bad\u2028name"),
        "log_separator": str(tmp_path / "bad<-->name"),
        "duplicate": os.path.join(str(dest.parent), ".", dest.name),
        "log_target": log.log_dir / "planned.log",
        "log_source": tmp_path / "log_moved",
    }
    captured = edit(dest, candidates[kind])
    second = log.last_path if kind == "log_source" else b
    with pytest.raises(PipelineError, match="第 2 行"):
        RenamePipeline(cfg, absolute=True).run_editor_mode(
            [str(a), str(second)], dry_run=dry_run
        )
    assert not captured["path"].exists()
    assert log.read_last() == [("older", "record")]
    assert a.read_text(encoding="utf-8") == "A"
    assert b.read_text(encoding="utf-8") == "B"
    assert not dest.parent.exists()


@pytest.mark.parametrize(
    "name",
    [
        r"C:foo",
        r"\foo",
        "C:\\",
        r"\\server\share",
        r"\\server\\file",
        r"\\.\C:\a",
        r"\\?\C:\a",
        r"C:\a:stream",
        r"C:\NUL\a",
        r"C:\COM¹\a",
        r"C:\dir.\a",
        r"C:\dir \a",
        r"C:\..\a",
        "\\\\server\\share\\a\\",
        r"C:\dir\a:b",
    ],
)
def test_windows_shape_rejects_ambiguous_targets(name):
    with pytest.raises(ValueError):
        validate_target(name, windows=True)


def test_windows_shape_keeps_unc_share_and_checks_final_name():
    assert (
        validate_target("C:/归档/./a.txt", windows=True, final_name=True)
        == r"C:\归档\a.txt"
    )
    assert (
        validate_target(r"\\server\share\归档\a.txt", windows=True, final_name=True)
        == r"\\server\share\归档\a.txt"
    )
    for name in ("AUX.txt", "CONIN$", "x.", "x?", "x "):
        with pytest.raises(ValueError):
            validate_target("C:\\dir\\" + name, windows=True, final_name=True)


@pytest.mark.parametrize(
    "kind", ["too_many", "invalid_utf8", "editor_error", "missing_editor"]
)
def test_absolute_temp_file_cleanup_on_failure(tmp_path, monkeypatch, cfg, kind):
    a = write(tmp_path / "a", "A")
    temp = tmp_path / "temp"
    temp.mkdir()

    def fail(_cmd, filename, _signature, **_kwargs):
        if kind == "editor_error":
            raise editor.EditorError("cannot start")
        filename.write_bytes(b"one\ntwo\n" if kind == "too_many" else b"\xff")

    errors = {
        "too_many": tempfile_mgr.LineCountError,
        "invalid_utf8": PipelineError,
        "editor_error": editor.EditorError,
        "missing_editor": PipelineError,
    }
    if kind == "missing_editor":
        cfg.editor = ""
    monkeypatch.setattr(editor, "launch_and_wait", fail)
    with pytest.raises(errors[kind]):
        RenamePipeline(cfg, temp_dir=temp, absolute=True).run_editor_mode([str(a)])
    assert list(temp.iterdir()) == []
    assert not config.log_dir().exists()


@pytest.mark.parametrize("scope", ["name", "stem", "ext", "full", "placeholder"])
def test_rule_must_keep_name_segments_or_produce_an_absolute_full_path(
    tmp_path, cfg, edit, scope
):
    a = write(tmp_path / "a.txt", "A")
    if scope == "placeholder":
        edit(a.with_name("<clip>.txt"))
    else:
        edit(a)
        cfg.auto_rules = [Rule(scope=scope, kind="insert", insert="elsewhere/")]
    with pytest.raises(PipelineError, match="第 1 行"):
        RenamePipeline(
            cfg, absolute=True, clipboard_text="elsewhere/name"
        ).run_editor_mode([str(a)])
    assert not config.log_dir().exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows name and ADS syntax")
def test_placeholder_punctuation_is_cleaned_but_ads_is_rejected(tmp_path, cfg, edit):
    a = write(tmp_path / "a.txt", "A")
    edit(a.with_name("<clip>.txt"))
    pipeline = RenamePipeline(cfg, absolute=True, clipboard_text="part:two")
    assert pipeline.run_editor_mode([str(a)], dry_run=True).pairs[-1][1] == str(
        a.with_name("part_two.txt")
    )
    cfg.safety.sanitize = False
    with pytest.raises(PipelineError, match="备用数据流"):
        pipeline.run_editor_mode([str(a)], dry_run=True)
    cfg.safety.sanitize = True
    edit(a)
    cfg.auto_rules = [Rule(scope="name", kind="insert", insert="C:")]
    with pytest.raises(PipelineError, match="备用数据流"):
        pipeline.run_editor_mode([str(a)], dry_run=True)
    cfg.auto_rules = []
    edit(a.with_name("<clip>.txt"))
    pipeline.clipboard_text = "C:part"
    assert pipeline.run_editor_mode([str(a)], dry_run=True).pairs[-1][1] == str(
        a.with_name("C_part.txt")
    )
    edit(a.with_name("a.txt:stream"))
    with pytest.raises(PipelineError, match="备用数据流"):
        pipeline.run_editor_mode([str(a)], dry_run=True)


def test_exchange_and_chain_stage_only_moving_dependencies(
    tmp_path, cfg, edit, monkeypatch
):
    a, b, c, d, e = [write(tmp_path / name, name) for name in "abcde"]
    f = tmp_path / "f"
    edit(b, a, d, f, e)
    native = pathitem.rename_no_replace
    actions = []

    def record(old, new):
        actions.append((old, new))
        native(old, new)

    monkeypatch.setattr(pathitem, "rename_no_replace", record)
    outcome = RenamePipeline(cfg, absolute=True).run_editor_mode(
        list(map(str, (a, b, c, d, e)))
    )
    assert outcome.result.success == list(
        zip(map(str, (a, b, c, d)), map(str, (b, a, d, f)))
    )
    assert outcome.result.skipped == [str(e)]
    assert {
        Path(old)
        for old, new in actions
        if Path(new).name.startswith(".__onomedit_tmp_")
    } == {a, b, d}
    assert [p.read_text(encoding="utf-8") for p in (a, b, d, e, f)] == list("baced")
    assert not c.exists()


def test_case_only_move_and_hard_links_are_separate_entries(tmp_path, cfg, edit):
    a = write(tmp_path / "name.txt", "A")
    hardlink = tmp_path / "other.txt"
    os.link(a, hardlink)
    upper = a.with_name("Name.txt")
    edit(upper, hardlink)
    result = (
        RenamePipeline(cfg, absolute=True)
        .run_editor_mode([str(a), str(hardlink)])
        .result
    )
    assert result.success == [(str(a), str(upper))]
    assert result.skipped == [str(hardlink)]
    assert {p.name for p in tmp_path.iterdir()} >= {upper.name, hardlink.name}
    assert a.name not in {p.name for p in tmp_path.iterdir()}
    assert upper.samefile(hardlink)


def test_skipped_occupant_and_planned_number_are_reserved(tmp_path, cfg, edit):
    a = write(tmp_path / "a", "A")
    b = write(tmp_path / "b.txt", "B")
    c = write(tmp_path / "c", "C")
    reserved = b.with_name("b (1).txt")
    edit(b, b, reserved)
    outcome = RenamePipeline(cfg, absolute=True).run_editor_mode(
        [str(a), str(b), str(c)]
    )
    landed = b.with_name("b (2).txt")
    assert outcome.result.success == [(str(a), str(landed)), (str(c), str(reserved))]
    assert outcome.result.skipped == [str(b)]
    assert [p.read_text(encoding="utf-8") for p in (landed, b, reserved)] == [
        "A",
        "B",
        "C",
    ]
    assert RenameLogger(config.log_dir()).read_last() == outcome.result.success


def test_parent_alias_deduplication_and_duplicate_goals(tmp_path, cfg, edit):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    symlink(alias, real, directory=True)
    a = write(real / "a", "A")
    b = write(real / "b", "B")
    captured = edit(a, b)
    outcome = RenamePipeline(cfg, absolute=True).run_editor_mode(
        [str(alias / "a"), str(a), str(b)]
    )
    assert captured["lines"] == [str(alias / "a"), str(b)]
    assert outcome.result.skipped == captured["lines"]
    edit(real / "out", alias / "out")
    with pytest.raises(PipelineError, match="目标重名"):
        RenamePipeline(cfg, absolute=True).run_editor_mode(
            [str(a), str(b)], dry_run=True
        )


@pytest.mark.parametrize(
    "case",
    ["selected_child", "own_subtree", "target_contains_source", "nested_targets"],
)
def test_directory_dependency_is_preflighted(tmp_path, cfg, edit, case):
    log = seed_log()
    directory = tmp_path / "dir"
    directory.mkdir()
    child = write(directory / "child", "CHILD")
    outside = write(tmp_path / "outside", "OUTSIDE")
    out = tmp_path / "new"
    sources, targets = {
        "selected_child": ([directory, child], [out, child]),
        "own_subtree": ([directory, outside], [directory / "inside", out]),
        "target_contains_source": ([child, outside], [out, directory]),
        "nested_targets": ([child, outside], [out, out / "nested"]),
    }[case]
    edit(*targets)
    with pytest.raises(PipelineError, match="目录依赖"):
        RenamePipeline(cfg, absolute=True).run_editor_mode(list(map(str, sources)))
    assert not out.exists()
    assert child.read_text(encoding="utf-8") == "CHILD"
    assert outside.read_text(encoding="utf-8") == "OUTSIDE"
    assert log.read_last() == [("older", "record")]


def test_directory_alias_dependency(tmp_path, cfg, edit):
    directory = tmp_path / "dir"
    directory.mkdir()
    alias = tmp_path / "alias"
    symlink(alias, directory, directory=True)
    edit(alias / "inside")
    with pytest.raises(PipelineError, match="目录依赖"):
        RenamePipeline(cfg, absolute=True).run_editor_mode([str(directory)])


@pytest.mark.skipif(os.name != "nt", reason="Windows junctions")
def test_junction_parent_is_a_directory_alias(tmp_path, cfg, edit):
    directory = tmp_path / "dir"
    directory.mkdir()
    alias = tmp_path / "junction"
    subprocess.run(
        ["cmd", "/d", "/c", "mklink", "/J", str(alias), str(directory)], check=True
    )
    edit(alias / "inside")
    with pytest.raises(PipelineError, match="目录依赖"):
        RenamePipeline(cfg, absolute=True).run_editor_mode([str(directory)])


def test_absolute_moves_a_directory_with_its_contents(tmp_path, cfg, edit):
    source = tmp_path / "dir"
    source.mkdir()
    write(source / "child", "CHILD")
    dest = tmp_path / "new" / "dir"
    edit(dest)
    result = RenamePipeline(cfg, absolute=True).run_editor_mode([str(source)]).result
    assert result.success == [(str(source), str(dest))]
    assert not source.exists()
    assert (dest / "child").read_text(encoding="utf-8") == "CHILD"


def test_source_link_identity_is_kept_when_selected(tmp_path, cfg, edit):
    real = write(tmp_path / "real", "REAL")
    link = tmp_path / "link"
    symlink(link, real)
    dest = tmp_path / "dest"
    captured = edit(dest)
    pipeline = RenamePipeline(cfg, absolute=True)
    with pytest.raises(PipelineError, match="排除规则"):
        pipeline.run_editor_mode([str(link)])
    cfg.exclude.symlinks = False
    result = pipeline.run_editor_mode([str(link)]).result
    assert result.success == [(str(link), str(dest))]
    assert captured["lines"] == [str(link)]
    assert dest.is_symlink() and not os.path.lexists(link)
    assert real.read_text(encoding="utf-8") == "REAL"


@pytest.mark.parametrize("dangling", [False, True])
def test_invalid_existing_target_ancestor(tmp_path, cfg, edit, dangling):
    source = write(tmp_path / "source", "A")
    ancestor = tmp_path / "ancestor"
    if dangling:
        symlink(ancestor, tmp_path / "missing", directory=True)
    else:
        write(ancestor, "BLOCKER")
    edit(ancestor / "subdir" / "file")
    with pytest.raises(PipelineError, match="第 1 行"):
        RenamePipeline(cfg, absolute=True).run_editor_mode([str(source)], dry_run=True)


def test_dangling_final_link_is_numbered(tmp_path, cfg, edit):
    a = write(tmp_path / "a", "A")
    target = tmp_path / "target.txt"
    symlink(target, tmp_path / "missing")
    edit(target)
    result = RenamePipeline(cfg, absolute=True).run_editor_mode([str(a)]).result
    landed = target.with_name("target (1).txt")
    assert result.success == [(str(a), str(landed))]
    assert landed.read_text(encoding="utf-8") == "A"
    assert target.is_symlink() and not target.exists()


def test_native_rename_never_replaces_an_existing_entry(tmp_path):
    source = write(tmp_path / "source", "A")
    target = write(tmp_path / "target", "B")
    with pytest.raises(FileExistsError):
        pathitem.rename_no_replace(str(source), str(target))
    assert source.read_text(encoding="utf-8") == "A"
    assert target.read_text(encoding="utf-8") == "B"
    vacant = str(tmp_path / "vacant")
    pathitem.rename_no_replace(str(source), vacant)
    assert Path(vacant).read_text(encoding="utf-8") == "A"


def test_late_target_creation_uses_native_no_replace_and_retries(
    tmp_path, cfg, edit, monkeypatch
):
    a = write(tmp_path / "a", "A")
    target = tmp_path / "dest" / "target.txt"
    edit(target)
    native = pathitem.rename_no_replace

    def race(old, new):
        if new == str(target):
            write(target, "RACER")
        native(old, new)

    monkeypatch.setattr(pathitem, "rename_no_replace", race)
    result = RenamePipeline(cfg, absolute=True).run_editor_mode([str(a)]).result
    landed = target.with_name("target (1).txt")
    assert result.success == [(str(a), str(landed))]
    assert target.read_text(encoding="utf-8") == "RACER"
    assert landed.read_text(encoding="utf-8") == "A"


def test_cross_device_preflight_preserves_previous_log(
    tmp_path, cfg, edit, monkeypatch
):
    log = seed_log()
    source = write(tmp_path / "source", "A")
    dest = tmp_path / "missing" / "file"
    edit(dest)
    inspect = absolute_rename.inspect_parent

    def other_device(path):
        parent = inspect(path)
        if Path(path) == dest.parent:
            last = parent.existing[-1]
            last = replace(
                last,
                directory=last.directory._replace(device=last.directory.device + 1),
            )
            parent = replace(parent, existing=(*parent.existing[:-1], last))
        return parent

    monkeypatch.setattr(absolute_rename, "inspect_parent", other_device)
    with pytest.raises(PipelineError, match="跨卷"):
        RenamePipeline(cfg, absolute=True).run_editor_mode([str(source)])
    assert source.read_text(encoding="utf-8") == "A"
    assert not dest.parent.exists()
    assert log.read_last() == [("older", "record")]


@pytest.mark.skipif(
    sys.platform != "linux", reason="Uses a separate Linux /dev/shm mount"
)
def test_real_cross_device_rename(tmp_path, cfg, edit):
    shared = Path("/dev/shm")
    if not shared.is_dir() or shared.stat().st_dev == tmp_path.stat().st_dev:
        pytest.skip("A separate shared-memory filesystem is required")
    source = write(tmp_path / "source", "A")
    with tempfile.TemporaryDirectory(dir=shared) as directory:
        target = Path(directory) / "file"
        edit(target)
        with pytest.raises(PipelineError, match="跨卷"):
            RenamePipeline(cfg, absolute=True).run_editor_mode([str(source)])
        with pytest.raises(OSError) as failure:
            pathitem.rename_no_replace(str(source), str(target))
        assert failure.value.errno == errno.EXDEV
        assert source.read_text(encoding="utf-8") == "A"
        assert not target.exists()


def test_unsupported_platform_can_preview(tmp_path, cfg, edit, monkeypatch):
    log = seed_log()
    source = write(tmp_path / "source", "A")
    dest = tmp_path / "missing" / "file"
    edit(dest)

    def unsupported():
        raise OSError(errno.ENOTSUP, "exclusive rename unavailable")

    monkeypatch.setattr(pathitem, "require_rename_no_replace", unsupported)
    pipeline = RenamePipeline(cfg, absolute=True)
    assert pipeline.run_editor_mode([str(source)], dry_run=True).pairs == [
        (str(source), str(dest))
    ]
    with pytest.raises(PipelineError, match="exclusive rename unavailable"):
        pipeline.run_editor_mode([str(source)])
    assert source.read_text(encoding="utf-8") == "A"
    assert not dest.parent.exists()
    assert log.read_last() == [("older", "record")]


@pytest.mark.parametrize("code", [errno.EXDEV, errno.EACCES, errno.ENOTSUP])
def test_native_move_error_preserves_source_and_reports_target(
    tmp_path, cfg, edit, monkeypatch, code
):
    a = write(tmp_path / "a", "A")
    target = tmp_path / "created" / "target"
    edit(target)

    def fail(_old, _new):
        raise OSError(code, "injected failure")

    monkeypatch.setattr(pathitem, "rename_no_replace", fail)
    result = RenamePipeline(cfg, absolute=True).run_editor_mode([str(a)]).result
    old, new, reason = result.failed[0]
    assert (old, new) == (str(a), str(target))
    assert "injected failure" in reason
    if code == errno.EXDEV:
        assert "跨卷" in reason
    assert a.read_text(encoding="utf-8") == "A"
    assert target.parent.is_dir() and not target.exists()
    log = RenameLogger(config.log_dir())
    assert log.read_last() == []
    assert "injected failure" in log.error_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("blocked", [False, True])
def test_failed_staged_move_recovers_or_reports_actual_location(
    tmp_path, cfg, edit, monkeypatch, blocked
):
    a = write(tmp_path / "a", "A")
    b = write(tmp_path / "b", "B")
    dest = tmp_path / "dest"
    edit(b, dest)
    native = pathitem.rename_no_replace

    def fail(old, new):
        if new == str(dest) or (not blocked and old == str(a) and new == str(b)):
            raise PermissionError(errno.EACCES, "injected failure")
        native(old, new)

    monkeypatch.setattr(pathitem, "rename_no_replace", fail)
    result = RenamePipeline(cfg, absolute=True).run_editor_mode([str(a), str(b)]).result
    temps = list(tmp_path.glob(".__onomedit_tmp_*"))
    log = RenameLogger(config.log_dir())
    if blocked:
        (recovery,) = temps
        assert recovery.read_text(encoding="utf-8") == "B"
        assert b.read_text(encoding="utf-8") == "A"
        assert str(recovery) in result.failed[0][2]
        assert str(recovery) in log.error_path.read_text(encoding="utf-8")
        assert log.read_last() == [(str(a), str(b))]
    else:
        assert temps == []
        assert log.read_last() == []
        assert b.read_text(encoding="utf-8") == "B"
        assert a.read_text(encoding="utf-8") == "A"


def test_source_replacement_during_edit_stops_before_session(tmp_path, cfg, edit):
    log = seed_log()
    source = write(tmp_path / "source", "original")
    saved = tmp_path / "saved"
    target = tmp_path / "new" / "target"

    def replace():
        source.rename(saved)
        write(source, "replacement")

    edit(target, before_save=replace)
    with pytest.raises(PipelineError, match="源目录项已变化"):
        RenamePipeline(cfg, absolute=True).run_editor_mode([str(source)])
    assert log.read_last() == [("older", "record")]
    assert not target.parent.exists()
    assert saved.read_text(encoding="utf-8") == "original"
    assert source.read_text(encoding="utf-8") == "replacement"


def test_target_parent_replacement_after_preflight_stops_before_move(
    tmp_path, cfg, edit, monkeypatch
):
    source = write(tmp_path / "source", "A")
    parent = tmp_path / "parent"
    parent.mkdir()
    dest = parent / "sub" / "target"
    edit(dest)
    begin = RenameLogger.begin_session

    def replace(log):
        begin(log)
        parent.rename(parent.with_name("saved"))
        parent.mkdir()

    monkeypatch.setattr(RenameLogger, "begin_session", replace)
    result = RenamePipeline(cfg, absolute=True).run_editor_mode([str(source)]).result
    assert "父目录已变化" in result.failed[0][2]
    assert source.read_text(encoding="utf-8") == "A"
    assert not dest.parent.exists()


def test_staged_source_alias_swap_reports_physical_recovery_path(
    tmp_path, cfg, edit, monkeypatch
):
    source = write(tmp_path / "source", "A")
    real = tmp_path / "real"
    other = tmp_path / "other"
    real.mkdir()
    other.mkdir()
    original = write(real / "b", "B")
    alias = tmp_path / "alias"
    symlink(alias, real, directory=True)
    dest = tmp_path / "target"
    edit(original, dest)
    native = pathitem.rename_no_replace

    def swap_alias(old, new):
        native(old, new)
        if Path(new).name.startswith(".__onomedit_tmp_"):
            alias.rename(tmp_path / "old_alias")
            symlink(alias, other, directory=True)

    monkeypatch.setattr(pathitem, "rename_no_replace", swap_alias)
    result = (
        RenamePipeline(cfg, absolute=True)
        .run_editor_mode([str(source), str(alias / "b")])
        .result
    )
    assert result.success == [(str(source), str(original))]
    (recovery,) = real.glob(".__onomedit_tmp_*")
    assert recovery.read_text(encoding="utf-8") == "B"
    assert str(recovery) in result.failed[0][2]
    assert original.read_text(encoding="utf-8") == "A"
    assert not dest.exists()


def test_active_last_log_alias_does_not_get_truncated(tmp_path, cfg, edit):
    log = seed_log()
    linked = tmp_path / "same-log-data"
    os.link(log.last_path, linked)
    edit(tmp_path / "target")
    with pytest.raises(PipelineError, match="活动日志"):
        RenamePipeline(cfg, absolute=True).run_editor_mode([str(linked)])
    assert log.read_last() == [("older", "record")]
    assert linked.samefile(log.last_path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX resolves '..' through symlinks")
def test_source_dot_segments_preserve_directory_entry_identity(
    tmp_path, cfg, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    deepest = tmp_path / "outer" / "inner"
    deepest.mkdir(parents=True)
    symlink(tmp_path / "alias", deepest, directory=True)
    write(tmp_path / "outer" / "source", "real target")
    write(tmp_path / "source", "lexical target")
    cfg.open_editor = False
    pipeline = RenamePipeline(cfg, absolute=True)
    with pytest.raises(PipelineError, match="源目录项相同"):
        pipeline.run_editor_mode(["alias/../source"], dry_run=True)
    with pytest.raises(PipelineError, match="源目录项相同"):
        pipeline.run_editor_mode(["alias/."], dry_run=True)
    assert pipeline.run_editor_mode(["outer/."], dry_run=True).pairs == [
        (str(deepest.parent), str(deepest.parent))
    ]


@pytest.mark.skipif(
    os.name != "posix", reason="These characters require POSIX filenames"
)
@pytest.mark.parametrize("name", ["a\nline", "bad<-->name", "bad\udcffname"])
def test_unserializable_source_stops_before_editor(tmp_path, cfg, monkeypatch, name):
    try:
        source = write(tmp_path / name, "content")
    except OSError as exc:
        if exc.errno in (errno.EILSEQ, errno.EINVAL):
            pytest.skip("The filesystem rejects this filename")
        raise

    def unexpected(*_args, **_kwargs):
        pytest.fail("invalid source must stop before launching the editor")

    monkeypatch.setattr(editor, "launch_and_wait", unexpected)
    with pytest.raises(PipelineError, match="第 1 行"):
        RenamePipeline(cfg, absolute=True).run_editor_mode([str(source)])
    assert not config.log_dir().exists()
