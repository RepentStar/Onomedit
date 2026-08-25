use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use tempfile::{Builder, TempPath};
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
    // TempPath 保留离开会话时的自动清理，但不像 NamedTempFile 那样持续持有
    // Windows 文件句柄。现代 Notepad/VS Code 可据此用原子替换完成 Ctrl+S。
    path: TempPath,
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
        Ok(Self {
            path: file.into_temp_path(),
        })
    }

    pub fn path(&self) -> &Path {
        &self.path
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
        self.path
            .keep()
            .unwrap_or_else(|error| error.path.to_owned())
    }
}

pub fn signature(path: &Path) -> io::Result<Signature> {
    let metadata = fs::metadata(path)?;
    Ok(Signature {
        modified: metadata.modified()?,
        size: metadata.len(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn editor_can_replace_the_file_while_session_is_alive() {
        let directory = tempfile::tempdir().unwrap();
        let item_path = directory.path().join("source.txt");
        fs::write(&item_path, "source").unwrap();
        let session = EditFile::create(&[PathItem::new(item_path)], PathType::Stem, None).unwrap();
        let edit_path = session.path().to_owned();

        // 现代编辑器常先写旁路文件，再删除/替换原文件。Windows 上若仍持有
        // NamedTempFile 句柄，remove_file 会报共享冲突并触发编辑器“另存为”。
        let replacement = edit_path.with_extension("replacement");
        fs::write(&replacement, "renamed\n").unwrap();
        fs::remove_file(&edit_path).unwrap();
        fs::rename(replacement, &edit_path).unwrap();

        assert_eq!(session.read_lines(1).unwrap(), ["renamed"]);
        drop(session);
        assert!(!edit_path.exists());
    }
}
