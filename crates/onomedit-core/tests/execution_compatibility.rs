use std::collections::BTreeMap;
use std::fs;
use std::path::{Component, Path, PathBuf};

use onomedit_core::journal::{ROTATE_BYTES, RenameLogger, SEPARATOR};
use onomedit_core::pipeline::{RenamePair, RenameResult, Renamer, restore};
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct Fixture {
    execute_cases: Vec<ExecuteCase>,
    restore_cases: Vec<RestoreCase>,
}

#[derive(Debug, Deserialize)]
struct ExecuteCase {
    name: String,
    files: BTreeMap<String, String>,
    pairs: Vec<Pair>,
    #[serde(default)]
    duplicate_error: bool,
    error_contains: Option<Vec<String>>,
    expected: Expected,
}

#[derive(Debug, Deserialize)]
struct RestoreCase {
    name: String,
    files: BTreeMap<String, String>,
    log_pairs: Vec<Pair>,
    partial_indexes: Option<Vec<usize>>,
    #[serde(default)]
    clear_last_before_restore: bool,
    #[serde(default)]
    all_history: bool,
    expected: Expected,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
struct Pair {
    old: String,
    new: String,
}

#[derive(Debug, Deserialize)]
struct Expected {
    success: Vec<Pair>,
    failed: Vec<Pair>,
    skipped: Vec<String>,
    tree: BTreeMap<String, String>,
    last: Vec<Pair>,
    history: Vec<Pair>,
}

fn fixture() -> Fixture {
    let path =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests-rust/fixtures/execution.json");
    serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap()
}

fn build_files(root: &Path, files: &BTreeMap<String, String>) {
    fs::create_dir(root).unwrap();
    for (relative, content) in files {
        let path = root.join(relative);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, content).unwrap();
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

fn absolute_pairs(root: &Path, pairs: &[Pair]) -> Vec<RenamePair> {
    pairs
        .iter()
        .map(|pair| RenamePair::new(root.join(&pair.old), root.join(&pair.new)))
        .collect()
}

fn normalized_pairs(root: &Path, pairs: &[(PathBuf, PathBuf)]) -> Vec<Pair> {
    pairs
        .iter()
        .map(|(old, new)| Pair {
            old: relative(root, old),
            new: relative(root, new),
        })
        .collect()
}

fn tree(root: &Path) -> BTreeMap<String, String> {
    walkdir::WalkDir::new(root)
        .into_iter()
        .filter_map(Result::ok)
        .filter(|entry| entry.file_type().is_file())
        .map(|entry| {
            (
                relative(root, entry.path()),
                fs::read_to_string(entry.path()).unwrap(),
            )
        })
        .collect()
}

fn assert_result(
    name: &str,
    root: &Path,
    result: &RenameResult,
    logger: &RenameLogger,
    expected: &Expected,
) {
    assert_eq!(
        normalized_pairs(root, &result.success),
        expected.success,
        "{name} success"
    );
    let failed: Vec<Pair> = result
        .failed
        .iter()
        .map(|(old, new, _)| Pair {
            old: relative(root, old),
            new: relative(root, new),
        })
        .collect();
    assert_eq!(failed, expected.failed, "{name} failed");
    let skipped: Vec<String> = result
        .skipped
        .iter()
        .map(|path| relative(root, path))
        .collect();
    assert_eq!(skipped, expected.skipped, "{name} skipped");
    assert_eq!(tree(root), expected.tree, "{name} tree");
    assert_eq!(
        normalized_pairs(root, &logger.read_last()),
        expected.last,
        "{name} last log"
    );
    assert_eq!(
        normalized_pairs(root, &logger.read_history()),
        expected.history,
        "{name} history log"
    );
    for entry in walkdir::WalkDir::new(root.parent().unwrap())
        .into_iter()
        .filter_map(Result::ok)
    {
        assert!(
            !entry
                .file_name()
                .to_string_lossy()
                .contains("__onomedit_tmp_"),
            "{name} left an internal temporary path"
        );
    }
    for path in [&logger.last_path, &logger.history_path] {
        if let Ok(contents) = fs::read_to_string(path) {
            assert!(
                !contents.contains("__onomedit_tmp_"),
                "{name} leaked a temporary path"
            );
        }
    }
}

#[test]
fn shared_execute_cases_match() {
    for case in fixture().execute_cases {
        let directory = tempfile::tempdir().unwrap();
        let root = directory.path().join("tree");
        let logger = RenameLogger::new(directory.path().join("log"));
        build_files(&root, &case.files);
        logger.begin_session();

        let outcome = Renamer::new(Some(logger.clone())).run(&absolute_pairs(&root, &case.pairs));
        let result = if case.duplicate_error {
            assert!(outcome.is_err(), "{} expected duplicate error", case.name);
            RenameResult::default()
        } else {
            outcome.unwrap()
        };
        assert_result(&case.name, &root, &result, &logger, &case.expected);

        if let Some(fragments) = case.error_contains {
            let error = fs::read_to_string(&logger.error_path).unwrap();
            for fragment in fragments {
                assert!(
                    error.contains(&fragment),
                    "{} error missing {fragment}",
                    case.name
                );
            }
        }
    }
}

#[test]
fn shared_restore_cases_match() {
    for case in fixture().restore_cases {
        let directory = tempfile::tempdir().unwrap();
        let root = directory.path().join("tree");
        let logger = RenameLogger::new(directory.path().join("log"));
        build_files(&root, &case.files);
        logger.begin_session();
        for pair in &case.log_pairs {
            logger.record(&root.join(&pair.old), &root.join(&pair.new));
        }
        if case.clear_last_before_restore {
            logger.begin_session();
        }

        let partial_lines = case.partial_indexes.map(|indexes| {
            indexes
                .into_iter()
                .map(|index| {
                    let pair = &case.log_pairs[index];
                    format!(
                        "{}{SEPARATOR}{}",
                        root.join(&pair.old).display(),
                        root.join(&pair.new).display()
                    )
                })
                .collect::<Vec<_>>()
        });
        let result = restore(&logger, case.all_history, partial_lines.as_deref()).unwrap();
        assert_result(&case.name, &root, &result, &logger, &case.expected);
    }
}

#[test]
fn shared_history_rotation_boundary() {
    let directory = tempfile::tempdir().unwrap();
    let logger = RenameLogger::new(directory.path().join("log"));
    logger.begin_session();
    fs::write(&logger.history_path, vec![b'x'; ROTATE_BYTES as usize + 1]).unwrap();
    logger.record(Path::new("old.txt"), Path::new("new.txt"));

    assert_eq!(
        fs::metadata(logger.log_dir.join("history.1.log"))
            .unwrap()
            .len(),
        ROTATE_BYTES + 1
    );
    assert_eq!(
        logger.read_history(),
        vec![(PathBuf::from("old.txt"), PathBuf::from("new.txt"))]
    );
    assert_eq!(logger.read_last(), logger.read_history());
}
