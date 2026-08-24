use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};

use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct Fixture {
    cases: Vec<Case>,
}

#[derive(Debug, Deserialize)]
struct Case {
    name: String,
    args: Vec<String>,
    stdin: Option<String>,
    exit_code: i32,
    stdout: Option<String>,
    stdout_windows: Option<String>,
    stderr: Option<String>,
    stderr_windows: Option<String>,
    #[serde(default)]
    stdout_contains: Vec<String>,
    #[serde(default)]
    stderr_contains: Vec<String>,
}

fn fixture() -> Fixture {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests-rust/fixtures/cli.json");
    serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap()
}

fn run(args: &[impl AsRef<std::ffi::OsStr>], config_root: &Path, stdin: Option<&str>) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_onomedit-cli"));
    command
        .args(args)
        .env("APPDATA", config_root)
        .env("XDG_CONFIG_HOME", config_root)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = command.spawn().unwrap();
    if let Some(input) = stdin {
        child
            .stdin
            .as_mut()
            .unwrap()
            .write_all(input.as_bytes())
            .unwrap();
    }
    drop(child.stdin.take());
    child.wait_with_output().unwrap()
}

#[test]
fn shared_cli_golden_cases_match() {
    for case in fixture().cases {
        let directory = tempfile::tempdir().unwrap();
        let output = run(
            &case.args,
            &directory.path().join("config"),
            case.stdin.as_deref(),
        );
        assert_eq!(
            output.status.code(),
            Some(case.exit_code),
            "{} code",
            case.name
        );
        let expected_stdout = if cfg!(windows) {
            case.stdout_windows.as_ref().or(case.stdout.as_ref())
        } else {
            case.stdout.as_ref()
        };
        let expected_stderr = if cfg!(windows) {
            case.stderr_windows.as_ref().or(case.stderr.as_ref())
        } else {
            case.stderr.as_ref()
        };
        let stdout = String::from_utf8(output.stdout).unwrap();
        let stderr = String::from_utf8(output.stderr).unwrap();
        if let Some(expected) = expected_stdout {
            assert_eq!(stdout, expected.as_str(), "{} stdout", case.name);
        }
        if let Some(expected) = expected_stderr {
            assert_eq!(stderr, expected.as_str(), "{} stderr", case.name);
        }
        for value in case.stdout_contains {
            assert!(
                stdout.contains(&value),
                "{} stdout omitted {value:?}",
                case.name
            );
        }
        for value in case.stderr_contains {
            assert!(
                stderr.contains(&value),
                "{} stderr omitted {value:?}",
                case.name
            );
        }
    }
}

#[test]
fn cli_only_entrypoints_report_gui_is_unavailable() {
    let directory = tempfile::tempdir().unwrap();
    for args in [Vec::<&str>::new(), vec!["gui"]] {
        let output = run(&args, directory.path(), None);
        assert_eq!(output.status.code(), Some(1));
        assert!(
            String::from_utf8(output.stderr)
                .unwrap()
                .contains("CLI-only")
        );
    }
}

#[test]
fn rust_cli_rename_history_restore_workflow() {
    let directory = tempfile::tempdir().unwrap();
    let config_root = directory.path().join("config");
    let source = directory.path().join("a.txt");
    let renamed = directory.path().join("renamed.txt");
    fs::write(&source, "payload").unwrap();

    let rules = r#"[{"scope":"stem","kind":"replace","find":"a","replace":"renamed"}]"#;
    for (key, value) in [
        ("open_editor", "false"),
        ("expand_subdirs", "false"),
        ("exclude.hidden", "false"),
        ("auto_rules", rules),
    ] {
        let output = run(&["config", "set", key, value], &config_root, None);
        assert!(
            output.status.success(),
            "setting {key} failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }

    let source_arg = source.to_string_lossy().into_owned();
    let output = run(
        &["rename", source_arg.as_str(), "--no-editor"],
        &config_root,
        None,
    );
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(
        String::from_utf8(output.stdout)
            .unwrap()
            .replace("\r\n", "\n"),
        "重命名完成: 成功 1 / 失败 0 / 无变化 0 / 总计 1\n"
    );
    assert!(!source.exists());
    assert_eq!(fs::read_to_string(&renamed).unwrap(), "payload");

    let history = run(&["history"], &config_root, None);
    assert_eq!(
        String::from_utf8(history.stdout).unwrap().trim(),
        format!("{}<-->{}", source.display(), renamed.display())
    );

    let restored = run(&["restore"], &config_root, None);
    assert!(restored.status.success());
    assert_eq!(
        String::from_utf8(restored.stdout)
            .unwrap()
            .replace("\r\n", "\n"),
        "恢复完成: 成功 1 / 失败 0 / 无变化 0 / 总计 1\n"
    );
    assert_eq!(fs::read_to_string(&source).unwrap(), "payload");
    assert!(!renamed.exists());

    let preview = run(
        &["rename", source_arg.as_str(), "--no-editor", "--dry-run"],
        &config_root,
        None,
    );
    assert!(preview.status.success());
    assert!(
        String::from_utf8(preview.stdout)
            .unwrap()
            .contains("（dry-run 预览，共 1 项，未执行）")
    );
    assert!(source.exists());
    assert!(!renamed.exists());
}
