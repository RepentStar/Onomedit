"""GUI 层：主窗口 / 设置窗口 / 列表窗口。

依赖 ttkbootstrap（缺失时由 CLI 的 ``gui`` 子命令提示安装）。
编辑器调用与等待必须在后台线程；完成后经事件循环回主线程。
"""

__all__ = ["app", "settings", "listview"]
