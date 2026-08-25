# Rust 重构会话交接

## 当前状态

- 分支：`rust`
- 最近代码提交：`5febad6 test: add migration and performance baselines`
- Python 实现仍作为兼容性基准保留，尚未进入最终切换阶段。
- Rust GUI、编辑器修复、第一阶段发布切换、迁移快照和性能基线均已提交；交接文档在本轮单独提交。用户另行修改的 `TODO.md` 不属于本轮工作，保持未提交。
- 本地 `rust` 分支未配置 upstream，本机也未安装 `gh` CLI。用户已决定忽略远端 CI/干净 runner 和真实用户 v0.1.6 数据复核两项门禁，不需要为当前 Python 移除流程推送分支；macOS/Linux CI 同样不作为现阶段门禁。

## 已完成

- 建立 Cargo workspace：
  - `crates/onomedit-core`：路径、配置、规则、占位符、收集、临时编辑文件、日志、重命名与恢复。
  - `crates/onomedit-platform`：剪贴板和外部编辑器协议。
  - `apps/onomedit`：CLI、补全脚本、完整/CLI-only 二进制入口及 GUI 骨架。
- 加入 `tests-rust/fixtures/core.json`，由 Python 与 Rust 共同读取。
- 当前 CI 在 Windows 运行 Python oracle、Rust CLI-only、Rust GUI/default、rustfmt 和 Clippy；原 macOS/Linux CI 暂缓但平台实现与共享 fixture 保留。
- 生成并提交 `Cargo.lock`。

## 上轮已提交

- 扩展 `tests-rust/fixtures/core.json`，Python/Rust 现在共同验证：
  - Unicode `title`、异常 URL 百分号解码；
  - 普通/忽略大小写/正则规则、条件、禁用、插入；
  - Python `\1`、`\g<1>`、命名组替换、字面 `$`/反斜杠和无效组；
  - 占位符计数序列、剪贴板和异常占位符；
  - 固定日期格式和多段字符 diff。
- Rust `title` 改用完整 Unicode titlecase 映射，并按 Python 的 cased/uncased 词边界处理数字、组合字符和复合字母。
- Rust `replace_icase` 增加 Python `re.IGNORECASE` 的 Unicode 单字符折叠及 `i/I/İ/ı` 特例。
- Rust 正则替换新增 Python 风格替换模板解析，避免 `$1` 被误当成 Rust 回引，并支持数字/命名回引及错误时整条规则跳过。
- Rust `diff_text` 已从公共前后缀近似实现替换为兼容 `difflib.SequenceMatcher` 的匹配块/opcode 算法（含 autojunk 边界）。
- 新增 `unicode-case-mapping 1.0.0`（Apache-2.0）并更新 `Cargo.lock`。

以上内容已提交为 `1cb632a test(core): expand Python Rust compatibility corpus`。

## 本轮已提交

- 新增 `tests-rust/fixtures/filesystem.json` 共享文件树语料，以及 Python/Rust 两端 runner。
- 9 个共享场景覆盖：
  - glob、缺失路径过滤、重叠输入去重；
  - 目录深度展开、文件/目录排除、名称/路径/大小排序；
  - `name`/`stem`/`ext` 临时编辑行与 UTF-8/LF 协议；
  - 编辑结果、安全名称清理、自动规则、批次计数器和 rename pairs；
  - 无有效输入、排除后为空、编辑行数不一致三类错误。
- 修复 Rust Windows glob 强制大小写敏感的问题：Windows 现在与 Python 一样不区分大小写，POSIX 仍保持区分。

以上内容已提交为 `9ae0ce7 test(core): add filesystem planning parity cases`。

## 最近已提交

- 新增 `tests-rust/fixtures/execution.json` 及 Python/Rust 两端执行 runner。
- 7 个执行场景覆盖：普通改名与 unchanged skip、外部占用连续编号、两节点交换、三节点环、创建缺失目标父目录、重复目标整批中止、单项失败后继续。
- 3 个恢复场景覆盖 partial restore、last swap restore、清空 last 后从完整 history 恢复。
- 日志差分同时验证 success/failed/skipped 顺序、最终文件树及内容、`last.log`/`history.log` 用户可见路径，并保证内部临时名不残留、不写入日志。
- 增加 1 MiB `history.log` 轮转边界共享测试。

以上内容已提交为 `f12ffc7 test(core): add execution and restore parity cases`。

## 本轮已提交

- 新增 `tests-rust/fixtures/editor.json`，由 Python 与 Rust 两端实际启动同一个 `tests/fakeditor.py`。
- 7 个共享场景覆盖：单进程保存、启动器快速退出后延迟保存、启动器保存超时、多标签延迟保存、多标签保存超时、存活进程超时和截断保存。
- 两端共同校验文件签名/内容变化，以及启动器、多标签、进程超时和保存超时的用户状态提示。
- `fakeditor.py` 新增 `launcher-delay` 与 `sleep` 模式；Rust platform crate 增加共享 fixture 集成测试所需的 dev dependencies。
- Rust 测试优先使用 `ONOMEDIT_TEST_PYTHON` 或仓库 `.venv`，CI/其他环境回退到 PATH 中的 `python3`/`python`。

以上内容已提交为 `0b2ebf4 test(platform): add editor state machine parity cases`。

## 本轮新增提交

- 将 `tests-rust/fixtures/filesystem.json` 从 9 个扩展为 15 个共享场景，Python/Rust 两端现在共同验证：
  - 文件及目录符号链接参与计划但目录链接不被递归跟随；
  - `exclude.symlinks` 同时过滤文件链接和目录链接；
  - Windows 只读/隐藏/系统属性与 POSIX 只读/点文件/无 system 属性的降级语义；
  - Windows 与 POSIX 的隐藏名称差异；
  - 固定 `mtime` 排序和按实际创建顺序验证的 `ctime` 排序。
- 两端 runner 可创建符号链接、设置固定修改时间和平台文件属性，并在能力不可用时显式跳过；Windows 测试结束会恢复属性，避免只读文件阻碍临时目录清理。
- 修复 Rust `ctime` 在 POSIX 上错误使用 birth/creation time 的差异：现在使用与 Python `os.stat().st_ctime` 对齐的 Unix metadata change time，Windows 继续使用 creation time。
- 修复 Rust POSIX 只读判断只看 mode bits 的差异：现在通过 `access(W_OK)` 与 Python `os.access(..., os.W_OK)` 对齐，包含 root/ACL 语义；新增 Unix-only `libc 0.2` 直接依赖。

以上内容已提交为 `6101feb test(core): add collection platform parity cases`。

## 最新提交

- 新增 `tests-rust/fixtures/cli.json` 及 Python/Rust 两端 CLI runner，12 个共享场景锁定：
  - version、空 last/all history、空 restore；
  - config reset、布尔设置和未知键；
  - 未知 help topic、空管道不回退剪贴板；
  - 根帮助/rename 帮助的命令与选项表面，以及禁用自动 `--help` 的退出码。
- Python 与 Rust 都新增真实子进程 E2E：隔离配置后执行自动规则改名，验证 `rename -> history -> restore -> dry-run` 的退出码、用户输出和最终文件树。
- Rust CLI-only 新增无参数和 `gui` 的 GUI 不可用回归测试。
- Rust 普通 CLI stdout/stderr 在 Windows 改为与 Python 一致的 CRLF，POSIX 保持 LF；completion 仍刻意逐字节保持 LF。
- Rust 未知配置键文案改为 Python 的单引号形式。
- Rust rename help 补齐各选项说明，并禁用 clap 自动 help flag，保持项目使用 `onomedit help [topic]` 的既有命令面。
- 加强补全契约：`pwsh` 注册名与 Python 对齐；`psc` 现在是真正的带中文 tip 自定义补全器；五种脚本均验证子命令、关键候选和 LF，`pwsh`/`psc` 另经 PowerShell AST 实际解析。

以上内容已提交为 `9531676 test(cli): add shared golden and workflow coverage`。

## 本轮日志提交

- 扩展 `tests-rust/fixtures/execution.json`，Python/Rust 共同验证：
  - 空行和无效行跳过、从最后一个 `<-->` 分割，以及空 old/new 字段；
  - LF、CRLF、单独 CR 三种通用换行读取；
  - 日志中任意位置出现无效 UTF-8 时整份读取为空；
  - `parse_line` 直接接收 CRLF 时保留 `\r` 的 Python 细节。
- 新增原始日志字节测试：Windows 的 `last.log`、`history.log`、`error.log` 使用 CRLF，POSIX 使用 LF。
- 新增连续 7 次轮转测试，确认只保留 `history.1.log` 至 `history.5.log`，内容依次为最新五代且不产生 `history.6.log`。
- 修复 Rust 损坏 UTF-8 日志会返回损坏前部分记录的问题；现在与 Python 一样整份返回空。
- Rust 日志读取现在兼容 Python 文本模式的 CR/LF/CRLF 通用换行，日志写入按平台使用原生换行。

以上内容已提交为 `03e045e test(core): expand journal corruption and rotation parity`。

## 本轮编辑器命令提交

- 先切回 `main` 修复 Python oracle：Windows 的 `shlex.split(..., posix=False)` 结果现在会去掉每个 token 的匹配外层引号，带空格的完整编辑器路径和普通参数不再收到字面引号。
- Python 新增真实回归：带空格参数传入 `fakeditor.py`，以及位于带空格目录中的 `.cmd` 编辑器路径；修复前两项均稳定失败，修复后定向和全量测试通过。
- Python 修复在 `main` 提交为 `d9f73d7 Fix Windows editor command quoting`，随后 cherry-pick 到 `rust` 为 `7d42547`。
- 扩展 `tests-rust/fixtures/editor.json`，Python/Rust 共同验证带引号的命令拆分和带空格参数传递；Windows 另共同实际启动：
  - 带空格完整路径的 `.cmd`；
  - 带空格完整路径的 `.bat`；
  - 仅命令名、通过 PATH 与 PATHEXT 解析的 `.cmd`；
  - 带空格的最终编辑文件参数。
- 新共享测试暴露 Rust 直接用多个 `Command::arg` 调用 `cmd /C` 时，`cmd.exe` 会按自身规则剥掉首尾引号并把带空格脚本路径截断。Rust 现在按 Windows 参数转义规则构造 UTF-16 命令行，并以 `cmd /D /S /C` 所需的额外外层引号通过 `raw_arg` 传入。
- Windows PATH/PATHEXT 测试串行保护并在每个场景后恢复进程环境，避免并发测试互相污染。

以上共享兼容性及 Rust 修复已提交为 `54d55cf test(platform): cover Windows editor commands`。

## 本轮 CLI 字节快照提交

- `tests-rust/fixtures/cli.json` 新增 15 个 Python/Rust 共享字节指纹快照：
  - 根帮助及 `completion`/`config`/`gui`/`help`/`history`/`rename`/`restore`/`version` 全部帮助主题；
  - 完整默认配置 JSON 与配置路径，仅对动态配置路径和平台默认编辑器作占位归一化；
  - bash、zsh、pwsh、fish、psc 五种补全脚本。
- 快照同时锁定 UTF-8 字节、缩进、空行和换行；帮助/配置在 Windows 验证 CRLF，补全脚本在所有平台保持 LF。
- 新门禁暴露 Rust 原有 clap 帮助文本和简化补全脚本与 Python oracle 并不相同；Rust 现在逐字节复刻全部帮助与五种补全输出。
- PowerShell `pwsh`/`psc` 脚本仍经现有 AST 测试解析，共享快照另防止文案、候选、空白或行尾漂移。

以上内容已提交为 `ce7c97f test(cli): lock byte-exact help and completion output`。

## 本轮 CLI 错误与配置异常提交

- `tests-rust/fixtures/cli.json` 新增 15 个 Python/Rust 共享 stderr 字节快照，覆盖：
  - 未知子命令，`completion` 缺参数/非法 shell，`config set` 缺 key/value；
  - 布尔、整数、浮点和 JSON 配置值解析错误；
  - `rename` 的 `path-type`/`sort-by`/`depth`/`timeout`/`exclude` 非法值，以及 `history` 多余参数。
- Rust 新增窄范围 argparse 兼容错误映射，现在与 Python 一致输出 usage、参数名、候选值、引用和平台换行，未命中的其他 clap 错误仍保持原回退。
- Rust `config set` 的整数、浮点和常见对象 JSON 解析错误已对齐 Python 文案。
- 新增 2 个真实配置文件场景：
  - 损坏 JSON 会原字节备份为 `config.json.bak`，再写入可读默认配置；
  - 缺失字段补默认、未知顶层/嵌套字段忽略，查看配置时不改写原文件。

以上内容已提交为 `1832b05 test(cli): cover errors and corrupt config`。

## 本轮正则兼容提交

- 将 `tests-rust/fixtures/core.json` 的共享规则语料从 20 条扩展为 59 条，新增覆盖：
  - 正/负向先行断言、负向后行断言、数字/命名模式回引；
  - 全局及局部 inline flags、multiline、dotall，以及 Python ASCII 模式下的 `\w`/`\W`/`\d`/`\D`/`\s`/`\S`/`\b`/`\B`；
  - `\A`/`\Z`、原子组、占有量词和用于 rule condition 的断言/回引/ASCII 模式；
  - 未匹配可选组、`\g<0>`、三位八进制替换、数字组歧义、Unicode 命名组、未知/非字母替换转义；
  - 空匹配、Unicode 空匹配及零宽断言的替换推进。
- Rust 正则编译增加 Python ASCII flag 适配：全局 `(?a)` 和局部 `(?a:...)` 会将速记字符类及单词边界展开为 ASCII 语义，同时保留其余 Rust/fancy-regex 可支持的 flags。
- Rust 正则替换不再使用会跳过相邻空匹配的 `captures_iter`，改为按 UTF-8 边界推进，复刻 Python 对“非空匹配后紧邻空匹配”的处理。
- Python 风格替换模板现在拒绝大于 `0o377` 的三位八进制转义，与 Python 的规则失败后 no-op 行为一致。
- Python/Rust 共享规则 runner 现在在失败时报告 fixture 索引和规则内容，便于直接定位差异。

以上内容已提交为 `cefc3ef test(core): expand Python regex compatibility`。

## 本轮嵌套正则模式提交

- 将共享规则语料从 59 条扩展为 70 条，Python/Rust 共同新增验证：
  - 组合式局部 `(?ai:...)`；
  - 局部及全局 ASCII 模式内嵌 `(?u:...)` 恢复 Unicode 字符类；
  - ASCII 模式字符类中的 `[\W]`、`[\D]`、`[\S]` 及对应取反形式；
  - scoped `(?ax:...)` 和全局 `(?x)` verbose 模式，包括注释内括号不参与分组配对。
- Rust 的 Python 正则适配从单次字符串替换升级为按 scope 递归的轻量解析器：
  - 逐层继承或切换 ASCII、Unicode、verbose 状态；
  - 保留 fancy-regex 支持的其他 inline flags，同时移除需手工展开的 `a`/`u`；
  - 在 verbose 注释及字符类中正确跳过括号解析。
- ASCII 字符类转换现在支持负向速记类；取反字符类通过零宽集合约束加单字符消费表达 Python 的交集语义。

以上内容已提交为 `98abb08 test(core): cover nested Python regex modes`。

## 本轮正则大小写与条件提交

- 将共享规则语料从 70 条扩展为 88 条，新增覆盖：
  - Python Unicode `IGNORECASE` 的 `i/I/İ/ı`、`s/S/ſ`、`k/K/K` 特殊等价类、反向特殊字符匹配及 `[a-z]` 范围；
  - Python ASCII `IGNORECASE` 对上述非 ASCII 特殊字符的排除，包含普通/取反 `[a-z]` 和非 ASCII 字面量；
  - 数字与命名条件子模式、局部 `(?-i:...)` 关闭、`(?#...)` 注释组；
  - ASCII 字符类中负向速记与普通字符混合、取反混合及字面 `]`。
- 新语料暴露 `fancy-regex` 的 Unicode 忽略大小写集合少于 Python、但 ASCII `[a-z]` 又会额外纳入 `ſ/K`。Rust 适配层现在按当前 scope：
  - 在 Unicode 模式补齐 Python 四个特殊字符族；
  - 在 ASCII 模式用局部关闭 `i` 的守卫校正 `ſ/K` 的字符类成员关系，并保持非 ASCII 字面量大小写敏感。
- Rust 编译前会按 Python 捕获组编号将 `(?(name)...)` 命名条件转换为底层支持的数字条件；数字条件保持原样。
- Python `(?#...)` 注释组转换为空的非捕获组；命名组声明和命名回引在 Unicode case 适配期间保持语法区不被改写。

以上内容已提交为 `665d27c test(core): cover Python regex case and conditions`。

## 本轮 Windows-only CI 提交

- `.github/workflows/ci.yml` 的 Python oracle 从 Ubuntu 移到 `windows-latest`。
- Rust core/CLI 三平台矩阵暂时移除，CLI-only 与完整 GUI/default 测试均只在 `windows-latest` 运行。
- `RUST_REFACTOR_PLAN.md` 和 `RUST_REFACTOR_DESIGN.md` 已同步：当前阶段、发布退出条件与兼容矩阵以 Windows 成功为准；macOS/Linux CI 和验收标记为暂缓，待 Windows 版本稳定后恢复。
- 跨平台生产实现和 POSIX 共享语料没有删除，避免未来恢复 CI 时重新建立兼容基线。

以上内容已提交为 `f730cfd ci: focus Rust migration checks on Windows`。

## 本轮 CLI 缺值与多余参数提交

- 将共享 CLI stderr 字节快照从 15 条扩展为 32 条，新增 17 条覆盖：
  - `help`、`completion`、`config set/reset`、`restore`、`gui`、`version` 的多余参数；
  - 未知 `config` 子操作和 `config set-editor` 缺命令；
  - `rename` 的 `path-type`、`timeout`、`sort-by`、`depth` 缺值，以及 `exclude` 缺至少一个值；
  - 配置 JSON 的未闭合数组、尾随逗号和对象缺失值。
- Rust 的 argparse 兼容映射补齐上述 usage、参数名、required/unrecognized 文案和平台换行；成功路径及未命中的 clap 回退保持不变。
- serde_json 的 EOF、trailing comma、expected value 位置现在映射为 Python `JSONDecodeError` 的 line/column/char 文案，并按 Unicode 字符数计算 char offset。

以上内容已提交为 `f39da8f test(cli): cover missing and extra arguments`。

## `main` 分支回归审计（已提交到 `main`）

- 审计确认 `main` 已有启动器延迟保存、多标签等待、保存超时和截断编辑的等价覆盖，无需把 Rust 共享 fixture 带回主线。
- `main` 缺少“编辑器进程持续存活直至总等待超时”的分支覆盖，因此 `tests/fakeditor.py` 新增 `sleep` 模式，`tests/test_editor.py` 新增对应回归测试。
- 新测试确认现有 Python 生产实现行为正确：超时后继续、文件保持不变，并发送“等待编辑器超时”状态；未发现需要修改的生产代码 bug。
- `tests/test_editor.py` 定向 11 项和 `main` 全量 Python 测试均已通过。
- `target/` 是在 Rust 分支构建产生、切到不忽略该目录的 `main` 后显示的本地构建产物，不应暂存。
- 后续又在 `main` 修复 Windows 编辑器命令引号，提交为 `d9f73d7`；该提交已单独 cherry-pick 到 `rust` 为 `7d42547`。

以上 Python 回归已在 `main` 提交为 `a1d939f Update pytest`，`target/` 忽略规则提交为 `b536455 Update .gitignore`；这两项提交尚未合并到 `rust`，Rust 分支的共享编辑器 fixture 已包含对应覆盖。

## 本轮 GUI 与编辑器提交

- 将 `apps/onomedit/src/gui.rs` 从仅显示标题/状态的骨架扩展为可用的 Rust 桌面工作流：
  - 主窗口支持文件、目录、剪贴板和 egui 原生拖放输入，按配置展开、去重、排序并显示最终处理顺序；
  - 支持路径类型、展开层级、编辑器模式、直接规则模式、强制只读预览和恢复上次操作；
  - `prepare -> 编辑器等待 -> plan`、确认后的执行以及恢复均在后台线程运行，通过 channel 向 UI 线程发送状态和结果，忙碌期间界面持续重绘；
  - 确认页使用稳定行 ID 和显式 `checked` 状态，支持全选/全不选、相对路径、差异/距离列及所选子集执行；dry-run 页不提供执行入口；
  - 设置页覆盖现有 Python GUI 暴露的编辑器、排序、展开、行为、排除、预览和安全选项，保存仍调用共享配置 API；
  - 目标重复会在任何文件操作前中止，并显示详情窗口；成功、失败、无变化统计及 `exit_after` 延迟退出已接入；
  - Windows 优先加载微软雅黑/黑体作为 egui 中文字体，其他平台保留常见 CJK 字体降级路径。
- 新增 4 个 GUI 状态单元测试，覆盖稳定行 ID/显式勾选、dry-run 状态、设置数字校验和结果统计文案。
- 首次实机反馈发现主窗口滚动列表会抢占剩余高度，导致操作按钮被挤出可视区域；当前工作区已改为操作区固定在列表上方、列表仅占剩余空间、状态栏固定在底部，确认页和设置页的按钮也固定在滚动内容之前。
- 第二轮实机反馈修复两项 GUI/编辑器问题：
  - 确认表格原先在 `push_id` 子 UI 中调用 `end_row`，没有结束外层 Grid 行，导致全部文件横向连成一行；现在稳定 ID 只包裹勾选框，并在 Grid 父 UI 上逐项结束行。
  - 现代 Windows Notepad 可能把文件交给已有标签页并让启动进程退出；旧的 2 秒快速退出判断会过早结束计划会话并删除临时文件，使后续 `Ctrl+S` 退化为“另存为”。Python/Rust 编辑器协议现在会自动识别 Notepad、Notepad++、VS Code/Codium、Sublime、Kate/Gedit 等常见单实例/标签式编辑器，直接轮询等待文件实际保存。
- 新增超过 2 秒才退出的 `notepad.cmd` 假启动器回归：启动器退出后由后台进程延迟保存，验证调用方在保存完成前不会返回；Python 和 Rust 两端均覆盖。
- 后续确认 Notepad 的“另存为”不属于 `%TEMP%` ACL 问题：Rust `EditFile` 持有 `NamedTempFile` 句柄，而现代编辑器常通过删除/替换原文件安全保存。现在改为 `TempPath` 管理生命周期，初始内容 flush 后立即关闭句柄，仍在会话结束时自动删除；新增会话存活期间删除并替换编辑文件、随后正常读回和清理的回归测试。
- 设置窗口“重置默认”暂时严格保留 Python 基线的“不保存并关闭”语义，避免在兼容迁移中夹带行为修复。
- 仍需 Windows 实机 smoke：原生文件/目录对话框、拖放、中文字体显示、编辑器窗口聚焦，以及确认页在大量长路径下的可用性。

GUI 工作流已提交为 `8a0b5da feat(gui): implement Rust desktop workflow`；标签式编辑器等待、Notepad 原子保存与对应 Python/Rust 回归已提交为 `304642a fix(editor): support tabbed editor saves`。

## 本轮 Rust 发布打包提交

- `.github/workflows/build-windows.yml` 已从 uv/Nuitka 切换为 Cargo release 构建，使用锁文件分别产出：
  - 默认 GUI feature 的 `onomedit.exe`；
  - `--no-default-features` 的 `onomedit-cli.exe`。
- 发布 workflow 新增 Rust 缓存、显式 `contents: write` 权限和手动运行入口；手动运行只构建、验证及上传 artifact，只有 `v*` 标签运行才创建 GitHub Release。
- 新增 `scripts/e2e_release.ps1`，只调用构建后的两个 `.exe`，在隔离 `%APPDATA%` 和临时文件树中验证：
  - 完整版及 CLI-only 的 `version`、`help`；
  - `config` 写入/读取；
  - `rename -> history -> restore -> dry-run` 的退出状态和最终文件树；
  - 整个流程不调用 Python 或开发环境命令。
- README 的 Windows 构建与发布说明已改为 Cargo，并列出两种 release 产物及发布物 E2E 命令。
- 本机 release 产物约为 7.62 MiB（GUI）和 3.24 MiB（CLI-only）；旧 Nuitka 脚本和 Python oracle 暂时保留，继续作为回滚与兼容基线，不参与新标签发布。

以上内容已提交为 `37fa2ab build: replace release packaging with Rust artifacts`。

## 本轮迁移与性能基线提交

- 新增 `tests-rust/fixtures/v0_1_6/` 代表性 Python v0.1.6 持久化快照：
  - 完整非默认配置包含带空格编辑器路径、嵌套选项、shell 属性、Unicode 自动规则和临时目录；
  - 日志包含 Unicode、UNC 路径，以及旧路径自身含 `<-->` 的右分割场景。
- Python oracle 新增共享快照读取测试；Rust 新增迁移集成测试，确认旧配置加载时不被重写，可修改、原子保存并再次加载，旧 `history.log`/`last.log` 无需转换即可读取。
- 新增 ignored release 性能测试，隔离覆盖 10,000 文件目录收集/排序/临时文件、10,000 项纯计划、252 字符长路径和 1.86 MB/20,000 对日志读取。
- 新增 `docs/RUST_PERFORMANCE_BASELINE.md`，记录可复现命令、环境、首轮数据和后续 25% 中位数回归判定方法。
- 2026-08-25 本机首轮 release 数据：大目录 prepare 845 ms、10,000 项 plan 2 ms、252 字符路径 1 ms、1.86 MB 日志读取 10 ms；10,000 个测试文件造数 5,449 ms，不计入核心流程。

以上内容已提交为 `5febad6 test: add migration and performance baselines`。

## 已验证

- Python：`342 passed`
- Rust 默认 feature：`58 passed`（原 56 项加 2 项 v0.1.6 迁移兼容）；性能基线另有 1 项 ignored 手动测试并已在 release 模式通过。
- Rust CLI-only：`54 passed`，性能基线同样默认 ignored。
- `cargo fmt --all -- --check` 通过。
- 完整版及 `--no-default-features` CLI-only 构建通过。
- Clippy `-D warnings` 通过。
- Rust CLI `version`、`help` smoke 通过。
- 两种 `--release` 构建通过；`scripts/e2e_release.ps1` 对实际 release exe 的 config/rename/history/restore/dry-run 全流程通过。
- 两套 Clippy `--all-targets -D warnings` 在新增迁移/性能测试后通过；新增 Rust 文件的 rustfmt 检查和仓库 `git diff --check` 通过。

本轮还单独验证了 `cargo test --workspace --offline`、全 feature/all target Clippy 和 CLI-only 离线构建。项目未声明 Ruff 开发依赖，因此 `uv run ruff check .` 无法找到 Ruff；这不是 lint 失败，也未为此改动 Python 工具链。

首次 Cargo 依赖下载在本机代理下较慢，但已完成缓存；无需修改系统代理或安装额外工具。

## 尚未完成

- 继续扩充 Python/Rust 差分语料及文件系统 E2E，覆盖全部既有行为；收集层符号链接、文件属性及 mtime/ctime 已进入共享门禁。macOS/Linux 真实平台确认按当前决定暂缓，现阶段只要求 Windows 成功。
- 继续补充 Python 正则方言语料；当前已覆盖常用断言/回引/替换、ASCII/Unicode 嵌套 scope、Python Unicode/ASCII `IGNORECASE` 特例、数字/命名条件、字符类负向速记、verbose/注释组、空匹配推进、原子组和占有量词，但完整 Python `re` 方言仍未穷尽。剩余窄边界包括 ASCII 忽略大小写字符类中显式非 ASCII 成员、转义 Unicode/十六进制字面量，以及 verbose 注释与命名条件编号交错的组合。
- 继续补齐日志多份轮转/损坏输入和平台能力的完整测试；基础编辑器等待状态机、日志轮转与 partial/last/all restore 已进入共享门禁。
- Windows GUI 聚焦行为仍需 Windows CI/实际 smoke 验证；编辑器命令的核心引号、`.cmd/.bat` 与 PATH/PATHEXT 行为已进入共享门禁，更复杂的 shell 元字符组合仍未穷尽。
- CLI 已有稳定输出 golden、完整默认 config JSON、全部 help topic、五种补全的字节快照、32 条参数/配置错误快照、损坏/容错配置 E2E 和完整 rename/history/restore E2E；后续仅按新发现差异补充，不再优先扩张错误类别。
- Rust GUI 核心桌面工作流已在当前工作区实现；继续补 Windows GUI 状态测试和实际 smoke，并根据结果修正交互细节。
- Rust 标签发布打包、Cargo 构建说明、本地发布物 E2E、性能基线和 Python v0.1.6 代表性配置/日志升级验证已完成；远端 CI/干净 runner 和真实用户数据复核已由用户明确排除，剩余发布项是补回滚说明。达到其余兼容门禁后再删除 Python 运行时代码及旧 Nuitka 脚本。

## 建议续接顺序

1. 继续按实机反馈完善 GUI，并补 Windows 状态测试与实际 smoke；正则和 CLI 仅按新发现差异继续扩充。
2. 用 Rust 测试辅助程序替换 `tests/fakeditor.py`，确保删除 Python 后编辑器协议测试仍可独立运行。
3. 补回滚说明并完成 Windows 本地兼容签字，然后切换/删除 Python 运行时；远端、macOS/Linux CI 及真实用户数据复核均不作为当前门禁。

详细契约仍以 `docs/RUST_REFACTOR_PLAN.md` 和 `docs/RUST_REFACTOR_DESIGN.md` 为准。
