"""环境变量引擎：递增与延续、参数组独立、日期格式、文件相关变量、剪贴板。"""

import datetime
import uuid

from onomedit.core.envvars import DEFAULT_DATE_FORMAT, EnvContext, EnvVars, format_date


def test_n_counter_continues_across_calls():
    e = EnvVars()
    assert e.expand("<n>1;3;1;") == "001"
    assert e.expand("<n>1;3;1;") == "002"
    assert e.expand("<n>1;3;1;") == "003"


def test_n_counter_param_group_isolation():
    e = EnvVars()
    assert e.expand("<n>1;2;1;") == "01"
    assert e.expand("<n>5;2;1;") == "05"  # 起始不同 → 新计数
    assert e.expand("<n>1;2;1;") == "02"  # 原组继续


def test_n_counter_step_and_width():
    e = EnvVars()
    assert e.expand("<n>10;4;5;") == "0010"
    assert e.expand("<n>10;4;5;") == "0015"


def test_n_no_trailing_semicolon():
    e = EnvVars()
    assert e.expand("<n>1;2;1") == "01"  # 无尾部分号也接受


def test_n_inside_text():
    e = EnvVars()
    assert e.expand("img_<n>1;3;1;.png") == "img_001.png"
    assert e.expand("img_<n>1;3;1;.png") == "img_002.png"


def test_new_instance_resets_counter():
    e1 = EnvVars()
    e1.expand("<n>1;2;1;")
    e2 = EnvVars()
    assert e2.expand("<n>1;2;1;") == "01"  # 新批次从起点开始


def test_format_date_tokens():
    dt = datetime.datetime(2026, 8, 12, 9, 5, 3, 123000)
    assert format_date("yyyy-MM-dd", dt) == "2026-08-12"
    assert format_date("yy/M/d", dt) == "26/8/12"
    assert format_date("HH:mm:ss", dt) == "09:05:03"
    assert format_date("hh:mm", dt) == "09:05"
    assert format_date("H:m:s", dt) == "9:5:3"
    assert format_date("fff", dt) == "123"
    assert format_date("", dt) == format_date(DEFAULT_DATE_FORMAT, dt)


def test_d_now_uses_now():
    e = EnvVars()
    out = e.expand("<d>yyyy;")
    assert len(out) == 4 and out.isdigit()


def test_t_and_tc_use_file_times(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x", encoding="utf-8")
    e = EnvVars()
    ctx = EnvContext(file=str(f))
    out = e.expand("<t>yyyy;", context=ctx)
    assert len(out) == 4 and out.isdigit()
    out2 = e.expand("<tc>yyyy;", context=ctx)
    assert len(out2) == 4 and out2.isdigit()


def test_t_without_file_returns_empty():
    e = EnvVars()
    assert e.expand("<t>yyyy;", context=EnvContext(file="")) == ""


def test_f_parent_dir_name(tmp_path):
    d = tmp_path / "album"
    d.mkdir()
    f = d / "img.jpg"
    f.write_text("x", encoding="utf-8")
    e = EnvVars()
    assert e.expand("<f>", context=EnvContext(file=str(f))) == "album"


def test_p_picture_pack_dir_returns_nearest_non_hidden(tmp_path):
    # <p>：从父目录向上找第一个非隐藏目录名
    e = EnvVars()
    # 父目录非隐藏 → 直接返回父目录名
    sub = tmp_path / "album" / "sub"
    sub.mkdir(parents=True)
    f = sub / "img.jpg"
    f.write_text("x", encoding="utf-8")
    assert e.expand("<p>", context=EnvContext(file=str(f))) == "sub"
    # 父目录是隐藏目录（.开头）时向上找
    hidden = tmp_path / "visible2" / ".hidden"
    hidden.mkdir(parents=True)
    g = hidden / "g.jpg"
    g.write_text("x", encoding="utf-8")
    assert e.expand("<p>", context=EnvContext(file=str(g))) == "visible2"


def test_r_random_8_digits():
    e = EnvVars()
    out = e.expand("<r>")
    assert len(out) == 8 and out.isdigit()


def test_rg_uuid():
    e = EnvVars()
    uuid.UUID(e.expand("<rg>"))  # 合法 UUID


def test_clip_single_line_replaces():
    e = EnvVars()
    ctx = EnvContext(file="", clip_text="剪贴板文本")
    assert e.expand("标题-<clip>", context=ctx) == "标题-剪贴板文本"


def test_clip_multiline_skipped():
    e = EnvVars()
    ctx = EnvContext(file="", clip_text="a\nb")
    assert e.expand("标题-<clip>", context=ctx) == "标题-<clip>"  # 原样保留


def test_clip_unavailable_kept():
    e = EnvVars()
    assert e.expand("<clip>", context=EnvContext(file="", clip_text=None)) == "<clip>"


def test_unknown_or_malformed_kept_verbatim():
    e = EnvVars()
    assert e.expand("a <x> b") == "a <x> b"
    assert e.expand("a <n>1;2; b") == "a <n>1;2; b"  # 参数不足
    assert e.expand("a <n> b") == "a <n> b"  # 无参数


def test_multiple_n_share_counter():
    e = EnvVars()
    assert e.expand("a <n>1;2;1; b <n>1;2;1;") == "a 01 b 02"


def test_unclosed_bracket_kept():
    e = EnvVars()
    assert e.expand("abc <n>1;2;1;") == "abc 01"
    assert e.expand("abc <n") == "abc <n"


def test_plain_text_unchanged():
    e = EnvVars()
    assert e.expand("hello world") == "hello world"
