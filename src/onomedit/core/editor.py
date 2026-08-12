"""编辑器等待策略（多次踩坑，语义必须保留）。

- 单实例型（记事本等）：进程退出即编辑结束。
- 启动器/多实例型（VSCode、已运行的 Notepad++ 等）：启动器把文件交给已有实例后立即退出，
  进程退出不代表编辑结束，须轮询等待文件被保存。
- 终端型（vim 等）：同单实例型。

默认等进程退出；进程快速退出且文件未改 → 判定为启动器型，改为轮询等待保存。
显式"多标签"配置时不依赖进程退出，直接轮询等待保存。"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import threading
import time

from onomedit.core import tempfile_mgr

# 快速退出经验阈值（秒）：更短且文件未改 → 判定启动器型
QUICK_EXIT_SECONDS = 2.0
# 轮询间隔（秒）
POLL_INTERVAL = 0.3
# 进程退出轮询间隔（秒）
PROCESS_POLL_INTERVAL = 0.05
# 等待编辑器主窗口出现并聚焦的最长时间（秒）
FOCUS_TIMEOUT = 5.0


class EditorError(RuntimeError):
    """编辑器命令无法启动。"""


def split_command(cmd: str) -> list[str]:
    """解析编辑器命令字符串为参数列表（支持带引号的路径）。"""
    if not cmd.strip():
        raise EditorError("编辑器命令为空，请先配置（config set-editor / config set editor）")
    if os.name == "nt":
        return shlex.split(cmd, posix=False)
    return shlex.split(cmd)


def _resolve_command(args: list[str]) -> tuple[str, bool]:
    """解析命令第一个 token，返回 (实际命令, 是否需经 shell 执行)。

    Windows 上 ``code`` 等命令实际是 ``.cmd``/``.bat`` 批处理脚本，
    CreateProcess 无法直接执行（报 WinError 2，但用户在终端手动执行没问题），
    须经 ``cmd /c``（shell）启动。找不到可执行文件时抛 EditorError。
    """
    first = args[0]
    if os.name != "nt":
        return first, False
    exe = shutil.which(first)
    if exe is None:
        raise EditorError(
            f"找不到可执行文件 {first!r}，请检查 PATH 或配置编辑器完整路径"
        )
    return exe, exe.lower().endswith((".cmd", ".bat"))


def launch_and_wait(
    editor_cmd: str,
    temp_path,
    sig: tuple[float, int],
    *,
    multi_tab: bool = False,
    timeout: float = 120.0,
    on_status=None,
) -> None:
    """启动外部编辑器并等待编辑完成（等待策略核心）。

    :param editor_cmd: 编辑器命令（可带参数）
    :param temp_path: 临时文件路径
    :param sig: 启动前记录的临时文件签名
    :param multi_tab: 显式"多标签"配置
    :param timeout: 总等待超时（秒）
    :param on_status: 状态提示回调
    """
    args = split_command(editor_cmd)
    exe, via_shell = _resolve_command(args)
    # 临时文件路径作为编辑器命令的最后一个参数（编辑器打开它）
    cmd_args = [exe, *args[1:], os.fspath(temp_path)]
    try:
        if via_shell:
            # 批处理（code.cmd 等）：CreateProcess 不能直接执行，经 cmd /c
            proc = subprocess.Popen(subprocess.list2cmdline(cmd_args), shell=True)
        else:
            proc = subprocess.Popen(cmd_args)
    except OSError as e:
        raise EditorError(f"无法启动编辑器 {editor_cmd!r}: {e}") from e

    # 后台线程把焦点转到编辑器主窗口（GUI 点击「开始」后的体验）
    threading.Thread(target=_focus_editor_window, args=(proc.pid,), daemon=True).start()

    status = on_status or (lambda msg: None)
    start = time.monotonic()

    if multi_tab:
        # 多标签型：不依赖进程退出，直接轮询等保存
        status("编辑器已启动（多标签模式），等待文件保存…")
        _poll_save(temp_path, sig, timeout, status)
        return

    # 默认：等待进程退出（有限超时）
    while True:
        if proc.poll() is not None:
            elapsed = time.monotonic() - start
            if elapsed < QUICK_EXIT_SECONDS and not tempfile_mgr.changed(
                sig, tempfile_mgr.signature(temp_path)
            ):
                # 快速退出且文件未修改 → 启动器型：轮询等待用户保存
                status("检测到启动器型编辑器，等待文件保存（超时后放弃）…")
                _poll_save(temp_path, sig, timeout, status)
            return  # 文件已保存或进程存活较久后退出 → 正常继续
        if time.monotonic() - start > timeout:
            status(f"等待编辑器超时（{timeout:.0f}s），按当前内容继续")
            return
        time.sleep(PROCESS_POLL_INTERVAL)


def _poll_save(temp_path, sig, timeout: float, status) -> None:
    """轮询等待临时文件被修改（用户保存）；超时后放弃。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if tempfile_mgr.changed(sig, tempfile_mgr.signature(temp_path)):
            return
        time.sleep(POLL_INTERVAL)
    status("等待保存超时，继续处理")


# ---------------------------------------------------------------- 焦点转移
def _focus_editor_window(pid: int) -> None:
    """后台线程：等待编辑器主窗口出现并把前台焦点转给它（Windows）。

    非 Windows 或无可见窗口（如无 GUI 的假编辑器）时静默跳过，绝不阻塞主流程。
    """
    if os.name != "nt":
        return
    import ctypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    void_p = ctypes.c_void_p
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, void_p, void_p)
    user32.EnumWindows.argtypes = [WNDENUMPROC, void_p]
    user32.EnumWindows.restype = ctypes.c_bool
    user32.GetWindowThreadProcessId.argtypes = [void_p, ctypes.POINTER(ctypes.c_uint)]
    user32.GetWindowThreadProcessId.restype = ctypes.c_uint
    user32.IsWindowVisible.argtypes = [void_p]
    user32.IsWindowVisible.restype = ctypes.c_bool
    user32.SetForegroundWindow.argtypes = [void_p]
    user32.SetForegroundWindow.restype = ctypes.c_bool
    user32.BringWindowToTop.argtypes = [void_p]
    user32.BringWindowToTop.restype = ctypes.c_bool

    found: list[int] = []

    @WNDENUMPROC
    def _enum(hwnd, _lparam) -> bool:  # noqa: N803 - Win32 回调参数名
        process_id = ctypes.c_uint()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    deadline = time.monotonic() + FOCUS_TIMEOUT
    while time.monotonic() < deadline and not found:
        try:
            user32.EnumWindows(_enum, None)
        except Exception:  # noqa: BLE001 - 聚焦是尽力而为
            return
        if not found:
            time.sleep(0.3)
    if found:
        try:
            user32.SetForegroundWindow(found[0])
            user32.BringWindowToTop(found[0])
        except Exception:  # noqa: BLE001 - 聚焦失败不影响流程
            pass
