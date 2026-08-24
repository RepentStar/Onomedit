use std::collections::{HashMap, HashSet};

pub fn levenshtein(a: &str, b: &str) -> usize {
    let mut a: Vec<char> = a.chars().collect();
    let mut b: Vec<char> = b.chars().collect();
    if a.len() < b.len() {
        std::mem::swap(&mut a, &mut b);
    }
    if b.is_empty() {
        return a.len();
    }
    let mut previous: Vec<usize> = (0..=b.len()).collect();
    for (i, ca) in a.iter().enumerate() {
        let mut current = vec![i + 1];
        for (j, cb) in b.iter().enumerate() {
            current.push(
                (previous[j + 1] + 1)
                    .min(current[j] + 1)
                    .min(previous[j] + usize::from(ca != cb)),
            );
        }
        previous = current;
    }
    previous[b.len()]
}

pub fn diff_text(a: &str, b: &str) -> String {
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();
    let mut out = String::new();
    for opcode in opcodes(&a, &b) {
        match opcode.tag {
            Tag::Equal => out.extend(&a[opcode.a_start..opcode.a_end]),
            Tag::Delete => {
                out.push_str("[-");
                out.extend(&a[opcode.a_start..opcode.a_end]);
                out.push_str("-]");
            }
            Tag::Insert => {
                out.push_str("[+");
                out.extend(&b[opcode.b_start..opcode.b_end]);
                out.push_str("+]");
            }
            Tag::Replace => {
                out.push_str("[-");
                out.extend(&a[opcode.a_start..opcode.a_end]);
                out.push_str("-][+");
                out.extend(&b[opcode.b_start..opcode.b_end]);
                out.push_str("+]");
            }
        }
    }
    out
}

#[derive(Clone, Copy)]
struct Match {
    a: usize,
    b: usize,
    size: usize,
}

#[derive(Clone, Copy)]
enum Tag {
    Equal,
    Delete,
    Insert,
    Replace,
}

struct Opcode {
    tag: Tag,
    a_start: usize,
    a_end: usize,
    b_start: usize,
    b_end: usize,
}

fn opcodes(a: &[char], b: &[char]) -> Vec<Opcode> {
    let mut result = Vec::new();
    let mut a_start = 0;
    let mut b_start = 0;
    for block in matching_blocks(a, b) {
        let tag = match (a_start < block.a, b_start < block.b) {
            (true, true) => Some(Tag::Replace),
            (true, false) => Some(Tag::Delete),
            (false, true) => Some(Tag::Insert),
            (false, false) => None,
        };
        if let Some(tag) = tag {
            result.push(Opcode {
                tag,
                a_start,
                a_end: block.a,
                b_start,
                b_end: block.b,
            });
        }
        if block.size > 0 {
            result.push(Opcode {
                tag: Tag::Equal,
                a_start: block.a,
                a_end: block.a + block.size,
                b_start: block.b,
                b_end: block.b + block.size,
            });
        }
        a_start = block.a + block.size;
        b_start = block.b + block.size;
    }
    result
}

fn matching_blocks(a: &[char], b: &[char]) -> Vec<Match> {
    let b_to_indices = index_sequence(b);
    let mut queue = vec![(0, a.len(), 0, b.len())];
    let mut blocks = Vec::new();
    while let Some((a_low, a_high, b_low, b_high)) = queue.pop() {
        let found = find_longest_match(a, b, &b_to_indices, a_low, a_high, b_low, b_high);
        if found.size == 0 {
            continue;
        }
        blocks.push(found);
        if a_low < found.a && b_low < found.b {
            queue.push((a_low, found.a, b_low, found.b));
        }
        if found.a + found.size < a_high && found.b + found.size < b_high {
            queue.push((found.a + found.size, a_high, found.b + found.size, b_high));
        }
    }
    blocks.sort_by_key(|block| (block.a, block.b));

    let mut collapsed: Vec<Match> = Vec::new();
    for block in blocks {
        if let Some(previous) = collapsed.last_mut()
            && previous.a + previous.size == block.a
            && previous.b + previous.size == block.b
        {
            previous.size += block.size;
            continue;
        }
        collapsed.push(block);
    }
    collapsed.push(Match {
        a: a.len(),
        b: b.len(),
        size: 0,
    });
    collapsed
}

fn index_sequence(sequence: &[char]) -> HashMap<char, Vec<usize>> {
    let mut indices: HashMap<char, Vec<usize>> = HashMap::new();
    for (index, ch) in sequence.iter().copied().enumerate() {
        indices.entry(ch).or_default().push(index);
    }
    if sequence.len() >= 200 {
        let popular_threshold = sequence.len() / 100 + 1;
        let popular: HashSet<char> = indices
            .iter()
            .filter_map(|(ch, positions)| (positions.len() > popular_threshold).then_some(*ch))
            .collect();
        indices.retain(|ch, _| !popular.contains(ch));
    }
    indices
}

fn find_longest_match(
    a: &[char],
    b: &[char],
    b_to_indices: &HashMap<char, Vec<usize>>,
    a_low: usize,
    a_high: usize,
    b_low: usize,
    b_high: usize,
) -> Match {
    let mut best = Match {
        a: a_low,
        b: b_low,
        size: 0,
    };
    let mut previous_lengths: HashMap<usize, usize> = HashMap::new();
    for (a_index, ch) in a.iter().enumerate().take(a_high).skip(a_low) {
        let mut current_lengths = HashMap::new();
        if let Some(b_indices) = b_to_indices.get(ch) {
            for &b_index in b_indices {
                if b_index < b_low {
                    continue;
                }
                if b_index >= b_high {
                    break;
                }
                let size = previous_lengths
                    .get(&b_index.wrapping_sub(1))
                    .copied()
                    .unwrap_or(0)
                    + 1;
                current_lengths.insert(b_index, size);
                if size > best.size {
                    best = Match {
                        a: a_index + 1 - size,
                        b: b_index + 1 - size,
                        size,
                    };
                }
            }
        }
        previous_lengths = current_lengths;
    }

    while best.a > a_low && best.b > b_low && a[best.a - 1] == b[best.b - 1] {
        best.a -= 1;
        best.b -= 1;
        best.size += 1;
    }
    while best.a + best.size < a_high
        && best.b + best.size < b_high
        && a[best.a + best.size] == b[best.b + best.size]
    {
        best.size += 1;
    }
    best
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn distance_and_simple_diff() {
        assert_eq!(levenshtein("kitten", "sitting"), 3);
        assert_eq!(diff_text("/d/a.txt", "/d/b.txt"), "/d/[-a-][+b+].txt");
        assert_eq!(diff_text("qabxcd", "abycdf"), "[-q-]ab[-x-][+y+]cd[+f+]");
    }
}
