use std::collections::{HashMap, HashSet};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use thiserror::Error;

use crate::collection::{self, path_key};
use crate::config::Config;
use crate::diff::{diff_text, levenshtein};
use crate::edit_file::{EditFile, EditFileError};
use crate::journal::{RenameLogger, parse_line};
use crate::path::PathItem;
use crate::rules;
use crate::safe_name::{sanitize_name, unique_path};
use crate::template::{EnvContext, EnvVars};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RenamePair {
    pub old: PathBuf,
    pub requested_new: PathBuf,
}

impl RenamePair {
    pub fn new(old: impl Into<PathBuf>, new: impl Into<PathBuf>) -> Self {
        Self {
            old: old.into(),
            requested_new: new.into(),
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct RenameResult {
    pub success: Vec<(PathBuf, PathBuf)>,
    pub failed: Vec<(PathBuf, PathBuf, String)>,
    pub skipped: Vec<PathBuf>,
}

impl RenameResult {
    pub fn total(&self) -> usize {
        self.success.len() + self.failed.len() + self.skipped.len()
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DuplicateTargetError {
    pub conflicts: Vec<(PathBuf, Vec<PathBuf>)>,
}

impl DuplicateTargetError {
    pub fn summary(&self) -> String {
        let involved: usize = self
            .conflicts
            .iter()
            .map(|(_, sources)| sources.len())
            .sum();
        format!(
            "检测到目标重名，已中止（未执行任何重命名）: {} 组目标、涉及 {involved} 个文件",
            self.conflicts.len()
        )
    }
}

impl std::fmt::Display for DuplicateTargetError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        writeln!(formatter, "检测到目标重名，已中止（未执行任何重命名）:")?;
        for (index, (target, sources)) in self.conflicts.iter().enumerate() {
            writeln!(formatter, "  目标: {}", target.display())?;
            for (source_index, source) in sources.iter().enumerate() {
                let final_line =
                    index + 1 == self.conflicts.len() && source_index + 1 == sources.len();
                if final_line {
                    write!(formatter, "    <- {}", source.display())?;
                } else {
                    writeln!(formatter, "    <- {}", source.display())?;
                }
            }
        }
        Ok(())
    }
}

impl std::error::Error for DuplicateTargetError {}

#[derive(Debug, Error)]
pub enum PipelineError {
    #[error("没有可处理的文件（路径不存在或剪贴板为空）")]
    NoFiles,
    #[error("应用排除规则后没有可处理的文件")]
    NoFilesAfterExclude,
    #[error(transparent)]
    EditFile(#[from] EditFileError),
    #[error(transparent)]
    DuplicateTarget(#[from] DuplicateTargetError),
    #[error(transparent)]
    Io(#[from] io::Error),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PreviewRow {
    pub old: PathBuf,
    pub new: PathBuf,
    pub diff: String,
    pub distance: usize,
}

#[derive(Debug, Clone, Default)]
pub struct PipelineOutcome {
    pub result: RenameResult,
    pub pairs: Vec<RenamePair>,
    pub preview: Option<Vec<PreviewRow>>,
    pub dry_run: bool,
    pub temp_path: PathBuf,
}

pub struct PlanSession {
    pub items: Vec<PathItem>,
    edit_file: EditFile,
}

impl PlanSession {
    pub fn edit_path(&self) -> &Path {
        self.edit_file.path()
    }

    pub fn signature(&self) -> Result<crate::edit_file::Signature, EditFileError> {
        self.edit_file.signature()
    }
}

pub struct RenamePipeline {
    pub config: Config,
    pub clipboard_text: Option<String>,
}

impl RenamePipeline {
    pub fn new(config: Config) -> Self {
        Self {
            config,
            clipboard_text: None,
        }
    }

    pub fn with_clipboard_text(mut self, clipboard_text: Option<String>) -> Self {
        self.clipboard_text = clipboard_text;
        self
    }

    pub fn prepare(&self, raw_paths: &[String]) -> Result<PlanSession, PipelineError> {
        let paths = collection::collect_paths(raw_paths);
        if paths.is_empty() {
            return Err(PipelineError::NoFiles);
        }
        let mut items: Vec<PathItem> = paths.into_iter().map(PathItem::new).collect();
        if self.config.expand_subdirs {
            items = collection::expand_subdirs(items, self.config.subdirs_depth);
        }
        items = collection::apply_excludes(items, &self.config.exclude);
        items = collection::dedupe_items(items);
        items = collection::sort_items(items, &self.config.sort_by, self.config.sort_reverse);
        if items.is_empty() {
            return Err(PipelineError::NoFilesAfterExclude);
        }
        let temp_dir = (!self.config.temp_dir.is_empty()).then(|| Path::new(&self.config.temp_dir));
        let edit_file = EditFile::create(&items, self.config.path_type, temp_dir)?;
        Ok(PlanSession { items, edit_file })
    }

    pub fn finish_plan(&self, session: &PlanSession) -> Result<Vec<RenamePair>, PipelineError> {
        let lines = session.edit_file.read_lines(session.items.len())?;
        let edited: Vec<PathBuf> = session
            .items
            .iter()
            .zip(lines)
            .map(|(item, line)| item.with_field(self.config.path_type, &line))
            .collect();
        Ok(self.plan(&session.items, &edited))
    }

    pub fn plan(&self, items: &[PathItem], edited: &[PathBuf]) -> Vec<RenamePair> {
        let mut environment = EnvVars::default();
        items
            .iter()
            .zip(edited)
            .map(|(item, edited)| {
                let mut full = edited.clone();
                if self.config.apply_rules {
                    if self.config.enable_auto_rules {
                        for rule in &self.config.auto_rules {
                            let current = PathItem::new(&full);
                            let value = rules::apply(&current.field(rule.scope), rule);
                            full = current.with_field(rule.scope, &value);
                        }
                    }
                    if self.config.enable_envvars {
                        let current = PathItem::new(&full);
                        let context = EnvContext {
                            file: item.full().to_string_lossy().into_owned(),
                            clip_text: self.clipboard_text.clone(),
                        };
                        let name = environment.expand(&current.name(), Some(&context));
                        full = current.directory().join(name);
                    }
                }
                if self.config.safety.sanitize {
                    let current = PathItem::new(&full);
                    full = current
                        .directory()
                        .join(sanitize_name(&current.name(), "_"));
                }
                RenamePair::new(item.full(), full)
            })
            .collect()
    }

    pub fn run_direct(
        &self,
        raw_paths: &[String],
        dry_run: bool,
        logger: Option<RenameLogger>,
    ) -> Result<PipelineOutcome, PipelineError> {
        let session = self.prepare(raw_paths)?;
        let temp_path = session.edit_path().to_owned();
        let pairs = self.finish_plan(&session)?;
        if dry_run {
            let preview = (self.config.preview.diff || self.config.preview.distance)
                .then(|| preview_rows(&pairs, &self.config));
            return Ok(PipelineOutcome {
                pairs,
                preview,
                dry_run: true,
                temp_path,
                ..PipelineOutcome::default()
            });
        }
        if let Some(log) = &logger {
            log.begin_session();
        }
        let result = Renamer::new(logger).run(&pairs)?;
        Ok(PipelineOutcome {
            result,
            pairs,
            temp_path,
            ..PipelineOutcome::default()
        })
    }
}

pub fn preview_rows(pairs: &[RenamePair], config: &Config) -> Vec<PreviewRow> {
    pairs
        .iter()
        .map(|pair| {
            let old = pair.old.to_string_lossy();
            let new = pair.requested_new.to_string_lossy();
            PreviewRow {
                old: pair.old.clone(),
                new: pair.requested_new.clone(),
                diff: if config.preview.diff {
                    diff_text(&old, &new)
                } else {
                    String::new()
                },
                distance: if config.preview.distance {
                    levenshtein(&old, &new)
                } else {
                    0
                },
            }
        })
        .collect()
}

pub fn find_duplicate_targets(pairs: &[RenamePair]) -> Vec<(PathBuf, Vec<PathBuf>)> {
    let mut groups: Vec<(PathBuf, Vec<PathBuf>)> = Vec::new();
    let mut indexes = HashMap::new();
    for pair in pairs {
        if pair.old == pair.requested_new {
            continue;
        }
        let key = path_key(&pair.requested_new);
        let index = *indexes.entry(key).or_insert_with(|| {
            groups.push((pair.requested_new.clone(), Vec::new()));
            groups.len() - 1
        });
        groups[index].1.push(pair.old.clone());
    }
    groups.retain(|(_, sources)| sources.len() > 1);
    groups
}

pub struct Renamer {
    logger: Option<RenameLogger>,
    temp_sequence: usize,
}

impl Renamer {
    pub fn new(logger: Option<RenameLogger>) -> Self {
        Self {
            logger,
            temp_sequence: 0,
        }
    }

    pub fn run(mut self, pairs: &[RenamePair]) -> Result<RenameResult, DuplicateTargetError> {
        let conflicts = find_duplicate_targets(pairs);
        if !conflicts.is_empty() {
            return Err(DuplicateTargetError { conflicts });
        }

        let mut result = RenameResult::default();
        let mut pending: HashMap<String, RenamePair> = pairs
            .iter()
            .cloned()
            .map(|pair| (path_key(&pair.old), pair))
            .collect();
        let mut removed = HashSet::new();
        let mut moved: Vec<(PathBuf, PathBuf, PathBuf)> = Vec::new();

        for pair in pairs {
            let old_key = path_key(&pair.old);
            if removed.contains(&old_key) {
                continue;
            }
            if pair.old == pair.requested_new {
                pending.remove(&old_key);
                result.skipped.push(pair.old.clone());
                continue;
            }
            let mut actual_new = pair.requested_new.clone();
            let operation = (|| -> io::Result<()> {
                let new_key = path_key(&actual_new);
                if actual_new.exists() && pending.contains_key(&new_key) {
                    let displaced = pending.remove(&new_key).expect("checked pending key");
                    let temporary = self.temp_name(&actual_new);
                    rename_ensure_parent(&actual_new, &temporary)?;
                    removed.insert(new_key);
                    moved.push((temporary, displaced.old, displaced.requested_new));
                }
                if actual_new.exists() {
                    actual_new = unique_path(&actual_new);
                }
                rename_ensure_parent(&pair.old, &actual_new)
            })();
            pending.remove(&old_key);
            match operation {
                Ok(()) => {
                    result.success.push((pair.old.clone(), actual_new.clone()));
                    self.record(&pair.old, &actual_new);
                }
                Err(error) => {
                    result
                        .failed
                        .push((pair.old.clone(), actual_new.clone(), error.to_string()));
                    self.record_error(&format!(
                        "{} -> {}: {error}",
                        pair.old.display(),
                        actual_new.display()
                    ));
                }
            }
        }

        for (temporary, old, mut target) in moved {
            if target.exists() {
                target = unique_path(&target);
            }
            let operation = rename_ensure_parent(&temporary, &target);
            match operation {
                Ok(()) => {
                    result.success.push((old.clone(), target.clone()));
                    self.record(&old, &target);
                }
                Err(error) => {
                    result
                        .failed
                        .push((old.clone(), target.clone(), error.to_string()));
                    self.record_error(&format!(
                        "{} -> {}: {error}",
                        old.display(),
                        target.display()
                    ));
                }
            }
        }
        Ok(result)
    }

    fn temp_name(&mut self, target: &Path) -> PathBuf {
        let parent = target.parent().unwrap_or_else(|| Path::new(""));
        let stem = target
            .file_stem()
            .map(|v| v.to_string_lossy())
            .unwrap_or_default();
        let extension = target
            .extension()
            .map(|v| format!(".{}", v.to_string_lossy()))
            .unwrap_or_default();
        loop {
            self.temp_sequence += 1;
            let candidate = parent.join(format!(
                ".__onomedit_tmp_{}_{}_{}{}",
                std::process::id(),
                self.temp_sequence,
                stem,
                extension
            ));
            if !candidate.exists() {
                return candidate;
            }
        }
    }

    fn record(&self, old: &Path, new: &Path) {
        if let Some(logger) = &self.logger {
            logger.record(old, new);
        }
    }

    fn record_error(&self, message: &str) {
        if let Some(logger) = &self.logger {
            logger.record_error(message);
        }
    }
}

pub fn rename_ensure_parent(old: &Path, new: &Path) -> io::Result<()> {
    match fs::rename(old, new) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound && old.exists() => {
            let Some(parent) = new.parent() else {
                return Err(error);
            };
            if parent.as_os_str().is_empty() {
                return Err(error);
            }
            fs::create_dir_all(parent)?;
            fs::rename(old, new)
        }
        Err(error) => Err(error),
    }
}

pub fn restore(
    logger: &RenameLogger,
    all_history: bool,
    partial_lines: Option<&[String]>,
) -> Result<RenameResult, PipelineError> {
    let pairs: Vec<(PathBuf, PathBuf)> = if let Some(lines) = partial_lines {
        lines
            .iter()
            .map(|line| parse_line(line))
            .collect::<Result<_, _>>()?
    } else if all_history {
        logger.read_history()
    } else {
        logger.read_last()
    };
    let reverse: Vec<RenamePair> = pairs
        .into_iter()
        .rev()
        .map(|(old, new)| RenamePair::new(new, old))
        .collect();
    Ok(Renamer::new(Some(logger.clone())).run(&reverse)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pair(old: &Path, new: &Path) -> RenamePair {
        RenamePair::new(old, new)
    }

    #[test]
    fn duplicate_target_aborts_before_changes() {
        let dir = tempfile::tempdir().unwrap();
        let a = dir.path().join("a.txt");
        let b = dir.path().join("b.txt");
        let same = dir.path().join("same.txt");
        fs::write(&a, "a").unwrap();
        fs::write(&b, "b").unwrap();
        let error = Renamer::new(None)
            .run(&[pair(&a, &same), pair(&b, &same)])
            .unwrap_err();
        assert_eq!(
            error.summary(),
            "检测到目标重名，已中止（未执行任何重命名）: 1 组目标、涉及 2 个文件"
        );
        assert!(a.exists() && b.exists() && !same.exists());
    }

    #[test]
    fn resolves_swap_cycle_without_temp_names_in_log() {
        let dir = tempfile::tempdir().unwrap();
        let a = dir.path().join("a.txt");
        let b = dir.path().join("b.txt");
        fs::write(&a, "AAA").unwrap();
        fs::write(&b, "BBB").unwrap();
        let logger = RenameLogger::new(dir.path().join("log"));
        logger.begin_session();
        let result = Renamer::new(Some(logger.clone()))
            .run(&[pair(&a, &b), pair(&b, &a)])
            .unwrap();
        assert_eq!(result.success.len(), 2);
        assert_eq!(fs::read_to_string(&a).unwrap(), "BBB");
        assert_eq!(fs::read_to_string(&b).unwrap(), "AAA");
        assert!(
            !fs::read_to_string(logger.last_path)
                .unwrap()
                .contains("__onomedit_tmp_")
        );
    }

    #[test]
    fn numbers_real_conflicts_and_creates_parent() {
        let dir = tempfile::tempdir().unwrap();
        let a = dir.path().join("a.txt");
        let b = dir.path().join("b.txt");
        fs::write(&a, "a").unwrap();
        fs::write(&b, "existing").unwrap();
        let result = Renamer::new(None).run(&[pair(&a, &b)]).unwrap();
        assert_eq!(result.success[0].1.file_name().unwrap(), "b (1).txt");
        let source = dir.path().join("source.txt");
        let target = dir.path().join("new/nested/target.txt");
        fs::write(&source, "x").unwrap();
        Renamer::new(None).run(&[pair(&source, &target)]).unwrap();
        assert!(target.exists());
    }
}
