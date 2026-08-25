use std::fs;
use std::time::Instant;

use onomedit_core::config::{Config, ExcludeOptions, SafetyOptions};
use onomedit_core::journal::RenameLogger;
use onomedit_core::path::PathItem;
use onomedit_core::pipeline::RenamePipeline;

const ITEM_COUNT: usize = 10_000;
const LOG_PAIR_COUNT: usize = 20_000;

#[test]
#[ignore = "manual release performance baseline"]
fn measure_large_collection_planning_long_paths_and_logs() {
    let directory = tempfile::tempdir().unwrap();
    let root = directory.path().join("large-directory");
    let scratch = directory.path().join("scratch");
    fs::create_dir(&root).unwrap();
    fs::create_dir(&scratch).unwrap();

    let started = Instant::now();
    for index in 0..ITEM_COUNT {
        fs::write(root.join(format!("file_{index:05}.txt")), []).unwrap();
    }
    let create_files = started.elapsed();

    let config = Config {
        expand_subdirs: true,
        subdirs_depth: 1,
        sort_by: "name".into(),
        temp_dir: scratch.to_string_lossy().into_owned(),
        exclude: ExcludeOptions {
            hidden: false,
            system: false,
            ..ExcludeOptions::default()
        },
        ..Config::default()
    };
    let pipeline = RenamePipeline::new(config);
    let inputs = vec![root.to_string_lossy().into_owned()];

    let started = Instant::now();
    let session = pipeline.prepare(&inputs).unwrap();
    let collect_and_prepare = started.elapsed();
    assert_eq!(session.items.len(), ITEM_COUNT);

    let items: Vec<PathItem> = (0..ITEM_COUNT)
        .map(|index| PathItem::new(root.join(format!("source_{index:05}.txt"))))
        .collect();
    let edited: Vec<_> = (0..ITEM_COUNT)
        .map(|index| root.join(format!("renamed_{index:05}.txt")))
        .collect();
    let plan_config = Config {
        apply_rules: false,
        safety: SafetyOptions { sanitize: false },
        ..Config::default()
    };
    let plan_pipeline = RenamePipeline::new(plan_config);
    let started = Instant::now();
    let pairs = plan_pipeline.plan(&items, &edited);
    let plan = started.elapsed();
    assert_eq!(pairs.len(), ITEM_COUNT);

    let mut long_directory = directory.path().join("long-path");
    while long_directory.to_string_lossy().chars().count() < 210 {
        long_directory = long_directory.join("segment_0123456789_0123456789");
    }
    fs::create_dir_all(&long_directory).unwrap();
    let long_file = long_directory.join("unicode_测试_file.txt");
    fs::write(&long_file, "payload").unwrap();
    let started = Instant::now();
    let long_session = pipeline
        .prepare(&[long_file.to_string_lossy().into_owned()])
        .unwrap();
    let long_pairs = pipeline.finish_plan(&long_session).unwrap();
    let long_path = started.elapsed();
    assert_eq!(long_pairs.len(), 1);

    let logger = RenameLogger::new(directory.path().join("large-log"));
    fs::create_dir_all(&logger.log_dir).unwrap();
    let mut history = String::with_capacity(LOG_PAIR_COUNT * 120);
    for index in 0..LOG_PAIR_COUNT {
        history.push_str(&format!(
            "C:\\资料\\source_{index:05}_with_a_long_name.txt<-->D:\\归档\\renamed_{index:05}_with_a_long_name.txt\r\n"
        ));
    }
    fs::write(&logger.history_path, history.as_bytes()).unwrap();
    let log_bytes = history.len();
    assert!(log_bytes > 1024 * 1024);
    let started = Instant::now();
    let log_pairs = logger.read_history();
    let read_log = started.elapsed();
    assert_eq!(log_pairs.len(), LOG_PAIR_COUNT);

    println!(
        "items={ITEM_COUNT} create_files_ms={} collect_prepare_ms={} plan_ms={} long_path_chars={} long_path_ms={} log_bytes={log_bytes} log_pairs={LOG_PAIR_COUNT} log_read_ms={}",
        create_files.as_millis(),
        collect_and_prepare.as_millis(),
        plan.as_millis(),
        long_file.to_string_lossy().chars().count(),
        long_path.as_millis(),
        read_log.as_millis(),
    );
}
