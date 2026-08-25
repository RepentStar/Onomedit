use std::path::PathBuf;

use chrono::{Local, TimeZone, Timelike};
use onomedit_core::diff::{diff_text, levenshtein};
use onomedit_core::path::PathItem;
use onomedit_core::rules::{self, Rule};
use onomedit_core::template::{EnvContext, EnvVars, SystemValueSource, format_date};
use onomedit_core::{safe_name, transforms};
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct Fixture {
    safe_names: Vec<SafeNameCase>,
    paths: Vec<PathCase>,
    transforms: Vec<TransformCase>,
    distances: Vec<DistanceCase>,
    rules: Vec<RuleCase>,
    template_sequences: Vec<TemplateSequence>,
    date_formats: Vec<DateFormatCase>,
    diffs: Vec<DiffCase>,
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

#[derive(Debug, Deserialize)]
struct RuleCase {
    value: String,
    rule: Rule,
    expected: String,
}

#[derive(Debug, Deserialize)]
struct TemplateSequence {
    inputs: Vec<TemplateInput>,
    expected: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct TemplateInput {
    text: String,
    clip_text: Option<String>,
}

#[derive(Debug, Deserialize)]
struct DateFormatCase {
    pattern: String,
    expected: String,
}

#[derive(Debug, Deserialize)]
struct DiffCase {
    left: String,
    right: String,
    expected: String,
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

#[test]
fn shared_rule_cases_match() {
    for (index, case) in fixture().rules.into_iter().enumerate() {
        assert_eq!(
            rules::apply(&case.value, &case.rule),
            case.expected,
            "rule case {index}: {:?}",
            case.rule
        );
    }
}

#[test]
fn shared_template_sequences_match() {
    for sequence in fixture().template_sequences {
        let mut env = EnvVars::new(SystemValueSource);
        let actual: Vec<String> = sequence
            .inputs
            .into_iter()
            .map(|input| {
                let context = EnvContext {
                    file: String::new(),
                    clip_text: input.clip_text,
                };
                env.expand(&input.text, Some(&context))
            })
            .collect();
        assert_eq!(actual, sequence.expected);
    }
}

#[test]
fn shared_date_formats_match() {
    let date = Local
        .with_ymd_and_hms(2026, 8, 12, 9, 5, 3)
        .single()
        .unwrap()
        .with_nanosecond(123_000_000)
        .unwrap();
    for case in fixture().date_formats {
        assert_eq!(format_date(&case.pattern, date), case.expected);
    }
}

#[test]
fn shared_diff_cases_match() {
    for case in fixture().diffs {
        assert_eq!(diff_text(&case.left, &case.right), case.expected);
    }
}
