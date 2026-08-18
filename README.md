# Onomedit

结合外部编辑器进行批量文件重命名的工具（CLI + GUI）。

**核心工作流**：程序把文件名列表写入临时文件，唤起你偏好的编辑器；在编辑器中
可视化修改，保存退出后程序读回并批量重命名。

## 功能特性

- **编辑器是核心**：拉起并等待编辑器（单实例 / 启动器 / 多标签自动适配），GUI 下焦点自动转到编辑器
- **两种模式**：CLI（子命令式）与 GUI，编辑内容均由你偏好的编辑器完成
- **路径类型四档**：全路径 / 文件名 / 不带扩展名 / 扩展名，默认「不带扩展名」
- **重命名顺序可选**：按名称 / 路径 / 修改时间 / 创建时间 / 大小排序，可反转；GUI 与 CLI（`--sort-by` / `--reverse`）均可配置
- **环境变量占位符**：`<n>` 递增、`<d>` 日期、`<f>`/`<p>` 目录名、`<t>`/`<tc>` 时间、`<r>`/`<rg>` 随机、`<clip>` 剪贴板
- **自动替换规则**：替换（三种）/ 转换 / 插入，可带条件
- **安全优先**：dry-run 预览、非法字符/保留名防护、重名序号、冲突解环、行数校验、目标重名中止（警告且不执行）
- **日志与恢复**：一键恢复上次 / 全部 / 部分
- **剪贴板收集**：资源管理器复制文件/文件夹（CF_HDROP）或文本路径均可作为输入
- **开箱即用**：首次启动自动探测默认编辑器；无参数运行默认打开 GUI

## 安装

### 使用预编译二进制

从 Release 下载预编译单文件二进制（推送 `v*` 标签后由 GitHub Actions 自动构建），Release 中两种版本都具备 CLI 能力

将文件移动到在 `PATH` 中的目录下即可在终端中全局使用；直接双击 exe 文件即可打开 GUI

### 从源码运行

```bash
uv sync                          # 源码运行（开发环境，含测试与打包依赖）
uv sync --extra gui --extra dnd  # 或仅 GUI 依赖（界面 + 拖拽）
```

> 可选依赖：`pywin32`（Shell 属性）、`Pillow`（图片尺寸）、`tkinterdnd2`（GUI 拖拽）。
> 拖拽为可选能力：未安装 `tkinterdnd2` 时状态栏会提示原因，仍可用按钮/剪贴板添加。
> 也可用 Nuitka 打包为单文件 exe，见[打包](#打包-nuitka)。

## 快速开始（CLI）

```bash
onomedit help                       # 帮助（可带子命令：onomedit help rename）
onomedit config set-editor notepad  # 配置编辑器（首次启动会自动探测，可跳过）
onomedit rename file1.txt "*.jpg"   # 拉起编辑器 → 修改 → 保存 → 重命名
onomedit rename "*.jpg" "*.png"     # 多模式并列：同时处理 jpg 与 png（见下方通配符说明）
onomedit rename folder/             # 目录默认展开子文件夹（层级 10）
onomedit rename folder/ --depth 2   # 临时只展开到第 2 层（不改配置）
onomedit rename                     # 缺省读剪贴板中的路径
onomedit rename *.txt --dry-run     # 预览（不执行）
onomedit rename *.txt --exclude h d --dry-run  # 临时排除隐藏文件与目录
onomedit restore                    # 恢复上次重命名
onomedit gui                        # 启动 GUI；无参数运行默认打开 GUI
```

## 路径匹配（glob 通配符）

`rename` 的路径参数支持 shell 风格的 glob 通配符（`*`、`?`、`[abc]` 字符类），且不依赖 shell：Windows（cmd / PowerShell）不会展开通配符，由程序内部自动展开；Unix 系 shell 会先展开，程序同时兼容两种方式（`"*.jpg"` 加引号可强制由程序展开）。

```bash
onomedit rename "*.jpg"             # 当前目录全部 jpg（* 不跨目录层级）
onomedit rename "?.jpg"             # ? 匹配单个字符：a.jpg、1.jpg…
onomedit rename "img[0-9].jpg"      # 字符类：img0.jpg ~ img9.jpg
onomedit rename "*.jpg" "*.png"     # 多模式并列：jpg 与 png（推荐写法）
```

注意：**集合 / 逻辑或写法不支持**。`*[jpg,png]` 是单字符类，只会匹配以 `j`/`p`/`g`/`,`/`n` 任一字符结尾的文件（会误匹配）；`*.{jpg,png}` 花括号仅 bash 会展开，程序内不生效，Windows 下会静默匹配为空。需要匹配 jpg 与 png 时请并列写多个模式。

## 子命令一览

| 子命令            | 说明                                                                                                                                          |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `help 【子命令】` | 帮助与示例                                                                                                                                    |
| `config`          | 查看配置；`config set KEY VALUE`、`config set-editor CMD`、`config reset`                                                                     |
| `rename [PATH]`   | 批量重命名（`--dry-run` / `--no-editor` / `--path-type` / `--sort-by` / `--reverse` / `--depth` / `--multi-tab` / `--timeout` / `--exclude`） |
| `restore`         | 恢复上次；`--all` 全部历史；`--partial` 编辑器筛选恢复                                                                                        |
| `history [--all]` | 查看重命名日志                                                                                                                                |
| `gui` / `version` | 图形界面 / 版本号                                                                                                                             |

## GUI 用法

- **主窗口**：添加文件（按钮 / 文件夹 / 剪贴板 / 拖拽）、选择路径类型与展开层级；
  拖拽需安装 `tkinterdnd2`（`uv sync --extra dnd`），未安装时状态栏提示并回退按钮；
  点「开始」后台完成「收集 → 展开 → 过滤 → 写临时文件 → 拉起并等待编辑器」，不冻结界面
- **执行与确认**：默认「跳过确认」直接执行；关闭后弹出确认窗口（差异/距离可配置列、
  默认全选、路径相对所选目录显示、全部成功后自动关闭）
- **设置窗口**：可视化编辑全部配置（含路径类型、排序依据、展开层级与排除项）；「完成后退出」默认开启；主窗口提供「恢复上次」快捷按钮

## 环境变量占位符

在临时文件行内或规则替换文本中使用（`enable_envvars` 默认开启）：

| 变量                    | 语义                  | 要点                             |
| ----------------------- | --------------------- | -------------------------------- |
| `<n>起始；位数；步长；` | 递增数字              | 跨文件延续；参数组相同才共享计数 |
| `<d>格式；`             | 当前时间              | `yyyy/MM/dd/HH/mm/ss/fff` 语法   |
| `<f>` / `<p>`           | 上级目录名 / 图包目录 | 依赖当前文件                     |
| `<t>` / `<tc>`          | 修改 / 创建时间       | 可带格式                         |
| `<r>` / `<rg>`          | 随机 8 位数字 / GUID  | 每处独立                         |
| `<clip>`                | 剪贴板文本            | 仅单行时替换                     |

示例：把 `img001.jpg` 改为 `IMG-20260812-001.jpg` 等，编辑器中写入 `IMG-<d>yyyyMMdd;-<n>1;3;1;`，保存后自动递增。

## 自动替换规则

配置 `auto_rules`（JSON 列表），作用于四档路径类型，规则顺序固定：
替换/转换/插入 → 环境变量展开 → 安全命名。

```bash
onomedit config set auto_rules '[{"scope":"stem","kind":"replace","find":"old","replace":"new"}]'
```

| 字段                    | 取值                                                                                 |
| ----------------------- | ------------------------------------------------------------------------------------ |
| `scope`                 | `full`/`name`/`stem`/`ext`                                                           |
| `kind`                  | `replace` / `replace_icase` / `regex` / `convert` / `insert` / `env`                 |
| `find` / `replace`      | 查找串 / 替换为（可含环境变量）                                                      |
| `convert`               | `upper` / `lower` / `capitalize` / `title` / `fullwidth` / `halfwidth` / `urldecode` |
| `insert` / `insert_at`  | 插入文本 / 位置（`start`/`end`）                                                     |
| `condition` / `enabled` | 条件正则（不匹配跳过）/ 是否启用                                                     |

> [!TIP]
> 此功能不推荐使用，建议使用编辑器中的搜索替换，使用熟悉的编辑器中的可视化操作更简单易懂。如果有自动化替换需求可以使用编辑器的宏功能，大多数高级编辑器都有，例如 Vim

## 路径类型（编辑范围）

| 类型   | 临时文件行         | 示例（`C:\x\a.tar.gz`） |
| ------ | ------------------ | ----------------------- |
| `full` | 全路径             | `C:\x\a.tar.gz`         |
| `name` | 文件名（含扩展名） | `a.tar.gz`              |
| `stem` | 不带扩展名         | `a.tar`                 |
| `ext`  | 扩展名（含点）     | `.gz`                   |

## 重命名顺序（`sort_by` / `--sort-by`）

重命名顺序 = 写入临时文件的行顺序（也影响 `<n>` 递增数字的编号次序）。配置键 `sort_by`（GUI 设置窗口「排序依据」下拉框；CLI 用 `--sort-by KEY` 临时覆盖，只对本次重命名生效）：

| 值        | 含义                   |
| --------- | ---------------------- |
| `default` | 原顺序（默认，不排序） |
| `name`    | 文件名（大小写不敏感） |
| `path`    | 完整路径               |
| `mtime`   | 修改时间（旧→新）      |
| `ctime`   | 创建时间（旧→新）      |
| `size`    | 文件大小（小→大）      |

反转：配置键 `sort_reverse`（GUI「反转顺序」勾选框；CLI 用 `--reverse` 临时开启）——
配合排序依据时按排序键降序，单独使用（`default`）时反转收集原顺序。

```bash
onomedit config set sort_by mtime             # 持久配置：按修改时间排序
onomedit config set sort_reverse true         # 持久反转（修改时间新→旧）
onomedit rename folder/ --sort-by size        # 临时覆盖：本次按大小排序（不改配置）
onomedit rename *.jpg --sort-by name --reverse --dry-run  # 按名称降序后预览
```

## 临时目录深度（`--depth`）

`rename` 支持用 `--depth N` 临时指定本次重命名的目录搜索深度，只对本次生效，
不改配置文件：1 = 直接子项，0 = 不展开；指定时临时开启子文件夹展开
（即使配置里 `expand_subdirs` 为 `false`）。

```bash
onomedit rename folder/ --depth 1     # 本次只处理直接子项（临时覆盖 subdirs_depth）
onomedit rename folder/ --depth 0     # 本次不展开（目录本身作为一项）
onomedit rename folder/ --depth 3 --sort-by mtime --dry-run  # 组合临时参数
```

## 临时排除（`--exclude`）

`rename` 支持用 `--exclude TYPE…` 临时排除路径类型，只对本次重命名生效，
不改配置文件；未列出的类型沿用现有配置 `exclude.*` 的取值（默认排除符号链接/隐藏/系统）。
参数可多值、可重复（如 `--exclude f h` 与 `--exclude f --exclude h` 等价）：

| tag            | 含义 | tag              | 含义     |
| -------------- | ---- | ---------------- | -------- |
| `f` / `file`   | 文件 | `l` / `link`     | 符号链接 |
| `d` / `dir`    | 目录 | `r` / `readonly` | 只读     |
| `h` / `hidden` | 隐藏 | `s` / `system`   | 系统     |

```bash
onomedit rename *.jpg --exclude d        # 排除目录（子文件夹展开后过滤）
onomedit rename folder/ --exclude h s    # 排除隐藏与系统文件
onomedit rename *.txt --exclude f --dry-run  # 排除普通文件，仅预览
```

## 配置

配置文件：Windows `%APPDATA%\Onomedit\config.json`；macOS `~/Library/Application Support/Onomedit`；其他 `~/.config/Onomedit`。缺失/损坏时回退默认（损坏先备份）。

常用键（`onomedit config` 查看全部，`config set KEY VALUE` 修改，值按类型推断）：

| 键                                  | 默认               | 说明                                                                       |
| ----------------------------------- | ------------------ | -------------------------------------------------------------------------- |
| `editor`                            | 自动探测           | 编辑器命令（Windows: 记事本→VSCode；macOS: TextEdit；Linux: nano→vi→kate） |
| `path_type`                         | `stem`             | 路径类型                                                                   |
| `sort_by`                           | `default`          | 重命名顺序（name/path/mtime/ctime/size）                                   |
| `sort_reverse`                      | `false`            | 反转重命名顺序（配合 sort_by 降序；default 时倒序）                        |
| `expand_subdirs` / `subdirs_depth`  | `true` / `10`      | 展开子文件夹及层级                                                         |
| `exclude.*`                         | 符号链接/隐藏/系统 | 排除开关（文件/目录/只读等）                                               |
| `preview.diff` / `preview.distance` | `false`            | 预览差异标注 / 编辑距离                                                    |
| `skip_confirmation`                 | `true`             | 跳过重命名确认（GUI 直接执行）                                             |
| `exit_after`                        | `true`             | 完成后退出（GUI）                                                          |
| `multi_tab` / `editor_timeout`      | `false` / `120`    | 多标签编辑器 / 等待超时（秒）                                              |
| `safety.sanitize`                   | `true`             | 安全命名（非法字符/保留名/序号）                                           |
| `auto_rules`                        | `[]`               | 自动替换规则                                                               |

## 打包（Nuitka）

生成单文件 `dist\onomedit.exe`（Windows，含 GUI 与拖拽支持）：

```bash
uv sync --extra gui --extra dnd --extra img
pwsh scripts\build_nuitka.ps1
```

- 在 uv 环境中打包（nuitka/zstandard 为 dev 依赖）；首次自动下载 MinGW64 编译器
- 产物内含 `ttkbootstrap` / `Pillow` / `tkinterdnd2`（含 tkdnd 库），拖拽开箱即用
- 控制台模式 force：CLI 命令在终端输出正常；双击启动 GUI 会保留控制台窗口，
  建议从终端运行 `onomedit gui` 或创建快捷方式

Release 提供两种产物（推送 `v*` 标签由 GitHub Actions 构建，参数见
`.github/workflows/build-windows.yml`）：

- `onomedit.exe`：完整版（含 GUI 与拖拽支持，当然也可以使用 CLI）
- `onomedit-cli.exe`：最小体积版（纯 CLI，不含 GUI 依赖，体积约 1/3；
  `gui` 子命令会提示缺少 GUI 依赖）

## 开发

```bash
uv run pytest                             # 单元测试
uv run python scripts/smoke_test.py       # 核心冒烟
pwsh scripts/e2e_cli.ps1                  # CLI 端到端（假编辑器）
uv run python scripts/gui_smoke.py        # GUI 冒烟
uv run python scripts/clipboard_check.py  # 剪贴板验证
pwsh scripts/build_nuitka.ps1             # Nuitka 打包
```

打包入口：`scripts/nuitka_entry.py`；测试工具：`tests/fakeditor.py`（假编辑器）、
`tests/conftest.py`（配置隔离夹具）。
