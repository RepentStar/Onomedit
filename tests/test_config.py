"""配置读写 / 默认值合并 / 损坏回退 / 按 KEY 设置。"""

import json

import pytest

from onomedit.core import config as config_mod
from onomedit.core.rules import Rule, rule_to_dict


def test_default_values():
    cfg = config_mod.default_config()
    assert cfg.path_type == "stem"
    assert cfg.open_editor is True
    assert cfg.apply_rules is True
    assert cfg.exclude.hidden is True
    assert cfg.exclude.files is False
    # 默认：差异/距离预览关闭；展开子文件夹开启（层级 10）
    assert cfg.preview.diff is False
    assert cfg.preview.distance is False
    assert cfg.expand_subdirs is True
    assert cfg.subdirs_depth == 10
    assert cfg.sort_by == "default"  # 重命名顺序默认不排序
    assert cfg.sort_reverse is False  # 默认不反转
    assert cfg.safety.sanitize is True
    assert cfg.skip_confirmation is True  # 跳过重命名确认默认开启
    assert cfg.exit_after is True  # 完成后退出默认开启
    assert cfg.version == config_mod.CONFIG_VERSION


def test_to_from_dict_roundtrip():
    cfg = config_mod.default_config()
    cfg.editor = "notepad"
    cfg.editor_timeout = 30.5
    cfg.exclude.readonly = True
    cfg.sort_by = "mtime"
    cfg.sort_reverse = True
    cfg.auto_rules = [Rule(scope="stem", kind="replace", find="a", replace="b")]
    data = config_mod.to_dict(cfg)
    restored = config_mod.from_dict(data)
    assert restored.editor == "notepad"
    assert restored.editor_timeout == 30.5
    assert restored.exclude.readonly is True
    assert restored.sort_by == "mtime"
    assert restored.sort_reverse is True
    assert len(restored.auto_rules) == 1
    assert restored.auto_rules[0].find == "a"


def test_from_dict_fills_defaults_for_missing():
    cfg = config_mod.from_dict({"editor": "vim"})
    assert cfg.editor == "vim"
    assert cfg.path_type == "stem"  # 默认值填充
    assert cfg.exclude.hidden is True


def test_from_dict_ignores_unknown_keys():
    cfg = config_mod.from_dict({"editor": "x", "unknown_key": 1, "exclude": {"no_such": True}})
    assert cfg.editor == "x"
    assert cfg.exclude.hidden is True  # 未知子键忽略


def test_load_save_roundtrip(isolated_config):
    cfg = config_mod.load_config()
    cfg.editor = "code -w"
    config_mod.save_config(cfg)
    again = config_mod.load_config()
    assert again.editor == "code -w"


def test_load_corrupt_falls_back(isolated_config):
    path = config_mod.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not valid json !!!", encoding="utf-8")
    cfg = config_mod.load_config()
    assert cfg.path_type == "stem"  # 回退默认
    assert path.with_suffix(".json.bak").exists()  # 原文件备份


def test_load_missing_writes_default(isolated_config):
    cfg = config_mod.load_config()
    assert config_mod.config_path().exists()


def test_set_value_type_inference(isolated_config):
    cfg = config_mod.default_config()
    assert config_mod.set_value(cfg, "exclude.hidden", "false") == "exclude.hidden = false"
    assert cfg.exclude.hidden is False
    config_mod.set_value(cfg, "subdirs_depth", "3")
    assert cfg.subdirs_depth == 3
    config_mod.set_value(cfg, "editor_timeout", "45.5")
    assert cfg.editor_timeout == 45.5
    config_mod.set_value(cfg, "editor", "notepad")
    assert cfg.editor == "notepad"


def test_set_value_errors(isolated_config):
    cfg = config_mod.default_config()
    with pytest.raises(KeyError):
        config_mod.set_value(cfg, "no.such.key", "1")
    with pytest.raises(ValueError):
        config_mod.set_value(cfg, "exclude.hidden", "maybe")


def test_set_value_auto_rules_json(isolated_config):
    cfg = config_mod.default_config()
    raw = '[{"scope": "stem", "kind": "replace", "find": "a", "replace": "b"}]'
    config_mod.set_value(cfg, "auto_rules", raw)
    assert len(cfg.auto_rules) == 1
    assert cfg.auto_rules[0].kind == "replace"


def test_config_dir_location(isolated_config):
    assert config_mod.config_dir().name == "Onomedit"


def test_ensure_default_editor_fills_when_empty(monkeypatch):
    cfg = config_mod.default_config()
    assert cfg.editor == ""
    monkeypatch.setattr(config_mod, "detect_default_editor", lambda: "notepad")
    config_mod._ensure_default_editor(cfg)
    assert cfg.editor == "notepad"


def test_ensure_default_editor_keeps_existing(monkeypatch):
    cfg = config_mod.default_config()
    cfg.editor = "vim"
    monkeypatch.setattr(config_mod, "detect_default_editor", lambda: "notepad")
    config_mod._ensure_default_editor(cfg)
    assert cfg.editor == "vim"  # 已配置不覆盖


def test_ensure_default_editor_no_detect_keeps_empty(monkeypatch):
    cfg = config_mod.default_config()
    monkeypatch.setattr(config_mod, "detect_default_editor", lambda: "")
    config_mod._ensure_default_editor(cfg)
    assert cfg.editor == ""


def test_load_config_fills_default_editor_on_first_run(isolated_config, monkeypatch):
    """首次启动（配置缺失）：自动探测默认编辑器并写入配置。"""
    monkeypatch.setattr(config_mod, "detect_default_editor", lambda: "notepad")
    cfg = config_mod.load_config()
    assert cfg.editor == "notepad"
    # 已持久化：再次加载仍保留
    again = config_mod.load_config()
    assert again.editor == "notepad"


def test_load_config_fills_empty_editor_in_existing_config(isolated_config, monkeypatch):
    """旧配置 editor 为空：加载时补写探测结果。"""
    path = config_mod.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"editor": ""}', encoding="utf-8")
    monkeypatch.setattr(config_mod, "detect_default_editor", lambda: "notepad")
    cfg = config_mod.load_config()
    assert cfg.editor == "notepad"


def test_load_config_keeps_configured_editor(isolated_config, monkeypatch):
    """已配置编辑器：不被探测覆盖。"""
    path = config_mod.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"editor": "myeditor"}', encoding="utf-8")
    monkeypatch.setattr(config_mod, "detect_default_editor", lambda: "notepad")
    cfg = config_mod.load_config()
    assert cfg.editor == "myeditor"


def _fake_which(available: set[str]):
    """构造 shutil.which 的替身：仅 available 中的命令返回路径。"""
    return lambda name: f"C:/bin/{name}.exe" if name in available else None


def test_detect_win_editor_notepad_first(monkeypatch):
    """Windows：notepad 优先于 code -w。"""
    monkeypatch.setattr(config_mod.shutil, "which", _fake_which({"notepad", "code"}))
    assert config_mod._detect_win_editor() == "notepad"


def test_detect_win_editor_code_fallback(monkeypatch):
    """Windows：无 notepad 时回退 code -w。"""
    monkeypatch.setattr(config_mod.shutil, "which", _fake_which({"code"}))
    assert config_mod._detect_win_editor() == "code -w"


def test_detect_win_editor_none(monkeypatch):
    monkeypatch.setattr(config_mod.shutil, "which", _fake_which(set()))
    assert config_mod._detect_win_editor() == ""


def test_detect_linux_editor_nano_first(monkeypatch):
    """Linux：nano → vi → kate。"""
    monkeypatch.setattr(config_mod.shutil, "which", _fake_which({"nano", "vi", "kate"}))
    assert config_mod._detect_linux_editor() == "nano"
    monkeypatch.setattr(config_mod.shutil, "which", _fake_which({"vi", "kate"}))
    assert config_mod._detect_linux_editor() == "vi"
    monkeypatch.setattr(config_mod.shutil, "which", _fake_which({"kate"}))
    assert config_mod._detect_linux_editor() == "kate"


def test_detect_linux_editor_editor_env_fallback(monkeypatch):
    monkeypatch.setattr(config_mod.shutil, "which", _fake_which(set()))
    monkeypatch.setenv("EDITOR", "myeditor")
    assert config_mod._detect_linux_editor() == "myeditor"


def test_migrate_noop_on_current():
    cfg = config_mod.default_config()
    migrated = config_mod.migrate(cfg)
    assert migrated.version == config_mod.CONFIG_VERSION


def test_merge_exclude_tags_aliases():
    base = config_mod.ExcludeOptions()
    merged = config_mod.merge_exclude_tags(base, ["f", "d", "l", "r", "h", "s"])
    assert merged.files and merged.dirs and merged.symlinks
    assert merged.readonly and merged.hidden and merged.system
    # 全名与别名等价
    assert config_mod.merge_exclude_tags(base, ["file"]).files
    assert config_mod.merge_exclude_tags(base, ["dir"]).dirs
    assert config_mod.merge_exclude_tags(base, ["link"]).symlinks
    assert config_mod.merge_exclude_tags(base, ["readonly"]).readonly
    assert config_mod.merge_exclude_tags(base, ["hidden"]).hidden
    assert config_mod.merge_exclude_tags(base, ["system"]).system


def test_merge_exclude_tags_preserves_base_and_defaults():
    base = config_mod.ExcludeOptions(files=True, hidden=False)
    merged = config_mod.merge_exclude_tags(base, ["h"])
    assert merged.files is True  # 已有排除位保留
    assert merged.hidden is True  # 新增位打开
    assert merged.system is True  # 默认值保留
    assert merged.dirs is False  # 未指定保持关闭
    # 原对象不受影响（“临时排除”不写回配置）
    assert base.files is True and base.hidden is False


def test_merge_exclude_tags_no_tags_returns_copy():
    base = config_mod.ExcludeOptions(readonly=True)
    merged = config_mod.merge_exclude_tags(base, [])
    assert merged is not base and merged.readonly is True
