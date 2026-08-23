use std::collections::HashMap;
use std::fs;
use std::path::Path;
use std::time::SystemTime;

use chrono::{DateTime, Datelike, Local, Timelike};
use rand::Rng;

pub const DEFAULT_DATE_FORMAT: &str = "yyyy-MM-dd HH:mm:ss";

#[derive(Debug, Clone, Default)]
pub struct EnvContext {
    pub file: String,
    pub clip_text: Option<String>,
}

pub trait ValueSource {
    fn now(&self) -> DateTime<Local>;
    fn random_digits(&self) -> String;
    fn uuid(&self) -> String;
}

#[derive(Debug, Default)]
pub struct SystemValueSource;

impl ValueSource for SystemValueSource {
    fn now(&self) -> DateTime<Local> {
        Local::now()
    }

    fn random_digits(&self) -> String {
        format!("{:08}", rand::rng().random_range(0..=99_999_999_u32))
    }

    fn uuid(&self) -> String {
        uuid::Uuid::new_v4().to_string()
    }
}

pub struct EnvVars<S = SystemValueSource> {
    counters: HashMap<(i64, usize, i64), i64>,
    source: S,
}

impl Default for EnvVars<SystemValueSource> {
    fn default() -> Self {
        Self::new(SystemValueSource)
    }
}

impl<S: ValueSource> EnvVars<S> {
    pub fn new(source: S) -> Self {
        Self {
            counters: HashMap::new(),
            source,
        }
    }

    pub fn expand(&mut self, text: &str, context: Option<&EnvContext>) -> String {
        if !text.contains('<') {
            return text.into();
        }
        let mut output = String::with_capacity(text.len());
        let mut index = 0;
        while index < text.len() {
            let remaining = &text[index..];
            if !remaining.starts_with('<') {
                let ch = remaining.chars().next().unwrap();
                output.push(ch);
                index += ch.len_utf8();
                continue;
            }
            let Some(relative_close) = remaining.find('>') else {
                output.push_str(remaining);
                break;
            };
            let close = index + relative_close;
            let name = &text[index + 1..close];
            let arity = match name {
                "n" => 3,
                "d" | "t" | "tc" => 1,
                "f" | "p" | "r" | "rg" | "clip" => 0,
                _ => {
                    output.push('<');
                    index += 1;
                    continue;
                }
            };
            let Some((args, next)) = parse_args(text, close + 1, arity) else {
                output.push('<');
                index += 1;
                continue;
            };
            if let Some(replacement) = self.build(name, &args, context) {
                output.push_str(&replacement);
                index = next;
            } else {
                output.push('<');
                index += 1;
            }
        }
        output
    }

    fn build(
        &mut self,
        name: &str,
        args: &[String],
        context: Option<&EnvContext>,
    ) -> Option<String> {
        match name {
            "n" => {
                let start = args.first()?.trim().parse::<i64>().ok()?;
                let width = args.get(1)?.trim().parse::<usize>().ok()?.max(1);
                let step = args.get(2)?.trim().parse::<i64>().ok()?.max(1);
                let current = self
                    .counters
                    .entry((start, width, step))
                    .or_insert(start - step);
                *current += step;
                Some(format!("{:0width$}", *current, width = width))
            }
            "d" => Some(format_date(
                args.first().map(String::as_str).unwrap_or(""),
                self.source.now(),
            )),
            "t" | "tc" => file_time(name, args, context),
            "f" => context
                .and_then(|ctx| Path::new(&ctx.file).parent()?.file_name())
                .map(|v| v.to_string_lossy().into_owned())
                .or(Some(String::new())),
            "p" => Some(picture_pack(context)),
            "r" => Some(self.source.random_digits()),
            "rg" => Some(self.source.uuid()),
            "clip" => context
                .and_then(|ctx| ctx.clip_text.as_ref())
                .filter(|text| !text.contains(['\n', '\r']))
                .cloned(),
            _ => None,
        }
    }
}

fn parse_args(text: &str, mut position: usize, arity: usize) -> Option<(Vec<String>, usize)> {
    let mut args = Vec::with_capacity(arity);
    for index in 0..arity {
        if let Some(relative) = text[position..].find(';') {
            let semi = position + relative;
            args.push(text[position..semi].into());
            position = semi + 1;
        } else if index == arity - 1 {
            args.push(text[position..].into());
            position = text.len();
        } else {
            return None;
        }
    }
    Some((args, position))
}

fn file_time(name: &str, args: &[String], context: Option<&EnvContext>) -> Option<String> {
    let Some(context) = context else {
        return Some(String::new());
    };
    if context.file.is_empty() {
        return Some(String::new());
    }
    let metadata = fs::metadata(&context.file).ok()?;
    let time: SystemTime = if name == "t" {
        metadata.modified().ok()?
    } else {
        metadata.created().or_else(|_| metadata.modified()).ok()?
    };
    let date: DateTime<Local> = time.into();
    Some(format_date(
        args.first().map(String::as_str).unwrap_or(""),
        date,
    ))
}

fn picture_pack(context: Option<&EnvContext>) -> String {
    let Some(context) = context else {
        return String::new();
    };
    let mut directory = Path::new(&context.file).parent();
    while let Some(path) = directory {
        if let Some(name) = path.file_name().map(|v| v.to_string_lossy())
            && !name.is_empty()
            && !name.starts_with('.')
        {
            return name.into_owned();
        }
        directory = path.parent();
    }
    String::new()
}

pub fn format_date(pattern: &str, date: DateTime<Local>) -> String {
    let pattern = if pattern.is_empty() {
        DEFAULT_DATE_FORMAT
    } else {
        pattern
    };
    let replacements = [
        ("yyyy", format!("{:04}", date.year())),
        ("yy", format!("{:02}", date.year().rem_euclid(100))),
        ("MM", format!("{:02}", date.month())),
        ("M", date.month().to_string()),
        ("dd", format!("{:02}", date.day())),
        ("d", date.day().to_string()),
        ("HH", format!("{:02}", date.hour())),
        ("H", date.hour().to_string()),
        ("hh", format!("{:02}", date.hour12().1)),
        ("h", date.hour12().1.to_string()),
        ("mm", format!("{:02}", date.minute())),
        ("m", date.minute().to_string()),
        ("ss", format!("{:02}", date.second())),
        ("s", date.second().to_string()),
        ("fff", format!("{:03}", date.timestamp_subsec_millis())),
    ];
    replacements
        .into_iter()
        .fold(pattern.to_owned(), |value, (token, replacement)| {
            value.replace(token, &replacement)
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn counters_continue_and_groups_are_isolated() {
        let mut env = EnvVars::default();
        assert_eq!(env.expand("<n>1;3;1;", None), "001");
        assert_eq!(env.expand("<n>1;3;1;", None), "002");
        assert_eq!(env.expand("<n>5;2;1;", None), "05");
        assert_eq!(env.expand("a <n>1;3;1; b <n>1;3;1;", None), "a 003 b 004");
    }

    #[test]
    fn malformed_and_multiline_clipboard_stay_verbatim() {
        let mut env = EnvVars::default();
        assert_eq!(env.expand("a <n>1;2; b", None), "a <n>1;2; b");
        let context = EnvContext {
            file: String::new(),
            clip_text: Some("a\nb".into()),
        };
        assert_eq!(env.expand("<clip>", Some(&context)), "<clip>");
    }
}
