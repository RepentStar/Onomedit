pub fn upper(text: &str) -> String {
    text.to_uppercase()
}

pub fn lower(text: &str) -> String {
    text.to_lowercase()
}

pub fn capitalize(text: &str) -> String {
    let mut chars = text.chars();
    match chars.next() {
        Some(first) => first.to_uppercase().chain(chars).collect(),
        None => String::new(),
    }
}

pub fn title(text: &str) -> String {
    let mut at_word_start = true;
    let mut output = String::with_capacity(text.len());
    for ch in text.chars() {
        if ch.is_alphanumeric() {
            if at_word_start {
                output.extend(ch.to_uppercase());
            } else {
                output.extend(ch.to_lowercase());
            }
            at_word_start = false;
        } else {
            output.push(ch);
            at_word_start = true;
        }
    }
    output
}

pub fn fullwidth(text: &str) -> String {
    text.chars()
        .map(|ch| match ch {
            ' ' => '\u{3000}',
            '!'..='~' => char::from_u32(ch as u32 + 0xfee0).unwrap_or(ch),
            _ => ch,
        })
        .collect()
}

pub fn halfwidth(text: &str) -> String {
    text.chars()
        .map(|ch| match ch {
            '\u{3000}' => ' ',
            '\u{ff01}'..='\u{ff5e}' => char::from_u32(ch as u32 - 0xfee0).unwrap_or(ch),
            _ => ch,
        })
        .collect()
}

pub fn url_decode(text: &str) -> String {
    let bytes = text.as_bytes();
    let mut decoded = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%'
            && i + 2 < bytes.len()
            && let (Some(high), Some(low)) = (hex(bytes[i + 1]), hex(bytes[i + 2]))
        {
            decoded.push(high * 16 + low);
            i += 3;
        } else {
            decoded.push(bytes[i]);
            i += 1;
        }
    }
    String::from_utf8_lossy(&decoded).into_owned()
}

fn hex(value: u8) -> Option<u8> {
    match value {
        b'0'..=b'9' => Some(value - b'0'),
        b'a'..=b'f' => Some(value - b'a' + 10),
        b'A'..=b'F' => Some(value - b'A' + 10),
        _ => None,
    }
}

pub fn apply(kind: &str, text: &str) -> Option<String> {
    Some(match kind {
        "upper" => upper(text),
        "lower" => lower(text),
        "capitalize" => capitalize(text),
        "title" => title(text),
        "fullwidth" => fullwidth(text),
        "halfwidth" => halfwidth(text),
        "urldecode" => url_decode(text),
        _ => return None,
    })
}
