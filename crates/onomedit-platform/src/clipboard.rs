#[cfg(not(windows))]
use std::process::Command;

pub fn parse_path_text(text: &str) -> Vec<String> {
    text.lines()
        .flat_map(|line| split_quoted(line.trim()))
        .filter(|path| !path.is_empty())
        .collect()
}

fn split_quoted(line: &str) -> Vec<String> {
    let mut paths = Vec::new();
    let mut current = String::new();
    let mut quoted = false;
    for ch in line.chars() {
        match ch {
            '"' => quoted = !quoted,
            ' ' | '\t' if !quoted => {
                if !current.is_empty() {
                    paths.push(std::mem::take(&mut current));
                }
            }
            _ => current.push(ch),
        }
    }
    if !current.is_empty() {
        paths.push(current);
    }
    paths
}

pub fn get_paths() -> Vec<String> {
    #[cfg(windows)]
    if let Some(paths) = windows_clipboard::get_hdrop() {
        return paths;
    }
    get_text().map_or_else(Vec::new, |text| parse_path_text(&text))
}

pub fn get_text() -> Option<String> {
    #[cfg(windows)]
    return windows_clipboard::get_text();
    #[cfg(target_os = "macos")]
    return run(&["pbpaste"]);
    #[cfg(all(unix, not(target_os = "macos")))]
    return run(&["xclip", "-o", "-selection", "clipboard"]).or_else(|| run(&["xsel", "-b"]));
    #[allow(unreachable_code)]
    None
}

#[cfg(not(windows))]
fn run(command: &[&str]) -> Option<String> {
    let output = Command::new(command[0]).args(&command[1..]).output().ok()?;
    output
        .status
        .success()
        .then(|| String::from_utf8_lossy(&output.stdout).into_owned())
}

#[cfg(windows)]
mod windows_clipboard {
    use std::ffi::c_void;

    const CF_UNICODETEXT: u32 = 13;
    const CF_HDROP: u32 = 15;

    #[link(name = "user32")]
    unsafe extern "system" {
        fn IsClipboardFormatAvailable(format: u32) -> i32;
        fn OpenClipboard(owner: *mut c_void) -> i32;
        fn GetClipboardData(format: u32) -> *mut c_void;
        fn CloseClipboard() -> i32;
    }

    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GlobalLock(memory: *mut c_void) -> *mut c_void;
        fn GlobalUnlock(memory: *mut c_void) -> i32;
        fn GlobalSize(memory: *mut c_void) -> usize;
    }

    #[link(name = "shell32")]
    unsafe extern "system" {
        fn DragQueryFileW(drop: *mut c_void, file: u32, path: *mut u16, size: u32) -> u32;
    }

    struct Clipboard;

    impl Clipboard {
        fn open(format: u32) -> Option<Self> {
            // SAFETY: These calls do not retain the null owner and only query process-global clipboard state.
            unsafe {
                if IsClipboardFormatAvailable(format) == 0
                    || OpenClipboard(std::ptr::null_mut()) == 0
                {
                    None
                } else {
                    Some(Self)
                }
            }
        }
    }

    impl Drop for Clipboard {
        fn drop(&mut self) {
            // SAFETY: This guard is created only after OpenClipboard succeeds.
            unsafe { CloseClipboard() };
        }
    }

    pub fn get_text() -> Option<String> {
        let _clipboard = Clipboard::open(CF_UNICODETEXT)?;
        // SAFETY: Clipboard remains open for the whole block. The global handle is locked before reading.
        unsafe {
            let handle = GetClipboardData(CF_UNICODETEXT);
            if handle.is_null() {
                return None;
            }
            let pointer = GlobalLock(handle).cast::<u16>();
            if pointer.is_null() {
                return None;
            }
            let length = GlobalSize(handle) / 2;
            let slice = std::slice::from_raw_parts(pointer, length);
            let end = slice.iter().position(|value| *value == 0).unwrap_or(length);
            let text = String::from_utf16_lossy(&slice[..end]);
            GlobalUnlock(handle);
            Some(text)
        }
    }

    pub fn get_hdrop() -> Option<Vec<String>> {
        let _clipboard = Clipboard::open(CF_HDROP)?;
        // SAFETY: Clipboard remains open and DragQueryFileW only reads the HDROP handle into owned buffers.
        unsafe {
            let handle = GetClipboardData(CF_HDROP);
            if handle.is_null() {
                return None;
            }
            let count = DragQueryFileW(handle, u32::MAX, std::ptr::null_mut(), 0);
            let mut paths = Vec::with_capacity(count as usize);
            for index in 0..count {
                let length = DragQueryFileW(handle, index, std::ptr::null_mut(), 0);
                let mut buffer = vec![0_u16; length as usize + 1];
                DragQueryFileW(handle, index, buffer.as_mut_ptr(), length + 1);
                paths.push(String::from_utf16_lossy(&buffer[..length as usize]));
            }
            Some(paths)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_quoted_windows_paths_without_escaping_backslashes() {
        assert_eq!(
            parse_path_text("\"C:\\a b\\x.txt\" C:\\d\\y.txt"),
            ["C:\\a b\\x.txt", "C:\\d\\y.txt"]
        );
    }
}
