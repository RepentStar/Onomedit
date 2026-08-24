use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct Fixture {
    launch_cases: Vec<LaunchCase>,
}

#[derive(Debug, Deserialize)]
struct LaunchCase {
    name: String,
    mode: String,
    #[serde(default)]
    args: Vec<String>,
    initial: String,
    multi_tab: bool,
    timeout_ms: u64,
    expected_changed: bool,
    expected_content: Option<String>,
    #[serde(default)]
    expected_status_contains: Vec<String>,
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn available_python(repo: &Path) -> PathBuf {
    if let Some(configured) = std::env::var_os("ONOMEDIT_TEST_PYTHON") {
        return PathBuf::from(configured);
    }

    #[cfg(windows)]
    let local = repo.join(".venv/Scripts/python.exe");
    #[cfg(not(windows))]
    let local = repo.join(".venv/bin/python");
    if local.is_file() {
        return local;
    }

    #[cfg(windows)]
    let candidates = ["python"];
    #[cfg(not(windows))]
    let candidates = ["python3", "python"];

    for candidate in candidates {
        if Command::new(candidate).arg("--version").output().is_ok() {
            return PathBuf::from(candidate);
        }
    }

    panic!("editor compatibility tests require Python on PATH or ONOMEDIT_TEST_PYTHON");
}

fn command_arg(value: &str) -> String {
    if value.chars().any(char::is_whitespace) {
        format!("\"{}\"", value.replace('"', "\\\""))
    } else {
        value.to_owned()
    }
}

#[test]
fn shared_editor_launch_cases_match_expected_behavior() {
    let repo = repo_root();
    let fixture_path = repo.join("tests-rust/fixtures/editor.json");
    let fixture: Fixture = serde_json::from_str(
        &fs::read_to_string(&fixture_path)
            .unwrap_or_else(|error| panic!("failed to read {}: {error}", fixture_path.display())),
    )
    .unwrap_or_else(|error| panic!("failed to parse {}: {error}", fixture_path.display()));
    let python = available_python(&repo);
    let fake_editor = repo.join("tests/fakeditor.py");

    for case in fixture.launch_cases {
        let temp = tempfile::tempdir().expect("create temporary directory");
        let edit_path = temp.path().join("edit.txt");
        fs::write(&edit_path, &case.initial).expect("write initial edit file");
        let before = onomedit_core::edit_file::signature(&edit_path)
            .expect("read initial edit file signature");

        let mut parts = vec![
            command_arg(&python.to_string_lossy()),
            command_arg(&fake_editor.to_string_lossy()),
            command_arg(&case.mode),
        ];
        parts.extend(case.args.iter().map(|arg| command_arg(arg)));
        let command = parts.join(" ");
        let mut statuses = Vec::new();

        onomedit_platform::editor::launch_and_wait(
            &command,
            &edit_path,
            before,
            case.multi_tab,
            Duration::from_millis(case.timeout_ms),
            |status| statuses.push(status.to_owned()),
        )
        .unwrap_or_else(|error| panic!("case {} failed to launch: {error}", case.name));

        let after = onomedit_core::edit_file::signature(&edit_path)
            .expect("read final edit file signature");
        assert_eq!(
            after != before,
            case.expected_changed,
            "case {} change detection mismatch; statuses: {statuses:?}",
            case.name
        );
        if let Some(expected) = &case.expected_content {
            assert_eq!(
                fs::read_to_string(&edit_path).expect("read edited file"),
                *expected,
                "case {} content mismatch",
                case.name
            );
        }
        for expected in &case.expected_status_contains {
            assert!(
                statuses.iter().any(|status| status.contains(expected)),
                "case {} expected status containing {expected:?}, got {statuses:?}",
                case.name
            );
        }
    }
}
