# Onomedit

Onomedit 是一个借助你熟悉的文本编辑器批量重命名文件和文件夹的工具，提供 CLI 和 GUI 两种使用方式。

它会把待处理名称按“一行一个”写进临时文件，打开记事本、VS Code、Vim 等外部编辑器；你可以使用编辑器已有的多光标、列编辑、查找替换或宏，保存并退出后，Onomedit 再安全地执行重命名。

工作流程：

1. 选择文件
2. 展开目录、过滤和排序
3. 在编辑器中修改
4. 校验
5. 重命名
6. 写入可恢复日志

> [!TIP]
> 当前版本使用 Python 实现，[Onomeditpp](https://github.com/RepentStar/Onemeditpp)项目已经使用 Rust 完成重写，如需更高性能要求可以使用 Onomeditpp

## 主要功能

- 同时支持命令行和图形界面；不带参数运行时默认打开 GUI。
- 可编辑完整路径、完整文件名、主文件名或扩展名，适合从简单改名到跨目录移动的不同任务。
- 支持显式路径、glob 通配符、目录递归、stdin 管道和剪贴板路径。
- 可按名称、路径、修改时间、创建时间或大小排序，并反转顺序。
- 提供递增编号、日期、文件时间、父目录、随机数和 GUID 等占位符。
- 支持普通替换、忽略大小写替换、正则替换、大小写/全半角转换和首尾插入等自动规则。
- 提供 dry-run 预览、非法名称清理、目标重名预检、占用目标自动编号、重命名链/环处理和编辑行数校验。
- 每次成功改名都会记录日志，可恢复最近一次、全部历史或手工选择部分记录。
- 核心 CLI 零第三方依赖；GUI 和拖拽按需安装。

## 安装

### 使用 Windows 预编译程序

从 [GitHub Releases](https://github.com/RepentStar/Onomedit/releases) 下载：

- `onomedit.exe`：完整版，包含 GUI、拖拽和 CLI。
- `onomedit-cli.exe`：体积较小的纯 CLI 版；执行 `gui` 会提示缺少 GUI 依赖。

双击完整版可以打开 GUI。若希望在任意终端使用 `onomedit`，可将程序放入一个已加入 `PATH` 的目录。

### 从源码运行

项目基于 Python 3.11 开发，未测试更低版本兼容性。推荐使用 [uv](https://docs.astral.sh/uv/)：

```bash
git clone https://github.com/RepentStar/Onomedit.git
cd Onomedit

uv sync                                      # CLI、测试和构建环境
uv sync --extra gui --extra dnd --extra img  # GUI、拖拽和图片能力

# 仅 Windows 需要 Shell 扩展属性时再安装
uv sync --extra win

uv run onomedit version
uv run onomedit gui
```

从源码运行时，将命令替换为 `uv run onomedit` 即可。

| Extra | 依赖           | 用途                                         |
| ----- | -------------- | -------------------------------------------- |
| `gui` | `ttkbootstrap` | 图形界面                                     |
| `dnd` | `tkinterdnd2`  | GUI 文件拖拽；未安装时仍可用按钮或剪贴板添加 |
| `img` | `Pillow`       | 可选图片信息能力                             |
| `win` | `pywin32`      | Windows Shell 扩展属性读取                   |

## 五分钟快速上手

### 第一次使用 CLI

首次启动会自动探测编辑器。如果探测结果不合适，可手工设置：

```powershell
onomedit config
onomedit config set-editor nvim

# VS Code 和 Sublime 必须使用 -w，确保 Onomedit 等待你保存并关闭临时文件
onomedit config set-editor code -w
```

创建几个测试文件，先进行一次安全演练：

```powershell
New-Item photo-a.jpg, photo-b.jpg, photo-c.jpg
onomedit rename "*.jpg" --dry-run
```

编辑器中会出现：

```text
photo-a
photo-b
photo-c
```

默认路径类型是 `stem`，所以扩展名不会显示，也不会被修改。将内容改为：

```text
旅行-001
旅行-002
旅行-003
```

保存并关闭后，终端只显示计划，不执行，因为使用了 `--dry-run`。确认无误后去掉该参数：

```powershell
onomedit rename "*.jpg"
```

建议新手始终先对少量测试文件使用 `--dry-run`，熟悉编辑范围和排序后再处理重要目录。

如果之后出现不慎误编辑的情况也不用惊慌，可以使用 `restore` 子命令恢复上一次重命名。

### 第一次使用 GUI

```powershell
onomedit gui

# 直接双击完整版，或不带参数，也会打开 GUI
onomedit
```

基本流程：

1. 用“添加文件”“添加文件夹”“从剪贴板”或拖拽加入路径。
2. 选择路径类型；需要处理目录内容时勾选“展开子文件夹”并设置层级。
3. 点击“预览”进入确认窗口检查计划，或点击“开始（打开编辑器）”。
4. 在外部编辑器中保持一行对应一个项目，修改后保存并关闭。
5. “预览”始终显示确认窗口，并允许继续执行选中项；普通“开始”则由 `skip_confirmation` 决定是否确认。

GUI 默认会跳过确认并在完成后退出。如果希望增加确认步骤并在结束一次重命名后仍保持打开状态则执行：

```powershell
onomedit config set skip_confirmation false
onomedit config set exit_after false
```

## 路径类型

路径类型决定临时文件里每行允许编辑哪一部分。以 `C:\照片、a.tar.gz` 为例：

| 值     | 临时文件内容        | 修改为                | 最终路径               | 建议用途                               |
| ------ | ------------------- | --------------------- | ---------------------- | -------------------------------------- |
| `stem` | `a.tar`             | `archive`             | `C:\照片、archive.gz`  | 最安全、最常用；保留最后一个扩展名     |
| `name` | `a.tar.gz`          | `archive.zip`         | `C:\照片、archive.zip` | 同时修改名称和扩展名                   |
| `ext`  | `.gz`               | `.zip`                | `C:\照片、a.tar.zip`   | 批量修改最后一个扩展名；值通常应带 `.` |
| `full` | `C:\照片、a.tar.gz` | `D:\归档、archive.gz` | `D:\归档、archive.gz`  | 改名并移动；缺失的目标目录会自动创建   |

单次覆盖配置：

```powershell
onomedit rename "*.jpg" --path-type stem
onomedit rename "*.jpeg" --path-type ext
onomedit rename "*.txt" --path-type name
onomedit rename "C:\待整理、*" --path-type full --dry-run
```

持久修改默认值：

```powershell
onomedit config set path_type name
```

多扩展名采用“最后一个扩展名”规则：`a.tar.gz` 的 `stem` 是 `a.tar`，`ext` 是 `.gz`。

## 输入路径

### 显式路径和 glob 通配符

```powershell
onomedit rename report.txt
onomedit rename a.txt b.txt "C:\My Photos\c.jpg"
onomedit rename "*.jpg"                 # * 不跨目录层级
onomedit rename "?.jpg"                 # a.jpg、1.jpg 等
onomedit rename "img[0-9].jpg"          # img0.jpg 到 img9.jpg
onomedit rename "*.jpg" "*.png"         # 同时匹配两类，推荐写法
```

路径含空格时请加引号。不存在的路径会被忽略；所有输入都无效时会报错。

请不要写 `*[jpg,png]`，它是“匹配一个字符”的字符类，不表示扩展名集合。`*.{jpg,png}` 只可能由部分 Unix shell 预先展开，程序本身不支持；请并列写多个模式。模式重叠、重复路径或父子目录重叠时，Onomedit 会在处理前去重。

### 目录和展开层级

默认会展开目录，配置深度为 10：

- `0`：不展开，目录本身作为一个待改名项目。
- `1`：目录的直接子项。
- `2`：直接子项及再下一层，以此类推。

```powershell
onomedit rename .\照片                       # 使用配置中的展开设置
onomedit rename .\照片 --depth 1             # 只处理直接子项
onomedit rename .\照片 --depth 3 --dry-run   # 最多展开三层
onomedit rename .\照片 --depth 0             # 修改“照片”目录本身
```

只要显式使用 `--depth`，本次就会临时开启目录展开；它不会修改持久配置。

### 剪贴板

不提供 `paths` 且 stdin 是交互终端时，`rename` 会读取剪贴板路径：

```powershell
# 先在资源管理器中复制文件或文件夹
onomedit rename
```

Windows 优先读取资源管理器的文件列表（CF_HDROP），也能解析以空格或换行分隔的文本路径；带空格的文本路径应放在双引号内。macOS 使用 `pbpaste`，Linux 会尝试 `xclip` 或 `xsel`。

### stdin 管道

未提供 `paths` 且 stdin 来自管道时，逐行读取路径，优先于剪贴板。相对路径按 Onomedit 的当前工作目录解析。

bash / zsh 示例：

```bash
find /data/photos -maxdepth 1 -type f | onomedit rename --path-type stem
cd /data/photos
ls | onomedit rename
```

PowerShell 应输出完整路径；不要把 `Get-ChildItem` 的格式化表格直接传入：

```powershell
Get-ChildItem C:\照片 -File | ForEach-Object FullName | onomedit rename

# 或先进入目标目录，再传裸文件名
Set-Location C:\照片
Get-ChildItem -File -Name *.jpg | onomedit rename
```

空管道会中止，不会回退剪贴板。文件名包含换行时不适合逐行管道输入。

## `rename`：完整参数参考

```text
onomedit rename [--dry-run] [--no-editor]
                [--path-type {full,name,stem,ext}] [--multi-tab]
                【--timeout 秒】 【--sort-by 键】 [--reverse]
                [--depth N] [--exclude 类型 【类型 ...】]
                [paths ...]
```

### 位置参数 `paths`

零个或多个文件、目录或 glob 模式。缺省时读取 stdin 管道或剪贴板。

```powershell
onomedit rename a.txt b.txt "*.jpg"
```

### `--dry-run`

生成并显示计划，但不执行。它默认仍会打开编辑器；若只想预览自动规则，请同时用 `--no-editor`。

```powershell
onomedit rename "*.jpg" --dry-run
onomedit rename "*.jpg" --no-editor --dry-run
```

开启以下配置后，dry-run 还会显示文本差异和编辑距离：

```powershell
onomedit config set preview.diff true
onomedit config set preview.distance true
```

### `--no-editor`

不打开编辑器，直接对原名称应用自动规则、占位符和安全清理。没有规则时通常不会产生变化。

```powershell
onomedit rename "*.txt" --no-editor --dry-run
```

### `--path-type {full,name,stem,ext}`

只覆盖本次编辑范围，不写入配置。四个值和示例见[理解“路径类型”](#理解路径类型)。

```powershell
onomedit rename "*.jpeg" --path-type ext
```

### `--multi-tab`

适用于 VS Code、Notepad++ 等已有实例或多标签编辑器。启用后直接轮询临时文件是否保存，而不只依赖编辑器进程退出。

```powershell
onomedit rename "*.txt" --multi-tab
onomedit config set multi_tab true
```

使用 VS Code 时仍建议配置 `code -w`。如果普通等待方式在编辑器启动后立即返回，再尝试 `--multi-tab`。

### `--timeout 秒`

临时设置等待编辑器保存的最长秒数，接受整数或小数；默认 120 秒。

```powershell
onomedit rename "*.jpg" --timeout 600
onomedit rename "*.jpg" --timeout 30.5
```

### `--sort-by 键`

决定临时文件的行顺序，也决定 `<n>` 编号顺序。

| 键        | 顺序                               | 示例                                            |
| --------- | ---------------------------------- | ----------------------------------------------- |
| `default` | 保持收集顺序                       | `onomedit rename a.txt b.txt --sort-by default` |
| `name`    | 文件名，不区分大小写               | `onomedit rename . --depth 1 --sort-by name`    |
| `path`    | 完整路径                           | `onomedit rename . --depth 2 --sort-by path`    |
| `mtime`   | 修改时间，旧到新                   | `onomedit rename . --depth 1 --sort-by mtime`   |
| `ctime`   | 创建时间，旧到新                   | `onomedit rename . --depth 1 --sort-by ctime`   |
| `size`    | 文件大小，小到大；目录按系统统计值 | `onomedit rename . --depth 1 --sort-by size`    |

持久设置：

```powershell
onomedit config set sort_by mtime
```

### `--reverse`

反转本次顺序。与 `--sort-by` 一起用时得到降序；默认排序下反转收集顺序。

```powershell
onomedit rename "*.jpg" --sort-by name --reverse
onomedit rename a.jpg b.jpg c.jpg --reverse
```

它只能临时开启反转，不能临时关闭配置中已开启的 `sort_reverse`。关闭时执行 `onomedit config set sort_reverse false`。

### `--depth N`

临时设置非负目录搜索深度，并隐式开启目录展开。

```powershell
onomedit rename .\素材 --depth 0
onomedit rename .\素材 --depth 1
onomedit rename .\素材 --depth 5 --dry-run
```

### `--exclude 类型...`

在已有 `exclude.*` 配置上追加本次排除项；未列出的类型保持原值。参数可接多个值，也可重复出现。

| 短名 | 全名       | 排除对象 | 示例                                      |
| ---- | ---------- | -------- | ----------------------------------------- |
| `f`  | `file`     | 普通文件 | `onomedit rename . --depth 1 --exclude f` |
| `d`  | `dir`      | 目录     | `onomedit rename . --depth 2 --exclude d` |
| `l`  | `link`     | 符号链接 | `onomedit rename . --depth 2 --exclude l` |
| `r`  | `readonly` | 只读项   | `onomedit rename . --depth 1 --exclude r` |
| `h`  | `hidden`   | 隐藏项   | `onomedit rename . --depth 2 --exclude h` |
| `s`  | `system`   | 系统项   | `onomedit rename . --depth 2 --exclude s` |

```powershell
onomedit rename .\素材 --depth 2 --exclude h s --dry-run
onomedit rename .\素材 --exclude file --exclude dir
```

默认已排除符号链接、隐藏项和系统项。`--exclude` 不能取消已有排除；若要包含隐藏文件：

```powershell
onomedit config set exclude.hidden false
```

## 占位符

当 `apply_rules` 和 `enable_envvars` 均为 `true` 时，占位符会在编辑后的文件名部分和规则结果中展开。处理顺序是：自动规则 → 占位符 → 安全名称清理。

| 写法                    | 含义                               | 示例结果                                         |
| ----------------------- | ---------------------------------- | ------------------------------------------------ |
| `<n>起始；位数；步长；` | 批次内递增编号；相同参数组共享计数 | `<n>1;3;1;` → `001`、`002`、`003`                |
| `<d>格式；`             | 当前日期和时间                     | `<d>yyyyMMdd;` → `20260823`                      |
| `<t>格式；`             | 原文件修改时间                     | `<t>yyyy-MM-dd;` → `2026-08-20`                  |
| `<tc>格式；`            | 原文件创建时间                     | `<tc>HHmmss;` → `093015`                         |
| `<f>`                   | 直接父目录名                       | `C:\相册、a.jpg` → `相册`                        |
| `<p>`                   | 向上找到的第一个非隐藏父目录名     | 隐藏目录层级中可回退到可见父目录                 |
| `<r>`                   | 每处独立的 8 位随机数字            | `04271836`                                       |
| `<rg>`                  | 每处独立的 UUID/GUID               | `f47ac10b-...`                                   |
| `<clip>`                | 单行剪贴板文本上下文               | 无文本、多行文本或当前入口未提供上下文时保留原样 |

日期支持 `yyyy`、`yy`、`MM`、`M`、`dd`、`d`、`HH`、`H`、`hh`、`h`、`mm`、`m`、`ss`、`s`、`fff`。

```text
IMG-<d>yyyyMMdd;-<n>1;4;1;
# → IMG-20260823-0001、IMG-20260823-0002……

<f>-<n>10;3;5;
# → 父目录名-010、父目录名-015……

<t>yyyyMMdd-HHmmss;-<r>
# → 20260820-093015-04271836
```

每个批次重置编号。步长或位数小于 1 会按 1 处理。未知或格式不完整的占位符会尽量原样保留。

## 自动规则

<details>
<summary>自动规则不常用可选择性查阅</summary>

> [!WARNING]
>
> 此功能较为复杂不建议使用
>
> 对于一般的自动重命名规则建议使用编辑器中的搜索替换，使用熟悉的编辑器中的可视化操作更简单易懂。如果有自动化替换需求可以使用编辑器的宏功能，大多数高级编辑器都有，例如 Vim

规则保存在 `auto_rules` JSON 数组中，按数组顺序执行。它适合稳定、重复的无人值守任务；一次性任务通常直接使用编辑器的查找替换、多光标或宏更直观。

| 字段        | 取值                             | 说明                       |
| ----------- | -------------------------------- | -------------------------- |
| `scope`     | `full` / `name` / `stem` / `ext` | 作用范围                   |
| `kind`      | 见下方示例                       | 规则类型                   |
| `condition` | 正则表达式                       | 可选；当前字段不匹配时跳过 |
| `enabled`   | `true` / `false`                 | 是否启用，默认 `true`      |

每种规则的完整示例：

```powershell
# 区分大小写普通替换：old → new
onomedit config set auto_rules '[{"scope":"stem","kind":"replace","find":"old","replace":"new"}]'

# 忽略大小写替换：IMG、Img、img → photo
onomedit config set auto_rules '[{"scope":"stem","kind":"replace_icase","find":"img","replace":"photo"}]'

# 正则替换：img12 → photo-12；反向引用使用 Python re 语法
onomedit config set auto_rules '[{"scope":"stem","kind":"regex","find":"^img(\\d+)$","replace":"photo-\\1"}]'

# 转为小写
onomedit config set auto_rules '[{"scope":"stem","kind":"convert","convert":"lower"}]'

# 在主文件名开头插入前缀
onomedit config set auto_rules '[{"scope":"stem","kind":"insert","insert":"旅行-","insert_at":"start"}]'

# 仅处理 IMG 开头的名称，在末尾加入编号模板
onomedit config set auto_rules '[{"scope":"stem","kind":"insert","insert":"-<n>1;3;1;","insert_at":"end","condition":"^IMG"}]'
```

`kind: "env"` 是占位符阶段的标记规则，本身不改变文本；通常无需手工配置。

`convert` 支持：

| 值           | 作用                     | 示例                      |
| ------------ | ------------------------ | ------------------------- |
| `upper`      | 全部大写                 | `photo` → `PHOTO`         |
| `lower`      | 全部小写                 | `PHOTO` → `photo`         |
| `capitalize` | 只把首字符大写，其余保持 | `photoNAME` → `PhotoNAME` |
| `title`      | 标题化                   | `my photo` → `My Photo`   |
| `fullwidth`  | ASCII 半角转全角         | `ABC 12` → `ABC　12`      |
| `halfwidth`  | ASCII 范围全角转半角     | `ABC　12` → `ABC 12`      |
| `urldecode`  | URL 百分号解码           | `my%20photo` → `my photo` |

多条规则必须作为同一个 JSON 数组一次设置：

```powershell
onomedit config set auto_rules '[
  {"scope":"stem","kind":"replace","find":" ","replace":"-"},
  {"scope":"stem","kind":"convert","convert":"lower"}
]'
onomedit rename "*.jpg" --no-editor --dry-run
```

PowerShell 外层建议使用单引号保护 JSON。Windows `cmd.exe` 的转义不同，复杂规则更适合直接编辑 `config.json`。无效正则会跳过该规则。

```powershell
onomedit config set enable_auto_rules false   # 暂停规则
onomedit config set auto_rules '[]'           # 清空规则
```

</details>

## 全部子命令

| 子命令                        | 用途                       |
| ----------------------------- | -------------------------- |
| `help [topic]`                | 查看总帮助或某个子命令帮助 |
| `config 【操作】`             | 查看、修改或重置配置       |
| `rename [paths...] 【选项】`  | 批量重命名                 |
| `restore [--all] [--partial]` | 按日志恢复                 |
| `history [--all]`             | 查看日志                   |
| `gui`                         | 启动图形界面               |
| `version`                     | 显示版本                   |
| `completion shell`            | 生成 shell 补全脚本        |

### `help [topic]`

项目使用 `help` 子命令。`topic` 可省略，或填写子命令名：

```powershell
onomedit help
onomedit help rename
onomedit help config
onomedit help restore
onomedit help history
onomedit help gui
onomedit help version
onomedit help completion
```

### `config`

不带操作时，以 JSON 显示完整生效配置和配置文件位置：

```powershell
onomedit config
```

#### `config set KEY VALUE`

`KEY` 是配置键，嵌套键使用点路径；`VALUE` 根据当前字段类型解析为布尔值、整数、浮点数、文本或 JSON。

```powershell
onomedit config set path_type stem
onomedit config set subdirs_depth 3
onomedit config set editor_timeout 300.5
onomedit config set exclude.hidden false
onomedit config set shell_props '["尺寸","标题"]'
```

界面和 CLI 支持简体中文与英文，默认使用简体中文。可以在 GUI 设置窗口选择语言，
也可以通过命令持久切换；重新启动 Onomedit 后，所有窗口和后续命令都会使用新语言：

```powershell
onomedit config set language en-US  # English
onomedit config set language zh-CN  # 简体中文
```

布尔值可用 `true/false`、`1/0`、`yes/no` 或 `on/off`。未知键或类型错误不会写入。

#### `config set-editor COMMAND...`

将一个或多个参数合并成编辑器命令：

```powershell
onomedit config set-editor notepad
onomedit config set-editor code -w
onomedit config set-editor "C:\Program Files\Notepad++\notepad++.exe"
```

路径含空格时必须加引号。需要传给编辑器的其他参数可继续写在后面。

#### `config reset`

```powershell
onomedit config reset
```

覆盖现有配置并恢复默认。下次加载时会重新探测空的编辑器设置；重要规则建议提前备份。

### `restore [--all] [--partial]`

恢复会倒序执行日志中的 `新路径 → 旧路径`，降低链式改名冲突。

```powershell
onomedit restore             # 恢复最近一次成功记录
onomedit restore --all       # 恢复 history.log 中的全部历史
onomedit restore --partial   # 打开最近一次日志，保留想恢复的行
```

`--partial` 会打开包含 `旧路径<-->新路径` 的临时文件。删除不想恢复的整行，保留想恢复的行，然后保存退出；不要修改分隔符或新增行。

`--all` 与 `--partial` 同时出现时，当前实现优先执行 `--partial`，只筛选最近一次记录；建议不要组合。恢复目标被占用时会沿用安全冲突处理并可能添加序号。

### `history [--all]`

```powershell
onomedit history          # 最近一次会话
onomedit history --all    # 当前历史日志中的全部记录
```

输出格式：`C:\旧名称.txt<-->C:\新名称.txt`。

### `gui`

```powershell
onomedit gui
```

需要 `ttkbootstrap`；从源码运行 `uv sync --extra gui`。拖拽另需 `dnd` extra，缺少它不影响其他 GUI 功能。

### `version`

```powershell
onomedit version
# onomedit 0.2.0
```

### `completion SHELL`

`SHELL` 必须是 `bash`、`zsh`、`pwsh`、`fish` 或 `psc`。脚本输出到 stdout，请重定向到文件。

```bash
# bash
mkdir -p ~/.local/share/bash-completion/completions
onomedit completion bash > ~/.local/share/bash-completion/completions/onomedit
source ~/.local/share/bash-completion/completions/onomedit

# zsh：确保 ~/.zfunc 已加入 fpath，并执行过 compinit
mkdir -p ~/.zfunc
onomedit completion zsh > ~/.zfunc/_onomedit

# fish
mkdir -p ~/.config/fish/completions
onomedit completion fish > ~/.config/fish/completions/onomedit.fish
```

```powershell
# PowerShell 原生参数补全；将 dot-source 行加入 $PROFILE 可永久生效
onomedit completion pwsh > "$HOME\Documents\PowerShell\onomedit.ps1"
. "$HOME\Documents\PowerShell\onomedit.ps1"

# PSCompletions 模块版本，候选项带中文提示
onomedit completion psc > "$HOME\Documents\PowerShell\onomedit.psc.ps1"
. "$HOME\Documents\PowerShell\onomedit.psc.ps1"
```

补全同时支持 `onomedit` 和 `onomedit.exe`。

## 配置参考

配置文件位置：

- Windows：`%APPDATA%\Onomedit\config.json`
- macOS：`~/Library/Application Support/Onomedit/config.json`
- Linux/其他：`${XDG_CONFIG_HOME:-~/.config}/Onomedit/config.json`

日志位于同目录的 `log` 文件夹。配置缺失时会创建默认文件；JSON 损坏时，原文件会尽量改名为 `config.json.bak`，然后恢复默认。

| 键                  | 默认值    | 说明                                            |
| ------------------- | --------- | ----------------------------------------------- |
| `version`           | `1`       | 配置格式版本，通常不要手工修改                  |
| `editor`            | 自动探测  | 主编辑器命令                                    |
| `editor_alt`        | `""`      | 备用编辑器配置；当前主流程尚未自动回退使用      |
| `editor_timeout`    | `120.0`   | 编辑器等待秒数                                  |
| `multi_tab`         | `false`   | 多标签轮询模式                                  |
| `open_editor`       | `true`    | 是否打开编辑器；CLI 更推荐单次用 `--no-editor`  |
| `apply_rules`       | `true`    | 自动规则与占位符总开关                          |
| `path_type`         | `stem`    | `full/name/stem/ext`                            |
| `sort_by`           | `default` | `default/name/path/mtime/ctime/size`            |
| `sort_reverse`      | `false`   | 持久反转排序                                    |
| `enable_envvars`    | `true`    | 占位符开关                                      |
| `enable_auto_rules` | `true`    | `auto_rules` 开关                               |
| `expand_subdirs`    | `true`    | 是否展开输入目录                                |
| `subdirs_depth`     | `10`      | 展开层级；`0` 表示不展开                        |
| `exclude.files`     | `false`   | 排除普通文件                                    |
| `exclude.dirs`      | `false`   | 排除目录                                        |
| `exclude.symlinks`  | `true`    | 排除符号链接                                    |
| `exclude.readonly`  | `false`   | 排除只读项                                      |
| `exclude.hidden`    | `true`    | 排除隐藏项                                      |
| `exclude.system`    | `true`    | 排除系统项                                      |
| `preview.diff`      | `false`   | dry-run/确认列表显示增删差异                    |
| `preview.distance`  | `false`   | 显示 Levenshtein 编辑距离                       |
| `safety.sanitize`   | `true`    | 清理非法字符、保留名和尾随点/空格               |
| `exit_after`        | `true`    | GUI 完成后自动退出                              |
| `skip_confirmation` | `true`    | GUI 编辑后直接执行，不显示确认窗口              |
| `shell_props`       | `[]`      | 预留 Shell 属性列表；当前重命名界面未展示这些列 |
| `auto_rules`        | `[]`      | 自动规则 JSON 数组                              |
| `temp_dir`          | `""`      | 临时文件目录；空值使用系统临时目录              |

首次探测编辑器时，优先读取 `EDITOR` 环境变量。未设置时，Windows 依次尝试记事本、VS Code；macOS 依次尝试 TextEdit、Sublime Text、VS Code、Vim；Linux 依次尝试 nano、vi、Kate。

## GUI 功能说明

主窗口提供：

- 添加多个文件、文件夹、剪贴板路径和可选文件拖拽。
- 路径类型、目录展开开关和 1–99 层深度设置。
- “开始（打开编辑器）”“直接应用规则（跳过编辑器）”和“预览（进入重命名确认）”。
- “恢复上次”和完整设置窗口。

列表显示顺序就是写入编辑器的顺序。设置窗口改变排序后，主列表会刷新。

“预览”不会自动改名，而是始终进入确认窗口；仍可在检查后点击“执行重命名”。确认窗口默认全选，支持全选、全不选、双击切换单行选择，并可按配置显示差异和编辑距离。路径会尽量相对于公共目录显示，但真正执行始终使用完整路径。全部成功后确认窗口自动关闭。

## 安全机制与使用建议

### 名称清理

默认开启 `safety.sanitize`：

- 将 Windows 非法字符 `< > : " / \\ | ? *` 和控制字符替换为 `_`。
- 去除首尾空白及结尾的点和空格。
- 为 `CON`、`PRN`、`AUX`、`NUL`、`COM1`、`LPT1` 等保留名添加 `_` 前缀。
- 清理后为空的名称变成 `_`。

该规则在所有平台都采用保守的跨平台名称。确有需要时可关闭：

```powershell
onomedit config set safety.sanitize false
```

### 冲突处理

- 多个源被编辑成同一个目标：整批预检失败，不执行任何一项。
- 目标被本批次之外的文件占用：自动生成 `name (1).ext`、`name (2).ext`。
- `a → b`、`b → a` 等交换、链和环：使用内部临时名称分两阶段完成。
- 单个操作系统错误：记录失败并继续其他项目，命令最终返回非零状态。
- 全路径模式目标父目录不存在：自动创建目录后重试。

### 编辑器中的注意事项

- 一行必须对应一个输入项目；不要新增或删除行，行数不一致会中止。
- 不建议用空行表示删除或跳过；安全清理可能将空名称改为 `_`。
- 要跳过 GUI 中的部分项目，请关闭 `skip_confirmation`，在确认窗口取消选择。
- CLI 先用 `--dry-run`；GUI 新手先关闭“跳过重命名确认”。
- 使用 `<n>` 前先设置排序，因为编号严格按行顺序分配。
- 改扩展名用 `name` 或 `ext`；默认 `stem` 会保留最后一个扩展名。
- 移动文件用 `full`，并先 dry-run 检查盘符和目录。

### 日志与恢复边界

日志目录包含：

- `last.log`：最近一次会话成功记录；新会话开始时清空。
- `history.log`：累计记录，过大时轮转为 `history.1.log` 等。
- `error.log`：失败信息。

恢复依赖日志和当前文件状态，不是文件内容备份。它只能撤销路径变化，不能恢复被其他程序删除或覆盖的内容。

## 常见问题

### 编辑器一闪而过，没有等待保存

```powershell
onomedit config set-editor code -w
onomedit config set multi_tab true
onomedit config set editor_timeout 600
```

### 提示编辑后的行数不一致

编辑器中新增或删除了行。确保每个原始项目仍有且只有一行；要跳过项目应在 GUI 确认窗口取消选择。

### glob 没匹配到文件

检查当前目录、引号和模式。跨平台推荐 `"*.jpg" "*.png"`，不要用 `*.{jpg,png}`。`*` 不递归；目录递归请传目录并用 `--depth`。

### 管道输入无法解析

PowerShell 的 `Get-ChildItem` 默认输出对象，交给原生命令时可能变为含表头的文本。使用 `ForEach-Object FullName`，或先进入目标目录再用 `-Name`。

### 想包含隐藏文件，但 `--exclude` 只能追加排除

```powershell
onomedit config set exclude.hidden false
# 完成后可恢复：onomedit config set exclude.hidden true
```

### GUI 无法启动或无法拖拽

```bash
uv sync --extra gui --extra dnd
```

只缺拖拽依赖时 GUI 仍可正常使用按钮和剪贴板。

## 开发与打包

```bash
uv sync
uv run pytest
uv run python scripts/smoke_test.py
pwsh scripts/e2e_cli.ps1
uv run python scripts/gui_smoke.py
uv run python scripts/clipboard_check.py
```

Windows 下用 Nuitka 生成完整版单文件程序：

```powershell
uv sync --extra gui --extra dnd --extra img
pwsh scripts/build_nuitka.ps1
```

产物为 `dist\onomedit.exe`。入口是 `scripts/nuitka_entry.py`；推送 `v*` 标签后，GitHub Actions 会构建完整版和 CLI 精简版并发布到 Releases。

## 许可证

Onomedit 使用 [MIT License](LICENSE)。
