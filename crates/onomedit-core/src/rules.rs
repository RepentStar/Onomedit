use fancy_regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
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
        "regex" if !rule.find.is_empty() => compile_python_regex(&rule.find)
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
    compile_python_regex(condition)
        .and_then(|regex| regex.is_match(value).ok())
        .unwrap_or(false)
}

fn compile_python_regex(pattern: &str) -> Option<Regex> {
    let pattern = adapt_named_conditionals(pattern);
    let pattern = adapt_python_pattern(&pattern);
    Regex::new(&pattern).ok()
}

fn adapt_named_conditionals(pattern: &str) -> String {
    let mut names = HashMap::new();
    let mut capture_count = 0;
    let mut output = String::with_capacity(pattern.len());
    let mut index = 0;
    let mut escaped = false;
    let mut in_class = false;
    while index < pattern.len() {
        let ch = pattern[index..]
            .chars()
            .next()
            .expect("valid character boundary");
        let char_len = ch.len_utf8();
        if escaped {
            output.push(ch);
            escaped = false;
            index += char_len;
            continue;
        }
        if ch == '\\' {
            output.push(ch);
            escaped = true;
            index += char_len;
            continue;
        }
        if ch == '[' {
            in_class = true;
            output.push(ch);
            index += char_len;
            continue;
        }
        if ch == ']' && in_class {
            in_class = false;
            output.push(ch);
            index += char_len;
            continue;
        }
        if in_class || ch != '(' {
            output.push(ch);
            index += char_len;
            continue;
        }
        if pattern[index..].starts_with("(?#") {
            let Some(comment_end) = pattern[index + 3..].find(')') else {
                output.push_str(&pattern[index..]);
                break;
            };
            let end = index + 3 + comment_end + 1;
            output.push_str(&pattern[index..end]);
            index = end;
            continue;
        }
        if pattern[index..].starts_with("(?P<") {
            let Some(name_end) = pattern[index + 4..].find('>') else {
                output.push_str(&pattern[index..]);
                break;
            };
            capture_count += 1;
            let end = index + 4 + name_end + 1;
            names.insert(pattern[index + 4..end - 1].to_owned(), capture_count);
            output.push_str(&pattern[index..end]);
            index = end;
            continue;
        }
        if pattern[index..].starts_with("(?(") {
            let Some(reference_end) = pattern[index + 3..].find(')') else {
                output.push_str(&pattern[index..]);
                break;
            };
            let end = index + 3 + reference_end;
            let reference = &pattern[index + 3..end];
            if let Some(group) = names.get(reference) {
                output.push_str(&format!("(?({group})"));
            } else {
                output.push_str(&pattern[index..end + 1]);
            }
            index = end + 1;
            continue;
        }
        if !pattern[index..].starts_with("(?") {
            capture_count += 1;
        }
        output.push(ch);
        index += char_len;
    }
    output
}

fn adapt_python_pattern(pattern: &str) -> String {
    // fancy-regex 无法关闭 Unicode，因此需展开 Python `(?a)` 的简写类和单词边界。
    let Some((flags, remainder)) = global_flags(pattern) else {
        return adapt_fragment(pattern, false, false, false, false).0;
    };
    if invalid_python_flags(flags) {
        return pattern.into();
    }
    let ascii_mode = flags.contains('a');
    let ignore_case = flags.contains('i');
    let verbose_mode = flags.contains('x');
    let rust_flags: String = flags
        .chars()
        .filter(|flag| !matches!(flag, 'a' | 'u'))
        .collect();
    let mut output = String::with_capacity(pattern.len());
    if !rust_flags.is_empty() {
        output.push_str(&format!("(?{rust_flags})"));
    }
    output.push_str(&adapt_fragment(remainder, ascii_mode, ignore_case, verbose_mode, false).0);
    output
}

fn global_flags(pattern: &str) -> Option<(&str, &str)> {
    let rest = pattern.strip_prefix("(?")?;
    let end = rest.find(')')?;
    let flags = &rest[..end];
    if flags.is_empty() || !flags.chars().all(|flag| "aiLmsux".contains(flag)) {
        return None;
    }
    Some((flags, &rest[end + 1..]))
}

fn invalid_python_flags(flags: &str) -> bool {
    flags.contains('L') || (flags.contains('a') && flags.contains('u'))
}

fn adapt_fragment(
    pattern: &str,
    ascii_mode: bool,
    ignore_case: bool,
    verbose_mode: bool,
    stop_at_close: bool,
) -> (String, usize) {
    const WORD_BOUNDARY: &str =
        "(?:(?<![A-Za-z0-9_])(?=[A-Za-z0-9_])|(?<=[A-Za-z0-9_])(?![A-Za-z0-9_]))";
    const NON_WORD_BOUNDARY: &str = "(?:(?=[\\s\\S])|(?<=[\\s\\S]))(?:(?<=[A-Za-z0-9_])(?=[A-Za-z0-9_])|(?<![A-Za-z0-9_])(?![A-Za-z0-9_]))";
    let mut output = String::with_capacity(pattern.len());
    let mut ordinary_depth: usize = 0;
    let mut index = 0;
    while index < pattern.len() {
        let ch = pattern[index..]
            .chars()
            .next()
            .expect("valid character boundary");
        let char_len = ch.len_utf8();
        if verbose_mode && ch == '#' {
            let comment_end = pattern[index..]
                .find('\n')
                .map_or(pattern.len(), |offset| index + offset + 1);
            output.push_str(&pattern[index..comment_end]);
            index = comment_end;
            continue;
        }
        if ch == '[' {
            let Some(class_end) = character_class_end(&pattern[index..]) else {
                output.push_str(&pattern[index..]);
                return (output, pattern.len());
            };
            let class = &pattern[index..index + class_end];
            if ascii_mode {
                let adapted = adapt_ascii_class(class);
                if ignore_case {
                    output.push_str(&adapt_ascii_ignore_case_class(class, &adapted));
                } else {
                    output.push_str(&adapted);
                }
            } else if ignore_case {
                output.push_str(&adapt_unicode_ignore_case_class(class));
            } else {
                output.push_str(class);
            }
            index += class_end;
            continue;
        }
        if ch == '(' {
            if pattern[index..].starts_with("(?#") {
                let Some(comment_end) = pattern[index + 3..].find(')') else {
                    output.push_str(&pattern[index..]);
                    return (output, pattern.len());
                };
                output.push_str("(?:)");
                index += 3 + comment_end + 1;
                continue;
            }
            if pattern[index..].starts_with("(?P<") {
                let Some(name_end) = pattern[index + 4..].find('>') else {
                    output.push_str(&pattern[index..]);
                    return (output, pattern.len());
                };
                let header_end = index + 4 + name_end + 1;
                output.push_str(&pattern[index..header_end]);
                ordinary_depth += 1;
                index = header_end;
                continue;
            }
            if pattern[index..].starts_with("(?P=") {
                let Some(backref_end) = pattern[index + 4..].find(')') else {
                    output.push_str(&pattern[index..]);
                    return (output, pattern.len());
                };
                let group_end = index + 4 + backref_end + 1;
                output.push_str(&pattern[index..group_end]);
                index = group_end;
                continue;
            }
            if let Some((body_start, flags)) = scoped_flags(pattern, index) {
                let (enabled, disabled) = flags.split_once('-').unwrap_or((flags, ""));
                let invalid = flags.matches('-').count() > 1
                    || invalid_python_flags(enabled)
                    || disabled.chars().any(|flag| matches!(flag, 'a' | 'u' | 'L'));
                let inner_ascii = if invalid {
                    ascii_mode
                } else if enabled.contains('a') {
                    true
                } else if enabled.contains('u') {
                    false
                } else {
                    ascii_mode
                };
                let inner_verbose = if enabled.contains('x') {
                    true
                } else if disabled.contains('x') {
                    false
                } else {
                    verbose_mode
                };
                let inner_ignore_case = if enabled.contains('i') {
                    true
                } else if disabled.contains('i') {
                    false
                } else {
                    ignore_case
                };
                let rust_flags: String = if invalid {
                    flags.into()
                } else {
                    flags
                        .chars()
                        .filter(|flag| !matches!(flag, 'a' | 'u'))
                        .collect()
                };
                output.push_str("(?");
                output.push_str(&rust_flags);
                output.push(':');
                let (body, body_end) = adapt_fragment(
                    &pattern[body_start..],
                    inner_ascii,
                    inner_ignore_case,
                    inner_verbose,
                    true,
                );
                output.push_str(&body);
                if body_end == pattern[body_start..].len() {
                    return (output, pattern.len());
                }
                output.push(')');
                index = body_start + body_end + 1;
                continue;
            }
            ordinary_depth += 1;
            output.push(ch);
            index += char_len;
            continue;
        }
        if ch == ')' {
            if ordinary_depth == 0 && stop_at_close {
                return (output, index);
            }
            ordinary_depth = ordinary_depth.saturating_sub(1);
            output.push(ch);
            index += char_len;
            continue;
        }
        if ch == '\\' {
            let escaped_start = index + char_len;
            let Some(escaped) = pattern[escaped_start..].chars().next() else {
                output.push(ch);
                return (output, pattern.len());
            };
            let replacement = if ascii_mode {
                match escaped {
                    'w' => Some("[A-Za-z0-9_]"),
                    'W' => Some("[^A-Za-z0-9_]"),
                    'd' => Some("[0-9]"),
                    'D' => Some("[^0-9]"),
                    's' => Some("[ \\t\\n\\r\\f\\v]"),
                    'S' => Some("[^ \\t\\n\\r\\f\\v]"),
                    'b' => Some(WORD_BOUNDARY),
                    'B' => Some(NON_WORD_BOUNDARY),
                    _ => None,
                }
            } else {
                None
            };
            if let Some(replacement) = replacement {
                output.push_str(replacement);
            } else {
                output.push(ch);
                output.push(escaped);
            }
            index = escaped_start + escaped.len_utf8();
            continue;
        }
        if ascii_mode && ignore_case && matches!(ch, 's' | 'S') {
            output.push_str("(?!(?-i:ſ))");
            output.push(ch);
        } else if ascii_mode && ignore_case && matches!(ch, 'k' | 'K') {
            output.push_str("(?!(?-i:K))");
            output.push(ch);
        } else if ascii_mode && ignore_case && !ch.is_ascii() {
            output.push_str(&format!("(?-i:{ch})"));
        } else if !ascii_mode && ignore_case {
            if let Some(case_class) = python_ignore_case_class(ch) {
                output.push_str(case_class);
            } else {
                output.push(ch);
            }
        } else {
            output.push(ch);
        }
        index += char_len;
    }
    (output, pattern.len())
}

fn scoped_flags(pattern: &str, start: usize) -> Option<(usize, &str)> {
    if !pattern[start..].starts_with("(?") {
        return None;
    }
    let flags_start = start + 2;
    let mut saw_flag = false;
    for (offset, ch) in pattern[flags_start..].char_indices() {
        if ch == ':' {
            return saw_flag.then_some((
                flags_start + offset + 1,
                &pattern[flags_start..flags_start + offset],
            ));
        }
        if !"aiLmsux-".contains(ch) {
            return None;
        }
        saw_flag |= ch != '-';
    }
    None
}

fn character_class_end(class: &str) -> Option<usize> {
    let mut escaped = false;
    let mut first = true;
    for (offset, ch) in class[1..].char_indices() {
        if escaped {
            escaped = false;
            first = false;
            continue;
        }
        if ch == '\\' {
            escaped = true;
            continue;
        }
        if first && ch == '^' {
            continue;
        }
        if ch == ']' && !first {
            return Some(offset + 2);
        }
        first = false;
    }
    None
}

fn adapt_ascii_class(class: &str) -> String {
    let mut content = &class[1..class.len() - 1];
    let negated = content.starts_with('^');
    if negated {
        content = &content[1..];
    }
    let chars: Vec<char> = content.chars().collect();
    let mut base = String::with_capacity(content.len());
    let mut complements = Vec::new();
    let mut index = 0;
    while index < chars.len() {
        if chars[index] != '\\' || index + 1 == chars.len() {
            base.push(chars[index]);
            index += 1;
            continue;
        }
        match chars[index + 1] {
            'w' => base.push_str("A-Za-z0-9_"),
            'd' => base.push_str("0-9"),
            's' => base.push_str(" \\t\\n\\r\\f\\v"),
            'W' => complements.push("A-Za-z0-9_"),
            'D' => complements.push("0-9"),
            'S' => complements.push(" \\t\\n\\r\\f\\v"),
            escaped => {
                base.push('\\');
                base.push(escaped);
            }
        }
        index += 2;
    }
    if complements.is_empty() {
        return format!("[{}{base}]", if negated { "^" } else { "" });
    }
    if !negated {
        let mut alternatives = Vec::new();
        if !base.is_empty() {
            alternatives.push(format!("[{base}]"));
        }
        alternatives.extend(complements.into_iter().map(|set| format!("[^{set}]")));
        return if alternatives.len() == 1 {
            alternatives.pop().expect("one alternative")
        } else {
            format!("(?:{})", alternatives.join("|"))
        };
    }
    let mut output = String::from("(?:");
    if !base.is_empty() {
        output.push_str(&format!("(?![{base}])"));
    }
    for set in complements {
        output.push_str(&format!("(?=[{set}])"));
    }
    output.push_str("[\\s\\S])");
    output
}

fn adapt_ascii_ignore_case_class(class: &str, adapted: &str) -> String {
    let content = class
        .strip_prefix("[^")
        .and_then(|content| content.strip_suffix(']'));
    let negated = content.is_some();
    let mut include = String::new();
    let mut exclude = String::new();
    for (ascii, special) in [(&['s', 'S'][..], 'ſ'), (&['k', 'K'][..], 'K')] {
        let has_ascii = class_mentions_any(class, ascii);
        let has_special = class_mentions_any(class, &[special]);
        let python_matches = if negated { !has_special } else { has_special };
        let fancy_matches = if negated {
            !(has_ascii || has_special)
        } else {
            has_ascii || has_special
        };
        if python_matches && !fancy_matches {
            include.push(special);
        } else if !python_matches && fancy_matches {
            exclude.push(special);
        }
    }
    let mut output = String::new();
    if !exclude.is_empty() {
        output.push_str(&format!("(?!(?-i:[{exclude}]))"));
    }
    if include.is_empty() {
        output.push_str(adapted);
    } else {
        output.push_str(&format!("(?:(?-i:[{include}])|{adapted})"));
    }
    output
}

fn python_ignore_case_class(ch: char) -> Option<&'static str> {
    match ch {
        'i' | 'I' | 'İ' | 'ı' => Some("[iIİı]"),
        's' | 'S' | 'ſ' => Some("[sSſ]"),
        'k' | 'K' | 'K' => Some("[kKK]"),
        _ => None,
    }
}

fn adapt_unicode_ignore_case_class(class: &str) -> String {
    let mut additions = String::new();
    if class_mentions_any(class, &['i', 'I', 'İ', 'ı']) {
        additions.push_str("iIİı");
    }
    if class_mentions_any(class, &['s', 'S', 'ſ']) {
        additions.push_str("sSſ");
    }
    if class_mentions_any(class, &['k', 'K', 'K']) {
        additions.push_str("kKK");
    }
    if additions.is_empty() {
        return class.into();
    }
    format!("{}{}]", &class[..class.len() - 1], additions)
}

fn class_mentions_any(class: &str, targets: &[char]) -> bool {
    let mut chars = class[1..class.len() - 1].chars().peekable();
    if chars.peek() == Some(&'^') {
        chars.next();
    }
    let mut previous = None;
    while let Some(ch) = chars.next() {
        if ch == '\\' {
            chars.next();
            previous = None;
            continue;
        }
        if ch == '-' {
            if let (Some(start), Some(&end)) = (previous, chars.peek()) {
                if targets
                    .iter()
                    .any(|target| start <= *target && *target <= end)
                {
                    return true;
                }
            }
            previous = None;
            continue;
        }
        if targets.contains(&ch) {
            return true;
        }
        previous = Some(ch);
    }
    false
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
                if value > 0o377 {
                    return Err(());
                }
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
    let mut search_start = 0;
    // 手动推进以保留 Python 在非空匹配后紧随空匹配的语义。
    while search_start <= value.len() {
        let Some(captures) = regex.captures_from_pos(value, search_start).ok()? else {
            break;
        };
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
        search_start = if whole.start() == whole.end() {
            next_utf8_boundary(value, whole.end())
        } else {
            whole.end()
        };
    }
    output.push_str(&value[previous_end..]);
    Some(output)
}

fn next_utf8_boundary(value: &str, position: usize) -> usize {
    value[position..]
        .chars()
        .next()
        .map_or(value.len() + 1, |ch| position + ch.len_utf8())
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
