"""重命名主流程：编辑器拉起/不拉起、规则与环境变量、行数校验、恢复、冲突处理。"""

import os

import pytest

from onomedit.core import config as config_mod
from onomedit.core.envvars import EnvContext, EnvVars
from onomedit.core.logger import RenameLogger
from onomedit.core.pathitem import PathItem
from onomedit.core.pipeline import (
    PipelineError,
    PipelineOutcome,
    RenamePipeline,
    Renamer,
    diff_text,
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


# ---------------------------------------------------------------- 完整流程
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


# ---------------------------------------------------------------- 恢复
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


# ---------------------------------------------------------------- 执行器细节
def test_duplicate_target_fails(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("1", encoding="utf-8")
    b.write_text("2", encoding="utf-8")
    target = str(tmp_path / "same.txt")
    result = Renamer().run([(str(a), target), (str(b), target)])
    assert len(result.failed) == 1  # 目标重复预检
    assert len(result.success) == 1
    assert (tmp_path / "same.txt").exists()


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


# ---------------------------------------------------------------- 预览工具
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
