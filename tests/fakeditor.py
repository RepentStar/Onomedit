"""假编辑器工具（文档第九节：可记录被调用、可修改临时文件模拟保存、可立即退出模拟启动器）。

用法（作为外部编辑器命令被 onomedit 启动）::

    python fakeditor.py <临时文件> <模式> [参数...]

模式:
    exit        立即退出且不修改文件（模拟启动器型 / 用户未改关闭）
    save        立即在文件末尾追加一行并退出（模拟用户保存）
    set         把第 <行号> 行替换为 <内容> 后退出（模拟用户编辑）
    delay       休眠 <秒> 后追加一行并退出（模拟用户在编辑器中停留后保存）
    launcher    立即退出且不修改（配合外部线程延迟修改，测试轮询等待）
"""

import json
import os
import sys
import time


def _log_call(argv: list[str]) -> None:
    log_path = os.environ.get("FAKE_EDITOR_LOG")
    if not log_path:
        return
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"argv": argv, "pid": os.getpid(), "cwd": os.getcwd()},
                ensure_ascii=False,
            )
            + "\n"
        )


def main() -> int:
    # 真实编辑器约定：最后一个参数是要打开的文件；前面依次是模式与附加参数。
    # 命令形态: python fakeditor.py <模式> [参数...] <文件>
    if len(sys.argv) < 2:
        return 2
    path = sys.argv[-1]
    mode = sys.argv[1] if len(sys.argv) > 1 else "exit"
    args = sys.argv[2:-1]
    _log_call(sys.argv)

    if mode == "save":
        with open(path, "a", encoding="utf-8") as f:
            f.write("\nsaved")
    elif mode == "set":
        lineno = int(args[0]) if args else 1
        content = args[1] if len(args) > 1 else "edited"
        lines = open(path, encoding="utf-8").read().splitlines()
        if 1 <= lineno <= len(lines):
            lines[lineno - 1] = content
        else:
            lines.append(content)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    elif mode == "delay":
        time.sleep(float(args[0]) if args else 0.5)
        with open(path, "a", encoding="utf-8") as f:
            f.write("\nsaved")
    elif mode == "truncate":
        # 只保留前 N 行（模拟用户删行，用于行数校验失败测试）
        keep = int(args[0]) if args else 1
        lines = open(path, encoding="utf-8").read().splitlines()
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            if lines[:keep]:
                f.write("\n".join(lines[:keep]) + "\n")
    # exit / launcher：立即退出，不修改
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
