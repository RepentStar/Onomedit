use std::fs::{self, FileTimes};
use std::path::{Component, Path, PathBuf};
use std::thread;
use std::time::{Duration, UNIX_EPOCH};

use onomedit_core::config;
use onomedit_core::edit_file::EditFileError;
use onomedit_core::pipeline::{PipelineError, RenamePipeline};
use serde::Deserialize;
use serde_json::Value;

#[derive(Debug, Deserialize)]
struct Fixture {
    tree: Tree,
    cases: Vec<Case>,
}

#[derive(Debug, Deserialize)]
struct Tree {
    directories: Vec<String>,
    files: Vec<TreeFile>,
    #[serde(default)]
    symlinks: Vec<TreeSymlink>,
}

#[derive(Debug, Deserialize)]
struct TreeFile {
    path: String,
    content: String,
    #[serde(default)]
    attributes: Vec<String>,
    mtime: Option<u64>,
    delay_before_ms: Option<u64>,
}

#[derive(Debug, Deserialize)]
struct TreeSymlink {
    path: String,
    target: String,
    kind: String,
}

#[derive(Debug, Deserialize)]
struct Case {
    name: String,
    inputs: Vec<String>,
    config: Value,
    edited_lines: Option<Vec<String>>,
    expected: Option<Expected>,
    expected_windows: Option<Expected>,
    expected_error: Option<String>,
    #[serde(default)]
    requires_symlinks: bool,
    #[serde(default)]
    requires_readonly_enforcement: bool,
}

#[derive(Debug, Deserialize)]
struct Expected {
    items: Vec<String>,
    edit_lines: Vec<String>,
    pairs: Vec<ExpectedPair>,
}

#[derive(Debug, Deserialize, PartialEq, Eq)]
struct ExpectedPair {
    old: String,
    new: String,
}

fn fixture() -> Fixture {
    let path =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests-rust/fixtures/filesystem.json");
    serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap()
}

#[cfg(windows)]
fn set_windows_attributes(path: &Path, attributes: &[String]) {
    use std::iter;
    use std::os::windows::ffi::OsStrExt;

    unsafe extern "system" {
        fn SetFileAttributesW(file_name: *const u16, file_attributes: u32) -> i32;
    }

    let value = attributes.iter().fold(0, |value, attribute| {
        value
            | match attribute.as_str() {
                "readonly" => 0x1,
                "hidden" => 0x2,
                "system" => 0x4,
                _ => 0,
            }
    });
    let wide: Vec<u16> = path
        .as_os_str()
        .encode_wide()
        .chain(iter::once(0))
        .collect();
    // SAFETY: wide is NUL-terminated and remains alive throughout the call.
    assert_ne!(
        unsafe { SetFileAttributesW(wide.as_ptr(), if value == 0 { 0x80 } else { value }) },
        0
    );
}

#[cfg(not(windows))]
fn set_windows_attributes(_path: &Path, _attributes: &[String]) {}

fn create_symlink(target: &Path, path: &Path, kind: &str) -> std::io::Result<()> {
    #[cfg(windows)]
    {
        use std::os::windows::fs::{symlink_dir, symlink_file};
        if kind == "dir" {
            symlink_dir(target, path)
        } else {
            symlink_file(target, path)
        }
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::symlink;
        let _ = kind;
        symlink(target, path)
    }
    #[cfg(not(any(unix, windows)))]
    {
        let _ = (target, path, kind);
        Err(std::io::Error::new(
            std::io::ErrorKind::Unsupported,
            "symlinks are unsupported on this platform",
        ))
    }
}

#[cfg(windows)]
fn readonly_is_enforced(path: &Path) -> bool {
    fs::metadata(path).is_ok_and(|metadata| metadata.permissions().readonly())
}

#[cfg(not(windows))]
fn readonly_is_enforced(path: &Path) -> bool {
    fs::OpenOptions::new().write(true).open(path).is_err()
}

fn build_tree(root: &Path, tree: &Tree) -> bool {
    fs::create_dir(root).unwrap();
    for relative in &tree.directories {
        fs::create_dir_all(root.join(relative)).unwrap();
    }
    for file in &tree.files {
        if let Some(delay) = file.delay_before_ms {
            thread::sleep(Duration::from_millis(delay));
        }
        let path = root.join(&file.path);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(&path, &file.content).unwrap();
        if let Some(mtime) = file.mtime {
            let file = fs::File::options().write(true).open(&path).unwrap();
            file.set_times(FileTimes::new().set_modified(UNIX_EPOCH + Duration::from_secs(mtime)))
                .unwrap();
        }
        if file.attributes.iter().any(|value| value == "readonly") && !cfg!(windows) {
            let mut permissions = fs::metadata(&path).unwrap().permissions();
            permissions.set_readonly(true);
            fs::set_permissions(&path, permissions).unwrap();
        }
        set_windows_attributes(&path, &file.attributes);
    }
    let mut ready = true;
    for link in &tree.symlinks {
        if create_symlink(&root.join(&link.target), &root.join(&link.path), &link.kind).is_err() {
            ready = false;
            break;
        }
    }
    ready
}

#[cfg(windows)]
struct AttributeCleanup(Vec<PathBuf>);

#[cfg(windows)]
impl Drop for AttributeCleanup {
    fn drop(&mut self) {
        for path in &self.0 {
            set_windows_attributes(path, &[]);
        }
    }
}

fn relative(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap()
        .components()
        .filter_map(|component| match component {
            Component::Normal(value) => Some(value.to_string_lossy()),
            _ => None,
        })
        .collect::<Vec<_>>()
        .join("/")
}

#[test]
fn shared_filesystem_prepare_and_plan_cases_match() {
    let fixture = fixture();
    for case in fixture.cases {
        let directory = tempfile::tempdir().unwrap();
        let root = directory.path().join("tree");
        let scratch = directory.path().join("scratch");
        let symlinks_ready = build_tree(&root, &fixture.tree);
        #[cfg(windows)]
        let _attribute_cleanup = AttributeCleanup(
            fixture
                .tree
                .files
                .iter()
                .filter(|file| !file.attributes.is_empty())
                .map(|file| root.join(&file.path))
                .collect(),
        );
        if case.requires_symlinks && !symlinks_ready {
            eprintln!("{} skipped: symlink creation is unavailable", case.name);
            continue;
        }
        if case.requires_readonly_enforcement
            && !readonly_is_enforced(&root.join("attributes/readonly.txt"))
        {
            eprintln!(
                "{} skipped: read-only permissions are not enforced",
                case.name
            );
            continue;
        }
        fs::create_dir(&scratch).unwrap();

        let mut cfg = config::from_value(case.config).unwrap();
        cfg.temp_dir = scratch.to_string_lossy().into_owned();
        let inputs: Vec<String> = case
            .inputs
            .iter()
            .map(|relative| root.join(relative).to_string_lossy().into_owned())
            .collect();
        let pipeline = RenamePipeline::new(cfg);
        let prepared = pipeline.prepare(&inputs);
        match case.expected_error.as_deref() {
            Some("no_files") => {
                assert!(
                    matches!(prepared, Err(PipelineError::NoFiles)),
                    "{}",
                    case.name
                );
                continue;
            }
            Some("no_files_after_exclude") => {
                assert!(
                    matches!(prepared, Err(PipelineError::NoFilesAfterExclude)),
                    "{}",
                    case.name
                );
                continue;
            }
            _ => {}
        }
        let session = prepared.unwrap();

        let raw_edit_file = fs::read(session.edit_path()).unwrap();
        assert!(
            !raw_edit_file.windows(2).any(|bytes| bytes == b"\r\n"),
            "{} wrote CRLF",
            case.name
        );
        let edit_lines: Vec<String> = String::from_utf8(raw_edit_file)
            .unwrap()
            .lines()
            .map(str::to_owned)
            .collect();
        let items: Vec<String> = session
            .items
            .iter()
            .map(|item| relative(&root, item.full()))
            .collect();

        if let Some(edited_lines) = case.edited_lines {
            let edited = edited_lines
                .into_iter()
                .map(|line| format!("{line}\n"))
                .collect::<String>();
            fs::write(session.edit_path(), edited).unwrap();
        }
        let planned = pipeline.finish_plan(&session);
        if case.expected_error.as_deref() == Some("line_count") {
            assert!(
                matches!(
                    planned,
                    Err(PipelineError::EditFile(EditFileError::LineCount { .. }))
                ),
                "{}",
                case.name
            );
            continue;
        }
        let pairs: Vec<ExpectedPair> = planned
            .unwrap()
            .into_iter()
            .map(|pair| ExpectedPair {
                old: relative(&root, &pair.old),
                new: relative(&root, &pair.requested_new),
            })
            .collect();

        let expected = if cfg!(windows) {
            case.expected_windows
                .as_ref()
                .or(case.expected.as_ref())
                .unwrap()
        } else {
            case.expected.as_ref().unwrap()
        };
        assert_eq!(items, expected.items, "{} items", case.name);
        assert_eq!(edit_lines, expected.edit_lines, "{} edit lines", case.name);
        assert_eq!(pairs, expected.pairs, "{} pairs", case.name);
    }
}
