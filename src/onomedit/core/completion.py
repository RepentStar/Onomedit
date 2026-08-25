"""为各主流 shell 生成 onomedit 补全脚本。

单一数据源 COMMANDS 描述全部子命令、选项与取值，由各 shell 模板消费，
避免脚本与 CLI 实现漂移；新增参数时改这里并跑测试守卫即可。
"""

from __future__ import annotations

from onomedit.i18n import EN_US, choose, get_language, tr

# 值型选项的补全取值（flag -> 候选）；行内末尾加 = 让 shell 补 `=`.
_VALUE_CHOICES: dict[str, list[str]] = {
    "--path-type": ["full", "name", "stem", "ext"],
    "--sort-by": ["default", "name", "path", "mtime", "ctime", "size"],
    "--exclude": [
        "f",
        "file",
        "d",
        "dir",
        "l",
        "link",
        "r",
        "readonly",
        "h",
        "hidden",
        "s",
        "system",
    ],
}

# 子命令 -> 布尔选项（无取值）。config 的子操作在 {config} 里单独处理。
_BOOL_FLAGS: dict[str, list[str]] = {
    "rename": ["--dry-run", "--no-editor", "--multi-tab", "--reverse"],
    "restore": ["--all", "--partial"],
    "history": ["--all"],
}
_VALUE_FLAGS: dict[str, list[str]] = {
    "rename": [
        "--timeout",
        "--depth",
        "--sort-by",
        "--exclude",
        "--path-type",
    ],
}
_CONFIG_ACTIONS = ["set", "set-editor", "reset"]

# 全部子命令（含 completion 自身），作为各级补全顶层的候选顺序。
SUBCOMMANDS = [
    "completion",
    "config",
    "gui",
    "help",
    "history",
    "rename",
    "restore",
    "version",
]

# 面向 PSCompletions 自定义补全的中文提示（子命令 / 选项 / 取值）。
_SUB_TIPS: dict[str, str] = {
    "completion": "生成 shell 补全脚本",
    "config": "查看/设置配置",
    "gui": "启动图形界面",
    "help": "显示帮助信息",
    "history": "查看重命名日志",
    "rename": "编辑器模式批量重命名",
    "restore": "恢复重命名",
    "version": "版本信息",
}
_FLAG_TIPS: dict[str, str] = {
    "--dry-run": "预览不执行",
    "--no-editor": "跳过编辑器直接重命名",
    "--multi-tab": "多标签编辑器适配",
    "--reverse": "反转排序顺序",
    "--timeout": "编辑器等待超时（秒）",
    "--depth": "目录搜索深度（层级）",
    "--sort-by": "重命名顺序",
    "--exclude": "排除的类型",
    "--path-type": "路径类型",
    "--all": "作用于全部历史",
    "--partial": "用编辑器筛选日志行",
}
_VALUE_TIPS: dict[str, dict[str, str]] = {
    "--path-type": {
        "full": "完整路径",
        "name": "仅文件名",
        "stem": "不含扩展名",
        "ext": "仅扩展名",
    },
    "--sort-by": {
        "default": "默认",
        "name": "名称",
        "path": "路径",
        "mtime": "修改时间",
        "ctime": "创建时间",
        "size": "大小",
    },
    "--exclude": {
        "f": "文件",
        "file": "文件",
        "d": "目录",
        "dir": "目录",
        "l": "链接",
        "link": "链接",
        "r": "只读",
        "readonly": "只读",
        "h": "隐藏",
        "hidden": "隐藏",
        "s": "系统",
        "system": "系统",
    },
}

_SUPPORTED_SHELLS = ("bash", "zsh", "pwsh", "fish", "psc")


def supported_shells() -> tuple[str, ...]:
    return _SUPPORTED_SHELLS


def completion_for(shell: str) -> str:
    """返回指定 shell 的补全脚本；未知 shell 抛 ValueError。"""
    key = shell.lower()
    if key in ("powershell", "powershell7"):
        key = "pwsh"
    if key not in _SUPPORTED_SHELLS:
        raise ValueError(
            choose(
                f"未知 shell: {shell!r}（支持: {', '.join(_SUPPORTED_SHELLS)}）",
                f"Unknown shell: {shell!r} (supported: {', '.join(_SUPPORTED_SHELLS)})",
            )
        )
    script = _GENERATORS[key]()
    if get_language() != EN_US:
        return script
    replacements = (
        ("生成 shell 补全脚本", "Generate a shell completion script"),
        ("查看/设置配置", "View/change configuration"),
        ("启动图形界面", "Start the graphical interface"),
        ("显示帮助信息", "Show help"),
        ("查看重命名日志", "View rename history"),
        ("编辑器模式批量重命名", "Batch rename in editor mode"),
        ("恢复重命名", "Restore renames"),
        ("版本信息", "Version information"),
        ("完整路径", "Full path"),
        ("仅文件名", "File name only"),
        ("不含扩展名", "Without extension"),
        ("仅扩展名", "Extension only"),
        ("生成", "Generate"),
        ("补全", "completion"),
        ("安装", "Install"),
    )
    for source, translated in replacements:
        script = script.replace(source, translated)
    return script


def completion_usage() -> str:
    """stdout 安装提示（按 shell 给出对应写入命令）。"""
    return choose(
        "示例:\n"
        "  onomedit completion bash > ~/.local/share/bash-completion/completions/onomedit\n"
        "  onomedit completion zsh  > ~/.zfunc/_onomedit\n"
        '  onomedit completion pwsh > "$HOME\\Documents\\PowerShell\\onomedit.ps1"\n'
        "  onomedit completion fish > ~/.config/fish/completions/onomedit.fish\n"
        '  onomedit completion psc  > "$HOME\\Documents\\PowerShell\\onomedit.psc.ps1"',
        "Examples:\n"
        "  onomedit completion bash > ~/.local/share/bash-completion/completions/onomedit\n"
        "  onomedit completion zsh  > ~/.zfunc/_onomedit\n"
        '  onomedit completion pwsh > "$HOME\\Documents\\PowerShell\\onomedit.ps1"\n'
        "  onomedit completion fish > ~/.config/fish/completions/onomedit.fish\n"
        '  onomedit completion psc  > "$HOME\\Documents\\PowerShell\\onomedit.psc.ps1"',
    )


def _sub_list() -> str:
    return " ".join(SUBCOMMANDS)


def _shell_list() -> str:
    """空格分隔的 shells（供 zsh 取值候选；单一数据源）。"""
    return " ".join(_SUPPORTED_SHELLS)


def _ps_shell_array() -> str:
    """pwsh 风格 shell 数组字面量（单一数据源）。"""
    return ",".join(f"'{s}'" for s in _SUPPORTED_SHELLS)


def _gen_bash() -> str:
    words = _sub_list()
    # 每个子命令的选项（含值型）与取值补全，写进 case 分支。
    rename_case = _bash_case("rename", _BOOL_FLAGS["rename"], _VALUE_FLAGS["rename"])
    restore_case = _bash_case("restore", _BOOL_FLAGS["restore"], [])
    history_case = _bash_case("history", _BOOL_FLAGS["history"], [])
    config_case = """\
        config)
            case "$prev" in
                set) comps="--help" ;;
                *)    comps="set set-editor reset" ;;
            esac
            ;;
"""
    return f"""# bash completion for onomedit
# 生成: onomedit completion bash
# 安装到 ~/.bashrc:  source /path/to/onomedit.bash
_onomedit()
{{
    local cur prev
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"

    local comps
    if [ "$COMP_CWORD" -eq 1 ]; then
        comps="{words}"
    else
        case "${{COMP_WORDS[1]}}" in
{rename_case}
{restore_case}
{history_case}
        help)
            comps="completion config gui help history rename restore version"
            ;;
{config_case}
            *) comps="" ;;
        esac
    fi

    # 值型选项的取值补全
    case "$prev" in
{_bash_value_case()}
        *) ;;
    esac

    if [ -n "$comps" ]; then
        COMPREPLY=( $(compgen -W "$comps" -- "$cur") )
    fi
    return 0
}}

complete -o default -F _onomedit onomedit
"""


def _bash_case(name: str, bools: list[str], values: list[str]) -> str:
    opts = bools + [v + "=" for v in values]
    return f'        {name})\n            comps="{" ".join(opts)}"\n            ;;\n'


def _bash_value_case() -> str:
    lines = []
    for flag, vals in _VALUE_CHOICES.items():
        lines.append(
            f'        {flag}) COMPREPLY=( $(compgen -W "{" ".join(vals)}" -- "$cur") ); return 0 ;;'
        )
    return "\n".join(lines)


def _gen_zsh() -> str:
    return f"""#compdef onomedit
# zsh completion for onomedit
# 生成: onomedit completion zsh
# 安装: 放到 fpath, 如 ~/.zfunc/_onomedit, 并确保 ~/.zfunc 在 fpath 中
#       然后 compinit.

_onomedit() {{
    local -a commands
    commands=(
        'completion:生成 shell 补全脚本'
        'config:查看/设置配置'
        'gui:启动图形界面'
        'help:显示帮助信息'
        'history:查看重命名日志'
        'rename:编辑器模式批量重命名'
        'restore:恢复重命名'
        'version:版本信息'
    )

    if (( CURRENT == 2 )); then
        _describe -t commands 'onomedit 子命令' commands
        return
    fi

    case "$words[2]" in
        rename)
            _arguments -s \\
{_zsh_rename_args()}
            ;;
        restore)
            _arguments -s '--all[恢复全部历史]' '--partial[编辑器筛选日志行]'
            ;;
        history)
            _arguments -s '--all[查看全部历史]'
            ;;
        config)
            _arguments -s \
                'set:设置配置项' \
                'set-editor:设置编辑器' \
                'reset:重置默认配置'
            ;;
        completion)
            _arguments -s '1:shell:({_shell_list()})'
            ;;
        help)
            _values 'topic' completion config gui help history rename restore version
            ;;
    esac
}}

_onomedit
"""


def _zsh_rename_args() -> str:
    lines = [
        "                '--dry-run[预览不执行]'",
        "                '--no-editor[跳过编辑器]'",
        "                '--multi-tab[多标签编辑器]'",
        "                '--reverse[反转顺序]'",
        "                '--timeout=[编辑器等待超时]:秒'",
        "                '--depth=[目录搜索深度]:层级'",
        "                '--path-type=[路径类型]:类型:(full name stem ext)'",
        "                '--sort-by=[重命名顺序]:键:(default name path mtime ctime size)'",
        "                '--exclude=[排除类型]:类型:(f file d dir l link r readonly h hidden s system)'",
        "                '*:文件:_files'",
    ]
    return "\n".join(lines)


def _gen_pwsh() -> str:
    words = _sub_list()
    return f"""# PowerShell completion for onomedit
# 生成: onomedit completion pwsh
# 安装: 把下面内容写入 $PROFILE (或单独文件后在 profile 中 . 或 Import)

Register-ArgumentCompleter -Native -CommandName onomedit, onomedit.exe -ScriptBlock {{
    param($wordToComplete, $commandAst, $cursorPosition)

    # 已敲入的参数（不含最后一个补全中的词）
    $tokens = $commandAst.CommandElements | ForEach-Object {{ $_.Extent.Text }}
    # 已知子命令；只有完整命中才视为子命令。否则视为第一级补全——CommandElements
    # 会把正在补全的半截词也算作元素，直接取 $tokens[1] 会让一级子命令补全失效。
    $cmds = '{words}'.Split(' ')
    $cmd = if ($tokens.Count -gt 1 -and $cmds -contains $tokens[1]) {{ $tokens[1] }} else {{ '' }}

    # 值型选项的取值
    $valueMap = @{{
        '--path-type' = 'full','name','stem','ext'
        '--sort-by'   = 'default','name','path','mtime','ctime','size'
        '--exclude'   = 'f','file','d','dir','l','link','r','readonly','h','hidden','s','system'
    }}

    {_pwsh_main_body(words)}
}}
"""


def _pwsh_main_body(words: str) -> str:
    # 在命令字面上构造完整脚本体；每行缩进对齐到 scriptblock 内
    body = f"""    # 当前补全目标前一个参数（用于值型选项）
    $last = $tokens[$tokens.Count - 1]
    if ($valueMap.ContainsKey($last)) {{
        $valueMap[$last] | Where-Object {{ $_ -like "$wordToComplete*" }} |
            ForEach-Object {{ [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_) }}
        return
    }}

    $candidates = @()
    switch ($cmd) {{
        '' {{ $candidates = $cmds }}
        'rename' {{
            $candidates = '--dry-run','--no-editor','--multi-tab','--reverse',
                '--timeout','--depth','--sort-by','--exclude','--path-type'
        }}
        'restore' {{ $candidates = '--all','--partial' }}
        'history' {{ $candidates = '--all' }}
        'config'  {{ $candidates = 'set','set-editor','reset' }}
        'completion' {{ $candidates = {_ps_shell_array()} }}
        'help'    {{ $candidates = '{words}'.Split(' ') }}
        default   {{ $candidates = @() }}
    }}

    $candidates | Where-Object {{ $_ -like "$wordToComplete*" }} |
        ForEach-Object {{ [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_) }}
"""
    # 缩进两格，使其落在 Register-ArgumentCompleter 的 scriptblock 内
    return "\n".join("  " + ln for ln in body.splitlines())


def _gen_fish() -> str:
    lines = [
        "# fish completion for onomedit",
        "# 生成: onomedit completion fish",
        "# 安装到 ~/.config/fish/completions/onomedit.fish",
        "",
    ]
    for sub in SUBCOMMANDS:
        lines.append(f"complete -c onomedit -f -n '__fish_use_subcommand' -a '{sub}'")
    lines.append("")
    lines.extend(
        _fish_sub(
            "rename",
            ["--dry-run", "--no-editor", "--multi-tab", "--reverse"],
            {
                "--path-type": "full name stem ext",
                "--sort-by": "default name path mtime ctime size",
                "--exclude": "f file d dir l link r readonly h hidden s system",
                "--timeout": "",
                "--depth": "",
            },
        )
    )
    lines.extend(_fish_sub("restore", ["--all", "--partial"], {}))
    lines.extend(_fish_sub("history", ["--all"], {}))
    lines.extend(_fish_sub("config", [], {}))
    lines.append(
        "complete -c onomedit -f -n '__fish_seen_subcommand_from config' -a 'set set-editor reset'"
    )
    lines.append(
        "complete -c onomedit -f -n '__fish_seen_subcommand_from completion' -a 'bash zsh pwsh fish psc'"
    )
    lines.append(
        "complete -c onomedit -f -n '__fish_seen_subcommand_from help' -a 'completion config gui help history rename restore version'"
    )
    return "\n".join(lines) + "\n"


def _fish_sub(sub: str, bools: list[str], value_flags: dict[str, str]) -> list[str]:
    lines = []
    cond = f"__fish_seen_subcommand_from {sub}"
    for flag in bools:
        lines.append(f"complete -c onomedit -f -n '{cond}' -l {flag[2:]} -d '{flag}'")
    for flag, vals in value_flags.items():
        name = flag[2:]
        if vals:
            lines.append(
                f"complete -c onomedit -f -n '{cond}' -l {name} -x -a '{vals}' -d '{name}'"
            )
        else:
            lines.append(
                f"complete -c onomedit -f -n '{cond}' -l {name} -r -d '{name}'"
            )
    lines.append("")
    return lines


def _ps_item(name: str, tip: str, indent: int = 8) -> str:
    """生成 PSCompletions 候选行 `@{ name='..'; tip='..' }`（带缩进）。"""
    return f"{' ' * indent}@{{ name='{name}'; tip='{tip}' }}"


def _ps_value_block(flag: str) -> str:
    """生成 valueMap 中一个值型选项的候选块（键 + 各取值候选，同行逗号分隔）。"""
    pad = " " * 12
    lines = [f"        '{flag}' = @("]
    vals = _VALUE_TIPS[flag]
    for i, v in enumerate(vals):
        comma = "," if i < len(vals) - 1 else ""
        lines.append(f"{pad}@{{ name='{v}'; tip='{_VALUE_TIPS[flag][v]}' }}{comma}")
    lines.append("        )")
    return "\n".join(lines)


def _gen_psc() -> str:
    """PSCompletions 自定义补全器：候选带中文 tip，注册为 -CommandName 普通补全。"""
    words = _sub_list()
    subs = "\n".join(_ps_item(s, tr(_SUB_TIPS[s])) for s in SUBCOMMANDS)
    rename_opts = "\n".join(
        _ps_item(f, tr(_FLAG_TIPS[f]))
        for f in _BOOL_FLAGS["rename"] + _VALUE_FLAGS["rename"]
    )
    value = "\n".join(_ps_value_block(f) for f in _VALUE_TIPS)
    shells = "\n".join(
        _ps_item(s, "生成 " + s + " 补全", indent=12) for s in supported_shells()
    )
    return f"""# PSCompletions completion for onomedit
# 生成: onomedit completion psc
# 用法: 配合 PSCompletions 模块（候选带 tip 提示）。把本脚本存为独立文件后在
#       $PROFILE 中 . 加载，或按 PSCompletions 的做法放置为补全文件。

Register-ArgumentCompleter -CommandName onomedit, onomedit.exe -ScriptBlock {{
    param($wordToComplete, $commandAst, $cursorPosition)

    [Console]::InputEncoding = [Console]::OutputEncoding = $OutputEncoding = [System.Text.Utf8Encoding]::new()

    # 已敲入的完成参数；不含正在补全的半截词，由 prevIdx 处理。
    $tokens = $commandAst.CommandElements | ForEach-Object {{ $_.Extent.Text }}
    $cmds = '{words}'.Split(' ')
    # 仅当 $tokens[1] 完整命中已知子命令才视为子命令；否则视为第一级补全——
    # CommandElements 会把正在补全的半截词也算作元素，直接取 $tokens[1] 会让
    # 一级子命令补全失效。
    $cmd = if ($tokens.Count -gt 1 -and $cmds -contains $tokens[1]) {{ $tokens[1] }} else {{ '' }}

    # 子命令候选（带 tip）
    $commands = @(
{subs}
    )

    # 值型选项 -> 取值候选（带 tip）
    $valueMap = @{{
{value}
    }}

    # rename 子命令的选项候选（带 tip）；布尔选项与值型选项
    $renameOpts = @(
{rename_opts}
    )

    # 值型选项判断：末位已是完成选项看末位；末位是正补的取值则看前一个。
    $prevIdx = if ($tokens.Count -gt 1 -and $tokens[-1] -eq $wordToComplete -and $wordToComplete -ne '') {{
        $tokens.Count - 2
    }} else {{
        $tokens.Count - 1
    }}
    $last = if ($prevIdx -ge 0) {{ $tokens[$prevIdx] }} else {{ '' }}
    if ($valueMap.ContainsKey($last)) {{
        $valueMap[$last] | Where-Object {{ $_.name -like \"$wordToComplete*\" }} |
            ForEach-Object {{ [System.Management.Automation.CompletionResult]::new($_.name, $_.name, 'ParameterValue', $_.tip) }}
        return
    }}

    $candidates = @()
    switch ($cmd) {{
        ''           {{ $candidates = $commands }}
        'rename'     {{ $candidates = $renameOpts }}
        'restore'    {{ $candidates = @(@{{ name='--all'; tip='恢复全部历史' }}, @{{ name='--partial'; tip='用编辑器筛选日志行' }}) }}
        'history'    {{ $candidates = @(@{{ name='--all'; tip='查看全部历史' }}) }}
        'config'     {{ $candidates = @(@{{ name='set'; tip='设置配置项' }}, @{{ name='set-editor'; tip='设置编辑器' }}, @{{ name='reset'; tip='重置默认配置' }}) }}
        'completion' {{ $candidates = @(
{shells}
        ) }}
        'help'       {{ $candidates = $commands }}
        default      {{ $candidates = @() }}
    }}

    $candidates | Where-Object {{ $_.name -like \"$wordToComplete*\" }} |
        ForEach-Object {{ [System.Management.Automation.CompletionResult]::new($_.name, $_.name, 'ParameterValue', $_.tip) }}
}}
"""


_GENERATORS = {
    "bash": _gen_bash,
    "zsh": _gen_zsh,
    "pwsh": _gen_pwsh,
    "fish": _gen_fish,
    "psc": _gen_psc,
}
