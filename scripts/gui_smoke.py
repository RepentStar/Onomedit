"""GUI 冒烟：创建主窗口 / 设置窗口 / 列表窗口并自动关闭（不进入人工交互）。

覆盖：窗口可创建、默认全选、相对路径显示、差异/距离列动态隐藏、目录展开显示。
注意：隔离配置目录，避免读取/影响用户真实 %APPDATA%\\Onomedit。
"""

import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    # 隔离配置目录（在构造 MainWindow 之前设置）
    isolated = tempfile.mkdtemp(prefix="onomedit_gui_smoke_")
    if os.name == "nt":
        os.environ["APPDATA"] = os.path.join(isolated, "appdata")
    else:
        os.environ["XDG_CONFIG_HOME"] = os.path.join(isolated, "xdg")

    try:
        import ttkbootstrap as tb
    except ImportError:
        print("缺少 ttkbootstrap，跳过 GUI 冒烟")
        return 0

    from onomedit.core import config as config_mod
    from onomedit.gui.app import MainWindow
    from onomedit.gui.listview import ListWindow
    from onomedit.gui.settings import SettingsWindow

    root = tb.Window(themename="flatly")
    win = MainWindow(root)
    assert win.listbox is not None
    assert win.cfg.skip_confirmation is True  # 跳过重命名确认默认开启
    assert win.cfg.exit_after is True  # 完成后退出默认开启

    # 1) 目录展开：勾选「展开子文件夹」后添加文件夹 → 列表立即展开显示
    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "sub"), exist_ok=True)
    open(os.path.join(tmp, "a.txt"), "w").close()
    open(os.path.join(tmp, "sub", "b.txt"), "w").close()
    win.subdirs_var.set(True)
    win.depth_var.set(1)
    win._add_paths([tmp])
    shown = list(win.listbox.get(0, "end"))
    assert any(x.endswith("a.txt") for x in shown), f"应显示展开后的文件: {shown}"
    assert any(x.endswith(os.sep + "sub") for x in shown), f"应显示层级 1 的子目录: {shown}"
    assert not any(x.endswith("b.txt") for x in shown), f"层级 1 不应显示更深文件: {shown}"

    # 2) 取消展开 → 只显示目录本身
    win.subdirs_var.set(False)
    win._refresh()
    shown = list(win.listbox.get(0, "end"))
    assert shown == [tmp], f"未勾选展开应只显示目录本身: {shown}"

    # 3) 确认窗口：默认配置（差异/距离关闭）→ 只有 2 列
    lw = ListWindow(root, [("C:/x/a.txt", "C:/x/b.txt"), ("C:/x/c.txt", "C:/x/c.txt")], base="C:/x")
    assert lw.tree is not None
    assert len(lw.tree.selection()) == 2  # 默认全选
    assert lw._display("C:/x/a.txt") == "a.txt"  # 相对路径
    assert len(lw.tree["columns"]) == 2, f"差异/距离关闭时应只有 2 列: {lw.tree['columns']}"

    # 4) 开启差异/距离 → 确认窗口 4 列
    cfg4 = config_mod.default_config()
    cfg4.preview.diff = True
    cfg4.preview.distance = True
    lw4 = ListWindow(root, [("C:/x/a.txt", "C:/x/b.txt")], cfg=cfg4, base="C:/x")
    assert len(lw4.tree["columns"]) == 4, f"开启后应为 4 列: {lw4.tree['columns']}"

    sw = SettingsWindow(root)

    root.after(600, root.destroy)
    root.mainloop()
    print("GUI 冒烟通过 ✔（窗口创建/默认全选/相对路径/列动态隐藏/目录展开）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
