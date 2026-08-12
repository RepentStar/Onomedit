"""Nuitka 打包入口：等价于 ``onomedit`` 命令。"""

import sys

from onomedit.cli import main

if __name__ == "__main__":
    sys.exit(main())
