use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
#[cfg(windows)]
use std::sync::Mutex;
use std::time::Duration;

use serde::Deserialize;

#[cfg(windows)]
static ENVIRONMENT_LOCK: Mutex<()> = Mutex::new(());

#[derive(Debug, Deserialize)]
struct Fixture {
    split_cases: Vec<SplitCase>,
    launch_cases: Vec<LaunchCase>,
    #[cfg(windows)]
    windows_launch_cases: Vec<WindowsLaunchCase>,
}

#[derive(Debug, Deserialize)]
struct SplitCase {
    name: String,
    command: String,
    expected: Vec<String>,
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

#[cfg(windows)]
#[derive(Debug, Deserialize)]
struct WindowsLaunchCase {
    name: String,
    extension: String,
    lookup: String,
    executable: String,
    pathext: Option<String>,
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

fn load_fixture() -> Fixture {
    let fixture_path = repo_root().join("tests-rust/fixtures/editor.json");
    serde_json::from_str(
        &fs::read_to_string(&fixture_path)
            .unwrap_or_else(|error| panic!("failed to read {}: {error}", fixture_path.display())),
    )
    .unwrap_or_else(|error| panic!("failed to parse {}: {error}", fixture_path.display()))
}

#[test]
fn shared_editor_split_cases_match_expected_behavior() {
    for case in load_fixture().split_cases {
        assert_eq!(
            onomedit_platform::editor::split_command(&case.command)
                .unwrap_or_else(|error| panic!("case {} failed to split: {error}", case.name)),
            case.expected,
            "case {} split mismatch",
            case.name
        );
    }
}

#[test]
fn shared_editor_launch_cases_match_expected_behavior() {
    #[cfg(windows)]
    let _environment_guard = ENVIRONMENT_LOCK.lock().expect("lock process environment");
    let repo = repo_root();
    let python = available_python(&repo);
    let fake_editor = repo.join("tests/fakeditor.py");

    for case in load_fixture().launch_cases {
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

#[cfg(windows)]
#[test]
fn shared_windows_editor_command_cases_match_expected_behavior() {
    let _environment_guard = ENVIRONMENT_LOCK.lock().expect("lock process environment");
    for case in load_fixture().windows_launch_cases {
        let temp = tempfile::tempdir().expect("create temporary directory");
        let edit_path = temp.path().join("names with spaces.txt");
        fs::write(&edit_path, "line1\n").expect("write initial edit file");
        let before = onomedit_core::edit_file::signature(&edit_path)
            .expect("read initial edit file signature");
        let tools_dir = temp.path().join("editor tools");
        fs::create_dir(&tools_dir).expect("create editor tools directory");
        let script = tools_dir.join(format!("{}.{}", case.executable, case.extension));
        fs::write(&script, "@echo off\r\necho saved>> \"%~1\"\r\n").expect("write batch editor");

        let old_path = std::env::var_os("PATH");
        let old_pathext = std::env::var_os("PATHEXT");
        let command = match case.lookup.as_str() {
            "direct" => command_arg(&script.to_string_lossy()),
            "path" => {
                let mut paths = vec![tools_dir];
                if let Some(path) = &old_path {
                    paths.extend(std::env::split_paths(path));
                }
                let path = std::env::join_paths(paths).expect("join PATH entries");
                // This integration-test binary runs these cases serially in one test,
                // and restores the process environment before checking the result.
                unsafe {
                    std::env::set_var("PATH", path);
                    std::env::set_var(
                        "PATHEXT",
                        case.pathext.as_deref().expect("path case requires PATHEXT"),
                    );
                }
                case.executable.clone()
            }
            lookup => panic!("case {} has unknown lookup {lookup:?}", case.name),
        };

        let result = onomedit_platform::editor::launch_and_wait(
            &command,
            &edit_path,
            before,
            false,
            Duration::from_secs(5),
            |_| {},
        );
        unsafe {
            match old_path {
                Some(path) => std::env::set_var("PATH", path),
                None => std::env::remove_var("PATH"),
            }
            match old_pathext {
                Some(value) => std::env::set_var("PATHEXT", value),
                None => std::env::remove_var("PATHEXT"),
            }
        }
        result.unwrap_or_else(|error| panic!("case {} failed to launch: {error}", case.name));

        let after = onomedit_core::edit_file::signature(&edit_path)
            .expect("read final edit file signature");
        assert_ne!(after, before, "case {} did not edit the file", case.name);
    }
}
