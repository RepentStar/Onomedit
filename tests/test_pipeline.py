"""重命名主流程：编辑器拉起/不拉起、规则与环境变量、行数校验、恢复、冲突处理。"""

import os

import pytest

from onomedit.core import config as config_mod
from onomedit.core.envvars import EnvContext, EnvVars
from onomedit.core.logger import RenameLogger
from onomedit.core.pathitem import PathItem
from onomedit.core.pipeline import (
    DuplicateTargetError,
    PipelineError,
    PipelineOutcome,
    RenamePipeline,
    Renamer,
    diff_text,
    find_duplicate_targets,
    levenshtein,
    restore,
)
from onomedit.core.rules import Rule
from onomedit.core import tempfile_mgr
from conftest import fake_editor_cmd


def _make_files(tmp_path, names=("a.txt", "b.txt", "c.txt")):
    paths = []
    for n in names:
        p = tmp_path / n
        p.write_text(n, encoding="utf-8")
        paths.append(str(p))
    return paths


def _cfg(tmp_path, **overrides):
    cfg = config_mod.default_config()
    cfg.temp_dir = str(tmp_path / "tmp")
    # 测试用短超时：假编辑器快速退出且未修改时会触发启动器型轮询
    cfg.editor_timeout = 3.0
    (tmp_path / "tmp").mkdir(exist_ok=True)
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def test_full_flow_editor_save(tmp_path, isolated_config):
    """流程 1：拉起编辑器 → 用户保存新名 → 重命名成功 + 日志。"""
    paths = _make_files(tmp_path)
    # path_type=stem：用户编辑第 1 行的"不带扩展名"部分为 renamed
    cfg = _cfg(tmp_path, editor=fake_editor_cmd("set", "1", "renamed"))
    pipeline = RenamePipeline(cfg)
    outcome = pipeline.run_editor_mode(paths)
    assert len(outcome.result.success) == 1
    assert (tmp_path / "renamed.txt").exists()
    assert not (tmp_path / "a.txt").exists()
    # 日志写入（隔离配置目录）
    log = RenameLogger(config_mod.log_dir())
    assert log.read_last() == [(str(tmp_path / "a.txt"), str(tmp_path / "renamed.txt"))]


def test_full_flow_no_editor_applies_rules(tmp_path, isolated_config):
    """不拉起编辑器（open_editor=False）+ 自动规则 → 直接应用。"""
    paths = _make_files(tmp_path)
    cfg = _cfg(
        tmp_path,
        open_editor=False,
        auto_rules=[Rule(scope="stem", kind="replace", find="a", replace="alpha")],
    )
    outcome = RenamePipeline(cfg).run_editor_mode(paths)
    assert len(outcome.result.success) == 1
    assert (tmp_path / "alpha.txt").exists()


def test_editor_exit_without_change_noop(tmp_path, isolated_config):
    """仅编辑器语义：编辑器未修改（退出）→ 全部无变化。"""
    paths = _make_files(tmp_path)
    cfg = _cfg(tmp_path, editor=fake_editor_cmd("exit"))
    outcome = RenamePipeline(cfg).run_editor_mode(paths)
    assert len(outcome.result.success) == 0
    assert len(outcome.result.skipped) == 3  # 3 个文件都无变化


def test_envvar_counter_continues_across_files(tmp_path, isolated_config):
    """环境变量递增跨文件延续（历史教训 3）。"""
    paths = _make_files(tmp_path)
    cfg = _cfg(
        tmp_path,
        open_editor=False,
        auto_rules=[Rule(scope="name", kind="regex", find=r"^.*$", replace="img_<n>1;3;1;.txt")],
    )
    outcome = RenamePipeline(cfg).run_editor_mode(paths)
    assert (tmp_path / "img_001.txt").exists()
    assert (tmp_path / "img_002.txt").exists()
    assert (tmp_path / "img_003.txt").exists()


def test_line_count_mismatch_aborts(tmp_path, isolated_config):
    """行数不一致必须中止（历史教训 8），不执行任何重命名。"""
    # 单元级：read_lines 校验
    names = tmp_path / "names.txt"
    names.write_text("a\nb\n", encoding="utf-8")
    with pytest.raises(tempfile_mgr.LineCountError):
        tempfile_mgr.read_lines(names, 3)

    # 流程级：假编辑器删行后读回 → LineCountError
    paths = _make_files(tmp_path)
    cfg = _cfg(tmp_path, editor=fake_editor_cmd("truncate", "1"))
    with pytest.raises(tempfile_mgr.LineCountError):
        RenamePipeline(cfg).run_editor_mode(paths)
    # 中止后不执行任何重命名
    assert (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").exists()
    assert (tmp_path / "c.txt").exists()


def test_dry_run_does_not_rename(tmp_path, isolated_config):
    paths = _make_files(tmp_path)
    cfg = _cfg(tmp_path, open_editor=False, auto_rules=[Rule(scope="stem", kind="replace", find="a", replace="x")])
    outcome = RenamePipeline(cfg).run_editor_mode(paths, dry_run=True)
    assert outcome.dry_run
    assert (tmp_path / "a.txt").exists()  # 未执行
    assert (tmp_path / "x.txt").exists() is False
    assert len(outcome.pairs) == 3  # 所有文件都有计划对
    assert any(new == str(tmp_path / "x.txt") for _, new in outcome.pairs)


def test_prepare_requires_existing_files(tmp_path, isolated_config):
    cfg = _cfg(tmp_path, open_editor=False)
    with pytest.raises(PipelineError):
        RenamePipeline(cfg).run_editor_mode([str(tmp_path / "ghost.txt")])


def test_missing_editor_raises(tmp_path, isolated_config):
    paths = _make_files(tmp_path)
    cfg = _cfg(tmp_path, editor="")
    with pytest.raises(PipelineError):
        RenamePipeline(cfg).run_editor_mode(paths)


def test_restore_last(tmp_path, isolated_config):
    paths = _make_files(tmp_path)
    cfg = _cfg(tmp_path, open_editor=False, auto_rules=[Rule(scope="stem", kind="replace", find="a", replace="renamed")])
    RenamePipeline(cfg).run_editor_mode(paths)
    assert (tmp_path / "renamed.txt").exists()

    log = RenameLogger(config_mod.log_dir())
    result = restore(log)
    assert len(result.success) == 1
    assert (tmp_path / "a.txt").exists()
    assert not (tmp_path / "renamed.txt").exists()


def test_restore_partial_lines(tmp_path, isolated_config):
    # 模拟改名后的状态：a.txt 已改名为 z.txt，b.txt 已改名为 y.txt
    z = tmp_path / "z.txt"
    y = tmp_path / "y.txt"
    z.write_text("1", encoding="utf-8")
    y.write_text("2", encoding="utf-8")
    log = RenameLogger(config_mod.log_dir())
    log.begin_session()
    log.record(str(tmp_path / "a.txt"), str(z))
    log.record(str(tmp_path / "b.txt"), str(y))
    # partial 行保持日志格式（旧<-->新），恢复时反向执行
    result = restore(log, partial_lines=[f"{tmp_path / 'a.txt'}<-->{z}"])
    assert len(result.success) == 1
    assert (tmp_path / "a.txt").exists()  # 只恢复了 z.txt→a.txt
    assert not z.exists()


def test_duplicate_target_fails(tmp_path):
    """目标重名 → 抛 DuplicateTargetError 并中止，未执行任何重命名（不"只改其中一个"）。"""
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("1", encoding="utf-8")
    b.write_text("2", encoding="utf-8")
    target = str(tmp_path / "same.txt")
    with pytest.raises(DuplicateTargetError) as excinfo:
        Renamer().run([(str(a), target), (str(b), target)])
    msg = str(excinfo.value)
    # 警告信息包含重复目标与涉及的源文件，且目标/源分行展示（可读性）
    assert f"  目标: {target}" in msg
    assert f"    <- {a}" in msg
    assert f"    <- {b}" in msg
    # 状态栏用一句话摘要
    assert excinfo.value.summary == "检测到目标重名，已中止（未执行任何重命名）: 1 组目标、涉及 2 个文件"
    # 中止：两个源文件都未动，目标文件未产生
    assert (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").exists()
    assert not (tmp_path / "same.txt").exists()


def test_duplicate_target_case_insensitive(tmp_path):
    """Windows 文件系统大小写不敏感：same.txt 与 SAME.TXT 视为同一目标；
    POSIX 上大小写敏感则正常执行。"""
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("1", encoding="utf-8")
    b.write_text("2", encoding="utf-8")
    t1 = str(tmp_path / "same.txt")
    t2 = str(tmp_path / "SAME.TXT")
    if os.path.normcase(t1) == os.path.normcase(t2):
        with pytest.raises(DuplicateTargetError):
            Renamer().run([(str(a), t1), (str(b), t2)])
        assert not (tmp_path / "same.txt").exists()
    else:
        result = Renamer().run([(str(a), t1), (str(b), t2)])
        assert len(result.success) == 2


def test_unchanged_item_not_duplicate_target(tmp_path):
    """保持原名（old == new）不算"重命名到重名目标"，不触发重名中止。"""
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("1", encoding="utf-8")
    b.write_text("2", encoding="utf-8")
    # a→b 且 b 保持原名：按既有链/真冲突逻辑处理，而非重名中止
    result = Renamer().run([(str(a), str(b)), (str(b), str(b))])
    assert result.failed == []
    assert (tmp_path / "b.txt").exists()


def test_find_duplicate_targets_groups():
    """find_duplicate_targets 分组：三源同一目标、两目标名不同、无变化项忽略。"""
    conflicts = find_duplicate_targets(
        [("/d/a.txt", "/d/same.txt"), ("/d/b.txt", "/d/same.txt"), ("/d/c.txt", "/d/other.txt")]
    )
    assert len(conflicts) == 1
    new, olds = conflicts[0]
    assert new == "/d/same.txt"
    assert olds == ["/d/a.txt", "/d/b.txt"]
    # 无变化项不参与判定
    assert find_duplicate_targets([("/d/a.txt", "/d/a.txt"), ("/d/b.txt", "/d/b.txt")]) == []


def test_duplicate_target_error_multiple_groups_format():
    """多组重名：警告按组分行展示，每组目标一行、每个源文件一行。"""
    err = DuplicateTargetError(
        [("/d/same.txt", ["/d/a.txt", "/d/b.txt", "/d/c.txt"]), ("/d/other.txt", ["/d/d.txt", "/d/e.txt"])]
    )
    msg = str(err)
    lines = msg.splitlines()
    assert lines[0] == "检测到目标重名，已中止（未执行任何重命名）:"
    assert lines[1] == "  目标: /d/same.txt"
    assert lines[2:5] == ["    <- /d/a.txt", "    <- /d/b.txt", "    <- /d/c.txt"]
    assert lines[5] == "  目标: /d/other.txt"
    assert lines[6:8] == ["    <- /d/d.txt", "    <- /d/e.txt"]
    assert err.summary == "检测到目标重名，已中止（未执行任何重命名）: 2 组目标、涉及 5 个文件"


def test_duplicate_target_aborts_flow(tmp_path, isolated_config):
    """流程级：编辑/规则产生目标重名 → 抛 DuplicateTargetError，不执行任何重命名。"""
    paths = _make_files(tmp_path)
    cfg = _cfg(
        tmp_path,
        open_editor=False,
        auto_rules=[Rule(scope="stem", kind="regex", find=r"^[abc]$", replace="same")],
    )
    with pytest.raises(DuplicateTargetError):
        RenamePipeline(cfg).run_editor_mode(paths)
    # 中止：三个源文件都未动，目标文件未产生
    assert (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").exists()
    assert (tmp_path / "c.txt").exists()
    assert not (tmp_path / "same.txt").exists()


def test_real_conflict_numbered(tmp_path):
    a = tmp_path / "a.txt"
    (tmp_path / "b.txt").write_text("existing", encoding="utf-8")
    a.write_text("1", encoding="utf-8")
    result = Renamer().run([(str(a), str(tmp_path / "b.txt"))])
    assert len(result.success) == 1
    assert (tmp_path / "b (1).txt").exists()  # 真冲突 → 序号化
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "existing"


def test_swap_cycle_solved(tmp_path):
    """A→B 且 B→A：两阶段解环，双方内容互换。"""
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("AAA", encoding="utf-8")
    b.write_text("BBB", encoding="utf-8")
    result = Renamer().run([(str(a), str(b)), (str(b), str(a))])
    assert len(result.success) == 2, result
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "BBB"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "AAA"


def test_chain_solved(tmp_path):
    """A→B、B→C、C→A 环：全部到位。"""
    names = ("a", "b", "c")
    src = {n: tmp_path / f"{n}.txt" for n in names}
    for p in src.values():
        p.write_text(p.stem, encoding="utf-8")
    pairs = [
        (str(src["a"]), str(src["b"])),
        (str(src["b"]), str(src["c"])),
        (str(src["c"]), str(src["a"])),
    ]
    result = Renamer().run(pairs)
    assert len(result.success) == 3, result
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "c"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "a"
    assert (tmp_path / "c.txt").read_text(encoding="utf-8") == "b"


def test_sanitize_applied_in_plan(tmp_path, isolated_config):
    paths = _make_files(tmp_path)
    cfg = _cfg(tmp_path, open_editor=False, auto_rules=[Rule(scope="stem", kind="replace", find="a", replace="con")])
    outcome = RenamePipeline(cfg).run_editor_mode(paths)
    assert len(outcome.result.success) == 1
    # con.txt 是保留名 → 安全命名加前缀 _con.txt
    assert (tmp_path / "_con.txt").exists()


def test_sort_by_mtime_orders_prepared_items(tmp_path, isolated_config):
    """sort_by 配置作用于 prepare 收集顺序（写入临时文件即排序后顺序）。"""
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("1", encoding="utf-8")
    b.write_text("2", encoding="utf-8")
    past = 1_000_000_000
    os.utime(a, (past, past))
    os.utime(b, (past + 10, past + 10))
    cfg = _cfg(tmp_path, open_editor=False, sort_by="mtime")
    items, _, _ = RenamePipeline(cfg).prepare([str(b), str(a)])
    assert [i.name for i in items] == ["a.txt", "b.txt"]  # 输入顺序 b,a → 按修改时间 a,b


def test_sort_by_default_keeps_input_order(tmp_path, isolated_config):
    """默认不排序：输入顺序原样进入 prepare。"""
    paths = _make_files(tmp_path)
    cfg = _cfg(tmp_path, open_editor=False)  # sort_by 默认 default
    items, _, _ = RenamePipeline(cfg).prepare(paths)
    assert [i.name for i in items] == ["a.txt", "b.txt", "c.txt"]


def test_sort_reverse_reverses_input_order(tmp_path, isolated_config):
    """sort_reverse 开启：原顺序反转（default + reverse）。"""
    paths = _make_files(tmp_path)
    cfg = _cfg(tmp_path, open_editor=False, sort_reverse=True)
    items, _, _ = RenamePipeline(cfg).prepare(paths)
    assert [i.name for i in items] == ["c.txt", "b.txt", "a.txt"]


def test_sort_reverse_mtime_descending(tmp_path, isolated_config):
    """sort_by=mtime + sort_reverse：修改时间新的在前。"""
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("1", encoding="utf-8")
    b.write_text("2", encoding="utf-8")
    past = 1_000_000_000
    os.utime(a, (past, past))
    os.utime(b, (past + 10, past + 10))
    cfg = _cfg(tmp_path, open_editor=False, sort_by="mtime", sort_reverse=True)
    items, _, _ = RenamePipeline(cfg).prepare([str(a), str(b)])
    assert [i.name for i in items] == ["b.txt", "a.txt"]


def test_preview_rows(tmp_path):
    from onomedit.core.pipeline import preview_rows

    items = [PathItem("/d/a.txt")]
    cfg = _cfg(tmp_path)
    # 预览默认关闭；此处显式开启验证计算
    cfg.preview.diff = True
    cfg.preview.distance = True
    rows = preview_rows(items, [("/d/a.txt", "/d/b.txt")], cfg)
    assert rows[0].old == "/d/a.txt"
    assert rows[0].new == "/d/b.txt"
    assert rows[0].diff == "/d/[-a-][+b+].txt"
    assert rows[0].distance == 1  # a→b 单字符替换


def test_preview_rows_disabled_by_default(tmp_path):
    from onomedit.core.pipeline import preview_rows

    items = [PathItem("/d/a.txt")]
    cfg = _cfg(tmp_path)  # 默认：差异/距离关闭
    rows = preview_rows(items, [("/d/a.txt", "/d/b.txt")], cfg)
    assert rows[0].diff == ""
    assert rows[0].distance == 0


def test_diff_text_marks_changes():
    assert "[-b-]" in diff_text("abc", "axc")
    assert "[+x+]" in diff_text("abc", "axc")


def test_levenshtein():
    assert levenshtein("", "abc") == 3
    assert levenshtein("abc", "abc") == 0
    assert levenshtein("kitten", "sitting") == 3


def test_prepare_dedupes_same_path_twice(tmp_path, isolated_config):
    """同一路径显式传入两次：只保留一项，避免同一文件在临时文件出现多行。"""
    paths = _make_files(tmp_path, names=("a.txt",))
    cfg = _cfg(tmp_path, open_editor=False)
    items, _, _ = RenamePipeline(cfg).prepare([paths[0], paths[0]])
    assert [i.full for i in items] == [paths[0]]


def test_prepare_dedupes_glob_overlap(tmp_path, isolated_config):
    """多模式重叠：glob 匹配到 a.txt，显式再给 a.txt → 只算一次。"""
    paths = _make_files(tmp_path)  # a.txt b.txt c.txt
    cfg = _cfg(tmp_path, open_editor=False)
    items, _, _ = RenamePipeline(cfg).prepare([str(tmp_path / "*.txt"), paths[0]])
    assert sorted(i.name for i in items) == ["a.txt", "b.txt", "c.txt"]


def test_prepare_dedupes_nested_subdir_expand(tmp_path, isolated_config):
    """目录 A 与其子目录 A\\sub 同时给出且展开：sub 内文件只出现一次。"""
    folder = tmp_path / "A"
    folder.mkdir()
    (folder / "a.txt").write_text("1", encoding="utf-8")
    (folder / "sub").mkdir()
    (folder / "sub" / "b.txt").write_text("2", encoding="utf-8")
    cfg = _cfg(tmp_path, open_editor=False, expand_subdirs=True, subdirs_depth=3)
    items, _, _ = RenamePipeline(cfg).prepare([str(folder), str(folder / "sub")])
    fulls = [i.full for i in items]
    assert len(fulls) == len(set(fulls))  # 无重复
    assert fulls.count(str(folder / "sub" / "b.txt")) == 1
