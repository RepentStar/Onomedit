"""编辑规则：替换/转换/插入/环境变量应用于指定字段。

三种替换（普通区分大小写 / 普通不区分大小写 / 正则）+ 转换 + 插入 + 环境变量标记。
规则可作用于四档路径类型之一，可带条件表达式（不匹配则跳过）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from onomedit.core.pathitem import PATH_TYPES
from onomedit.utils import transforms

# 规则种类
KIND_REPLACE = "replace"  # 普通（区分大小写）
KIND_REPLACE_ICASE = "replace_icase"  # 普通（不区分大小写）
KIND_REGEX = "regex"
KIND_CONVERT = "convert"
KIND_INSERT = "insert"
KIND_ENV = "env"  # 仅标记：字段在环境变量阶段统一展开

RULE_KINDS = (KIND_REPLACE, KIND_REPLACE_ICASE, KIND_REGEX, KIND_CONVERT, KIND_INSERT, KIND_ENV)

# 插入位置
INSERT_START = "start"
INSERT_END = "end"


@dataclass
class Rule:
    scope: str = "name"  # 作用字段：full | name | stem | ext
    kind: str = KIND_REPLACE
    find: str = ""  # replace / regex 的查找串
    replace: str = ""  # 替换为（可含环境变量占位符，最后统一展开）
    convert: str = ""  # convert 种类：upper/lower/capitalize/title/fullwidth/halfwidth/urldecode
    insert: str = ""  # insert 文本
    insert_at: str = INSERT_START  # start | end
    condition: str = ""  # 可选正则；字段值不匹配时规则跳过
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.scope not in PATH_TYPES:
            raise ValueError(f"未知作用字段: {self.scope}")
        if self.kind not in RULE_KINDS:
            raise ValueError(f"未知规则种类: {self.kind}")
        if self.insert_at not in (INSERT_START, INSERT_END):
            raise ValueError(f"未知插入位置: {self.insert_at}")


def apply_rule(value: str, rule: Rule) -> str:
    """对字段值应用单条规则；条件不满足或规则禁用时原样返回。"""
    if not rule.enabled:
        return value
    if rule.condition:
        try:
            if re.search(rule.condition, value) is None:
                return value
        except re.error:
            return value
    if rule.kind == KIND_REPLACE:
        if not rule.find:
            return value
        return value.replace(rule.find, rule.replace)
    if rule.kind == KIND_REPLACE_ICASE:
        if not rule.find:
            return value
        return re.sub(re.escape(rule.find), lambda _: rule.replace, value, flags=re.IGNORECASE)
    if rule.kind == KIND_REGEX:
        if not rule.find:
            return value
        try:
            return re.sub(rule.find, rule.replace, value)
        except re.error:
            return value
    if rule.kind == KIND_CONVERT:
        fn = transforms.CONVERSIONS.get(rule.convert)
        if fn is None:
            return value
        return fn(value)
    if rule.kind == KIND_INSERT:
        if not rule.insert:
            return value
        return value + rule.insert if rule.insert_at == INSERT_END else rule.insert + value
    if rule.kind == KIND_ENV:
        # 环境变量展开由主流程统一执行（保持顺序固定：最后展开）
        return value
    return value


def rule_to_dict(rule: Rule) -> dict:
    return {
        "scope": rule.scope,
        "kind": rule.kind,
        "find": rule.find,
        "replace": rule.replace,
        "convert": rule.convert,
        "insert": rule.insert,
        "insert_at": rule.insert_at,
        "condition": rule.condition,
        "enabled": rule.enabled,
    }


def rule_from_dict(data: dict) -> Rule:
    return Rule(
        scope=data.get("scope", "name"),
        kind=data.get("kind", KIND_REPLACE),
        find=data.get("find", ""),
        replace=data.get("replace", ""),
        convert=data.get("convert", ""),
        insert=data.get("insert", ""),
        insert_at=data.get("insert_at", INSERT_START),
        condition=data.get("condition", ""),
        enabled=data.get("enabled", True),
    )


def field_names() -> tuple[str, ...]:
    return PATH_TYPES
