"""CLI 补全生成：completion 子命令与各 shell 脚本内容守卫。"""

import pytest

from onomedit.cli import build_parser
from onomedit.core import completion


def _all_subs() -> list[str]:
    return list(completion.SUBCOMMANDS)


def test_supported_shells_order():
    assert completion.supported_shells() == ("bash", "zsh", "pwsh", "fish", "psc")


def test_unknown_shell_rejected():
    with pytest.raises(ValueError):
        completion.completion_for("tcsh")


def test_powershell_alias_maps_to_pwsh():
    assert completion.completion_for("powershell") == completion.completion_for("pwsh")


def test_every_shell_mentions_all_subcommands():
    for name in completion.supported_shells():
        script = completion.completion_for(name)
        for sub in _all_subs():
            assert sub in script, f"{name} 补全缺子命令 {sub}"


def test_bash_covers_rename_and_config():
    script = completion.completion_for("bash")
    for flag in ("--dry-run", "--no-editor", "--multi-tab", "--reverse", "--path-type", "--sort-by"):
        assert flag in script
    for action in ("set", "set-editor", "reset"):
        assert action in script


def test_bash_value_choices_present():
    script = completion.completion_for("bash")
    for vals in completion._VALUE_CHOICES.values():
        for v in vals:
            assert v in script, f"bash 取值缺 {v}"


def test_zsh_covers_rename_options():
    script = completion.completion_for("zsh")
    for flag in ("--dry-run", "--timeout", "--path-type", "--sort-by", "--exclude"):
        assert flag in script


def test_zsh_value_candidates_embedded():
    script = completion.completion_for("zsh")
    assert "full name stem ext" in script
    assert "default name path mtime ctime size" in script


def test_pwsh_registers_completer_and_values():
    script = completion.completion_for("pwsh")
    assert "Register-ArgumentCompleter" in script
    # exe 调用（打包后的 onomedit.exe）同样触发补全
    assert "-CommandName onomedit, onomedit.exe" in script
    assert "--path-type" in script and "full" in script


def test_fish_covers_subcommands_and_flags():
    script = completion.completion_for("fish")
    assert "complete -c onomedit" in script
    assert "set set-editor reset" in script
    assert "-l dry-run" in script


def test_psc_is_custom_completer_with_tips():
    script = completion.completion_for("psc")
    # 普通命令名 + exe（打包后的 onomedit.exe 也触发），-Tip 非 Native 补全
    assert "Register-ArgumentCompleter -CommandName onomedit, onomedit.exe" in script
    assert "-Native" not in script
    # 候选带中文 tip
    assert "tip='生成 shell 补全脚本'" in script
    assert "tip='编辑器模式批量重命名'" in script
    # 值型选项取值
    assert "tip='完整路径'" in script and "full" in script


def test_cli_parses_completion_shell():
    args = build_parser().parse_args(["completion", "zsh"])
    assert args.shell == "zsh"
    assert args.handler is not None


def test_cli_rejects_unknown_shell():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["completion", "tcsh"])
