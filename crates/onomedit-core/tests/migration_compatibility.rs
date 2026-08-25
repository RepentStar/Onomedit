use std::fs;
use std::path::{Path, PathBuf};

use onomedit_core::config::{self, CONFIG_VERSION};
use onomedit_core::journal::RenameLogger;
use onomedit_core::path::PathType;

fn fixture_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests-rust/fixtures/v0_1_6")
}

#[test]
fn python_v0_1_6_config_load_modify_and_save_round_trip() {
    let directory = tempfile::tempdir().unwrap();
    let path = directory.path().join("config.json");
    let original = fs::read(fixture_root().join("config.json")).unwrap();
    fs::write(&path, &original).unwrap();

    let mut loaded = config::load_from(&path);
    assert_eq!(loaded.version, CONFIG_VERSION);
    assert_eq!(loaded.path_type, PathType::Name);
    assert_eq!(
        loaded.editor,
        "\"C:\\Program Files\\Notepad++\\notepad++.exe\" -multiInst"
    );
    assert_eq!(loaded.editor_timeout, 45.5);
    assert_eq!(loaded.sort_by, "mtime");
    assert!(loaded.sort_reverse);
    assert!(loaded.exclude.readonly);
    assert!(!loaded.exclude.hidden);
    assert!(loaded.preview.diff && loaded.preview.distance);
    assert_eq!(loaded.shell_props[0]["property"], "System.Size");
    assert_eq!(loaded.auto_rules.len(), 1);
    assert_eq!(loaded.auto_rules[0].find, "旧");
    assert_eq!(loaded.temp_dir, "D:\\Onomedit Temp");
    assert_eq!(
        fs::read(&path).unwrap(),
        original,
        "load rewrote v0.1.6 config"
    );

    config::set_value(&mut loaded, "skip_confirmation", "true").unwrap();
    config::save_to(&loaded, &path).unwrap();
    let reloaded = config::load_from(&path);
    assert!(reloaded.skip_confirmation);
    assert_eq!(reloaded.editor, loaded.editor);
    assert_eq!(reloaded.auto_rules[0], loaded.auto_rules[0]);
    assert!(!path.with_extension("json.tmp").exists());
}

#[test]
fn python_v0_1_6_logs_are_read_without_conversion() {
    let log = RenameLogger::new(fixture_root().join("log"));
    assert_eq!(
        log.read_history(),
        vec![
            (
                PathBuf::from(r"C:\资料\old.txt"),
                PathBuf::from(r"D:\归档\new.txt")
            ),
            (
                PathBuf::from(r"C:\资料\old<-->part.txt"),
                PathBuf::from(r"D:\归档\newer.txt")
            ),
            (
                PathBuf::from(r"\\server\share\旧.txt"),
                PathBuf::from(r"\\server\share\新.txt")
            ),
        ]
    );
    assert_eq!(
        log.read_last(),
        vec![(
            PathBuf::from(r"\\server\share\旧.txt"),
            PathBuf::from(r"\\server\share\新.txt")
        )]
    );
    assert_eq!(
        fs::read_to_string(log.error_path).unwrap().trim_end(),
        "无法重命名: 文件已存在"
    );
    assert!(Path::new(&log.history_path).exists());
}
