use std::ffi::OsString;
use std::io::{self, IsTerminal, Read, Write};
use std::path::PathBuf;
use std::time::Duration;

use clap::{Args, Parser, Subcommand};
use onomedit_core::collection;
use onomedit_core::config::{self, Config};
use onomedit_core::journal::{RenameLogger, SEPARATOR};
use onomedit_core::path::PathType;
use onomedit_core::pipeline::{PipelineOutcome, RenamePipeline, restore};
use onomedit_platform::{clipboard, editor};

use crate::completion;
use crate::i18n::{Language, current, set_current};

fn write_platform_line(mut writer: impl Write, arguments: std::fmt::Arguments<'_>) {
    let text = arguments.to_string();
    if cfg!(windows) {
        let text = text.replace("\r\n", "\n").replace('\n', "\r\n");
        let _ = writer.write_all(text.as_bytes());
    } else {
        let _ = writer.write_all(text.as_bytes());
    }
    let _ = writer.write_all(if cfg!(windows) { b"\r\n" } else { b"\n" });
}

macro_rules! output_line {
    ($($argument:tt)*) => {
        write_platform_line(io::stdout().lock(), format_args!($($argument)*))
    };
}

macro_rules! error_line {
    ($($argument:tt)*) => {
        write_platform_line(io::stderr().lock(), format_args!($($argument)*))
    };
}

#[derive(Debug, Parser)]
#[command(
    name = "onomedit",
    version,
    disable_version_flag = true,
    about = "结合外部编辑器进行批量文件重命名的工具",
    disable_help_subcommand = true,
    disable_help_flag = true
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// 显示帮助信息（可指定子命令）
    #[command(disable_help_flag = true)]
    Help { topic: Option<String> },
    /// 查看/设置配置
    #[command(disable_help_flag = true)]
    Config {
        #[command(subcommand)]
        action: Option<ConfigAction>,
    },
    /// 编辑器模式批量重命名
    #[command(disable_help_flag = true)]
    Rename(RenameArgs),
    /// 恢复重命名
    #[command(disable_help_flag = true)]
    Restore {
        #[arg(long)]
        all: bool,
        #[arg(long)]
        partial: bool,
    },
    /// 查看重命名日志
    #[command(disable_help_flag = true)]
    History {
        #[arg(long)]
        all: bool,
    },
    /// 启动图形界面
    #[command(disable_help_flag = true)]
    Gui,
    /// 版本信息
    #[command(disable_help_flag = true)]
    Version,
    /// 生成 shell 补全脚本
    #[command(disable_help_flag = true)]
    Completion {
        #[arg(value_parser = completion::SHELLS)]
        shell: String,
    },
}

#[derive(Debug, Subcommand)]
enum ConfigAction {
    /// 按 KEY 设置配置项
    #[command(disable_help_flag = true)]
    Set { key: String, value: String },
    /// 设置编辑器命令
    #[command(disable_help_flag = true)]
    SetEditor {
        #[arg(required = true, trailing_var_arg = true, allow_hyphen_values = true)]
        command: Vec<String>,
    },
    /// 重置默认配置
    #[command(disable_help_flag = true)]
    Reset,
}

#[derive(Debug, Args)]
struct RenameArgs {
    /// 文件/目录路径（可含通配符）；缺省读剪贴板或 stdin 管道
    paths: Vec<String>,
    #[arg(long, help = "仅预览（差异/距离），不执行")]
    dry_run: bool,
    #[arg(long, help = "跳过编辑器（直接应用规则）")]
    no_editor: bool,
    #[arg(long, value_parser = ["full", "name", "stem", "ext"], help = "覆盖路径类型")]
    path_type: Option<String>,
    #[arg(long, help = "多标签编辑器：直接轮询等保存")]
    multi_tab: bool,
    #[arg(long, help = "编辑器等待超时（秒）")]
    timeout: Option<f64>,
    #[arg(long, value_parser = collection::SORT_BY_CHOICES, help = "临时重命名顺序")]
    sort_by: Option<String>,
    #[arg(long, help = "临时反转重命名顺序")]
    reverse: bool,
    #[arg(long, help = "临时目录搜索深度；指定时开启子文件夹展开")]
    depth: Option<i32>,
    #[arg(
        long,
        num_args = 1..,
        action = clap::ArgAction::Append,
        value_parser = ["f", "file", "d", "dir", "l", "link", "r", "readonly", "h", "hidden", "s", "system"],
        help = "临时追加排除路径类型（可多次/多值）"
    )]
    exclude: Vec<String>,
}

pub fn entry(arguments: impl IntoIterator<Item = OsString>, gui_available: bool) -> i32 {
    set_current(Language::from_code(&config::load().language));
    let arguments: Vec<OsString> = arguments.into_iter().collect();
    if arguments.is_empty() {
        if gui_available {
            match current() {
                Language::ZhCn => {
                    output_line!("启动 Onomedit 图形界面…");
                    output_line!(
                        "提示: 输入 onomedit help 查看全部子命令与用法；也可直接使用 CLI（如 onomedit rename *.txt --dry-run）"
                    );
                }
                Language::EnUs => {
                    output_line!("Starting the Onomedit graphical interface…");
                    output_line!(
                        "Tip: run onomedit help for commands and usage, or use the CLI directly (for example onomedit rename *.txt --dry-run)"
                    );
                }
            }
            return launch_gui();
        }
        error_line!(
            "{}",
            match current() {
                Language::ZhCn =>
                    "错误: 当前为 CLI-only 版本，不包含 GUI；请使用 onomedit.exe 或指定 CLI 子命令",
                Language::EnUs =>
                    "Error: this CLI-only build has no GUI; use onomedit.exe or specify a CLI command",
            }
        );
        return 1;
    }
    let args = std::iter::once(OsString::from("onomedit")).chain(arguments.iter().cloned());
    let cli = match Cli::try_parse_from(args) {
        Ok(cli) => cli,
        Err(error) => {
            let code = if error.use_stderr() { 2 } else { 0 };
            if let Some(message) = compatible_parse_error(&arguments) {
                error_line!("{message}");
            } else {
                let _ = error.print();
            }
            return code;
        }
    };
    match cli.command {
        Command::Help { topic } => command_help(topic.as_deref()),
        Command::Config { action } => command_config(action),
        Command::Rename(args) => command_rename(args),
        Command::Restore { all, partial } => command_restore(all, partial),
        Command::History { all } => command_history(all),
        Command::Gui => {
            if gui_available {
                launch_gui()
            } else {
                error_line!(
                    "{}",
                    match current() {
                        Language::ZhCn => "错误: 当前为 CLI-only 版本，不包含 GUI",
                        Language::EnUs => "Error: this build does not include the GUI",
                    }
                );
                1
            }
        }
        Command::Version => {
            output_line!("onomedit {}", env!("CARGO_PKG_VERSION"));
            0
        }
        Command::Completion { shell } => {
            print!("{}", completion::generate(&shell).expect("validated shell"));
            0
        }
    }
}

const ROOT_USAGE: &str = "usage: onomedit <子命令> ...";
const COMPLETION_USAGE: &str = "usage: onomedit completion {bash,zsh,pwsh,fish,psc}";
const CONFIG_USAGE: &str = "usage: onomedit config <操作> ...";
const CONFIG_SET_USAGE: &str = "usage: onomedit config set key value";
const CONFIG_SET_EDITOR_USAGE: &str = "usage: onomedit config set-editor command [command ...]";
const RENAME_USAGE: &str = "usage: onomedit rename [--dry-run] [--no-editor]\n                       [--path-type {full,name,stem,ext}] [--multi-tab]\n                       [--timeout TIMEOUT] [--sort-by KEY] [--reverse]\n                       [--depth N] [--exclude TYPE [TYPE ...]]\n                       [paths ...]";

fn compatible_parse_error(arguments: &[OsString]) -> Option<String> {
    let args: Vec<String> = arguments
        .iter()
        .map(|value| value.to_string_lossy().into_owned())
        .collect();
    let command = args.first()?.as_str();
    let commands = [
        "help",
        "config",
        "rename",
        "restore",
        "history",
        "gui",
        "version",
        "completion",
    ];
    if !commands.contains(&command) {
        return Some(format!(
            "{ROOT_USAGE}\nonomedit: error: argument <子命令>: invalid choice: {} (choose from 'help', 'config', 'rename', 'restore', 'history', 'gui', 'version', 'completion')",
            python_quote(command)
        ));
    }
    match command {
        "completion" => match args.get(1) {
            None => Some(format!(
                "{COMPLETION_USAGE}\nonomedit completion: error: the following arguments are required: shell"
            )),
            Some(shell) if !completion::SHELLS.contains(&shell.as_str()) => Some(format!(
                "{COMPLETION_USAGE}\nonomedit completion: error: argument shell: invalid choice: {} (choose from 'bash', 'zsh', 'pwsh', 'fish', 'psc')",
                python_quote(shell)
            )),
            _ => root_unrecognized(&args, 2),
        },
        "config" => compatible_config_parse_error(&args),
        "rename" => compatible_rename_parse_error(&args),
        "history" if args.iter().skip(1).any(|argument| argument != "--all") => {
            let unexpected = args
                .iter()
                .skip(1)
                .filter(|argument| argument.as_str() != "--all")
                .cloned()
                .collect::<Vec<_>>()
                .join(" ");
            Some(format!(
                "{ROOT_USAGE}\nonomedit: error: unrecognized arguments: {unexpected}"
            ))
        }
        "help" => root_unrecognized(&args, 2),
        "restore" => {
            let unexpected = args
                .iter()
                .skip(1)
                .filter(|argument| !matches!(argument.as_str(), "--all" | "--partial"))
                .cloned()
                .collect::<Vec<_>>();
            (!unexpected.is_empty()).then(|| {
                format!(
                    "{ROOT_USAGE}\nonomedit: error: unrecognized arguments: {}",
                    unexpected.join(" ")
                )
            })
        }
        "gui" | "version" => root_unrecognized(&args, 1),
        _ => None,
    }
}

fn compatible_config_parse_error(args: &[String]) -> Option<String> {
    match args.get(1).map(String::as_str) {
        Some("set") => match args.len() {
            2 => Some(format!(
                "{CONFIG_SET_USAGE}\nonomedit config set: error: the following arguments are required: key, value"
            )),
            3 => Some(format!(
                "{CONFIG_SET_USAGE}\nonomedit config set: error: the following arguments are required: value"
            )),
            5.. => root_unrecognized(args, 4),
            _ => None,
        },
        Some("set-editor") if args.len() == 2 => Some(format!(
            "{CONFIG_SET_EDITOR_USAGE}\nonomedit config set-editor: error: the following arguments are required: command"
        )),
        Some("reset") => root_unrecognized(args, 2),
        Some(action) => Some(format!(
            "{CONFIG_USAGE}\nonomedit config: error: argument <操作>: invalid choice: {} (choose from 'set', 'set-editor', 'reset')",
            python_quote(action)
        )),
        None => None,
    }
}

fn root_unrecognized(args: &[String], allowed: usize) -> Option<String> {
    (args.len() > allowed).then(|| {
        format!(
            "{ROOT_USAGE}\nonomedit: error: unrecognized arguments: {}",
            args[allowed..].join(" ")
        )
    })
}

fn compatible_rename_parse_error(args: &[String]) -> Option<String> {
    const PATH_TYPES: [&str; 4] = ["full", "name", "stem", "ext"];
    const SORT_KEYS: [&str; 6] = ["default", "name", "path", "mtime", "ctime", "size"];
    const EXCLUDE_TYPES: [&str; 12] = [
        "f", "file", "d", "dir", "l", "link", "r", "readonly", "h", "hidden", "s", "system",
    ];
    let mut index = 1;
    while index < args.len() {
        let option = args[index].as_str();
        let value = args.get(index + 1).map(String::as_str);
        let invalid_choice = |name: &str, choices: &[&str], display: &str| {
            value
                .filter(|value| !value.starts_with("--") && !choices.contains(value))
                .map(|value| {
                    format!(
                        "{RENAME_USAGE}\nonomedit rename: error: argument {name}: invalid choice: {} (choose from {display})",
                        python_quote(value)
                    )
                })
        };
        match option {
            "--path-type" => {
                if value.is_none_or(|value| value.starts_with("--")) {
                    return Some(format!(
                        "{RENAME_USAGE}\nonomedit rename: error: argument --path-type: expected one argument"
                    ));
                }
                if let Some(message) =
                    invalid_choice("--path-type", &PATH_TYPES, "'full', 'name', 'stem', 'ext'")
                {
                    return Some(message);
                }
                index += 2;
            }
            "--sort-by" => {
                if value.is_none_or(|value| value.starts_with("--")) {
                    return Some(format!(
                        "{RENAME_USAGE}\nonomedit rename: error: argument --sort-by: expected one argument"
                    ));
                }
                if let Some(message) = invalid_choice(
                    "--sort-by",
                    &SORT_KEYS,
                    "'default', 'name', 'path', 'mtime', 'ctime', 'size'",
                ) {
                    return Some(message);
                }
                index += 2;
            }
            "--exclude" => {
                let mut value_index = index + 1;
                if value_index == args.len() || args[value_index].starts_with('-') {
                    return Some(format!(
                        "{RENAME_USAGE}\nonomedit rename: error: argument --exclude: expected at least one argument"
                    ));
                }
                while value_index < args.len() && !args[value_index].starts_with('-') {
                    let value = &args[value_index];
                    if !EXCLUDE_TYPES.contains(&value.as_str()) {
                        return Some(format!(
                            "{RENAME_USAGE}\nonomedit rename: error: argument --exclude: invalid choice: {} (choose from 'f', 'file', 'd', 'dir', 'l', 'link', 'r', 'readonly', 'h', 'hidden', 's', 'system')",
                            python_quote(value)
                        ));
                    }
                    value_index += 1;
                }
                index = value_index;
            }
            "--depth" => {
                if value.is_none_or(|value| value.starts_with("--")) {
                    return Some(format!(
                        "{RENAME_USAGE}\nonomedit rename: error: argument --depth: expected one argument"
                    ));
                }
                if let Some(value) = value {
                    if !value.starts_with("--") && value.parse::<i32>().is_err() {
                        return Some(format!(
                            "{RENAME_USAGE}\nonomedit rename: error: argument --depth: invalid int value: {}",
                            python_quote(value)
                        ));
                    }
                }
                index += 2;
            }
            "--timeout" => {
                if value.is_none_or(|value| value.starts_with("--")) {
                    return Some(format!(
                        "{RENAME_USAGE}\nonomedit rename: error: argument --timeout: expected one argument"
                    ));
                }
                if let Some(value) = value {
                    if !value.starts_with("--") && value.parse::<f64>().is_err() {
                        return Some(format!(
                            "{RENAME_USAGE}\nonomedit rename: error: argument --timeout: invalid float value: {}",
                            python_quote(value)
                        ));
                    }
                }
                index += 2;
            }
            _ => index += 1,
        }
    }
    None
}

fn python_quote(value: &str) -> String {
    format!("'{}'", value.replace('\\', "\\\\").replace('\'', "\\'"))
}

fn command_help(topic: Option<&str>) -> i32 {
    if let Some(help) = help_text(topic) {
        output_line!("{help}");
        return 0;
    }
    if let Some(topic) = topic {
        match current() {
            Language::ZhCn => error_line!("未知子命令: {topic}（可执行 onomedit help 查看全部）"),
            Language::EnUs => {
                error_line!("Unknown command: {topic} (run onomedit help to list commands)")
            }
        }
        return 1;
    }
    unreachable!("root help is always defined")
}

fn help_text(topic: Option<&str>) -> Option<&'static str> {
    if current() == Language::EnUs {
        return help_text_en(topic);
    }
    Some(match topic {
        None => {
            r#"usage: onomedit <子命令> ...

结合外部编辑器进行批量文件重命名的工具

positional arguments:
  <子命令>
    help      显示帮助信息（可指定子命令）
    config    查看/设置配置
    rename    编辑器模式批量重命名
    restore   恢复重命名
    history   查看重命名日志（最近一次）
    gui       启动图形界面
    version   版本信息
    completion
              生成 shell 补全脚本（pipe 到文件后配置）

示例:
  onomedit help                     查看本帮助
  onomedit help rename              查看 rename 子命令帮助
  onomedit config set-editor notepad  配置编辑器后即可开始
  onomedit rename *.jpg --dry-run   预览（差异/距离），不执行
  onomedit restore                  恢复上一次重命名"#
        }
        Some("completion") => {
            r#"usage: onomedit completion {bash,zsh,pwsh,fish,psc}

输出指定 shell 的补全脚本到 stdout；把 stdout 重定向到文件后配置到 shell。
支持: bash, zsh, pwsh, fish, psc。

positional arguments:
  {bash,zsh,pwsh,fish,psc}
                        目标 shell（bash / zsh / pwsh / fish）

示例:
  onomedit completion bash > ~/.local/share/bash-completion/completions/onomedit
  onomedit completion zsh  > ~/.zfunc/_onomedit
  onomedit completion pwsh > "$HOME\Documents\PowerShell\onomedit.ps1"
  onomedit completion fish > ~/.config/fish/completions/onomedit.fish
  onomedit completion psc  > "$HOME\Documents\PowerShell\onomedit.psc.ps1""#
        }
        Some("config") => {
            r#"usage: onomedit config <操作> ...

查看配置、按 KEY 设置任意项、设置编辑器、重置默认。

positional arguments:
  <操作>
    set       按 KEY 设置配置项（config set KEY VALUE）
    set-editor
              设置编辑器命令
    reset     重置默认配置

示例:
  onomedit config
  onomedit config set path_type name
  onomedit config set exclude.hidden false
  onomedit config set-editor notepad
  onomedit config reset"#
        }
        Some("gui") => {
            r#"usage: onomedit gui

启动图形界面（依赖 ttkbootstrap；未安装时给出提示）。

示例:
  onomedit gui"#
        }
        Some("help") => {
            r#"usage: onomedit help [topic]

positional arguments:
  topic  子命令名（如 rename / restore）"#
        }
        Some("history") => {
            r#"usage: onomedit history [--all]

显示重命名记录（旧路径<-->新路径）；--all 显示全部历史。

options:
  --all  查看全部历史

示例:
  onomedit history
  onomedit history --all"#
        }
        Some("rename") => {
            r#"usage: onomedit rename [--dry-run] [--no-editor]
                       [--path-type {full,name,stem,ext}] [--multi-tab]
                       [--timeout TIMEOUT] [--sort-by KEY] [--reverse]
                       [--depth N] [--exclude TYPE [TYPE ...]]
                       [paths ...]

把文件名列表写入临时文件并拉起编辑器；用户修改保存后读回并批量重命名。
路径可含通配符；不提供路径时从剪贴板读取；若 stdin 来自管道则读其行作路径。

positional arguments:
  paths                 文件/目录路径（可含通配符）；缺省读剪贴板或 stdin 管道

options:
  --dry-run             仅预览（差异/距离），不执行
  --no-editor           跳过编辑器（直接应用规则）
  --path-type {full,name,stem,ext}
                        覆盖路径类型
  --multi-tab           多标签编辑器：直接轮询等保存
  --timeout TIMEOUT     编辑器等待超时（秒）
  --sort-by KEY         临时重命名顺序：default 原顺序、name 名称、path 路径、mtime 修改时间、ctime
                        创建时间、size 大小
  --reverse             临时反转重命名顺序：与 --sort-by 组合时按排序键降序，否则反转原顺序
  --depth N             临时目录搜索深度：1 = 直接子项，0 = 不展开；指定时临时开启子文件夹展开
  --exclude TYPE [TYPE ...]
                        临时排除路径类型（可多次/多值）：f/file 文件、d/dir 目录、l/link
                        符号链接、r/readonly 只读、h/hidden 隐藏、s/system 系统；在现有配置
                        exclude.* 基础上追加

示例:
  onomedit rename a.txt b.txt
  onomedit rename *.jpg --dry-run
  onomedit rename --no-editor --path-type name  仅应用规则不拉起编辑器
  onomedit rename *.txt --exclude h d --dry-run  临时排除隐藏文件与目录
  dir /b *.jpg | onomedit rename  从管道读入路径（编辑模式下重命名）"#
        }
        Some("restore") => {
            r#"usage: onomedit restore [--all] [--partial]

按日志反向恢复：默认恢复最近一次；--all 恢复全部历史；--partial 在编辑器中筛选日志行。

options:
  --all      恢复全部历史
  --partial  恢复部分（编辑器筛选日志行）

示例:
  onomedit restore
  onomedit restore --all
  onomedit restore --partial"#
        }
        Some("version") => {
            r#"usage: onomedit version

显示版本号。

示例:
  onomedit version"#
        }
        Some(_) => return None,
    })
}

fn localized_error(error: &impl std::fmt::Display) {
    match current() {
        Language::ZhCn => error_line!("错误: {error}"),
        Language::EnUs => error_line!("Error: {error}"),
    }
}

fn help_text_en(topic: Option<&str>) -> Option<&'static str> {
    Some(match topic {
        None => {
            r#"usage: onomedit <command> ...

Batch rename files with your external editor

commands:
  help        Show help (optionally for a command)
  config      View or change configuration
  rename      Batch rename in editor mode
  restore     Restore renames
  history     View rename history
  gui         Start the graphical interface
  version     Show version information
  completion  Generate a shell completion script

Examples:
  onomedit help
  onomedit help rename
  onomedit config set language en-US
  onomedit rename *.jpg --dry-run
  onomedit restore"#
        }
        Some("completion") => {
            r#"usage: onomedit completion {bash,zsh,pwsh,fish,psc}

Write a completion script to stdout and redirect it to your shell's completion directory.

Examples:
  onomedit completion bash > ~/.local/share/bash-completion/completions/onomedit
  onomedit completion zsh > ~/.zfunc/_onomedit
  onomedit completion pwsh > "$HOME\Documents\PowerShell\onomedit.ps1""#
        }
        Some("config") => {
            r#"usage: onomedit config <action> ...

View configuration, set any key, configure the editor, or reset defaults.

actions:
  set         Set a value (config set KEY VALUE)
  set-editor  Set the editor command
  reset       Reset configuration defaults

Examples:
  onomedit config
  onomedit config set language en-US
  onomedit config set-editor notepad"#
        }
        Some("gui") => "usage: onomedit gui\n\nStart the graphical interface.",
        Some("help") => {
            "usage: onomedit help [topic]\n\ntopic  Command name (for example rename or restore)"
        }
        Some("history") => {
            "usage: onomedit history [--all]\n\nShow rename records; --all shows all history."
        }
        Some("rename") => {
            r#"usage: onomedit rename [--dry-run] [--no-editor]
                       [--path-type {full,name,stem,ext}] [--multi-tab]
                       [--timeout TIMEOUT] [--sort-by KEY] [--reverse]
                       [--depth N] [--exclude TYPE [TYPE ...]]
                       [paths ...]

Write names to an edit file, open it in your editor, then apply the saved names.
Paths may include globs; input defaults to the clipboard or piped stdin.

options:
  --dry-run      Preview without applying
  --no-editor    Apply rules without opening the editor
  --path-type    Override the path type
  --multi-tab    Poll a multi-tab editor for saves
  --timeout      Editor wait timeout in seconds
  --sort-by      Temporary rename order
  --reverse      Reverse the rename order
  --depth        Temporary folder expansion depth
  --exclude      Temporarily exclude path types"#
        }
        Some("restore") => {
            "usage: onomedit restore [--all] [--partial]\n\nRestore the latest rename, all history, or entries selected in an editor."
        }
        Some("version") => "usage: onomedit version\n\nShow the version.",
        Some(_) => return None,
    })
}

fn command_config(action: Option<ConfigAction>) -> i32 {
    match action {
        None => {
            let config = config::load();
            match serde_json::to_string_pretty(&config) {
                Ok(json) => {
                    match current() {
                        Language::ZhCn => {
                            output_line!("{json}\n\n配置文件: {}", config::config_path().display())
                        }
                        Language::EnUs => output_line!(
                            "{json}\n\nConfiguration file: {}",
                            config::config_path().display()
                        ),
                    }
                    0
                }
                Err(error) => {
                    localized_error(&error);
                    1
                }
            }
        }
        Some(ConfigAction::Set { key, value }) => {
            let mut settings = config::load();
            match config::set_value(&mut settings, &key, &value).and_then(|description| {
                config::save(&settings)?;
                Ok(description)
            }) {
                Ok(description) => {
                    if key == "language" {
                        set_current(Language::from_code(&settings.language));
                    }
                    output_line!("{description}");
                    0
                }
                Err(error) => {
                    let error = compatible_config_set_error(&key, &value, &error);
                    match current() {
                        Language::ZhCn => error_line!("错误: {error}"),
                        Language::EnUs => error_line!("Error: {error}"),
                    }
                    1
                }
            }
        }
        Some(ConfigAction::SetEditor { command }) => {
            let mut settings = config::load();
            settings.editor = command.join(" ");
            match config::save(&settings) {
                Ok(()) => {
                    match current() {
                        Language::ZhCn => output_line!("编辑器已设置为: {}", settings.editor),
                        Language::EnUs => output_line!("Editor set to: {}", settings.editor),
                    }
                    0
                }
                Err(error) => {
                    localized_error(&error);
                    1
                }
            }
        }
        Some(ConfigAction::Reset) => match config::save(&Config::default()) {
            Ok(()) => {
                match current() {
                    Language::ZhCn => output_line!("配置已重置为默认值"),
                    Language::EnUs => output_line!("Configuration reset to defaults"),
                }
                0
            }
            Err(error) => {
                localized_error(&error);
                1
            }
        },
    }
}

fn compatible_config_set_error(key: &str, raw: &str, error: &config::ConfigError) -> String {
    let value = raw.trim();
    if key == "subdirs_depth" && value.parse::<i64>().is_err() {
        return format!(
            "invalid literal for int() with base 10: {}",
            python_quote(value)
        );
    }
    if key == "editor_timeout" && value.parse::<f64>().is_err() {
        return format!("could not convert string to float: {}", python_quote(value));
    }
    if matches!(key, "auto_rules" | "shell_props") {
        if let config::ConfigError::Json(json_error) = error {
            let message = json_error.to_string();
            if message.starts_with("key must be a string") {
                let line = json_error.line();
                let column = json_error.column();
                let character = json_character_offset(raw, line, column);
                return format!(
                    "Expecting property name enclosed in double quotes: line {line} column {column} (char {character})"
                );
            }
            if message.starts_with("EOF while parsing") {
                let (line, column, character) = json_end_position(raw);
                return format!("Expecting value: line {line} column {column} (char {character})");
            }
            if message.starts_with("trailing comma") || message.starts_with("expected value") {
                let line = json_error.line();
                let column = json_error.column();
                let character = json_character_offset(raw, line, column);
                return format!("Expecting value: line {line} column {column} (char {character})");
            }
        }
    }
    error.to_string()
}

fn json_character_offset(raw: &str, line: usize, column: usize) -> usize {
    raw.split_inclusive('\n')
        .take(line.saturating_sub(1))
        .map(|segment| segment.chars().count())
        .sum::<usize>()
        + column.saturating_sub(1)
}

fn json_end_position(raw: &str) -> (usize, usize, usize) {
    let line = raw.chars().filter(|ch| *ch == '\n').count() + 1;
    let column = raw
        .rsplit('\n')
        .next()
        .map_or(1, |last| last.chars().count() + 1);
    (line, column, raw.chars().count())
}

fn command_rename(args: RenameArgs) -> i32 {
    let mut settings = config::load();
    if let Some(path_type) = args.path_type {
        settings.path_type = path_type.parse::<PathType>().expect("validated path type");
    }
    if args.multi_tab {
        settings.multi_tab = true;
    }
    if let Some(timeout) = args.timeout {
        settings.editor_timeout = timeout;
    }
    if args.no_editor {
        settings.open_editor = false;
    }
    if let Some(sort_by) = args.sort_by {
        settings.sort_by = sort_by;
    }
    if args.reverse {
        settings.sort_reverse = true;
    }
    if let Some(depth) = args.depth {
        settings.subdirs_depth = depth;
        settings.expand_subdirs = true;
    }
    if !args.exclude.is_empty() {
        settings.exclude = config::merge_exclude_tags(&settings.exclude, &args.exclude);
    }

    let mut paths = args.paths;
    let from_pipe = paths.is_empty() && !io::stdin().is_terminal();
    if from_pipe {
        paths = match collection::read_stream_paths(io::stdin().lock()) {
            Ok(paths) => paths,
            Err(error) => {
                match current() {
                    Language::ZhCn => error_line!("错误: 无法读取管道: {error}"),
                    Language::EnUs => error_line!("Error: could not read stdin: {error}"),
                }
                return 1;
            }
        };
        if paths.is_empty() {
            error_line!(
                "{}",
                match current() {
                    Language::ZhCn => "错误: 管道未提供任何路径",
                    Language::EnUs => "Error: stdin did not provide any paths",
                }
            );
            return 1;
        }
    } else if paths.is_empty() {
        paths = clipboard::get_paths();
    }
    let clipboard_text = clipboard::get_text();
    let pipeline = RenamePipeline::new(settings.clone()).with_clipboard_text(clipboard_text);
    let outcome = (|| {
        let session = pipeline
            .prepare(&paths)
            .map_err(|error| error.to_string())?;
        if settings.open_editor {
            if settings.editor.trim().is_empty() {
                return Err(match current() {
                    Language::ZhCn => "未配置编辑器，请先运行: onomedit config set-editor <命令>\n（或使用 --no-editor 跳过编辑器）".to_owned(),
                    Language::EnUs => "No editor is configured. Run: onomedit config set-editor <command>\n(or use --no-editor to skip the editor)".to_owned(),
                });
            }
            match current() {
                Language::ZhCn => output_line!(
                    "已写入临时文件: {}\n请在编辑器中修改后保存并退出…",
                    session.edit_path().display()
                ),
                Language::EnUs => output_line!(
                    "Edit file created: {}\nEdit it, save, and close the editor…",
                    session.edit_path().display()
                ),
            }
            let signature = session.signature().map_err(|error| error.to_string())?;
            editor::launch_and_wait(
                &settings.editor,
                session.edit_path(),
                signature,
                settings.multi_tab,
                Duration::from_secs_f64(settings.editor_timeout.max(0.0)),
                |message| output_line!("{message}"),
            )
            .map_err(|error| error.to_string())?;
        }
        let pairs = pipeline
            .finish_plan(&session)
            .map_err(|error| error.to_string())?;
        if args.dry_run {
            let preview = (settings.preview.diff || settings.preview.distance)
                .then(|| onomedit_core::pipeline::preview_rows(&pairs, &settings));
            Ok(PipelineOutcome {
                pairs,
                preview,
                dry_run: true,
                ..PipelineOutcome::default()
            })
        } else {
            let logger = RenameLogger::new(config::log_dir());
            logger.begin_session();
            let result = onomedit_core::pipeline::Renamer::new(Some(logger))
                .run(&pairs)
                .map_err(|error| error.to_string())?;
            Ok(PipelineOutcome {
                pairs,
                result,
                ..PipelineOutcome::default()
            })
        }
    })();
    let outcome = match outcome {
        Ok(outcome) => outcome,
        Err(error) => {
            localized_error(&error);
            if from_pipe {
                error_line!("{}", pipe_hint());
            }
            return 1;
        }
    };
    print_outcome(outcome)
}

fn print_outcome(outcome: PipelineOutcome) -> i32 {
    if outcome.dry_run {
        if let Some(preview) = outcome.preview {
            for row in preview {
                let mut extra = String::new();
                if !row.diff.is_empty() {
                    extra.push_str(&match current() {
                        Language::ZhCn => format!("  差异: {}", row.diff),
                        Language::EnUs => format!("  Difference: {}", row.diff),
                    });
                }
                if row.distance != 0 {
                    extra.push_str(&match current() {
                        Language::ZhCn => format!("  距离: {}", row.distance),
                        Language::EnUs => format!("  Distance: {}", row.distance),
                    });
                }
                output_line!("{}  →  {}{extra}", row.old.display(), row.new.display());
            }
        } else {
            for pair in &outcome.pairs {
                output_line!(
                    "{}  →  {}",
                    pair.old.display(),
                    pair.requested_new.display()
                );
            }
        }
        match current() {
            Language::ZhCn => {
                output_line!("（dry-run 预览，共 {} 项，未执行）", outcome.pairs.len())
            }
            Language::EnUs => output_line!(
                "(dry-run preview: {} items; not applied)",
                outcome.pairs.len()
            ),
        }
        return 0;
    }
    match current() {
        Language::ZhCn => output_line!(
            "重命名完成: 成功 {} / 失败 {} / 无变化 {} / 总计 {}",
            outcome.result.success.len(),
            outcome.result.failed.len(),
            outcome.result.skipped.len(),
            outcome.result.total()
        ),
        Language::EnUs => output_line!(
            "Rename complete: {} succeeded / {} failed / {} unchanged / {} total",
            outcome.result.success.len(),
            outcome.result.failed.len(),
            outcome.result.skipped.len(),
            outcome.result.total()
        ),
    }
    for (old, new, error) in &outcome.result.failed {
        match current() {
            Language::ZhCn => error_line!("失败: {} -> {}: {error}", old.display(), new.display()),
            Language::EnUs => {
                error_line!("Failed: {} -> {}: {error}", old.display(), new.display())
            }
        }
    }
    i32::from(!outcome.result.failed.is_empty())
}

fn command_restore(all: bool, partial: bool) -> i32 {
    let logger = RenameLogger::new(config::log_dir());
    let selected_lines = if partial {
        match edit_restore_lines(&logger) {
            Ok(lines) => Some(lines),
            Err(error) => {
                error_line!("{error}");
                return 1;
            }
        }
    } else {
        None
    };
    match restore(&logger, all, selected_lines.as_deref()) {
        Ok(result) => {
            match current() {
                Language::ZhCn => output_line!(
                    "恢复完成: 成功 {} / 失败 {} / 无变化 {} / 总计 {}",
                    result.success.len(),
                    result.failed.len(),
                    result.skipped.len(),
                    result.total()
                ),
                Language::EnUs => output_line!(
                    "Restore complete: {} succeeded / {} failed / {} unchanged / {} total",
                    result.success.len(),
                    result.failed.len(),
                    result.skipped.len(),
                    result.total()
                ),
            }
            for (old, new, error) in &result.failed {
                match current() {
                    Language::ZhCn => {
                        error_line!("失败: {} -> {}: {error}", old.display(), new.display())
                    }
                    Language::EnUs => {
                        error_line!("Failed: {} -> {}: {error}", old.display(), new.display())
                    }
                }
            }
            i32::from(!result.failed.is_empty())
        }
        Err(error) => {
            localized_error(&error);
            1
        }
    }
}

fn edit_restore_lines(logger: &RenameLogger) -> Result<Vec<String>, String> {
    let pairs = logger.read_last();
    if pairs.is_empty() {
        return Err(match current() {
            Language::ZhCn => "没有可恢复的记录（最近一次日志为空）",
            Language::EnUs => "Nothing to restore (the latest log is empty)",
        }
        .into());
    }
    let settings = config::load();
    if settings.editor.trim().is_empty() {
        return Err(match current() {
            Language::ZhCn => "未配置编辑器，无法进行部分恢复（先 config set-editor）",
            Language::EnUs => {
                "An editor is required for partial restore (run config set-editor first)"
            }
        }
        .into());
    }
    let mut file = tempfile::Builder::new()
        .prefix("onomedit_restore_")
        .suffix(".txt")
        .tempfile_in(if settings.temp_dir.is_empty() {
            std::env::temp_dir()
        } else {
            PathBuf::from(&settings.temp_dir)
        })
        .map_err(|error| error.to_string())?;
    for (old, new) in &pairs {
        writeln!(file, "{}{SEPARATOR}{}", old.display(), new.display())
            .map_err(|error| error.to_string())?;
    }
    file.flush().map_err(|error| error.to_string())?;
    let signature =
        onomedit_core::edit_file::signature(file.path()).map_err(|error| error.to_string())?;
    match current() {
        Language::ZhCn => output_line!(
            "请在编辑器中删去不想恢复的行，保存后退出…（{}）",
            file.path().display()
        ),
        Language::EnUs => output_line!(
            "Delete entries you do not want to restore, then save and close the editor… ({})",
            file.path().display()
        ),
    }
    editor::launch_and_wait(
        &settings.editor,
        file.path(),
        signature,
        settings.multi_tab,
        Duration::from_secs_f64(settings.editor_timeout.max(0.0)),
        |message| output_line!("{message}"),
    )
    .map_err(|error| error.to_string())?;
    let mut contents = String::new();
    file.reopen()
        .and_then(|mut reader| reader.read_to_string(&mut contents))
        .map_err(|error| error.to_string())?;
    let lines: Vec<String> = contents
        .lines()
        .filter(|line| !line.is_empty())
        .map(str::to_owned)
        .collect();
    if lines.len() > pairs.len() {
        return Err(match current() {
            Language::ZhCn => "错误: 筛选后的行数超过原始行数，已中止",
            Language::EnUs => {
                "Error: the filtered list has more entries than the original; operation cancelled"
            }
        }
        .into());
    }
    Ok(lines)
}

fn command_history(all: bool) -> i32 {
    let logger = RenameLogger::new(config::log_dir());
    let pairs = if all {
        logger.read_history()
    } else {
        logger.read_last()
    };
    if pairs.is_empty() {
        output_line!(
            "{}",
            match current() {
                Language::ZhCn => "（空）",
                Language::EnUs => "(empty)",
            }
        );
    } else {
        for (old, new) in pairs {
            output_line!("{}{SEPARATOR}{}", old.display(), new.display());
        }
    }
    0
}

fn pipe_hint() -> &'static str {
    if current() == Language::EnUs && cfg!(windows) {
        "Tip: piped relative paths are resolved from the current directory.\n  · Pipe full paths: Get-ChildItem C:\\dir | ForEach-Object FullName | onomedit rename …\n  · Or change directory first: cd C:\\dir; Get-ChildItem -Name | onomedit rename …\n  · Do not pipe PowerShell file objects directly; their table formatting cannot be parsed"
    } else if current() == Language::EnUs {
        "Tip: piped relative paths are resolved from the current directory.\n  · Pipe full paths: find /some/dir -maxdepth 1 | onomedit rename …\n  · Or change directory first: cd /some/dir; ls | onomedit rename …"
    } else if cfg!(windows) {
        "提示: 管道里的路径解析失败——相对路径会按当前目录查找。\n  · 提供完整路径：Get-ChildItem C:\\dir | ForEach-Object FullName | onomedit rename …\n  · 或先 cd 到目标目录：cd C:\\dir; Get-ChildItem -Name | onomedit rename …\n  · 直接传 PowerShell 文件对象会渲染成带表头表格，无法解析"
    } else {
        "提示: 管道里的路径解析失败——相对路径会按当前目录查找。\n  · 提供完整路径：find /some/dir -maxdepth 1 | onomedit rename …\n  · 或先 cd 到目标目录：cd /some/dir; ls | onomedit rename …"
    }
}

fn launch_gui() -> i32 {
    #[cfg(feature = "gui")]
    {
        match crate::gui::run() {
            Ok(()) => 0,
            Err(error) => {
                match current() {
                    Language::ZhCn => error_line!("错误: 无法启动 GUI: {error}"),
                    Language::EnUs => error_line!("Error: could not start the GUI: {error}"),
                }
                1
            }
        }
    }
    #[cfg(not(feature = "gui"))]
    {
        error_line!(
            "{}",
            match current() {
                Language::ZhCn => "错误: 当前构建不包含 GUI",
                Language::EnUs => "Error: this build does not include the GUI",
            }
        );
        1
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cli_surface_parses_rename_options() {
        let cli = Cli::try_parse_from([
            "onomedit",
            "rename",
            "a.txt",
            "--exclude",
            "f",
            "h",
            "--sort-by",
            "mtime",
            "--depth",
            "3",
            "--reverse",
        ])
        .unwrap();
        let Command::Rename(args) = cli.command else {
            panic!()
        };
        assert_eq!(args.exclude, ["f", "h"]);
        assert_eq!(args.sort_by.as_deref(), Some("mtime"));
        assert_eq!(args.depth, Some(3));
        assert!(args.reverse);
    }

    #[test]
    fn invalid_choices_are_rejected() {
        assert!(Cli::try_parse_from(["onomedit", "rename", "a", "--path-type", "bad"]).is_err());
        assert!(Cli::try_parse_from(["onomedit", "completion", "bad"]).is_err());
        assert!(Cli::try_parse_from(["onomedit", "--help"]).is_err());
        assert!(Cli::try_parse_from(["onomedit", "rename", "--help"]).is_err());
    }
}
