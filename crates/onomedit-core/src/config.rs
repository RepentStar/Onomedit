use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;

use crate::path::PathType;
use crate::rules::Rule;

pub const CONFIG_VERSION: u32 = 1;
pub const DEFAULT_LANGUAGE: &str = "zh-CN";
pub const SUPPORTED_LANGUAGES: [&str; 2] = ["zh-CN", "en-US"];

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct ExcludeOptions {
    pub files: bool,
    pub dirs: bool,
    pub symlinks: bool,
    pub readonly: bool,
    pub hidden: bool,
    pub system: bool,
}

impl Default for ExcludeOptions {
    fn default() -> Self {
        Self {
            files: false,
            dirs: false,
            symlinks: true,
            readonly: false,
            hidden: true,
            system: true,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct PreviewOptions {
    pub diff: bool,
    pub distance: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct SafetyOptions {
    pub sanitize: bool,
}

impl Default for SafetyOptions {
    fn default() -> Self {
        Self { sanitize: true }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Config {
    pub version: u32,
    pub language: String,
    pub editor: String,
    pub editor_alt: String,
    pub editor_timeout: f64,
    pub multi_tab: bool,
    pub open_editor: bool,
    pub apply_rules: bool,
    pub path_type: PathType,
    pub sort_by: String,
    pub sort_reverse: bool,
    pub enable_envvars: bool,
    pub enable_auto_rules: bool,
    pub expand_subdirs: bool,
    pub subdirs_depth: i32,
    pub exclude: ExcludeOptions,
    pub preview: PreviewOptions,
    pub safety: SafetyOptions,
    pub exit_after: bool,
    pub skip_confirmation: bool,
    pub shell_props: Vec<Value>,
    pub auto_rules: Vec<Rule>,
    pub temp_dir: String,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            version: CONFIG_VERSION,
            language: DEFAULT_LANGUAGE.into(),
            editor: String::new(),
            editor_alt: String::new(),
            editor_timeout: 120.0,
            multi_tab: false,
            open_editor: true,
            apply_rules: true,
            path_type: PathType::Stem,
            sort_by: "default".into(),
            sort_reverse: false,
            enable_envvars: true,
            enable_auto_rules: true,
            expand_subdirs: true,
            subdirs_depth: 10,
            exclude: ExcludeOptions::default(),
            preview: PreviewOptions::default(),
            safety: SafetyOptions::default(),
            exit_after: true,
            skip_confirmation: true,
            shell_props: Vec::new(),
            auto_rules: Vec::new(),
            temp_dir: String::new(),
        }
    }
}

#[derive(Debug, Error)]
pub enum ConfigError {
    #[error("配置 I/O 错误: {0}")]
    Io(#[from] std::io::Error),
    #[error("配置 JSON 错误: {0}")]
    Json(#[from] serde_json::Error),
    #[error("未知配置键 '{0}'")]
    UnknownKey(String),
    #[error("{0}")]
    InvalidValue(String),
}

pub fn config_dir() -> PathBuf {
    if cfg!(windows) {
        let base = env::var_os("APPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|| home_dir().join("AppData").join("Roaming"));
        base.join("Onomedit")
    } else if cfg!(target_os = "macos") {
        home_dir()
            .join("Library")
            .join("Application Support")
            .join("Onomedit")
    } else {
        env::var_os("XDG_CONFIG_HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| home_dir().join(".config"))
            .join("Onomedit")
    }
}

fn home_dir() -> PathBuf {
    env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" })
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

pub fn config_path() -> PathBuf {
    config_dir().join("config.json")
}

pub fn log_dir() -> PathBuf {
    config_dir().join("log")
}

pub fn from_value(value: Value) -> Result<Config, ConfigError> {
    if !value.is_object() {
        return Err(ConfigError::InvalidValue(
            "config root is not an object".into(),
        ));
    }
    let mut config: Config = serde_json::from_value(value)?;
    config.language = normalize_language(&config.language).into();
    Ok(config)
}

pub fn load() -> Config {
    load_from(&config_path())
}

pub fn load_from(path: &Path) -> Config {
    if !path.exists() {
        let mut config = Config::default();
        ensure_default_editor(&mut config);
        let _ = save_to(&config, path);
        return config;
    }
    match fs::read_to_string(path)
        .map_err(ConfigError::from)
        .and_then(|raw| serde_json::from_str::<Value>(&raw).map_err(ConfigError::from))
        .and_then(from_value)
    {
        Ok(mut config) => {
            if config.version < CONFIG_VERSION {
                config.version = CONFIG_VERSION;
                let _ = save_to(&config, path);
            }
            if config.editor.trim().is_empty() {
                ensure_default_editor(&mut config);
                let _ = save_to(&config, path);
            }
            config
        }
        Err(_) => {
            let backup = path.with_extension("json.bak");
            let _ = fs::rename(path, backup);
            let mut config = Config::default();
            ensure_default_editor(&mut config);
            let _ = save_to(&config, path);
            config
        }
    }
}

pub fn save(config: &Config) -> Result<(), ConfigError> {
    save_to(config, &config_path())
}

pub fn save_to(config: &Config, path: &Path) -> Result<(), ConfigError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let temporary = path.with_extension("json.tmp");
    let mut json = serde_json::to_string_pretty(config)?;
    json.push('\n');
    fs::write(&temporary, json)?;
    fs::rename(temporary, path)?;
    Ok(())
}

pub fn ensure_default_editor(config: &mut Config) {
    if config.editor.trim().is_empty() {
        config.editor = detect_default_editor();
    }
}

pub fn detect_default_editor() -> String {
    if cfg!(windows) {
        for (command, result) in [("notepad", "notepad"), ("code", "code -w")] {
            if command_exists(command) {
                return result.into();
            }
        }
    } else if cfg!(target_os = "macos") {
        if Path::new("/System/Applications/TextEdit.app").exists() {
            return "open -W -a TextEdit".into();
        }
        for command in ["subl", "code"] {
            if command_exists(command) {
                return format!("{command} -w");
            }
        }
        if command_exists("vim") {
            return "vim".into();
        }
    } else {
        for command in ["nano", "vi", "kate"] {
            if command_exists(command) {
                return command.into();
            }
        }
        return env::var("EDITOR").unwrap_or_default();
    }
    String::new()
}

fn command_exists(command: &str) -> bool {
    let locator = if cfg!(windows) { "where" } else { "which" };
    Command::new(locator)
        .arg(command)
        .output()
        .is_ok_and(|output| output.status.success())
}

pub fn merge_exclude_tags(base: &ExcludeOptions, tags: &[String]) -> ExcludeOptions {
    let mut result = base.clone();
    for tag in tags {
        match tag.as_str() {
            "f" | "file" => result.files = true,
            "d" | "dir" => result.dirs = true,
            "l" | "link" => result.symlinks = true,
            "r" | "readonly" => result.readonly = true,
            "h" | "hidden" => result.hidden = true,
            "s" | "system" => result.system = true,
            _ => {}
        }
    }
    result
}

pub fn set_value(config: &mut Config, dotted: &str, raw: &str) -> Result<String, ConfigError> {
    let mut root = serde_json::to_value(&*config)?;
    let parts: Vec<&str> = dotted.split('.').collect();
    let mut current = &mut root;
    for part in &parts[..parts.len().saturating_sub(1)] {
        current = current
            .get_mut(*part)
            .ok_or_else(|| ConfigError::UnknownKey(dotted.into()))?;
    }
    let key = parts
        .last()
        .ok_or_else(|| ConfigError::UnknownKey(dotted.into()))?;
    let old = current
        .get(*key)
        .ok_or_else(|| ConfigError::UnknownKey(dotted.into()))?;
    let mut value = coerce(raw, old)?;
    if dotted == "language" {
        let normalized = normalize_language(raw);
        let supplied = raw.trim().replace('_', "-").to_ascii_lowercase();
        if !matches!(
            supplied.as_str(),
            "zh" | "zh-cn" | "zh-hans" | "en" | "en-us"
        ) {
            return Err(ConfigError::InvalidValue(format!(
                "unsupported language {raw:?}; choose from: {}",
                SUPPORTED_LANGUAGES.join(", ")
            )));
        }
        value = Value::String(normalized.into());
    }
    current[*key] = value.clone();
    *config = serde_json::from_value(root)?;
    Ok(format!("{dotted} = {}", serde_json::to_string(&value)?))
}

pub fn normalize_language(language: &str) -> &'static str {
    match language
        .trim()
        .replace('_', "-")
        .to_ascii_lowercase()
        .as_str()
    {
        "en" | "en-us" => "en-US",
        "zh" | "zh-cn" | "zh-hans" => "zh-CN",
        _ => DEFAULT_LANGUAGE,
    }
}

fn coerce(raw: &str, current: &Value) -> Result<Value, ConfigError> {
    match current {
        Value::Bool(_) => match raw.trim().to_ascii_lowercase().as_str() {
            "true" | "1" | "yes" | "on" => Ok(Value::Bool(true)),
            "false" | "0" | "no" | "off" => Ok(Value::Bool(false)),
            _ => Err(ConfigError::InvalidValue(
                "需要布尔值（true/false/1/0）".into(),
            )),
        },
        Value::Number(number) if number.is_i64() || number.is_u64() => raw
            .trim()
            .parse::<i64>()
            .map(Value::from)
            .map_err(|error| ConfigError::InvalidValue(error.to_string())),
        Value::Number(_) => raw
            .trim()
            .parse::<f64>()
            .map(Value::from)
            .map_err(|error| ConfigError::InvalidValue(error.to_string())),
        Value::Array(_) | Value::Object(_) => Ok(serde_json::from_str(raw)?),
        _ => Ok(Value::String(raw.into())),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_and_missing_fields() {
        let config = from_value(serde_json::json!({"editor": "vim", "unknown": 1})).unwrap();
        assert_eq!(config.editor, "vim");
        assert_eq!(config.path_type, PathType::Stem);
        assert!(config.exclude.hidden);
        assert_eq!(config.language, "zh-CN");
    }

    #[test]
    fn language_is_normalized_and_validated() {
        let mut config = Config::default();
        set_value(&mut config, "language", "en_US").unwrap();
        assert_eq!(config.language, "en-US");
        assert!(set_value(&mut config, "language", "fr-FR").is_err());
    }

    #[test]
    fn setters_infer_types() {
        let mut config = Config::default();
        assert_eq!(
            set_value(&mut config, "exclude.hidden", "false").unwrap(),
            "exclude.hidden = false"
        );
        set_value(&mut config, "subdirs_depth", "3").unwrap();
        set_value(&mut config, "editor_timeout", "45.5").unwrap();
        assert!(!config.exclude.hidden);
        assert_eq!(config.subdirs_depth, 3);
        assert_eq!(config.editor_timeout, 45.5);
    }

    #[test]
    fn corrupt_file_is_backed_up() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.json");
        fs::write(&path, "{broken").unwrap();
        let config = load_from(&path);
        assert_eq!(config.path_type, PathType::Stem);
        assert!(dir.path().join("config.json.bak").exists());
    }
}
