use std::path::PathBuf;

use onomedit_core::diff::levenshtein;
use onomedit_core::path::PathItem;
use onomedit_core::{safe_name, transforms};
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct Fixture {
    safe_names: Vec<SafeNameCase>,
    paths: Vec<PathCase>,
    transforms: Vec<TransformCase>,
    distances: Vec<DistanceCase>,
}

#[derive(Debug, Deserialize)]
struct SafeNameCase {
    input: String,
    expected: String,
}

#[derive(Debug, Deserialize)]
struct PathCase {
    input: String,
    name: String,
    stem: String,
    ext: String,
}

#[derive(Debug, Deserialize)]
struct TransformCase {
    kind: String,
    input: String,
    expected: String,
}

#[derive(Debug, Deserialize)]
struct DistanceCase {
    left: String,
    right: String,
    expected: usize,
}

fn fixture() -> Fixture {
    let path =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests-rust/fixtures/core.json");
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

#[test]
fn shared_safe_name_cases_match() {
    for case in fixture().safe_names {
        assert_eq!(safe_name::sanitize_name(&case.input, "_"), case.expected);
    }
}

#[test]
fn shared_path_cases_match() {
    for case in fixture().paths {
        let item = PathItem::new(case.input);
        assert_eq!(item.name(), case.name);
        assert_eq!(item.stem(), case.stem);
        assert_eq!(item.ext(), case.ext);
    }
}

#[test]
fn shared_transform_cases_match() {
    for case in fixture().transforms {
        assert_eq!(
            transforms::apply(&case.kind, &case.input).unwrap(),
            case.expected
        );
    }
}

#[test]
fn shared_distance_cases_match() {
    for case in fixture().distances {
        assert_eq!(levenshtein(&case.left, &case.right), case.expected);
    }
}
