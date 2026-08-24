use std::fs;
use std::path::{Component, Path, PathBuf};

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
}

#[derive(Debug, Deserialize)]
struct TreeFile {
    path: String,
    content: String,
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

fn build_tree(root: &Path, tree: &Tree) {
    fs::create_dir(root).unwrap();
    for relative in &tree.directories {
        fs::create_dir_all(root.join(relative)).unwrap();
    }
    for file in &tree.files {
        let path = root.join(&file.path);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, &file.content).unwrap();
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
        build_tree(&root, &fixture.tree);
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
