use fancy_regex::Regex;
use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::path::PathType;
use crate::transforms;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct Rule {
    pub scope: PathType,
    pub kind: String,
    pub find: String,
    pub replace: String,
    pub convert: String,
    pub insert: String,
    pub insert_at: String,
    pub condition: String,
    pub enabled: bool,
}

impl Default for Rule {
    fn default() -> Self {
        Self {
            scope: PathType::Name,
            kind: "replace".into(),
            find: String::new(),
            replace: String::new(),
            convert: String::new(),
            insert: String::new(),
            insert_at: "start".into(),
            condition: String::new(),
            enabled: true,
        }
    }
}

#[derive(Debug, Error)]
pub enum RuleError {
    #[error("未知规则种类: {0}")]
    UnknownKind(String),
    #[error("未知插入位置: {0}")]
    UnknownInsertPosition(String),
}

impl Rule {
    pub fn validate(&self) -> Result<(), RuleError> {
        if !matches!(
            self.kind.as_str(),
            "replace" | "replace_icase" | "regex" | "convert" | "insert" | "env"
        ) {
            return Err(RuleError::UnknownKind(self.kind.clone()));
        }
        if !matches!(self.insert_at.as_str(), "start" | "end") {
            return Err(RuleError::UnknownInsertPosition(self.insert_at.clone()));
        }
        Ok(())
    }
}

pub fn apply(value: &str, rule: &Rule) -> String {
    if !rule.enabled || !condition_matches(value, &rule.condition) {
        return value.into();
    }
    match rule.kind.as_str() {
        "replace" if !rule.find.is_empty() => value.replace(&rule.find, &rule.replace),
        "replace_icase" if !rule.find.is_empty() => {
            let pattern = format!("(?i:{})", fancy_regex::escape(&rule.find));
            Regex::new(&pattern)
                .ok()
                .map(|regex| regex.replace_all(value, rule.replace.as_str()).into_owned())
                .unwrap_or_else(|| value.into())
        }
        "regex" if !rule.find.is_empty() => {
            let replacement = python_replacement(&rule.replace);
            Regex::new(&rule.find)
                .ok()
                .map(|regex| regex.replace_all(value, replacement.as_str()).into_owned())
                .unwrap_or_else(|| value.into())
        }
        "convert" => transforms::apply(&rule.convert, value).unwrap_or_else(|| value.into()),
        "insert" if !rule.insert.is_empty() && rule.insert_at == "end" => {
            format!("{value}{}", rule.insert)
        }
        "insert" if !rule.insert.is_empty() => format!("{}{value}", rule.insert),
        _ => value.into(),
    }
}

fn condition_matches(value: &str, condition: &str) -> bool {
    if condition.is_empty() {
        return true;
    }
    Regex::new(condition)
        .ok()
        .and_then(|regex| regex.is_match(value).ok())
        .unwrap_or(false)
}

fn python_replacement(replacement: &str) -> String {
    let mut output = String::with_capacity(replacement.len());
    let mut chars = replacement.chars().peekable();
    while let Some(ch) = chars.next() {
        if ch == '\\' && chars.peek().is_some_and(char::is_ascii_digit) {
            output.push('$');
            while chars.peek().is_some_and(char::is_ascii_digit) {
                output.push(chars.next().unwrap());
            }
        } else {
            output.push(ch);
        }
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn supports_all_rule_kinds() {
        let mut rule = Rule {
            find: "a".into(),
            replace: "X".into(),
            ..Rule::default()
        };
        assert_eq!(apply("banana", &rule), "bXnXnX");
        rule.kind = "replace_icase".into();
        assert_eq!(apply("Banana", &rule), "BXnXnX");
        rule.kind = "regex".into();
        rule.find = r"(\d+)".into();
        rule.replace = r"[\1]".into();
        assert_eq!(apply("img12x34", &rule), "img[12]x[34]");
        rule.kind = "convert".into();
        rule.convert = "upper".into();
        assert_eq!(apply("abc", &rule), "ABC");
    }

    #[test]
    fn invalid_regex_is_noop() {
        let rule = Rule {
            kind: "regex".into(),
            find: "(".into(),
            replace: "x".into(),
            ..Rule::default()
        };
        assert_eq!(apply("abc", &rule), "abc");
    }
}
