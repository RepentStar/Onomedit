use std::env;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::Path;
use std::process::{Command, Stdio};
use std::thread;
use std::time::Duration;

fn delay_seconds(value: Option<&String>, fallback: f64) -> Duration {
    Duration::from_secs_f64(
        value
            .and_then(|value| value.parse::<f64>().ok())
            .unwrap_or(fallback),
    )
}

fn append_saved(path: &Path) {
    let mut file = OpenOptions::new().append(true).open(path).unwrap();
    file.write_all(b"\nsaved").unwrap();
}

fn spawn_delayed_save(delay: &str, path: &Path) {
    Command::new(env::current_exe().unwrap())
        .arg("delay")
        .arg(delay)
        .arg(path)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
}

fn main() {
    let arguments: Vec<String> = env::args().collect();
    if arguments.len() < 3 {
        std::process::exit(2);
    }
    let mode = &arguments[1];
    let path = Path::new(arguments.last().unwrap());
    let extra = &arguments[2..arguments.len() - 1];

    match mode.as_str() {
        "save" => append_saved(path),
        "set" => {
            let line_number = extra
                .first()
                .and_then(|value| value.parse::<usize>().ok())
                .unwrap_or(1);
            let content = extra.get(1).map_or("edited", String::as_str);
            let mut lines: Vec<String> = fs::read_to_string(path)
                .unwrap()
                .lines()
                .map(str::to_owned)
                .collect();
            if (1..=lines.len()).contains(&line_number) {
                lines[line_number - 1] = content.to_owned();
            } else {
                lines.push(content.to_owned());
            }
            fs::write(path, format!("{}\n", lines.join("\n"))).unwrap();
        }
        "delay" => {
            thread::sleep(delay_seconds(extra.first(), 0.5));
            append_saved(path);
        }
        "launcher-delay" => {
            spawn_delayed_save(extra.first().map_or("0.5", String::as_str), path);
        }
        "slow-launcher-delay" => {
            thread::sleep(delay_seconds(extra.first(), 2.1));
            spawn_delayed_save(extra.get(1).map_or("0.2", String::as_str), path);
        }
        "sleep" => thread::sleep(delay_seconds(extra.first(), 1.0)),
        "truncate" => {
            let keep = extra
                .first()
                .and_then(|value| value.parse::<usize>().ok())
                .unwrap_or(1);
            let lines: Vec<_> = fs::read_to_string(path)
                .unwrap()
                .lines()
                .take(keep)
                .map(str::to_owned)
                .collect();
            let contents = if lines.is_empty() {
                String::new()
            } else {
                format!("{}\n", lines.join("\n"))
            };
            fs::write(path, contents).unwrap();
        }
        "exit" | "launcher" => {}
        _ => std::process::exit(2),
    }
}
