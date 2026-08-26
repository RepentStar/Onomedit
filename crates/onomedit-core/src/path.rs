use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "lowercase")]
pub enum PathType {
    Full,
    Name,
    #[default]
    Stem,
    Ext,
}

impl PathType {
    pub const ALL: [&'static str; 4] = ["full", "name", "stem", "ext"];
}

impl std::str::FromStr for PathType {
    type Err = PathError;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "full" => Ok(Self::Full),
            "name" => Ok(Self::Name),
            "stem" => Ok(Self::Stem),
            "ext" => Ok(Self::Ext),
            _ => Err(PathError::UnknownType(value.to_owned())),
        }
    }
}

impl std::fmt::Display for PathType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            Self::Full => "full",
            Self::Name => "name",
            Self::Stem => "stem",
            Self::Ext => "ext",
        })
    }
}

#[derive(Debug, Error)]
pub enum PathError {
    #[error("未知路径类型: {0}")]
    UnknownType(String),
    #[error("路径缺少文件名: {0}")]
    MissingName(PathBuf),
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct PathItem {
    full: PathBuf,
    is_dir: bool,
}

impl PathItem {
    pub fn new(path: impl Into<PathBuf>) -> Self {
        let full = path.into();
        let is_dir = full.is_dir();
        Self { full, is_dir }
    }

    pub fn with_directory_hint(path: impl Into<PathBuf>, is_dir: bool) -> Self {
        Self {
            full: path.into(),
            is_dir,
        }
    }

    pub fn full(&self) -> &Path {
        &self.full
    }

    pub fn directory(&self) -> &Path {
        self.full.parent().unwrap_or_else(|| Path::new(""))
    }

    pub fn name(&self) -> String {
        self.full
            .file_name()
            .map(|v| v.to_string_lossy().into_owned())
            .unwrap_or_default()
    }

    pub fn stem(&self) -> String {
        if self.is_dir {
            return self.name();
        }
        self.full
            .file_stem()
            .map(|v| v.to_string_lossy().into_owned())
            .unwrap_or_default()
    }

    pub fn ext(&self) -> String {
        if self.is_dir {
            return String::new();
        }
        self.full
            .extension()
            .map(|v| format!(".{}", v.to_string_lossy()))
            .unwrap_or_default()
    }

    pub fn field(&self, path_type: PathType) -> String {
        match path_type {
            PathType::Full => self.full.to_string_lossy().into_owned(),
            PathType::Name => self.name(),
            PathType::Stem => self.stem(),
            PathType::Ext => self.ext(),
        }
    }

    pub fn with_field(&self, path_type: PathType, value: &str) -> PathBuf {
        match path_type {
            PathType::Full => PathBuf::from(value),
            PathType::Name => self.directory().join(value),
            PathType::Stem => self.directory().join(format!("{}{}", value, self.ext())),
            PathType::Ext => self.directory().join(format!("{}{}", self.stem(), value)),
        }
    }

    pub fn serialize(&self, path_type: PathType) -> String {
        self.field(path_type)
    }
}

impl<T: Into<PathBuf>> From<T> for PathItem {
    fn from(value: T) -> Self {
        Self::new(value)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn four_segments_and_dotfiles() {
        let item = PathItem::new("C:/x/y/report.tar.gz");
        assert_eq!(item.name(), "report.tar.gz");
        assert_eq!(item.stem(), "report.tar");
        assert_eq!(item.ext(), ".gz");
        let hidden = PathItem::new("/home/u/.gitignore");
        assert_eq!(hidden.stem(), ".gitignore");
        assert_eq!(hidden.ext(), "");
    }

    #[test]
    fn fields_round_trip() {
        let item = PathItem::new("/d/report.tar.gz");
        assert_eq!(
            item.with_field(PathType::Stem, "notes"),
            PathBuf::from("/d/notes.gz")
        );
        assert_eq!(
            item.with_field(PathType::Name, "full.txt"),
            PathBuf::from("/d/full.txt")
        );
        assert_eq!(
            item.with_field(PathType::Ext, ".md"),
            PathBuf::from("/d/report.tar.md")
        );
    }

    #[test]
    fn dotted_directory_has_no_extension() {
        let directory = tempfile::tempdir().unwrap();
        let dotted = directory.path().join("0ikj2.56234.345");
        std::fs::create_dir(&dotted).unwrap();
        let item = PathItem::new(&dotted);
        assert_eq!(item.stem(), "0ikj2.56234.345");
        assert_eq!(item.ext(), "");
        assert_eq!(
            item.with_field(PathType::Stem, "renamed.folder"),
            directory.path().join("renamed.folder")
        );
    }
}
