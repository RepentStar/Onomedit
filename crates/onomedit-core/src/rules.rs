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
            replace_ignore_case(value, &rule.find, &rule.replace)
        }
        "regex" if !rule.find.is_empty() => Regex::new(&rule.find)
            .ok()
            .and_then(|regex| {
                let parts = parse_python_replacement(&rule.replace, &regex).ok()?;
                replace_with_captures(value, &regex, &parts)
            })
            .unwrap_or_else(|| value.into()),
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

fn replace_ignore_case(value: &str, find: &str, replacement: &str) -> String {
    let value: Vec<char> = value.chars().collect();
    let find: Vec<char> = find.chars().collect();
    let mut output = String::new();
    let mut index = 0;
    while index < value.len() {
        let matches = value[index..].get(..find.len()).is_some_and(|candidate| {
            candidate
                .iter()
                .zip(&find)
                .all(|(left, right)| python_case_eq(*left, *right))
        });
        if matches {
            output.push_str(replacement);
            index += find.len();
        } else {
            output.push(value[index]);
            index += 1;
        }
    }
    output
}

fn python_case_eq(left: char, right: char) -> bool {
    fn folded(ch: char) -> char {
        if matches!(ch, 'i' | 'I' | 'İ' | 'ı') {
            return 'i';
        }
        unicode_case_mapping::case_folded(ch)
            .and_then(|codepoint| char::from_u32(codepoint.get()))
            .unwrap_or(ch)
    }
    folded(left) == folded(right)
}

#[derive(Debug, PartialEq, Eq)]
enum Part {
    Literal(String),
    GroupIndex(usize),
    GroupName(String),
}

fn parse_python_replacement(replacement: &str, regex: &Regex) -> Result<Vec<Part>, ()> {
    let chars: Vec<char> = replacement.chars().collect();
    let names: std::collections::HashSet<&str> = regex.capture_names().flatten().collect();
    let mut parts = Vec::new();
    let mut literal = String::new();
    let mut index = 0;
    while index < chars.len() {
        if chars[index] != '\\' {
            literal.push(chars[index]);
            index += 1;
            continue;
        }
        index += 1;
        let escaped = *chars.get(index).ok_or(())?;
        if escaped == 'g' {
            if !literal.is_empty() {
                parts.push(Part::Literal(std::mem::take(&mut literal)));
            }
            index += 1;
            if chars.get(index) != Some(&'<') {
                return Err(());
            }
            let end = chars[index + 1..]
                .iter()
                .position(|ch| *ch == '>')
                .map(|offset| index + 1 + offset)
                .ok_or(())?;
            let name: String = chars[index + 1..end].iter().collect();
            if let Ok(group) = name.parse::<usize>() {
                if group >= regex.captures_len() {
                    return Err(());
                }
                parts.push(Part::GroupIndex(group));
            } else if !name.is_empty() && names.contains(name.as_str()) {
                parts.push(Part::GroupName(name));
            } else {
                return Err(());
            }
            index = end + 1;
            continue;
        }
        if escaped.is_ascii_digit() {
            let start = index;
            let mut end = index + 1;
            while end < chars.len() && end < start + 3 && chars[end].is_ascii_digit() {
                end += 1;
            }
            let digits: String = chars[start..end].iter().collect();
            if escaped == '0'
                || (digits.len() == 3 && digits.chars().all(|ch| ('0'..='7').contains(&ch)))
            {
                let octal: String = digits
                    .chars()
                    .take(3)
                    .take_while(|ch| ('0'..='7').contains(ch))
                    .collect();
                let value = u32::from_str_radix(&octal, 8).map_err(|_| ())?;
                literal.push(char::from_u32(value).ok_or(())?);
                index = start + octal.len();
                continue;
            }
            if !literal.is_empty() {
                parts.push(Part::Literal(std::mem::take(&mut literal)));
            }
            let group_digits: String = digits.chars().take(2).collect();
            let group = group_digits.parse::<usize>().map_err(|_| ())?;
            if group == 0 || group >= regex.captures_len() {
                return Err(());
            }
            parts.push(Part::GroupIndex(group));
            index = start + group_digits.len();
            continue;
        }
        let decoded = match escaped {
            '\\' => '\\',
            'n' => '\n',
            'r' => '\r',
            't' => '\t',
            'f' => '\u{c}',
            'v' => '\u{b}',
            'a' => '\u{7}',
            'b' => '\u{8}',
            ch if ch.is_ascii_alphabetic() => return Err(()),
            ch => {
                literal.push('\\');
                ch
            }
        };
        literal.push(decoded);
        index += 1;
    }
    if !literal.is_empty() {
        parts.push(Part::Literal(literal));
    }
    Ok(parts)
}

fn replace_with_captures(value: &str, regex: &Regex, parts: &[Part]) -> Option<String> {
    let mut output = String::with_capacity(value.len());
    let mut previous_end = 0;
    for captures in regex.captures_iter(value) {
        let captures = captures.ok()?;
        let whole = captures.get(0)?;
        output.push_str(&value[previous_end..whole.start()]);
        for part in parts {
            match part {
                Part::Literal(text) => output.push_str(text),
                Part::GroupIndex(index) => {
                    if let Some(found) = captures.get(*index) {
                        output.push_str(found.as_str());
                    }
                }
                Part::GroupName(name) => {
                    if let Some(found) = captures.name(name) {
                        output.push_str(found.as_str());
                    }
                }
            }
        }
        previous_end = whole.end();
    }
    output.push_str(&value[previous_end..]);
    Some(output)
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

    #[test]
    fn python_replacements_support_named_groups_and_literal_dollars() {
        let named = Rule {
            kind: "regex".into(),
            find: r"(?P<word>[a-z]+)".into(),
            replace: r"<\g<word>>".into(),
            ..Rule::default()
        };
        assert_eq!(apply("abc 12 def", &named), "<abc> 12 <def>");

        let dollar = Rule {
            kind: "regex".into(),
            find: "a".into(),
            replace: "$1".into(),
            ..Rule::default()
        };
        assert_eq!(apply("a", &dollar), "$1");
    }
}
