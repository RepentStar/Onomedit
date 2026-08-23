"""冒烟脚本：核心模块导入与基本行为验证（快速回归基准之一）。"""

import datetime
import os
import sys
import tempfile
from pathlib import Path

# Windows 控制台中文输出依赖 UTF-8（与 CLI 行为一致）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from onomedit.core.envvars import EnvVars, format_date
from onomedit.core.pathitem import PathItem
from onomedit.core.pipeline import Renamer, diff_text, levenshtein
from onomedit.core.rules import Rule, apply_rule
from onomedit.utils.safename import sanitize_name


def main() -> None:
    # 路径四段对称性（含点开头、多扩展名）
    p = PathItem("C:/x/y/a.tar.gz")
    assert p.stem == "a.tar" and p.ext == ".gz"
    assert Path(p.with_field("stem", "b")) == Path("C:/x/y/b.gz")
    assert Path(p.with_field("ext", ".md")) == Path("C:/x/y/a.tar.md")
    assert Path(p.with_field("name", "z")) == Path("C:/x/y/z")
    assert p.with_field("full", "X") == "X"
    q = PathItem("/tmp/.gitignore")
    assert q.stem == ".gitignore" and q.ext == ""
    assert Path(q.with_field("name", "x")) == Path("/tmp/x")

    # 环境变量：计数延续 / 参数组独立 / 日期一次到位
    e = EnvVars()
    assert e.expand("<n>1;3;1;") == "001"
    assert e.expand("<n>1;3;1;") == "002"  # 同实例跨调用延续
    e2 = EnvVars()
    assert e2.expand("<n>5;2;1;") == "05"  # 不同参数独立
    assert format_date("yyyy-MM-dd", datetime.datetime(2026, 8, 12, 10, 30)) == "2026-08-12"
    assert format_date("HH:mm:ss", datetime.datetime(2026, 1, 1, 9, 5, 3)) == "09:05:03"

    # 规则
    assert apply_rule("cat", Rule(scope="stem", kind="replace", find="a", replace="b")) == "cbt"
    assert apply_rule("cat", Rule(scope="stem", kind="replace_icase", find="A", replace="X")) == "cXt"
    assert apply_rule("img12", Rule(scope="stem", kind="regex", find=r"(\d+)", replace=r"[\1]")) == "img[12]"
    assert apply_rule("abc", Rule(scope="stem", kind="convert", convert="upper")) == "ABC"
    cond = Rule(scope="stem", kind="replace", find="a", replace="b", condition=r"^c")
    assert apply_rule("cat", cond) == "cbt"
    assert apply_rule("bat", cond) == "bat"  # 条件不匹配跳过

    # 安全命名
    assert sanitize_name("con.txt") == "_con.txt"
    assert sanitize_name("a<b>.txt") == "a_b_.txt"
    assert sanitize_name("name. ") == "name"
    assert sanitize_name("COM1") == "_COM1"

    # 距离/差异
    assert levenshtein("kitten", "sitting") == 3
    assert "[-b-]" in diff_text("abc", "axc") and "[+x+]" in diff_text("abc", "axc")

    # 执行器：普通重命名 / 交换解环
    tmp = tempfile.mkdtemp()
    a = os.path.join(tmp, "a.txt")
    b = os.path.join(tmp, "b.txt")
    with open(a, "w") as f:
        f.write("1")
    with open(b, "w") as f:
        f.write("2")
    res = Renamer().run([(a, os.path.join(tmp, "c.txt"))])
    assert len(res.success) == 1 and os.path.exists(os.path.join(tmp, "c.txt"))

    x = os.path.join(tmp, "x.txt")
    y = os.path.join(tmp, "y.txt")
    with open(x, "w") as f:
        f.write("x")
    with open(y, "w") as f:
        f.write("y")
    res = Renamer().run([(x, y), (y, x)])  # 交换
    assert len(res.success) == 2, res
    assert open(y).read() == "x" and open(x).read() == "y"

    print("冒烟测试通过 ✔")


if __name__ == "__main__":
    main()
