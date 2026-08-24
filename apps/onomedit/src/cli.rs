use std::ffi::OsString;
use std::io::{self, IsTerminal, Read, Write};
use std::path::PathBuf;
use std::time::Duration;

use clap::{Args, CommandFactory, Parser, Subcommand};
use onomedit_core::collection;
use onomedit_core::config::{self, Config};
use onomedit_core::journal::{RenameLogger, SEPARATOR};
use onomedit_core::path::PathType;
use onomedit_core::pipeline::{PipelineOutcome, RenamePipeline, restore};
use onomedit_platform::{clipboard, editor};

use crate::completion;

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
    let arguments: Vec<OsString> = arguments.into_iter().collect();
    if arguments.is_empty() {
        if gui_available {
            output_line!("启动 Onomedit 图形界面…");
            output_line!(
                "提示: 输入 onomedit help 查看全部子命令与用法；也可直接使用 CLI（如 onomedit rename *.txt --dry-run）"
            );
            return launch_gui();
        }
        error_line!(
            "错误: 当前为 CLI-only 版本，不包含 GUI；请使用 onomedit.exe 或指定 CLI 子命令"
        );
        return 1;
    }
    let args = std::iter::once(OsString::from("onomedit")).chain(arguments);
    let cli = match Cli::try_parse_from(args) {
        Ok(cli) => cli,
        Err(error) => {
            let code = if error.use_stderr() { 2 } else { 0 };
            let _ = error.print();
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
                error_line!("错误: 当前为 CLI-only 版本，不包含 GUI");
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

fn command_help(topic: Option<&str>) -> i32 {
    let mut command = Cli::command();
    if let Some(topic) = topic {
        if let Some(subcommand) = command.find_subcommand_mut(topic) {
            output_line!("{}", subcommand.render_long_help());
            return 0;
        }
        error_line!("未知子命令: {topic}（可执行 onomedit help 查看全部）");
        return 1;
    }
    output_line!("{}", command.render_long_help());
    0
}

fn command_config(action: Option<ConfigAction>) -> i32 {
    match action {
        None => {
            let config = config::load();
            match serde_json::to_string_pretty(&config) {
                Ok(json) => {
                    output_line!("{json}\n\n配置文件: {}", config::config_path().display());
                    0
                }
                Err(error) => {
                    error_line!("错误: {error}");
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
                    output_line!("{description}");
                    0
                }
                Err(error) => {
                    error_line!("错误: {error}");
                    1
                }
            }
        }
        Some(ConfigAction::SetEditor { command }) => {
            let mut settings = config::load();
            settings.editor = command.join(" ");
            match config::save(&settings) {
                Ok(()) => {
                    output_line!("编辑器已设置为: {}", settings.editor);
                    0
                }
                Err(error) => {
                    error_line!("错误: {error}");
                    1
                }
            }
        }
        Some(ConfigAction::Reset) => match config::save(&Config::default()) {
            Ok(()) => {
                output_line!("配置已重置为默认值");
                0
            }
            Err(error) => {
                error_line!("错误: {error}");
                1
            }
        },
    }
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
                error_line!("错误: 无法读取管道: {error}");
                return 1;
            }
        };
        if paths.is_empty() {
            error_line!("错误: 管道未提供任何路径");
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
                return Err("未配置编辑器，请先运行: onomedit config set-editor <命令>\n（或使用 --no-editor 跳过编辑器）".to_owned());
            }
            output_line!(
                "已写入临时文件: {}\n请在编辑器中修改后保存并退出…",
                session.edit_path().display()
            );
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
            error_line!("错误: {error}");
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
                    extra.push_str(&format!("  差异: {}", row.diff));
                }
                if row.distance != 0 {
                    extra.push_str(&format!("  距离: {}", row.distance));
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
        output_line!("（dry-run 预览，共 {} 项，未执行）", outcome.pairs.len());
        return 0;
    }
    output_line!(
        "重命名完成: 成功 {} / 失败 {} / 无变化 {} / 总计 {}",
        outcome.result.success.len(),
        outcome.result.failed.len(),
        outcome.result.skipped.len(),
        outcome.result.total()
    );
    for (old, new, error) in &outcome.result.failed {
        error_line!("失败: {} -> {}: {error}", old.display(), new.display());
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
            output_line!(
                "恢复完成: 成功 {} / 失败 {} / 无变化 {} / 总计 {}",
                result.success.len(),
                result.failed.len(),
                result.skipped.len(),
                result.total()
            );
            for (old, new, error) in &result.failed {
                error_line!("失败: {} -> {}: {error}", old.display(), new.display());
            }
            i32::from(!result.failed.is_empty())
        }
        Err(error) => {
            error_line!("错误: {error}");
            1
        }
    }
}

fn edit_restore_lines(logger: &RenameLogger) -> Result<Vec<String>, String> {
    let pairs = logger.read_last();
    if pairs.is_empty() {
        return Err("没有可恢复的记录（最近一次日志为空）".into());
    }
    let settings = config::load();
    if settings.editor.trim().is_empty() {
        return Err("未配置编辑器，无法进行部分恢复（先 config set-editor）".into());
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
    output_line!(
        "请在编辑器中删去不想恢复的行，保存后退出…（{}）",
        file.path().display()
    );
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
        return Err("错误: 筛选后的行数超过原始行数，已中止".into());
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
        output_line!("（空）");
    } else {
        for (old, new) in pairs {
            output_line!("{}{SEPARATOR}{}", old.display(), new.display());
        }
    }
    0
}

fn pipe_hint() -> &'static str {
    if cfg!(windows) {
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
                error_line!("错误: 无法启动 GUI: {error}");
                1
            }
        }
    }
    #[cfg(not(feature = "gui"))]
    {
        error_line!("错误: 当前构建不包含 GUI");
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
