use std::path::{Path, PathBuf};

const RESERVED: &[&str] = &[
    "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8",
    "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
];

pub fn sanitize_name(name: &str, replacement: &str) -> String {
    if name.is_empty() {
        return String::new();
    }
    let mut cleaned = String::with_capacity(name.len());
    for ch in name.chars() {
        if ch <= '\u{1f}' || matches!(ch, '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*') {
            cleaned.push_str(replacement);
        } else {
            cleaned.push(ch);
        }
    }
    let cleaned = cleaned.trim().trim_end_matches(['.', ' ']);
    if cleaned.is_empty() {
        return replacement.to_owned();
    }
    let stem = cleaned.split('.').next().unwrap_or(cleaned);
    if RESERVED.iter().any(|v| stem.eq_ignore_ascii_case(v)) {
        format!("_{cleaned}")
    } else {
        cleaned.to_owned()
    }
}

pub fn unique_path(target: &Path) -> PathBuf {
    if !target.exists() {
        return target.to_owned();
    }
    let parent = target.parent().unwrap_or_else(|| Path::new(""));
    let stem = target
        .file_stem()
        .map(|v| v.to_string_lossy().into_owned())
        .unwrap_or_default();
    let suffix = target
        .extension()
        .map(|v| format!(".{}", v.to_string_lossy()))
        .unwrap_or_default();
    for n in 1_u64.. {
        let candidate = parent.join(format!("{stem} ({n}){suffix}"));
        if !candidate.exists() {
            return candidate;
        }
    }
    unreachable!()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sanitizes_windows_names_everywhere() {
        assert_eq!(
            sanitize_name("a<b>:c\"d/e\\f|g?h*i.txt", "_"),
            "a_b__c_d_e_f_g_h_i.txt"
        );
        assert_eq!(sanitize_name("  name... ", "_"), "name");
        assert_eq!(sanitize_name("CON.txt", "_"), "_CON.txt");
        assert_eq!(sanitize_name("...", "_"), "_");
        assert_eq!(sanitize_name("", "_"), "");
    }

    #[test]
    fn numbers_conflicts() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("x.tar.gz"), "x").unwrap();
        assert_eq!(
            unique_path(&dir.path().join("x.tar.gz"))
                .file_name()
                .unwrap(),
            "x.tar (1).gz"
        );
    }
}
