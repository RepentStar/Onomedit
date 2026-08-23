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
    let mut prefix = 0;
    while prefix < a.len() && prefix < b.len() && a[prefix] == b[prefix] {
        prefix += 1;
    }
    let mut suffix = 0;
    while suffix < a.len() - prefix
        && suffix < b.len() - prefix
        && a[a.len() - suffix - 1] == b[b.len() - suffix - 1]
    {
        suffix += 1;
    }
    let mut out: String = a[..prefix].iter().collect();
    if prefix + suffix < a.len() {
        out.push_str("[-");
        out.extend(&a[prefix..a.len() - suffix]);
        out.push_str("-]");
    }
    if prefix + suffix < b.len() {
        out.push_str("[+");
        out.extend(&b[prefix..b.len() - suffix]);
        out.push_str("+]");
    }
    out.extend(&a[a.len() - suffix..]);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn distance_and_simple_diff() {
        assert_eq!(levenshtein("kitten", "sitting"), 3);
        assert_eq!(diff_text("/d/a.txt", "/d/b.txt"), "/d/[-a-][+b+].txt");
    }
}
