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
Register-ArgumentCompleter -Native -CommandName onomedit,onomedit.exe,onomedit-cli,onomedit-cli.exe -ScriptBlock {{
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
        "psc" => format!(
            r#"# PSCompletions definition for onomedit
$OnomeditCompletions = @{{
  Commands = '{COMMANDS}'.Split(' ')
  RenameOptions = '{RENAME_FLAGS}'.Split(' ')
  Shells = 'bash','zsh','pwsh','fish','psc'
}}
"#
        ),
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
        }
    }
}
