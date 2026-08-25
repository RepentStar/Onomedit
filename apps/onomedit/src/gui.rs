use std::fs;
use std::path::{Path, PathBuf};
use std::str::FromStr;
use std::sync::mpsc::{self, Receiver, Sender};
use std::time::{Duration, Instant};

use eframe::egui::{self, Color32, RichText};
use onomedit_core::collection;
use onomedit_core::config::{self, Config};
use onomedit_core::diff::{diff_text, levenshtein};
use onomedit_core::journal::RenameLogger;
use onomedit_core::path::{PathItem, PathType};
use onomedit_core::pipeline::{
    DuplicateTargetError, RenamePair, RenamePipeline, RenameResult, Renamer,
    find_duplicate_targets, restore,
};
use onomedit_platform::{clipboard, editor};

const WINDOW_TITLE: &str = "Onomedit - 批量重命名";

pub fn run() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_inner_size([900.0, 640.0]),
        ..eframe::NativeOptions::default()
    };
    eframe::run_native(
        WINDOW_TITLE,
        options,
        Box::new(|creation| Ok(Box::new(OnomeditApp::new(creation)))),
    )
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Operation {
    Rename,
    Restore,
}

enum WorkerEvent {
    Status(String),
    Planned {
        pairs: Vec<RenamePair>,
        base: PathBuf,
        config: Config,
        dry_run: bool,
    },
    Completed {
        result: RenameResult,
        operation: Operation,
    },
    Failed(String),
}

#[derive(Debug, Clone)]
struct ConfirmRow {
    id: usize,
    pair: RenamePair,
    old_display: String,
    new_display: String,
    diff: String,
    distance: usize,
    checked: bool,
}

#[derive(Debug, Clone)]
struct ConfirmationState {
    rows: Vec<ConfirmRow>,
    config: Config,
    dry_run: bool,
}

impl ConfirmationState {
    fn new(pairs: Vec<RenamePair>, base: &Path, config: Config, dry_run: bool) -> Self {
        let rows = pairs
            .into_iter()
            .enumerate()
            .map(|(id, pair)| {
                let old_display = display_path(&pair.old, base);
                let new_display = display_path(&pair.requested_new, base);
                ConfirmRow {
                    id,
                    diff: if config.preview.diff {
                        diff_text(&old_display, &new_display)
                    } else {
                        String::new()
                    },
                    distance: if config.preview.distance {
                        levenshtein(&old_display, &new_display)
                    } else {
                        0
                    },
                    pair,
                    old_display,
                    new_display,
                    checked: true,
                }
            })
            .collect();
        Self {
            rows,
            config,
            dry_run,
        }
    }

    fn selected_pairs(&self) -> Vec<RenamePair> {
        self.rows
            .iter()
            .filter(|row| row.checked)
            .map(|row| row.pair.clone())
            .collect()
    }
}

#[derive(Debug, Clone)]
struct SettingsDraft {
    config: Config,
    editor_timeout: String,
    subdirs_depth: String,
}

impl SettingsDraft {
    fn new(config: &Config) -> Self {
        Self {
            config: config.clone(),
            editor_timeout: config.editor_timeout.to_string(),
            subdirs_depth: config.subdirs_depth.to_string(),
        }
    }

    fn finish(mut self) -> Result<Config, String> {
        self.config.editor_timeout = self
            .editor_timeout
            .trim()
            .parse()
            .map_err(|_| "等待超时必须是数字".to_owned())?;
        self.config.subdirs_depth = self
            .subdirs_depth
            .trim()
            .parse()
            .map_err(|_| "展开层级必须是整数".to_owned())?;
        Ok(self.config)
    }
}

#[derive(Debug, Clone)]
enum View {
    Main,
    Confirm(ConfirmationState),
    Settings(SettingsDraft),
}

struct OnomeditApp {
    config: Config,
    raw_paths: Vec<PathBuf>,
    shown_paths: Vec<PathBuf>,
    path_type: PathType,
    expand_subdirs: bool,
    depth: i32,
    status: String,
    busy: bool,
    view: View,
    sender: Sender<WorkerEvent>,
    receiver: Receiver<WorkerEvent>,
    close_at: Option<Instant>,
    alert: Option<String>,
}

impl OnomeditApp {
    fn new(creation: &eframe::CreationContext<'_>) -> Self {
        install_system_font(&creation.egui_ctx);
        let config = config::load();
        let (sender, receiver) = mpsc::channel();
        Self {
            path_type: config.path_type,
            expand_subdirs: config.expand_subdirs,
            depth: config.subdirs_depth,
            config,
            raw_paths: Vec::new(),
            shown_paths: Vec::new(),
            status: "就绪（可拖入文件或文件夹）".to_owned(),
            busy: false,
            view: View::Main,
            sender,
            receiver,
            close_at: None,
            alert: None,
        }
    }

    fn add_paths(&mut self, paths: impl IntoIterator<Item = PathBuf>) {
        let before = self.raw_paths.len();
        for path in paths {
            if path.exists() && !self.raw_paths.contains(&path) {
                self.raw_paths.push(path);
            }
        }
        self.refresh_paths();
        self.status = format!(
            "已添加 {} 项，共 {} 项",
            self.raw_paths.len() - before,
            self.raw_paths.len()
        );
    }

    fn refresh_paths(&mut self) {
        let items: Vec<PathItem> = self.raw_paths.iter().cloned().map(PathItem::new).collect();
        let items = if self.expand_subdirs {
            collection::expand_subdirs(items, self.depth)
        } else {
            items
        };
        self.shown_paths = collection::sort_items(
            collection::dedupe_items(items),
            &self.config.sort_by,
            self.config.sort_reverse,
        )
        .into_iter()
        .map(|item| item.full().to_owned())
        .collect();
    }

    fn start_plan(&mut self, context: &egui::Context, no_editor: bool, dry_run: bool) {
        if self.busy {
            return;
        }
        if self.shown_paths.is_empty() {
            self.status = "请先添加文件".to_owned();
            return;
        }
        let paths: Vec<String> = self
            .shown_paths
            .iter()
            .map(|path| path.to_string_lossy().into_owned())
            .collect();
        let base = collection::display_base(
            &self
                .raw_paths
                .iter()
                .map(|path| path.to_string_lossy().into_owned())
                .collect::<Vec<_>>(),
        );
        let mut settings = self.config.clone();
        settings.path_type = self.path_type;
        settings.expand_subdirs = false;
        settings.subdirs_depth = self.depth;
        if no_editor {
            settings.open_editor = false;
        }

        self.busy = true;
        self.status = if settings.open_editor {
            "后台线程：准备文件并等待编辑器…".to_owned()
        } else {
            "后台线程：正在生成重命名计划…".to_owned()
        };
        let sender = self.sender.clone();
        let repaint = context.clone();
        std::thread::spawn(move || {
            let result = (|| -> Result<(), String> {
                let clipboard_text = clipboard::get_text();
                let pipeline =
                    RenamePipeline::new(settings.clone()).with_clipboard_text(clipboard_text);
                let session = pipeline
                    .prepare(&paths)
                    .map_err(|error| error.to_string())?;
                if settings.open_editor {
                    if settings.editor.trim().is_empty() {
                        return Err("未配置编辑器，请先在设置中填写编辑器命令".to_owned());
                    }
                    send_event(
                        &sender,
                        &repaint,
                        WorkerEvent::Status(format!(
                            "已写入临时文件: {}，等待编辑器保存并退出…",
                            session.edit_path().display()
                        )),
                    );
                    let signature = session.signature().map_err(|error| error.to_string())?;
                    editor::launch_and_wait(
                        &settings.editor,
                        session.edit_path(),
                        signature,
                        settings.multi_tab,
                        Duration::from_secs_f64(settings.editor_timeout.max(0.0)),
                        |message| {
                            send_event(&sender, &repaint, WorkerEvent::Status(message.to_owned()));
                        },
                    )
                    .map_err(|error| error.to_string())?;
                }
                let pairs = pipeline
                    .finish_plan(&session)
                    .map_err(|error| error.to_string())?;
                if !dry_run {
                    let conflicts = find_duplicate_targets(&pairs);
                    if !conflicts.is_empty() {
                        return Err(DuplicateTargetError { conflicts }.to_string());
                    }
                }
                if !dry_run && settings.skip_confirmation {
                    let logger = RenameLogger::new(config::log_dir());
                    logger.begin_session();
                    let result = Renamer::new(Some(logger))
                        .run(&pairs)
                        .map_err(|error| error.to_string())?;
                    send_event(
                        &sender,
                        &repaint,
                        WorkerEvent::Completed {
                            result,
                            operation: Operation::Rename,
                        },
                    );
                } else {
                    send_event(
                        &sender,
                        &repaint,
                        WorkerEvent::Planned {
                            pairs,
                            base,
                            config: settings,
                            dry_run,
                        },
                    );
                }
                Ok(())
            })();
            if let Err(error) = result {
                send_event(&sender, &repaint, WorkerEvent::Failed(error));
            }
        });
    }

    fn execute_confirmation(&mut self, context: &egui::Context) {
        if self.busy {
            return;
        }
        let View::Confirm(confirmation) = &self.view else {
            return;
        };
        if confirmation.dry_run {
            self.status = "预览模式不会执行重命名".to_owned();
            return;
        }
        let pairs = confirmation.selected_pairs();
        if pairs.is_empty() {
            self.status = "未勾选任何项目".to_owned();
            return;
        }
        self.busy = true;
        self.status = "后台线程：正在执行重命名…".to_owned();
        let sender = self.sender.clone();
        let repaint = context.clone();
        std::thread::spawn(move || {
            let logger = RenameLogger::new(config::log_dir());
            logger.begin_session();
            match Renamer::new(Some(logger)).run(&pairs) {
                Ok(result) => send_event(
                    &sender,
                    &repaint,
                    WorkerEvent::Completed {
                        result,
                        operation: Operation::Rename,
                    },
                ),
                Err(error) => send_event(&sender, &repaint, WorkerEvent::Failed(error.to_string())),
            }
        });
    }

    fn restore_last(&mut self, context: &egui::Context) {
        if self.busy {
            return;
        }
        self.busy = true;
        self.status = "后台线程：正在恢复上次重命名…".to_owned();
        let sender = self.sender.clone();
        let repaint = context.clone();
        std::thread::spawn(move || {
            let logger = RenameLogger::new(config::log_dir());
            match restore(&logger, false, None) {
                Ok(result) => send_event(
                    &sender,
                    &repaint,
                    WorkerEvent::Completed {
                        result,
                        operation: Operation::Restore,
                    },
                ),
                Err(error) => send_event(&sender, &repaint, WorkerEvent::Failed(error.to_string())),
            }
        });
    }

    fn receive_events(&mut self) {
        while let Ok(event) = self.receiver.try_recv() {
            match event {
                WorkerEvent::Status(status) => self.status = status,
                WorkerEvent::Planned {
                    pairs,
                    base,
                    config,
                    dry_run,
                } => {
                    self.busy = false;
                    self.status = if dry_run {
                        format!("预览共 {} 项（未执行）", pairs.len())
                    } else {
                        format!("重命名计划共 {} 项，请确认", pairs.len())
                    };
                    self.view =
                        View::Confirm(ConfirmationState::new(pairs, &base, config, dry_run));
                }
                WorkerEvent::Completed { result, operation } => {
                    self.busy = false;
                    self.status = format_result(operation, &result);
                    self.view = View::Main;
                    self.refresh_paths();
                    if operation == Operation::Rename && self.config.exit_after {
                        self.close_at = Some(Instant::now() + Duration::from_millis(600));
                    }
                }
                WorkerEvent::Failed(error) => {
                    self.busy = false;
                    if error.starts_with("检测到目标重名") {
                        self.alert = Some(error.clone());
                    }
                    self.status = format!("出错: {error}");
                }
            }
        }
    }

    fn show_main(&mut self, context: &egui::Context, ui: &mut egui::Ui) {
        ui.heading(WINDOW_TITLE);
        ui.add_space(6.0);
        ui.horizontal_wrapped(|ui| {
            if ui.button("添加文件…").clicked()
                && let Some(paths) = rfd::FileDialog::new().pick_files()
            {
                self.add_paths(paths);
            }
            if ui.button("添加文件夹…").clicked()
                && let Some(path) = rfd::FileDialog::new().pick_folder()
            {
                self.add_paths([path]);
            }
            if ui.button("从剪贴板").clicked() {
                let paths: Vec<PathBuf> =
                    clipboard::get_paths().into_iter().map(Into::into).collect();
                if paths.is_empty() {
                    self.status = "剪贴板为空或不可读".to_owned();
                } else {
                    self.add_paths(paths);
                }
            }
            if ui.button("清空").clicked() {
                self.raw_paths.clear();
                self.shown_paths.clear();
                self.status = "已清空".to_owned();
            }
            ui.separator();
            if ui.button("恢复上次").clicked() {
                self.restore_last(context);
            }
            if ui.button("设置…").clicked() {
                self.view = View::Settings(SettingsDraft::new(&self.config));
            }
        });

        ui.add_space(6.0);
        ui.horizontal_wrapped(|ui| {
            ui.label("路径类型:");
            egui::ComboBox::from_id_salt("main_path_type")
                .selected_text(self.path_type.to_string())
                .show_ui(ui, |ui| {
                    for value in PathType::ALL {
                        let path_type = PathType::from_str(value).expect("static path type");
                        ui.selectable_value(&mut self.path_type, path_type, value);
                    }
                });
            if ui
                .checkbox(&mut self.expand_subdirs, "展开子文件夹")
                .changed()
            {
                self.refresh_paths();
            }
            ui.label("层级:");
            if ui
                .add(egui::DragValue::new(&mut self.depth).range(1..=99))
                .changed()
            {
                self.refresh_paths();
            }
        });

        ui.add_space(6.0);
        ui.horizontal_wrapped(|ui| {
            if ui.button("开始（打开编辑器）").clicked() {
                self.start_plan(context, false, false);
            }
            if ui.button("直接应用规则（跳过编辑器）").clicked() {
                self.start_plan(context, true, false);
            }
            if ui.button("预览（进入重命名确认）").clicked() {
                self.start_plan(context, false, true);
            }
        });

        ui.add_space(6.0);
        let list_height = ui.available_height().max(120.0);
        ui.group(|ui| {
            ui.set_min_height(list_height);
            ui.label("文件（将按此顺序写入临时文件）");
            ui.separator();
            egui::ScrollArea::vertical()
                .auto_shrink([false, false])
                .max_height((list_height - 38.0).max(80.0))
                .show(ui, |ui| {
                    if self.shown_paths.is_empty() {
                        ui.weak("拖入文件/文件夹，或使用上方按钮添加");
                    }
                    for (index, path) in self.shown_paths.iter().enumerate() {
                        ui.label(format!("{}. {}", index + 1, path.display()));
                    }
                });
        });
    }

    fn show_confirmation(&mut self, context: &egui::Context, ui: &mut egui::Ui) {
        let View::Confirm(confirmation) = &mut self.view else {
            return;
        };
        ui.horizontal(|ui| {
            ui.heading(if confirmation.dry_run {
                "重命名预览"
            } else {
                "重命名确认"
            });
            if confirmation.dry_run {
                ui.label(RichText::new("只读，不会修改文件").color(Color32::DARK_GREEN));
            }
        });
        ui.separator();
        let mut cancel = false;
        let mut execute = false;
        ui.horizontal(|ui| {
            if !confirmation.dry_run {
                if ui.button("全选").clicked() {
                    confirmation
                        .rows
                        .iter_mut()
                        .for_each(|row| row.checked = true);
                }
                if ui.button("全不选").clicked() {
                    confirmation
                        .rows
                        .iter_mut()
                        .for_each(|row| row.checked = false);
                }
            }
            ui.label(format!(
                "共 {} 项，已选 {} 项",
                confirmation.rows.len(),
                confirmation.rows.iter().filter(|row| row.checked).count()
            ));
            if ui
                .button(if confirmation.dry_run {
                    "关闭预览"
                } else {
                    "取消"
                })
                .clicked()
            {
                cancel = true;
            }
            if !confirmation.dry_run && ui.button("执行重命名").clicked() {
                execute = true;
            }
        });

        ui.add_space(6.0);
        egui::ScrollArea::both()
            .auto_shrink([false, false])
            .max_height(ui.available_height().max(100.0))
            .show(ui, |ui| {
                egui::Grid::new("confirmation_grid")
                    .striped(true)
                    .min_col_width(80.0)
                    .show(ui, |ui| {
                        ui.strong("执行");
                        ui.strong("原文件名");
                        ui.strong("新文件名");
                        if confirmation.config.preview.diff {
                            ui.strong("差异");
                        }
                        if confirmation.config.preview.distance {
                            ui.strong("距离");
                        }
                        ui.end_row();
                        for row in &mut confirmation.rows {
                            ui.push_id(("checked", row.id), |ui| {
                                ui.add_enabled(
                                    !confirmation.dry_run,
                                    egui::Checkbox::without_text(&mut row.checked),
                                );
                            });
                            ui.label(&row.old_display)
                                .on_hover_text(row.pair.old.display().to_string());
                            ui.label(&row.new_display)
                                .on_hover_text(row.pair.requested_new.display().to_string());
                            if confirmation.config.preview.diff {
                                ui.label(&row.diff);
                            }
                            if confirmation.config.preview.distance {
                                ui.label(row.distance.to_string());
                            }
                            // 必须在 Grid 的父 UI 上结束行；放进 push_id 子 UI 会让所有项目连成一行。
                            ui.end_row();
                        }
                    });
            });
        if cancel {
            let dry_run = confirmation.dry_run;
            self.view = View::Main;
            self.status = if dry_run {
                "预览已关闭（未执行）".to_owned()
            } else {
                "重命名确认已取消".to_owned()
            };
        } else if execute {
            self.execute_confirmation(context);
        }
    }

    fn show_settings(&mut self, ui: &mut egui::Ui) {
        let View::Settings(draft) = &mut self.view else {
            return;
        };
        ui.heading("Onomedit 设置");
        ui.separator();
        let mut save_requested = false;
        let mut cancel_requested = false;
        let mut reset_requested = false;
        ui.horizontal(|ui| {
            if ui.button("保存").clicked() {
                save_requested = true;
            }
            if ui.button("重置默认").clicked() {
                reset_requested = true;
            }
            if ui.button("取消").clicked() {
                cancel_requested = true;
            }
        });
        ui.add_space(6.0);
        egui::ScrollArea::vertical()
            .max_height(ui.available_height().max(120.0))
            .show(ui, |ui| {
                egui::Grid::new("settings_grid")
                    .num_columns(2)
                    .spacing([18.0, 5.0])
                    .show(ui, |ui| {
                        setting_text(ui, "主编辑器命令", &mut draft.config.editor);
                        setting_text(ui, "备用编辑器命令", &mut draft.config.editor_alt);
                        setting_text(ui, "等待超时（秒）", &mut draft.editor_timeout);
                        setting_check(ui, "多标签编辑器", &mut draft.config.multi_tab);
                        setting_check(ui, "打开编辑器", &mut draft.config.open_editor);
                        setting_check(ui, "应用规则", &mut draft.config.apply_rules);
                        setting_check(ui, "环境变量替换", &mut draft.config.enable_envvars);
                        setting_check(ui, "自动替换规则", &mut draft.config.enable_auto_rules);

                        ui.label("路径类型");
                        egui::ComboBox::from_id_salt("settings_path_type")
                            .selected_text(draft.config.path_type.to_string())
                            .show_ui(ui, |ui| {
                                for value in PathType::ALL {
                                    let path_type =
                                        PathType::from_str(value).expect("static path type");
                                    ui.selectable_value(
                                        &mut draft.config.path_type,
                                        path_type,
                                        value,
                                    );
                                }
                            });
                        ui.end_row();

                        ui.label("排序依据");
                        egui::ComboBox::from_id_salt("settings_sort_by")
                            .selected_text(&draft.config.sort_by)
                            .show_ui(ui, |ui| {
                                for value in collection::SORT_BY_CHOICES {
                                    ui.selectable_value(
                                        &mut draft.config.sort_by,
                                        value.to_owned(),
                                        value,
                                    );
                                }
                            });
                        ui.end_row();
                        setting_check(ui, "反转顺序", &mut draft.config.sort_reverse);
                        setting_check(ui, "展开子文件夹", &mut draft.config.expand_subdirs);
                        setting_text(ui, "展开层级", &mut draft.subdirs_depth);
                        setting_check(ui, "跳过重命名确认", &mut draft.config.skip_confirmation);
                        setting_check(ui, "完成后退出", &mut draft.config.exit_after);

                        setting_check(ui, "排除文件", &mut draft.config.exclude.files);
                        setting_check(ui, "排除目录", &mut draft.config.exclude.dirs);
                        setting_check(ui, "排除符号链接", &mut draft.config.exclude.symlinks);
                        setting_check(ui, "排除只读", &mut draft.config.exclude.readonly);
                        setting_check(ui, "排除隐藏", &mut draft.config.exclude.hidden);
                        setting_check(ui, "排除系统", &mut draft.config.exclude.system);

                        setting_check(ui, "显示差异", &mut draft.config.preview.diff);
                        setting_check(ui, "显示距离", &mut draft.config.preview.distance);
                        setting_check(ui, "安全命名", &mut draft.config.safety.sanitize);
                    });
            });
        if reset_requested {
            // Python 基线的“重置默认”只关闭窗口，不写配置；兼容迁移阶段保留该语义。
            self.view = View::Main;
            self.status = "已取消设置（重置默认未保存）".to_owned();
        } else if cancel_requested {
            self.view = View::Main;
            self.status = "设置未更改".to_owned();
        } else if save_requested {
            let View::Settings(draft) = self.view.clone() else {
                return;
            };
            match draft.finish() {
                Ok(config) => match config::save(&config) {
                    Ok(()) => {
                        self.config = config;
                        self.path_type = self.config.path_type;
                        self.expand_subdirs = self.config.expand_subdirs;
                        self.depth = self.config.subdirs_depth;
                        self.refresh_paths();
                        self.view = View::Main;
                        self.status = "设置已保存".to_owned();
                    }
                    Err(error) => self.status = format!("保存设置失败: {error}"),
                },
                Err(error) => self.status = format!("设置无效: {error}"),
            }
        }
    }
}

impl eframe::App for OnomeditApp {
    fn update(&mut self, context: &egui::Context, _frame: &mut eframe::Frame) {
        self.receive_events();
        let dropped: Vec<PathBuf> = context.input(|input| {
            input
                .raw
                .dropped_files
                .iter()
                .filter_map(|file| file.path.clone())
                .collect()
        });
        if !dropped.is_empty() && !self.busy && matches!(self.view, View::Main) {
            self.add_paths(dropped);
        }
        if self.busy {
            context.request_repaint_after(Duration::from_millis(100));
        }
        if self
            .close_at
            .is_some_and(|deadline| Instant::now() >= deadline)
        {
            context.send_viewport_cmd(egui::ViewportCommand::Close);
        } else if let Some(deadline) = self.close_at {
            context.request_repaint_after(deadline.saturating_duration_since(Instant::now()));
        }

        egui::TopBottomPanel::bottom("status_bar")
            .exact_height(34.0)
            .show(context, |ui| {
                ui.horizontal(|ui| {
                    if self.busy {
                        ui.spinner();
                    }
                    let color = if self.status.starts_with("出错")
                        || self.status.starts_with("保存设置失败")
                        || self.status.starts_with("设置无效")
                    {
                        Color32::RED
                    } else {
                        ui.visuals().text_color()
                    };
                    ui.label(RichText::new(&self.status).color(color));
                });
            });
        egui::CentralPanel::default().show(context, |ui| {
            ui.add_enabled_ui(!self.busy, |ui| match self.view {
                View::Main => self.show_main(context, ui),
                View::Confirm(_) => self.show_confirmation(context, ui),
                View::Settings(_) => self.show_settings(ui),
            });
        });
        if let Some(message) = self.alert.clone() {
            let mut open = true;
            let mut dismiss = false;
            egui::Window::new("目标重名，已中止")
                .collapsible(false)
                .resizable(true)
                .open(&mut open)
                .show(context, |ui| {
                    ui.label(message);
                    ui.add_space(8.0);
                    if ui.button("关闭").clicked() {
                        dismiss = true;
                    }
                });
            if dismiss || !open {
                self.alert = None;
            }
        }
    }
}

fn send_event(sender: &Sender<WorkerEvent>, context: &egui::Context, event: WorkerEvent) {
    let _ = sender.send(event);
    context.request_repaint();
}

fn format_result(operation: Operation, result: &RenameResult) -> String {
    let label = match operation {
        Operation::Rename => "重命名完成",
        Operation::Restore => "恢复完成",
    };
    format!(
        "{label}: 成功 {} / 失败 {} / 无变化 {}",
        result.success.len(),
        result.failed.len(),
        result.skipped.len()
    )
}

fn display_path(path: &Path, base: &Path) -> String {
    if base.as_os_str().is_empty() {
        return path.to_string_lossy().into_owned();
    }
    path.strip_prefix(base)
        .ok()
        .filter(|relative| !relative.as_os_str().is_empty())
        .unwrap_or(path)
        .to_string_lossy()
        .into_owned()
}

fn setting_text(ui: &mut egui::Ui, label: &str, value: &mut String) {
    ui.label(label);
    ui.text_edit_singleline(value);
    ui.end_row();
}

fn setting_check(ui: &mut egui::Ui, label: &str, value: &mut bool) {
    ui.label(label);
    ui.checkbox(value, "");
    ui.end_row();
}

fn install_system_font(context: &egui::Context) {
    let candidates = if cfg!(windows) {
        vec![
            PathBuf::from(r"C:\Windows\Fonts\msyh.ttc"),
            PathBuf::from(r"C:\Windows\Fonts\simhei.ttf"),
        ]
    } else if cfg!(target_os = "macos") {
        vec![PathBuf::from("/System/Library/Fonts/PingFang.ttc")]
    } else {
        vec![
            PathBuf::from("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
            PathBuf::from("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        ]
    };
    let Some(bytes) = candidates.into_iter().find_map(|path| fs::read(path).ok()) else {
        return;
    };
    let mut fonts = egui::FontDefinitions::default();
    fonts.font_data.insert(
        "onomedit_cjk".to_owned(),
        egui::FontData::from_owned(bytes).into(),
    );
    for family in [egui::FontFamily::Proportional, egui::FontFamily::Monospace] {
        fonts
            .families
            .entry(family)
            .or_default()
            .insert(0, "onomedit_cjk".to_owned());
    }
    context.set_fonts(fonts);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pair(old: &str, new: &str) -> RenamePair {
        RenamePair::new(old, new)
    }

    #[test]
    fn confirmation_keeps_stable_ids_and_explicit_checks() {
        let mut state = ConfirmationState::new(
            vec![
                pair("C:/work/a.txt", "C:/work/b.txt"),
                pair("C:/work/c.txt", "C:/work/d.txt"),
            ],
            Path::new("C:/work"),
            Config::default(),
            false,
        );
        assert_eq!(state.rows[0].id, 0);
        assert_eq!(state.rows[0].old_display, "a.txt");
        assert!(state.rows.iter().all(|row| row.checked));
        state.rows[0].checked = false;
        assert_eq!(
            state.selected_pairs(),
            vec![pair("C:/work/c.txt", "C:/work/d.txt")]
        );
    }

    #[test]
    fn dry_run_is_read_only_even_though_rows_are_visible() {
        let state = ConfirmationState::new(
            vec![pair("a.txt", "b.txt")],
            Path::new(""),
            Config::default(),
            true,
        );
        assert!(state.dry_run);
        assert_eq!(state.selected_pairs().len(), 1);
    }

    #[test]
    fn settings_validates_numeric_fields_without_mutating_source() {
        let source = Config::default();
        let mut draft = SettingsDraft::new(&source);
        draft.editor_timeout = "invalid".to_owned();
        assert_eq!(draft.finish().unwrap_err(), "等待超时必须是数字");
        assert_eq!(source.editor_timeout, Config::default().editor_timeout);
    }

    #[test]
    fn result_status_reports_all_categories() {
        let result = RenameResult {
            success: vec![("a".into(), "b".into())],
            failed: vec![("c".into(), "d".into(), "no".into())],
            skipped: vec!["e".into()],
        };
        assert_eq!(
            format_result(Operation::Rename, &result),
            "重命名完成: 成功 1 / 失败 1 / 无变化 1"
        );
    }
}
