"""字符串转换工具：大小写、首字母、全半角、URI 解码。

均为纯函数，供编辑规则（convert）调用。
"""

from __future__ import annotations

from urllib.parse import unquote


def to_upper(text: str) -> str:
    return text.upper()


def to_lower(text: str) -> str:
    return text.lower()


def to_capitalize(text: str) -> str:
    """首字母大写，其余保持原样。"""
    if not text:
        return text
    return text[0].upper() + text[1:]


def to_title(text: str) -> str:
    return text.title()


def to_fullwidth(text: str) -> str:
    """半角 → 全角（ASCII 0x20-0x7E 映射到 U+3000 / U+FF01-U+FF5E）。"""
    out = []
    for ch in text:
        code = ord(ch)
        if code == 0x20:
            out.append("\u3000")
        elif 0x21 <= code <= 0x7E:
            out.append(chr(code + 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


def to_halfwidth(text: str) -> str:
    """全角 → 半角（U+3000 / U+FF01-U+FF5E 映射回 ASCII）。"""
    out = []
    for ch in text:
        code = ord(ch)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


def urldecode(text: str) -> str:
    """URI 百分比解码（%20 → 空格 等）。"""
    return unquote(text)


CONVERSIONS: dict[str, callable] = {
    "upper": to_upper,
    "lower": to_lower,
    "capitalize": to_capitalize,
    "title": to_title,
    "fullwidth": to_fullwidth,
    "halfwidth": to_halfwidth,
    "urldecode": urldecode,
}
