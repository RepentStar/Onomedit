pub mod cli;
pub mod completion;
#[cfg(feature = "gui")]
pub mod gui;

pub fn entry(gui_available: bool) -> i32 {
    cli::entry(std::env::args_os().skip(1), gui_available)
}
