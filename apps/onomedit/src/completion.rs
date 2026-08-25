pub const SHELLS: [&str; 5] = ["bash", "zsh", "pwsh", "fish", "psc"];

const BASH: &str = r#"# bash completion for onomedit
# 生成: onomedit completion bash
# 安装到 ~/.bashrc:  source /path/to/onomedit.bash
_onomedit()
{
    local cur prev
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    local comps
    if [ "$COMP_CWORD" -eq 1 ]; then
        comps="completion config gui help history rename restore version"
    else
        case "${COMP_WORDS[1]}" in
        rename)
            comps="--dry-run --no-editor --multi-tab --reverse --timeout= --depth= --sort-by= --exclude= --path-type="
            ;;

        restore)
            comps="--all --partial"
            ;;

        history)
            comps="--all"
            ;;

        help)
            comps="completion config gui help history rename restore version"
            ;;
        config)
            case "$prev" in
                set) comps="--help" ;;
                *)    comps="set set-editor reset" ;;
            esac
            ;;

            *) comps="" ;;
        esac
    fi

    # 值型选项的取值补全
    case "$prev" in
        --path-type) COMPREPLY=( $(compgen -W "full name stem ext" -- "$cur") ); return 0 ;;
        --sort-by) COMPREPLY=( $(compgen -W "default name path mtime ctime size" -- "$cur") ); return 0 ;;
        --exclude) COMPREPLY=( $(compgen -W "f file d dir l link r readonly h hidden s system" -- "$cur") ); return 0 ;;
        *) ;;
    esac

    if [ -n "$comps" ]; then
        COMPREPLY=( $(compgen -W "$comps" -- "$cur") )
    fi
    return 0
}

complete -o default -F _onomedit onomedit
"#;

const ZSH: &str = r#"#compdef onomedit
# zsh completion for onomedit
# 生成: onomedit completion zsh
# 安装: 放到 fpath, 如 ~/.zfunc/_onomedit, 并确保 ~/.zfunc 在 fpath 中
#       然后 compinit.

_onomedit() {
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
            _arguments -s \
                '--dry-run[预览不执行]'
                '--no-editor[跳过编辑器]'
                '--multi-tab[多标签编辑器]'
                '--reverse[反转顺序]'
                '--timeout=[编辑器等待超时]:秒'
                '--depth=[目录搜索深度]:层级'
                '--path-type=[路径类型]:类型:(full name stem ext)'
                '--sort-by=[重命名顺序]:键:(default name path mtime ctime size)'
                '--exclude=[排除类型]:类型:(f file d dir l link r readonly h hidden s system)'
                '*:文件:_files'
            ;;
        restore)
            _arguments -s '--all[恢复全部历史]' '--partial[编辑器筛选日志行]'
            ;;
        history)
            _arguments -s '--all[查看全部历史]'
            ;;
        config)
            _arguments -s                 'set:设置配置项'                 'set-editor:设置编辑器'                 'reset:重置默认配置'
            ;;
        completion)
            _arguments -s '1:shell:(bash zsh pwsh fish psc)'
            ;;
        help)
            _values 'topic' completion config gui help history rename restore version
            ;;
    esac
}

_onomedit
"#;

const PWSH: &str = r#"# PowerShell completion for onomedit
# 生成: onomedit completion pwsh
# 安装: 把下面内容写入 $PROFILE (或单独文件后在 profile 中 . 或 Import)

Register-ArgumentCompleter -Native -CommandName onomedit, onomedit.exe -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)

    # 已敲入的参数（不含最后一个补全中的词）
    $tokens = $commandAst.CommandElements | ForEach-Object { $_.Extent.Text }
    # 已知子命令；只有完整命中才视为子命令。否则视为第一级补全——CommandElements
    # 会把正在补全的半截词也算作元素，直接取 $tokens[1] 会让一级子命令补全失效。
    $cmds = 'completion config gui help history rename restore version'.Split(' ')
    $cmd = if ($tokens.Count -gt 1 -and $cmds -contains $tokens[1]) { $tokens[1] } else { '' }

    # 值型选项的取值
    $valueMap = @{
        '--path-type' = 'full','name','stem','ext'
        '--sort-by'   = 'default','name','path','mtime','ctime','size'
        '--exclude'   = 'f','file','d','dir','l','link','r','readonly','h','hidden','s','system'
    }

          # 当前补全目标前一个参数（用于值型选项）
      $last = $tokens[$tokens.Count - 1]
      if ($valueMap.ContainsKey($last)) {
          $valueMap[$last] | Where-Object { $_ -like "$wordToComplete*" } |
              ForEach-Object { [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_) }
          return
      }
@@TWO_SPACES@@
      $candidates = @()
      switch ($cmd) {
          '' { $candidates = $cmds }
          'rename' {
              $candidates = '--dry-run','--no-editor','--multi-tab','--reverse',
                  '--timeout','--depth','--sort-by','--exclude','--path-type'
          }
          'restore' { $candidates = '--all','--partial' }
          'history' { $candidates = '--all' }
          'config'  { $candidates = 'set','set-editor','reset' }
          'completion' { $candidates = 'bash','zsh','pwsh','fish','psc' }
          'help'    { $candidates = 'completion config gui help history rename restore version'.Split(' ') }
          default   { $candidates = @() }
      }
@@TWO_SPACES@@
      $candidates | Where-Object { $_ -like "$wordToComplete*" } |
          ForEach-Object { [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_) }
}
"#;

const FISH: &str = r#"# fish completion for onomedit
# 生成: onomedit completion fish
# 安装到 ~/.config/fish/completions/onomedit.fish

complete -c onomedit -f -n '__fish_use_subcommand' -a 'completion'
complete -c onomedit -f -n '__fish_use_subcommand' -a 'config'
complete -c onomedit -f -n '__fish_use_subcommand' -a 'gui'
complete -c onomedit -f -n '__fish_use_subcommand' -a 'help'
complete -c onomedit -f -n '__fish_use_subcommand' -a 'history'
complete -c onomedit -f -n '__fish_use_subcommand' -a 'rename'
complete -c onomedit -f -n '__fish_use_subcommand' -a 'restore'
complete -c onomedit -f -n '__fish_use_subcommand' -a 'version'

complete -c onomedit -f -n '__fish_seen_subcommand_from rename' -l dry-run -d '--dry-run'
complete -c onomedit -f -n '__fish_seen_subcommand_from rename' -l no-editor -d '--no-editor'
complete -c onomedit -f -n '__fish_seen_subcommand_from rename' -l multi-tab -d '--multi-tab'
complete -c onomedit -f -n '__fish_seen_subcommand_from rename' -l reverse -d '--reverse'
complete -c onomedit -f -n '__fish_seen_subcommand_from rename' -l path-type -x -a 'full name stem ext' -d 'path-type'
complete -c onomedit -f -n '__fish_seen_subcommand_from rename' -l sort-by -x -a 'default name path mtime ctime size' -d 'sort-by'
complete -c onomedit -f -n '__fish_seen_subcommand_from rename' -l exclude -x -a 'f file d dir l link r readonly h hidden s system' -d 'exclude'
complete -c onomedit -f -n '__fish_seen_subcommand_from rename' -l timeout -r -d 'timeout'
complete -c onomedit -f -n '__fish_seen_subcommand_from rename' -l depth -r -d 'depth'

complete -c onomedit -f -n '__fish_seen_subcommand_from restore' -l all -d '--all'
complete -c onomedit -f -n '__fish_seen_subcommand_from restore' -l partial -d '--partial'

complete -c onomedit -f -n '__fish_seen_subcommand_from history' -l all -d '--all'


complete -c onomedit -f -n '__fish_seen_subcommand_from config' -a 'set set-editor reset'
complete -c onomedit -f -n '__fish_seen_subcommand_from completion' -a 'bash zsh pwsh fish psc'
complete -c onomedit -f -n '__fish_seen_subcommand_from help' -a 'completion config gui help history rename restore version'
"#;

const PSC: &str = r#"# PSCompletions completion for onomedit
# 生成: onomedit completion psc
# 用法: 配合 PSCompletions 模块（候选带 tip 提示）。把本脚本存为独立文件后在
#       $PROFILE 中 . 加载，或按 PSCompletions 的做法放置为补全文件。

Register-ArgumentCompleter -CommandName onomedit, onomedit.exe -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)

    [Console]::InputEncoding = [Console]::OutputEncoding = $OutputEncoding = [System.Text.Utf8Encoding]::new()

    # 已敲入的完成参数；不含正在补全的半截词，由 prevIdx 处理。
    $tokens = $commandAst.CommandElements | ForEach-Object { $_.Extent.Text }
    $cmds = 'completion config gui help history rename restore version'.Split(' ')
    # 仅当 $tokens[1] 完整命中已知子命令才视为子命令；否则视为第一级补全——
    # CommandElements 会把正在补全的半截词也算作元素，直接取 $tokens[1] 会让
    # 一级子命令补全失效。
    $cmd = if ($tokens.Count -gt 1 -and $cmds -contains $tokens[1]) { $tokens[1] } else { '' }

    # 子命令候选（带 tip）
    $commands = @(
        @{ name='completion'; tip='生成 shell 补全脚本' }
        @{ name='config'; tip='查看/设置配置' }
        @{ name='gui'; tip='启动图形界面' }
        @{ name='help'; tip='显示帮助信息' }
        @{ name='history'; tip='查看重命名日志' }
        @{ name='rename'; tip='编辑器模式批量重命名' }
        @{ name='restore'; tip='恢复重命名' }
        @{ name='version'; tip='版本信息' }
    )

    # 值型选项 -> 取值候选（带 tip）
    $valueMap = @{
        '--path-type' = @(
            @{ name='full'; tip='完整路径' },
            @{ name='name'; tip='仅文件名' },
            @{ name='stem'; tip='不含扩展名' },
            @{ name='ext'; tip='仅扩展名' }
        )
        '--sort-by' = @(
            @{ name='default'; tip='默认' },
            @{ name='name'; tip='名称' },
            @{ name='path'; tip='路径' },
            @{ name='mtime'; tip='修改时间' },
            @{ name='ctime'; tip='创建时间' },
            @{ name='size'; tip='大小' }
        )
        '--exclude' = @(
            @{ name='f'; tip='文件' },
            @{ name='file'; tip='文件' },
            @{ name='d'; tip='目录' },
            @{ name='dir'; tip='目录' },
            @{ name='l'; tip='链接' },
            @{ name='link'; tip='链接' },
            @{ name='r'; tip='只读' },
            @{ name='readonly'; tip='只读' },
            @{ name='h'; tip='隐藏' },
            @{ name='hidden'; tip='隐藏' },
            @{ name='s'; tip='系统' },
            @{ name='system'; tip='系统' }
        )
    }

    # rename 子命令的选项候选（带 tip）；布尔选项与值型选项
    $renameOpts = @(
        @{ name='--dry-run'; tip='预览不执行' }
        @{ name='--no-editor'; tip='跳过编辑器直接重命名' }
        @{ name='--multi-tab'; tip='多标签编辑器适配' }
        @{ name='--reverse'; tip='反转排序顺序' }
        @{ name='--timeout'; tip='编辑器等待超时（秒）' }
        @{ name='--depth'; tip='目录搜索深度（层级）' }
        @{ name='--sort-by'; tip='重命名顺序' }
        @{ name='--exclude'; tip='排除的类型' }
        @{ name='--path-type'; tip='路径类型' }
    )

    # 值型选项判断：末位已是完成选项看末位；末位是正补的取值则看前一个。
    $prevIdx = if ($tokens.Count -gt 1 -and $tokens[-1] -eq $wordToComplete -and $wordToComplete -ne '') {
        $tokens.Count - 2
    } else {
        $tokens.Count - 1
    }
    $last = if ($prevIdx -ge 0) { $tokens[$prevIdx] } else { '' }
    if ($valueMap.ContainsKey($last)) {
        $valueMap[$last] | Where-Object { $_.name -like "$wordToComplete*" } |
            ForEach-Object { [System.Management.Automation.CompletionResult]::new($_.name, $_.name, 'ParameterValue', $_.tip) }
        return
    }

    $candidates = @()
    switch ($cmd) {
        ''           { $candidates = $commands }
        'rename'     { $candidates = $renameOpts }
        'restore'    { $candidates = @(@{ name='--all'; tip='恢复全部历史' }, @{ name='--partial'; tip='用编辑器筛选日志行' }) }
        'history'    { $candidates = @(@{ name='--all'; tip='查看全部历史' }) }
        'config'     { $candidates = @(@{ name='set'; tip='设置配置项' }, @{ name='set-editor'; tip='设置编辑器' }, @{ name='reset'; tip='重置默认配置' }) }
        'completion' { $candidates = @(
            @{ name='bash'; tip='生成 bash 补全' }
            @{ name='zsh'; tip='生成 zsh 补全' }
            @{ name='pwsh'; tip='生成 pwsh 补全' }
            @{ name='fish'; tip='生成 fish 补全' }
            @{ name='psc'; tip='生成 psc 补全' }
        ) }
        'help'       { $candidates = $commands }
        default      { $candidates = @() }
    }

    $candidates | Where-Object { $_.name -like "$wordToComplete*" } |
        ForEach-Object { [System.Management.Automation.CompletionResult]::new($_.name, $_.name, 'ParameterValue', $_.tip) }
}
"#;

pub fn generate(shell: &str) -> Option<String> {
    match shell {
        "bash" => Some(BASH.to_owned()),
        "zsh" => Some(ZSH.to_owned()),
        "pwsh" => Some(PWSH.replace("@@TWO_SPACES@@", "  ")),
        "fish" => Some(FISH.to_owned()),
        "psc" => Some(PSC.to_owned()),
        _ => None,
    }
}

pub fn usage() -> &'static str {
    "示例:\n  onomedit completion bash > ~/.local/share/bash-completion/completions/onomedit\n  onomedit completion zsh  > ~/.zfunc/_onomedit\n  onomedit completion pwsh > \"$HOME\\Documents\\PowerShell\\onomedit.ps1\"\n  onomedit completion fish > ~/.config/fish/completions/onomedit.fish\n  onomedit completion psc  > \"$HOME\\Documents\\PowerShell\\onomedit.psc.ps1\""
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_shell_contains_contract_surface() {
        for shell in SHELLS {
            let script = generate(shell).unwrap();
            for command in
                "completion config gui help history rename restore version".split_whitespace()
            {
                assert!(script.contains(command), "{shell} omitted {command}");
            }
            assert!(!script.as_bytes().windows(2).any(|bytes| bytes == b"\r\n"));
        }
        let bash = generate("bash").unwrap();
        for value in ["full", "name", "stem", "ext", "mtime", "readonly", "system"] {
            assert!(bash.contains(value));
        }
        let pwsh = generate("pwsh").unwrap();
        assert!(pwsh.contains("Register-ArgumentCompleter -Native"));
        assert!(pwsh.contains("-CommandName onomedit, onomedit.exe"));
        let psc = generate("psc").unwrap();
        assert!(psc.contains("Register-ArgumentCompleter -CommandName onomedit, onomedit.exe"));
        assert!(!psc.contains("Register-ArgumentCompleter -Native"));
        assert!(psc.contains("tip='生成 shell 补全脚本'"));
        assert!(psc.contains("tip='编辑器模式批量重命名'"));
        assert!(psc.contains("tip='完整路径'"));
    }
}
