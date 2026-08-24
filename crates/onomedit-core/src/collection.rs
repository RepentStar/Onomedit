use std::cmp::Ordering;
use std::collections::HashSet;
use std::fs;
use std::io::{self, BufRead};
use std::path::{Component, Path, PathBuf};

use glob::{MatchOptions, glob_with};

use crate::config::ExcludeOptions;
use crate::path::PathItem;

pub const SORT_BY_CHOICES: [&str; 6] = ["default", "name", "path", "mtime", "ctime", "size"];

pub fn read_stream_paths(reader: impl BufRead) -> io::Result<Vec<String>> {
    reader
        .lines()
        .map(|line| line.map(|value| value.trim().to_owned()))
        .filter(|line| line.as_ref().is_ok_and(|value| !value.is_empty()))
        .collect()
}

pub fn collect_paths(raw_paths: &[String]) -> Vec<PathBuf> {
    let options = MatchOptions {
        case_sensitive: !cfg!(windows),
        require_literal_separator: false,
        require_literal_leading_dot: true,
    };
    let mut output = Vec::new();
    for raw in raw_paths {
        if has_magic(raw) {
            if let Ok(matches) = glob_with(raw, options) {
                output.extend(matches.filter_map(Result::ok).filter(|path| path.exists()));
            }
        } else {
            let path = PathBuf::from(raw);
            if path.exists() {
                output.push(path);
            }
        }
    }
    output
}

fn has_magic(path: &str) -> bool {
    path.contains(['*', '?', '['])
}

pub fn expand_subdirs(items: Vec<PathItem>, depth: i32) -> Vec<PathItem> {
    if depth <= 0 {
        return items;
    }
    let mut output = Vec::new();
    for item in items {
        if item.full().is_dir() {
            expand_directory(item.full(), 1, depth, &mut output);
        } else {
            output.push(item);
        }
    }
    output
}

fn expand_directory(directory: &Path, level: i32, depth: i32, output: &mut Vec<PathItem>) {
    if level > depth {
        return;
    }
    let Ok(entries) = fs::read_dir(directory) else {
        return;
    };
    let mut directories = Vec::new();
    let mut files = Vec::new();
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() && !path.is_symlink() {
            directories.push(path);
        } else {
            files.push(path);
        }
    }
    output.extend(directories.iter().cloned().map(PathItem::new));
    output.extend(files.into_iter().map(PathItem::new));
    for child in directories {
        expand_directory(&child, level + 1, depth, output);
    }
}

pub fn dedupe_items(items: Vec<PathItem>) -> Vec<PathItem> {
    let mut seen = HashSet::new();
    items
        .into_iter()
        .filter(|item| seen.insert(path_key(item.full())))
        .collect()
}

pub fn path_key(path: &Path) -> String {
    let absolute = if path.is_absolute() {
        path.to_owned()
    } else {
        std::env::current_dir().unwrap_or_default().join(path)
    };
    let mut normalized = PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                normalized.pop();
            }
            other => normalized.push(other.as_os_str()),
        }
    }
    let key = normalized.to_string_lossy().into_owned();
    if cfg!(windows) {
        key.to_lowercase()
    } else {
        key
    }
}

pub fn apply_excludes(items: Vec<PathItem>, exclude: &ExcludeOptions) -> Vec<PathItem> {
    items
        .into_iter()
        .filter(|item| {
            let path = item.full();
            !(exclude.files && path.is_file()
                || exclude.dirs && path.is_dir()
                || exclude.symlinks && path.is_symlink()
                || exclude.readonly && is_readonly(path)
                || exclude.hidden && is_hidden(path)
                || exclude.system && is_system(path))
        })
        .collect()
}

pub fn sort_items(mut items: Vec<PathItem>, sort_by: &str, reverse: bool) -> Vec<PathItem> {
    if sort_by == "default" || !SORT_BY_CHOICES.contains(&sort_by) {
        if reverse {
            items.reverse();
        }
        return items;
    }
    items.sort_by(|left, right| compare(left, right, sort_by));
    if reverse {
        items.reverse();
    }
    items
}

fn compare(left: &PathItem, right: &PathItem, sort_by: &str) -> Ordering {
    match sort_by {
        "name" => string_key(&left.name()).cmp(&string_key(&right.name())),
        "path" => path_key(left.full()).cmp(&path_key(right.full())),
        "mtime" => metadata_time(left.full(), true).cmp(&metadata_time(right.full(), true)),
        "ctime" => metadata_time(left.full(), false).cmp(&metadata_time(right.full(), false)),
        "size" => metadata_size(left.full()).cmp(&metadata_size(right.full())),
        _ => Ordering::Equal,
    }
}

fn string_key(value: &str) -> String {
    if cfg!(windows) {
        value.to_lowercase()
    } else {
        value.into()
    }
}

fn metadata_time(path: &Path, modified: bool) -> std::time::SystemTime {
    fs::metadata(path)
        .ok()
        .and_then(|metadata| {
            if modified {
                metadata.modified().ok()
            } else {
                metadata.created().ok()
            }
        })
        .unwrap_or(std::time::UNIX_EPOCH)
}

fn metadata_size(path: &Path) -> u64 {
    fs::metadata(path)
        .map(|metadata| metadata.len())
        .unwrap_or(0)
}

pub fn display_base(paths: &[String]) -> PathBuf {
    if paths.is_empty() {
        return PathBuf::new();
    }
    let absolute: Vec<PathBuf> = paths
        .iter()
        .map(|path| {
            let path = PathBuf::from(path);
            if path.is_absolute() {
                path
            } else {
                std::env::current_dir().unwrap_or_default().join(path)
            }
        })
        .collect();
    let mut common: Vec<_> = absolute[0].components().collect();
    for path in &absolute[1..] {
        let components: Vec<_> = path.components().collect();
        let length = common
            .iter()
            .zip(&components)
            .take_while(|(a, b)| a == b)
            .count();
        common.truncate(length);
    }
    let mut base: PathBuf = common
        .iter()
        .map(|component| component.as_os_str())
        .collect();
    if paths.len() == 1 {
        base.pop();
    }
    base
}

#[cfg(windows)]
fn attributes(path: &Path) -> u32 {
    use std::os::windows::fs::MetadataExt;
    fs::metadata(path)
        .map(|metadata| metadata.file_attributes())
        .unwrap_or(0)
}

fn is_readonly(path: &Path) -> bool {
    fs::metadata(path).is_ok_and(|metadata| metadata.permissions().readonly())
}

fn is_hidden(path: &Path) -> bool {
    #[cfg(windows)]
    return attributes(path) & 0x2 != 0;
    #[cfg(not(windows))]
    return path
        .file_name()
        .is_some_and(|name| name.to_string_lossy().starts_with('.'));
}

fn is_system(path: &Path) -> bool {
    #[cfg(windows)]
    return attributes(path) & 0x4 != 0;
    #[cfg(not(windows))]
    return false;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn expands_with_depth_and_deduplicates() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(dir.path().join("a.txt"), "a").unwrap();
        fs::create_dir(dir.path().join("sub")).unwrap();
        fs::write(dir.path().join("sub").join("b.txt"), "b").unwrap();
        let depth_one = expand_subdirs(vec![PathItem::new(dir.path())], 1);
        assert!(depth_one.iter().any(|item| item.name() == "a.txt"));
        assert!(depth_one.iter().any(|item| item.name() == "sub"));
        assert!(!depth_one.iter().any(|item| item.name() == "b.txt"));
        let duplicate = PathItem::new(dir.path().join("a.txt"));
        assert_eq!(dedupe_items(vec![duplicate.clone(), duplicate]).len(), 1);
    }
}
