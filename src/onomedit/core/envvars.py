"""环境变量引擎：``<n>`` ``<d>`` 等占位符替换。

- ``<n>`` 计数跨文件延续，按 (起始, 位数, 步长) 整组共享计数。
- 日期格式直接 token 替换，不经过二次格式化。
- ``<r>`` / ``<rg>`` 每处独立；``<clip>`` 仅单行剪贴板替换，多行跳过。
"""

from __future__ import annotations

import datetime
import os
import random
import uuid

# 变量名 → 参数个数（n=3：起始/位数/步长；d/t/tc=1：格式；其余 0）
VAR_ARITY = {
    "n": 3,
    "d": 1,
    "t": 1,
    "tc": 1,
    "f": 0,
    "p": 0,
    "r": 0,
    "rg": 0,
    "clip": 0,
}

DEFAULT_DATE_FORMAT = "yyyy-MM-dd HH:mm:ss"


class EnvContext:
    """展开上下文：当前文件路径、剪贴板文本。"""

    __slots__ = ("clip_text", "file")

    def __init__(self, file: str = "", clip_text: str | None = None):
        self.file = file
        self.clip_text = clip_text


class EnvVars:
    """批次级环境变量引擎：计数状态跨文件延续（同批共享一个实例）。"""

    def __init__(self) -> None:
        self._counters: dict[tuple[int, int, int], int] = {}

    def expand(self, text: str, *, context: EnvContext | None = None) -> str:
        if "<" not in text:
            return text
        out: list[str] = []
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            if ch != "<":
                out.append(ch)
                i += 1
                continue
            close = text.find(">", i + 1)
            if close == -1:
                out.append(text[i:])
                break
            name = text[i + 1 : close]
            arity = VAR_ARITY.get(name)
            if arity is None:
                # 不是已知变量：原样保留 `<`，继续扫描
                out.append("<")
                i += 1
                continue
            args: list[str] = []
            pos = close + 1
            ok = True
            for k in range(arity):
                semi = text.find(";", pos)
                if semi == -1:
                    if k == arity - 1:
                        args.append(text[pos:])
                        pos = len(text)
                    else:
                        ok = False
                        break
                else:
                    args.append(text[pos:semi])
                    pos = semi + 1
            if not ok:
                out.append("<")
                i += 1
                continue
            replacement = self._build(name, args, context)
            if replacement is None:
                # 无法解析/不适用（如多行剪贴板）：原样保留
                out.append("<")
                i += 1
                continue
            out.append(replacement)
            i = pos
        return "".join(out)

    def _build(self, name: str, args: list[str], ctx: EnvContext | None) -> str | None:
        if name == "n":
            try:
                start = int(args[0].strip())
                width = int(args[1].strip())
                step = int(args[2].strip())
            except (ValueError, IndexError):
                return None
            width = max(width, 1)
            step = max(step, 1)
            key = (start, width, step)
            cur = self._counters.get(key)
            cur = start if cur is None else cur + step
            self._counters[key] = cur
            return f"{cur:0{width}d}"
        if name == "d":
            pattern = args[0] if args and args[0] else DEFAULT_DATE_FORMAT
            return format_date(pattern, datetime.datetime.now())
        if name in ("t", "tc"):
            if not ctx or not ctx.file:
                return ""
            try:
                st = os.stat(ctx.file)
            except OSError:
                return ""
            ts = st.st_mtime if name == "t" else st.st_ctime
            pattern = args[0] if args and args[0] else DEFAULT_DATE_FORMAT
            return format_date(pattern, datetime.datetime.fromtimestamp(ts))
        if name == "f":
            if not ctx or not ctx.file:
                return ""
            return os.path.basename(os.path.dirname(ctx.file))
        if name == "p":
            # 图包目录：从父目录向上找第一个非隐藏目录名
            if not ctx or not ctx.file:
                return ""
            d = os.path.dirname(ctx.file)
            while d:
                base = os.path.basename(d)
                if base and not base.startswith("."):
                    return base
                parent = os.path.dirname(d)
                if parent == d:
                    break
                d = parent
            return ""
        if name == "r":
            return f"{random.randint(0, 99999999):08d}"
        if name == "rg":
            return str(uuid.uuid4())
        if name == "clip":
            clip = ctx.clip_text if ctx else None
            if clip is None or "\n" in clip or "\r" in clip:
                return None  # 无法读取或多行：原样保留
            return clip
        return None


def format_date(pattern: str, dt: datetime.datetime) -> str:
    """按原版语法（yyyy/MM/dd/HH/mm/ss 等）一次到位格式化。"""
    if not pattern:
        pattern = DEFAULT_DATE_FORMAT
    # 长 token 在前，避免子串误替换（yyyy 先于 yy、MM 先于 M …）
    repls = [
        ("yyyy", f"{dt.year:04d}"),
        ("yy", f"{dt.year % 100:02d}"),
        ("MM", f"{dt.month:02d}"),
        ("M", str(dt.month)),
        ("dd", f"{dt.day:02d}"),
        ("d", str(dt.day)),
        ("HH", f"{dt.hour:02d}"),
        ("H", str(dt.hour)),
        ("hh", f"{dt.hour % 12 or 12:02d}"),
        ("h", str(dt.hour % 12 or 12)),
        ("mm", f"{dt.minute:02d}"),
        ("m", str(dt.minute)),
        ("ss", f"{dt.second:02d}"),
        ("s", str(dt.second)),
        ("fff", f"{dt.microsecond // 1000:03d}"),
    ]
    out = pattern
    for tok, val in repls:
        out = out.replace(tok, val)
    return out
