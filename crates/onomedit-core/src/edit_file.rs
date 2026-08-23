use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use tempfile::{Builder, NamedTempFile};
use thiserror::Error;

use crate::path::{PathItem, PathType};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Signature {
    pub modified: SystemTime,
    pub size: u64,
}

#[derive(Debug, Error)]
pub enum EditFileError {
    #[error(transparent)]
    Io(#[from] io::Error),
    #[error("临时文件行数 {actual} 与文件数 {expected} 不一致，已中止（防止错位改名）")]
    LineCount { actual: usize, expected: usize },
}

pub struct EditFile {
    file: NamedTempFile,
}

impl EditFile {
    pub fn create(
        items: &[PathItem],
        path_type: PathType,
        temp_dir: Option<&Path>,
    ) -> Result<Self, EditFileError> {
        let mut builder = Builder::new();
        builder.prefix("onomedit_").suffix(".txt");
        let mut file = match temp_dir {
            Some(directory) => builder.tempfile_in(directory)?,
            None => builder.tempfile()?,
        };
        for item in items {
            file.write_all(item.serialize(path_type).as_bytes())?;
            file.write_all(b"\n")?;
        }
        file.flush()?;
        Ok(Self { file })
    }

    pub fn path(&self) -> &Path {
        self.file.path()
    }

    pub fn signature(&self) -> Result<Signature, EditFileError> {
        signature(self.path()).map_err(Into::into)
    }

    pub fn read_lines(&self, expected: usize) -> Result<Vec<String>, EditFileError> {
        let contents = fs::read_to_string(self.path())?;
        let lines: Vec<String> = contents.lines().map(str::to_owned).collect();
        if lines.len() != expected {
            return Err(EditFileError::LineCount {
                actual: lines.len(),
                expected,
            });
        }
        Ok(lines)
    }

    pub fn into_path(self) -> PathBuf {
        self.file.path().to_owned()
    }
}

pub fn signature(path: &Path) -> io::Result<Signature> {
    let metadata = fs::metadata(path)?;
    Ok(Signature {
        modified: metadata.modified()?,
        size: metadata.len(),
    })
}
