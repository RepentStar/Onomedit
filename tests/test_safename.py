"""安全命名：非法字符替换、保留名、结尾点/空格、重名序号。"""

from onomedit.utils.safename import sanitize_name, unique_path


def test_illegal_chars_replaced():
    assert sanitize_name('a<b>:c"d/e\\f|g?h*i.txt') == "a_b__c_d_e_f_g_h_i.txt"


def test_control_chars_replaced():
    # 每个控制字符各替换为一个下划线
    assert sanitize_name("a\x00b\x1fc.txt") == "a_b_c.txt"


def test_strip_and_trailing_dot_space():
    assert sanitize_name("  name  ") == "name"
    assert sanitize_name("name. ") == "name"
    assert sanitize_name("name...") == "name"


def test_reserved_names():
    for name in ("CON", "con", "PrN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9"):
        assert sanitize_name(name + ".txt").startswith("_"), name
    assert sanitize_name("CON.txt") == "_CON.txt"
    assert sanitize_name("console.txt") == "console.txt"  # 非保留名不动


def test_empty_name_passthrough():
    assert sanitize_name("") == ""
    assert sanitize_name("...") == "_"


def test_unique_path_no_conflict(tmp_path):
    target = tmp_path / "a.txt"
    assert unique_path(target) == target


def test_unique_path_numbering(tmp_path):
    (tmp_path / "a.txt").write_text("1", encoding="utf-8")
    (tmp_path / "a (1).txt").write_text("2", encoding="utf-8")
    result = unique_path(tmp_path / "a.txt")
    assert result == tmp_path / "a (2).txt"


def test_unique_path_keeps_extension(tmp_path):
    (tmp_path / "x.tar.gz").write_text("1", encoding="utf-8")
    result = unique_path(tmp_path / "x.tar.gz")
    assert result.name == "x.tar (1).gz"
