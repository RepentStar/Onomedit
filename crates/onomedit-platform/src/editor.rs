use std::env;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::thread;
use std::time::{Duration, Instant};

use onomedit_core::edit_file::{Signature, signature};
use thiserror::Error;

pub const QUICK_EXIT: Duration = Duration::from_secs(2);
pub const POLL_INTERVAL: Duration = Duration::from_millis(300);
pub const PROCESS_POLL_INTERVAL: Duration = Duration::from_millis(50);

#[derive(Debug, Error)]
pub enum EditorError {
    #[error("编辑器命令为空，请先配置（config set-editor / config set editor）")]
    EmptyCommand,
    #[error("编辑器命令中的引号未闭合")]
    UnclosedQuote,
    #[error("找不到可执行文件 {0:?}，请检查 PATH 或配置编辑器完整路径")]
    NotFound(String),
    #[error("无法启动编辑器 {command:?}: {source}")]
    Launch {
        command: String,
        source: std::io::Error,
    },
    #[error("无法检查临时文件: {0}")]
    Signature(#[from] std::io::Error),
}

pub fn split_command(command: &str) -> Result<Vec<String>, EditorError> {
    if command.trim().is_empty() {
        return Err(EditorError::EmptyCommand);
    }
    let mut args = Vec::new();
    let mut current = String::new();
    let mut quote = None;
    let mut escaped = false;
    for ch in command.chars() {
        if escaped && !cfg!(windows) {
            current.push(ch);
            escaped = false;
        } else if ch == '\\' && !cfg!(windows) {
            escaped = true;
        } else if matches!(ch, '\'' | '"') {
            if quote == Some(ch) {
                quote = None;
            } else if quote.is_none() {
                quote = Some(ch);
            } else {
                current.push(ch);
            }
        } else if ch.is_whitespace() && quote.is_none() {
            if !current.is_empty() {
                args.push(std::mem::take(&mut current));
            }
        } else {
            current.push(ch);
        }
    }
    if quote.is_some() {
        return Err(EditorError::UnclosedQuote);
    }
    if escaped {
        current.push('\\');
    }
    if !current.is_empty() {
        args.push(current);
    }
    Ok(args)
}

pub fn launch_and_wait(
    editor_command: &str,
    edit_path: &Path,
    original_signature: Signature,
    multi_tab: bool,
    timeout: Duration,
    mut on_status: impl FnMut(&str),
) -> Result<(), EditorError> {
    let args = split_command(editor_command)?;
    let executable =
        resolve_command(&args[0]).ok_or_else(|| EditorError::NotFound(args[0].clone()))?;
    let mut process =
        spawn(&executable, &args[1..], edit_path).map_err(|source| EditorError::Launch {
            command: editor_command.into(),
            source,
        })?;
    let started = Instant::now();
    if multi_tab {
        on_status("编辑器已启动（多标签模式），等待文件保存…");
        poll_save(edit_path, original_signature, timeout, &mut on_status)?;
        return Ok(());
    }
    loop {
        if process
            .try_wait()
            .map_err(|source| EditorError::Launch {
                command: editor_command.into(),
                source,
            })?
            .is_some()
        {
            if started.elapsed() < QUICK_EXIT && signature(edit_path)? == original_signature {
                on_status("检测到启动器型编辑器，等待文件保存（超时后放弃）…");
                poll_save(edit_path, original_signature, timeout, &mut on_status)?;
            }
            return Ok(());
        }
        if started.elapsed() > timeout {
            on_status(&format!(
                "等待编辑器超时（{:.0}s），按当前内容继续",
                timeout.as_secs_f64()
            ));
            return Ok(());
        }
        thread::sleep(PROCESS_POLL_INTERVAL);
    }
}

fn poll_save(
    path: &Path,
    original: Signature,
    timeout: Duration,
    on_status: &mut impl FnMut(&str),
) -> Result<(), EditorError> {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if signature(path)? != original {
            return Ok(());
        }
        thread::sleep(POLL_INTERVAL);
    }
    on_status("等待保存超时，继续处理");
    Ok(())
}

fn spawn(executable: &Path, arguments: &[String], edit_path: &Path) -> std::io::Result<Child> {
    if cfg!(windows)
        && executable
            .extension()
            .is_some_and(|ext| ext.eq_ignore_ascii_case("cmd") || ext.eq_ignore_ascii_case("bat"))
    {
        Command::new("cmd")
            .arg("/C")
            .arg(executable)
            .args(arguments)
            .arg(edit_path)
            .spawn()
    } else {
        Command::new(executable)
            .args(arguments)
            .arg(edit_path)
            .spawn()
    }
}

fn resolve_command(command: &str) -> Option<PathBuf> {
    let direct = PathBuf::from(command);
    if direct.is_file() {
        return Some(direct);
    }
    let path = env::var_os("PATH")?;
    #[cfg(windows)]
    let extensions: Vec<String> = env::var("PATHEXT")
        .unwrap_or_else(|_| ".COM;.EXE;.BAT;.CMD".into())
        .split(';')
        .map(str::to_owned)
        .collect();
    for directory in env::split_paths(&path) {
        let candidate = directory.join(command);
        if candidate.is_file() {
            return Some(candidate);
        }
        #[cfg(windows)]
        for extension in &extensions {
            let candidate = directory.join(format!("{command}{extension}"));
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn splits_plain_and_quoted_commands() {
        assert_eq!(split_command("code -w").unwrap(), ["code", "-w"]);
        assert_eq!(
            split_command("\"C:\\Program Files\\edit.exe\" -w").unwrap(),
            ["C:\\Program Files\\edit.exe", "-w"]
        );
        assert!(matches!(
            split_command("   "),
            Err(EditorError::EmptyCommand)
        ));
    }
}
