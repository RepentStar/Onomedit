pub const SHELLS: [&str; 5] = ["bash", "zsh", "pwsh", "fish", "psc"];
const COMMANDS: &str = "completion config gui help history rename restore version";
const RENAME_FLAGS: &str =
    "--dry-run --no-editor --multi-tab --reverse --timeout --depth --sort-by --exclude --path-type";

pub fn generate(shell: &str) -> Option<String> {
    Some(match shell {
        "bash" => format!(
            r#"# bash completion for onomedit
_onomedit() {{
    local cur prev cmd
    cur="${{COMP_WORDS[COMP_CWORD]}}"; prev="${{COMP_WORDS[COMP_CWORD-1]}}"; cmd="${{COMP_WORDS[1]}}"
    local words="{COMMANDS}"
    case "$cmd" in
      rename) words="{RENAME_FLAGS}" ;;
      restore) words="--all --partial" ;;
      history) words="--all" ;;
      config) words="set set-editor reset" ;;
      completion) words="bash zsh pwsh fish psc" ;;
    esac
    case "$prev" in
      --path-type) words="full name stem ext" ;;
      --sort-by) words="default name path mtime ctime size" ;;
      --exclude) words="f file d dir l link r readonly h hidden s system" ;;
    esac
    COMPREPLY=( $(compgen -W "$words" -- "$cur") )
}}
complete -o default -F _onomedit onomedit
"#
        ),
        "zsh" => format!(
            r#"#compdef onomedit
_onomedit() {{
  local -a commands
  commands=({COMMANDS})
  if (( CURRENT == 2 )); then _describe 'command' commands; return; fi
  case "$words[2]" in
    rename) _arguments '*:file:_files' '--dry-run' '--no-editor' '--multi-tab' '--reverse' '--timeout=[seconds]' '--depth=[depth]' '--path-type=[type]:(full name stem ext)' '--sort-by=[key]:(default name path mtime ctime size)' '--exclude=[type]:(f file d dir l link r readonly h hidden s system)' ;;
    restore) _arguments '--all' '--partial' ;;
    history) _arguments '--all' ;;
    completion) _values shell bash zsh pwsh fish psc ;;
  esac
}}
_onomedit
"#
        ),
        "pwsh" => format!(
            r#"# PowerShell completion for onomedit
Register-ArgumentCompleter -Native -CommandName onomedit, onomedit.exe -ScriptBlock {{
  param($wordToComplete, $commandAst, $cursorPosition)
  $tokens = $commandAst.CommandElements | ForEach-Object {{ $_.Extent.Text }}
  $commands = '{COMMANDS}'.Split(' ')
  $values = if ($tokens.Count -le 2) {{ $commands }} elseif ($tokens[1] -eq 'rename') {{ '{RENAME_FLAGS}'.Split(' ') }} elseif ($tokens[1] -eq 'restore') {{ '--all','--partial' }} elseif ($tokens[1] -eq 'history') {{ '--all' }} elseif ($tokens[1] -eq 'config') {{ 'set','set-editor','reset' }} elseif ($tokens[1] -eq 'completion') {{ 'bash','zsh','pwsh','fish','psc' }} else {{ @() }}
  $values | Where-Object {{ $_ -like "$wordToComplete*" }} | ForEach-Object {{ [System.Management.Automation.CompletionResult]::new($_,$_, 'ParameterValue', $_) }}
}}
"#
        ),
        "fish" => {
            let mut output =
                String::from("# fish completion for onomedit\ncomplete -c onomedit -f\n");
            for command in COMMANDS.split_whitespace() {
                output.push_str(&format!(
                    "complete -c onomedit -n '__fish_use_subcommand' -a '{command}'\n"
                ));
            }
            for flag in RENAME_FLAGS.split_whitespace() {
                output.push_str(&format!(
                    "complete -c onomedit -n '__fish_seen_subcommand_from rename' -l '{}'
",
                    flag.trim_start_matches("--")
                ));
            }
            output
        }
        "psc" => r#"# PSCompletions completion for onomedit
# 生成: onomedit completion psc
# 配合 PSCompletions 模块使用；候选带中文 tip。
Register-ArgumentCompleter -CommandName onomedit, onomedit.exe -ScriptBlock {
  param($wordToComplete, $commandAst, $cursorPosition)
  [Console]::InputEncoding = [Console]::OutputEncoding = $OutputEncoding = [System.Text.Utf8Encoding]::new()
  $tokens = $commandAst.CommandElements | ForEach-Object { $_.Extent.Text }
  $cmds = '{COMMANDS}'.Split(' ')
  $cmd = if ($tokens.Count -gt 1 -and $cmds -contains $tokens[1]) { $tokens[1] } else { '' }
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
  $valueMap = @{
    '--path-type' = @(
      @{ name='full'; tip='完整路径' }, @{ name='name'; tip='仅文件名' },
      @{ name='stem'; tip='不含扩展名' }, @{ name='ext'; tip='仅扩展名' }
    )
    '--sort-by' = 'default','name','path','mtime','ctime','size' | ForEach-Object { @{ name=$_; tip=$_ } }
    '--exclude' = 'f','file','d','dir','l','link','r','readonly','h','hidden','s','system' | ForEach-Object { @{ name=$_; tip=$_ } }
  }
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
  $last = if ($tokens.Count -gt 0) { $tokens[-1] } else { '' }
  if ($valueMap.ContainsKey($last)) {
    $valueMap[$last] | Where-Object { $_.name -like "$wordToComplete*" } |
      ForEach-Object { [System.Management.Automation.CompletionResult]::new($_.name, $_.name, 'ParameterValue', $_.tip) }
    return
  }
  $candidates = switch ($cmd) {
    '' { $commands }
    'rename' { $renameOpts }
    'restore' { @{ name='--all'; tip='恢复全部历史' }, @{ name='--partial'; tip='用编辑器筛选日志行' } }
    'history' { @{ name='--all'; tip='查看全部历史' } }
    'config' { @{ name='set'; tip='设置配置项' }, @{ name='set-editor'; tip='设置编辑器' }, @{ name='reset'; tip='重置默认配置' } }
    'completion' { 'bash','zsh','pwsh','fish','psc' | ForEach-Object { @{ name=$_; tip="生成 $_ 补全" } } }
    'help' { $commands }
    default { @() }
  }
  $candidates | Where-Object { $_.name -like "$wordToComplete*" } |
    ForEach-Object { [System.Management.Automation.CompletionResult]::new($_.name, $_.name, 'ParameterValue', $_.tip) }
}
"#
        .replace("{COMMANDS}", COMMANDS),
        _ => return None,
    })
}

pub fn usage() -> &'static str {
    "示例:\n  onomedit completion bash > ~/.local/share/bash-completion/completions/onomedit\n  onomedit completion zsh > ~/.zfunc/_onomedit\n  onomedit completion pwsh > onomedit.ps1\n  onomedit completion fish > ~/.config/fish/completions/onomedit.fish\n  onomedit completion psc > onomedit.psc.ps1"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_shell_contains_contract_surface() {
        for shell in SHELLS {
            let script = generate(shell).unwrap();
            for command in COMMANDS.split_whitespace() {
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
