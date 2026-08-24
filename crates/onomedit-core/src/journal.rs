use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};

pub const SEPARATOR: &str = "<-->";
pub const ROTATE_BYTES: u64 = 1024 * 1024;
pub const ROTATE_KEEP: usize = 5;

#[derive(Debug, Clone)]
pub struct RenameLogger {
    pub log_dir: PathBuf,
    pub history_path: PathBuf,
    pub last_path: PathBuf,
    pub error_path: PathBuf,
}

impl RenameLogger {
    pub fn new(log_dir: impl Into<PathBuf>) -> Self {
        let log_dir = log_dir.into();
        Self {
            history_path: log_dir.join("history.log"),
            last_path: log_dir.join("last.log"),
            error_path: log_dir.join("error.log"),
            log_dir,
        }
    }

    pub fn begin_session(&self) {
        let _ = fs::create_dir_all(&self.log_dir);
        let _ = fs::write(&self.last_path, []);
    }

    pub fn record(&self, old: &Path, new: &Path) {
        let line = format!(
            "{}{SEPARATOR}{}\n",
            old.to_string_lossy(),
            new.to_string_lossy()
        );
        self.append_history(&line);
        append(&self.last_path, &line);
    }

    pub fn record_error(&self, message: &str) {
        append(
            &self.error_path,
            &format!("{}\n", message.trim_end_matches('\n')),
        );
    }

    pub fn read_last(&self) -> Vec<(PathBuf, PathBuf)> {
        read_pairs(&self.last_path)
    }

    pub fn read_history(&self) -> Vec<(PathBuf, PathBuf)> {
        read_pairs(&self.history_path)
    }

    fn append_history(&self, line: &str) {
        let _ = fs::create_dir_all(&self.log_dir);
        if fs::metadata(&self.history_path).is_ok_and(|metadata| metadata.len() > ROTATE_BYTES) {
            self.rotate();
        }
        append(&self.history_path, line);
    }

    fn rotate(&self) {
        for index in (1..ROTATE_KEEP).rev() {
            let source = self.log_dir.join(format!("history.{index}.log"));
            let target = self.log_dir.join(format!("history.{}.log", index + 1));
            if source.exists() {
                let _ = fs::remove_file(&target);
                let _ = fs::rename(source, target);
            }
        }
        let _ = fs::rename(&self.history_path, self.log_dir.join("history.1.log"));
    }
}

fn append(path: &Path, text: &str) {
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
        if cfg!(windows) {
            let text = text.replace('\n', "\r\n");
            let _ = file.write_all(text.as_bytes());
        } else {
            let _ = file.write_all(text.as_bytes());
        }
    }
}

pub fn parse_line(line: &str) -> io::Result<(PathBuf, PathBuf)> {
    line.trim_end_matches('\n')
        .rsplit_once(SEPARATOR)
        .map(|(old, new)| (PathBuf::from(old), PathBuf::from(new)))
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                format!("无法解析日志行: {line:?}"),
            )
        })
}

fn read_pairs(path: &Path) -> Vec<(PathBuf, PathBuf)> {
    let Ok(contents) = fs::read_to_string(path) else {
        return Vec::new();
    };
    let contents = contents.replace("\r\n", "\n").replace('\r', "\n");
    contents
        .split('\n')
        .filter(|line| !line.is_empty())
        .filter_map(|line| parse_line(line).ok())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn journal_round_trip_uses_last_separator() {
        let dir = tempfile::tempdir().unwrap();
        let log = RenameLogger::new(dir.path());
        log.begin_session();
        log.record(Path::new("旧<-->.txt"), Path::new("新.txt"));
        assert_eq!(
            log.read_last(),
            vec![(PathBuf::from("旧<-->.txt"), PathBuf::from("新.txt"))]
        );
        assert_eq!(
            parse_line("a<-->b<-->c").unwrap(),
            (PathBuf::from("a<-->b"), PathBuf::from("c"))
        );
    }
}
