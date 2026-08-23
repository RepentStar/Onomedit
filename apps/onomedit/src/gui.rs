pub fn run() -> eframe::Result<()> {
    let options = eframe::NativeOptions::default();
    eframe::run_native(
        "Onomedit - 批量重命名",
        options,
        Box::new(|_context| Ok(Box::<OnomeditApp>::default())),
    )
}

#[derive(Default)]
struct OnomeditApp {
    status: String,
}

impl eframe::App for OnomeditApp {
    fn update(&mut self, context: &eframe::egui::Context, _frame: &mut eframe::Frame) {
        eframe::egui::CentralPanel::default().show(context, |ui| {
            ui.heading("Onomedit");
            ui.label("Rust 重写版");
            ui.separator();
            ui.label(if self.status.is_empty() {
                "就绪"
            } else {
                &self.status
            });
        });
    }
}
