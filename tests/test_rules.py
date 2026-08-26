"""编辑规则：替换（三种）/ 转换 / 插入 / 条件跳过 / 序列化。"""

import pytest

from onomedit.core.rules import (
    INSERT_END,
    INSERT_START,
    KIND_CONVERT,
    KIND_INSERT,
    KIND_REGEX,
    KIND_REPLACE,
    KIND_REPLACE_ICASE,
    Rule,
    apply_rule,
    rule_from_dict,
    rule_to_dict,
)


def test_replace_case_sensitive():
    r = Rule(kind=KIND_REPLACE, find="a", replace="X")
    assert apply_rule("banana", r) == "bXnXnX"
    assert apply_rule("Banana", r) == "BXnXnX"  # 大小写敏感：首字母 B 不替换


def test_replace_icase():
    r = Rule(kind=KIND_REPLACE_ICASE, find="a", replace="X")
    assert apply_rule("Banana", r) == "BXnXnX"


def test_replace_empty_find_noop():
    r = Rule(kind=KIND_REPLACE, find="", replace="X")
    assert apply_rule("abc", r) == "abc"


def test_regex():
    r = Rule(kind=KIND_REGEX, find=r"(\d+)", replace=r"[\1]")
    assert apply_rule("img12x34", r) == "img[12]x[34]"


def test_regex_invalid_pattern_keeps_value():
    r = Rule(kind=KIND_REGEX, find="(", replace="X")
    assert apply_rule("abc", r) == "abc"


def test_convert_dispatch():
    assert apply_rule("abc", Rule(kind=KIND_CONVERT, convert="upper")) == "ABC"
    assert apply_rule("ABC", Rule(kind=KIND_CONVERT, convert="lower")) == "abc"
    assert apply_rule("abc", Rule(kind=KIND_CONVERT, convert="capitalize")) == "Abc"
    assert apply_rule("abc", Rule(kind=KIND_CONVERT, convert="title")) == "Abc"
    assert (
        apply_rule("abc", Rule(kind=KIND_CONVERT, convert="unknown")) == "abc"
    )  # 未知转换跳过


def test_insert_start_and_end():
    assert (
        apply_rule("abc", Rule(kind=KIND_INSERT, insert=">", insert_at=INSERT_START))
        == ">abc"
    )
    assert (
        apply_rule("abc", Rule(kind=KIND_INSERT, insert="<", insert_at=INSERT_END))
        == "abc<"
    )


def test_env_kind_passthrough():
    r = Rule(kind="env")
    assert apply_rule("abc", r) == "abc"  # 环境变量阶段统一展开


def test_condition_skip():
    r = Rule(kind=KIND_REPLACE, find="a", replace="b", condition=r"^cat")
    assert apply_rule("cat", r) == "cbt"
    assert apply_rule("bat", r) == "bat"  # 条件不匹配 → 跳过


def test_disabled_rule_noop():
    r = Rule(kind=KIND_REPLACE, find="a", replace="b", enabled=False)
    assert apply_rule("cat", r) == "cat"


def test_rule_serialization_roundtrip():
    r = Rule(
        scope="ext",
        kind=KIND_REGEX,
        find=r"\.(jpg|jpeg)",
        replace=".png",
        condition="x",
        enabled=False,
    )
    restored = rule_from_dict(rule_to_dict(r))
    assert restored == r
    assert restored.scope == "ext"
    assert restored.enabled is False


def test_invalid_rule_fields():
    with pytest.raises(ValueError):
        Rule(scope="bogus")
    with pytest.raises(ValueError):
        Rule(kind="bogus")
    with pytest.raises(ValueError):
        Rule(insert_at="middle")
