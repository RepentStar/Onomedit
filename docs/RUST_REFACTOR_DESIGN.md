# Onomedit Rust 重构设计

## 1. 目标与边界

本次重构的目标是用 Rust 复刻 Onomedit 的可观察行为，同时降低发布体积、部署复杂度和运行时依赖。现有 Python 实现和测试在迁移期间作为行为基准（oracle），不是仅供参考的旧代码。

必须保持兼容的内容包括：

- CLI 子命令、参数、默认值、退出码、stdout/stderr 分流和主要提示文本；
- 配置文件位置、JSON 字段、默认值、损坏备份和版本迁移行为；
- 路径收集、glob、stdin/剪贴板优先级、目录展开、排除、去重和排序；
- `full`、`name`、`stem`、`ext` 四种编辑范围及多扩展名、点文件语义；
- 临时文件的 UTF-8/LF 编码、一项一行和行数不一致时整批中止；
- 自动规则、占位符、应用顺序、安全名称清理和预览结果；
- 编辑器启动、等待、快速退出识别、多标签轮询和超时后继续；
- 重复目标预检、外部目标占用自动编号、链/环处理、逐项失败继续；
- `last.log`、`history.log`、`error.log` 的位置、格式、轮转和恢复语义；
- Windows、macOS、Linux 上当前已有的降级行为；
- 完整版与 CLI-only 版的入口行为和 shell 补全输出。

GUI 不要求像素级复刻，可以调整布局、主题和控件，但下列核心交互必须保留：添加文件/目录/剪贴板/拖拽、展开与排序、编辑器模式、直接应用规则、强制预览、选择部分项目执行、设置、恢复最近一次，以及后台执行时界面不冻结。

本阶段不顺带改变重命名策略、配置格式、日志格式、正则语法或 CLI 文案。发现旧实现缺陷时先用回归测试记录，再单独决定是否在兼容版本之后修正。

## 2. 当前行为模型

核心流程不是“遍历后直接 rename”，而是一个带安全闸门的流水线：

```mermaid
flowchart LR
    A[CLI / GUI 输入] --> B[收集与 glob]
    B --> C[目录展开、排除、去重、排序]
    C --> D[按 path_type 写临时文件]
    D --> E[外部编辑器或直接规则]
    E --> F[读回并校验行数]
    F --> G[自动规则]
    G --> H[占位符展开]
    H --> I[安全名称清理]
    I --> J[重复目标整批预检]
    J --> K[dry-run / GUI 确认]
    K --> L[链环解开与逐项重命名]
    L --> M[日志与恢复]
```

顺序本身就是兼容契约。例如 `<n>` 的结果取决于排序后的行序，名称清理必须发生在重复目标检查之前，恢复必须把日志倒序后执行 `new -> old`。

### 2.1 关键兼容细节

- 未传 `paths` 时，非 TTY stdin 优先于剪贴板；空管道直接失败，不回退剪贴板。
- glob 不递归；不存在的显式路径或无匹配模式被忽略，最终为空才报错。
- `depth <= 0` 保留目录本身；`depth = 1` 只包含直接子项，展开后不保留输入目录。
- 去重键是平台语义下的规范化绝对路径，保留首次出现项。
- Windows 名称/路径排序和目标重复判断不区分大小写，POSIX 保持大小写敏感。
- 点文件 `.gitignore` 的 `stem` 是 `.gitignore`，`ext` 为空；`a.tar.gz` 只把 `.gz` 当最后一个扩展名。
- 占位符计数器按 `(start, width, step)` 分组，在一个批次内跨文件、跨同一文本中的多个位置连续计数。
- 无效条件正则、无效替换正则和未知转换均静默跳过，不使批次失败。
- 名称清理在所有平台采用 Windows 的非法字符、设备保留名和尾随点/空格规则。
- 多个变化项指向同一目标时，在执行任何文件操作之前中止；`old == new` 的项不参与该检查。
- 已存在且不属于本批次的目标使用 `name (1).ext` 递增；链和环使用内部临时名分两阶段落位，日志不能泄露临时名。
- 单项 `rename` 失败会记录错误并继续；全路径模式仅在源仍存在时创建缺失目标父目录并重试。
- 编辑器正常模式等待进程退出；若进程在 2 秒内退出且临时文件未变化，则切换为保存轮询；显式多标签模式直接轮询。

## 3. 推荐架构

采用 Cargo workspace，把无 UI 的业务逻辑、平台适配和界面隔离。建议目录如下：

```text
Onomedit/
├─ Cargo.toml
├─ Cargo.lock
├─ crates/
│  ├─ onomedit-core/       # 纯业务规则，尽量不直接调用 UI 或全局环境
│  └─ onomedit-platform/   # 剪贴板、文件属性、编辑器进程、窗口聚焦、配置目录
├─ apps/
│  └─ onomedit/            # CLI 分发；可选 gui feature 和 GUI 模块
├─ tests-rust/
│  ├─ fixtures/            # Python/Rust 共用的输入与期望结果
│  └─ differential/        # 两个实现的差分测试驱动
├─ src/                    # 迁移期间保留的 Python oracle
├─ tests/                  # 迁移期间保留的 Python 回归测试
└─ docs/
```

依赖方向固定为：

```text
onomedit UI ──┐
              ├──> onomedit-core
onomedit CLI ─┘          ↑
       │                 │
       └────> onomedit-platform
```

`onomedit-core` 不依赖 GUI，也不读取进程级全局配置。时间、随机数、UUID、剪贴板文本、文件元数据和文件操作应通过参数或窄接口注入，使关键算法可以确定性测试。

### 3.1 模块映射

| 现有 Python 模块 | Rust 模块建议 | 职责 |
| --- | --- | --- |
| `core/pathitem.py` | `onomedit_core::path` | 四种路径字段、字段替换、平台路径键 |
| `core/collection.py` | `onomedit_core::collection` | 收集、展开、排除、去重、排序 |
| `core/config.py` | `onomedit_core::config` | 类型、默认值、JSON 兼容与迁移 |
| `core/rules.py` | `onomedit_core::rules` | 规则校验、条件与转换 |
| `core/envvars.py` | `onomedit_core::template` | 批次占位符状态机 |
| `utils/safename.py` | `onomedit_core::safe_name` | 清理和占用目标序号化 |
| `core/pipeline.py` | `onomedit_core::pipeline` | prepare、plan、execute、preview、restore |
| `core/logger.py` | `onomedit_core::journal` | 兼容日志、轮转、读取 |
| `core/tempfile_mgr.py` | `onomedit_core::edit_file` | 临时文件协议与签名 |
| `core/editor.py` | `onomedit_platform::editor` | 命令解析、进程等待、Windows 聚焦 |
| `utils/clipboard.py` | `onomedit_platform::clipboard` | HDROP、文本和跨平台降级 |
| `utils/fileattr.py` | `onomedit_platform::file_attr` | 只读、隐藏、系统属性 |
| `core/completion.py` | `apps::onomedit::completion` | 五种 shell 的兼容脚本生成 |
| `cli.py` | `apps::onomedit::cli` | 参数解析、输出与退出码 |
| `gui/*` | `apps::onomedit::gui` | 主窗口、设置、确认列表和后台任务 |

### 3.2 核心类型

建议显式建模，减少字符串和布尔值在模块间的隐式约定：

- `Config` 及 `ExcludeOptions`、`PreviewOptions`、`SafetyOptions`：使用 `serde`，所有字段有与 v1 JSON 一致的默认值，未知字段忽略。
- `PathType`、`SortBy`、`RuleKind`、`ConvertKind`、`InsertAt`：枚举负责解析和序列化，不在流程中传播裸字符串。
- `PathItem`：保留原始 `PathBuf`，提供四段读取和替换；显示字符串与文件系统路径分开处理。
- `RenamePair { old, requested_new }`：计划阶段结果不可修改。
- `AppliedRename { old, actual_new }`：执行阶段记录自动编号后的真实目标。
- `RenameResult { success, failed, skipped }`：结构与现有统计保持一致。
- `PipelineOutcome`：明确 dry-run、计划、预览和执行结果。
- `Clock`、`RandomSource`、`FileSystem`：先以小 trait 或参数注入；测试使用固定实现，生产使用系统实现。

不要为了抽象而把每个函数做成 trait。只有时间/随机/文件系统等会造成非确定性或平台差异的边界需要接口。

## 4. 技术选型

建议只锁定能力，不在设计文档中锁死版本号；实际版本由 `Cargo.lock` 和依赖审计决定。

| 能力 | 建议 | 说明 |
| --- | --- | --- |
| CLI | `clap` derive/builder | 复刻子命令与参数校验；帮助文本需 golden test，不依赖默认文案恰好相同 |
| 序列化 | `serde`、`serde_json` | 保持 v1 配置 JSON |
| 错误 | `thiserror` | 库层结构化错误；应用层决定中文提示和退出码 |
| 临时文件 | `tempfile` | 保持系统临时目录或 `temp_dir` 覆盖 |
| glob/遍历 | `glob`、`walkdir` 或小型自实现 | 必须配置并测试前导点、大小写、符号链接和遍历顺序，不直接接受默认行为 |
| 正则候选 | `fancy-regex` + 项目适配层 | 支持反向引用和环视，但不是 Python `re` 的完全替代，必须通过兼容语料门禁 |
| 日期/UUID/随机数 | `chrono`、`uuid`、`rand` | 格式化仍使用项目自己的 token 替换器 |
| 平台 API | `windows`（Windows target） | CF_HDROP、文件属性、编辑器窗口聚焦 |
| GUI | `eframe/egui`，文件对话框可用 `rfd` | 原生单文件发布友好，拖拽和后台消息模型简单；只要求交互等价 |

需要特别处理的能力：

1. **Python 正则兼容**：Rust `regex` 不是 Python `re` 的等价实现，尤其是反向引用、环视和替换串 `\1` 语法。第一候选是 `fancy-regex`，因为它支持反向引用和环视；但其目标语法也不是 Python `re`，且仍有缺失特性。规则层必须封装 `RegexEngine` 和替换串转换，并增加 Python/Rust 语料差分。至少必须支持文档和现有测试中的 Python 风格分组替换；遇到不支持的、但 Python 可执行的表达式应视为兼容阻塞项，不能静默改变结果。
2. **Python 字符串转换兼容**：Unicode `upper`、`lower`、`capitalize`、`title` 和 URL 解码在不同库中可能不同。用包含中文、组合字符、特殊大小写和非法 UTF-8 百分号序列的 golden corpus 固化结果。
3. **`difflib.SequenceMatcher` 兼容**：第三方 diff 库的分块可能与 Python 不同。若 CLI/GUI 显示必须相同，应移植当前所需的 SequenceMatcher 算法，而不是只保证编辑距离相同。
4. **命令行拆分兼容**：Windows 和 POSIX 对引号、反斜杠、`.cmd/.bat` 的处理不同。为 `set-editor` 常见命令建立平台测试；Windows 批处理文件仍需通过命令解释器启动。

## 5. 重命名执行器设计

执行器保持现有的“预检 + 两阶段执行 + 最佳努力日志”语义，不擅自升级成全事务系统。

### 5.1 预检

1. 忽略 `old == new` 项。
2. 按平台路径键对 `new` 分组。
3. 任一组包含两个以上源路径时返回结构化 `DuplicateTargetError`。
4. 预检失败时不得创建目录、临时文件或日志会话，不得移动任何源文件。

### 5.2 执行

1. 建立保留输入顺序的待处理映射。
2. 若目标是尚未执行的源，先把该源移到同目录的唯一内部临时名。
3. 若目标仍被批次外实体占用，计算 `name (N).ext`。
4. 执行 `old -> actual_new`；必要时创建目标父目录后重试一次。
5. 单项失败写入 `failed/error.log`，继续后续项。
6. 第二阶段把临时项放到最终目标；再次处理真实占用冲突。
7. 只把用户可见的 `old -> actual_new` 写入成功日志。

内部临时名沿用 `.__onomedit_tmp_<pid>_<seq>_<stem><ext>` 形态，便于迁移期排查。需补充崩溃残留测试和清理策略，但在兼容发布中不要改变正常成功路径的可观察结果。

### 5.3 文件系统竞态

“检查目标不存在”与 `rename` 之间存在天然竞态。第一版 Rust 重构保持当前结果语义，同时把检查和执行集中到 `FileSystem` 边界。后续若改为平台原子 API，需要单独设计并评估 Windows/POSIX 差异，不能夹带在兼容重构里。

## 6. 配置、日志与发布兼容

### 6.1 配置

- Windows：`%APPDATA%\Onomedit\config.json`，缺失 `APPDATA` 时回退用户目录下 `AppData\Roaming`。
- macOS：`~/Library/Application Support/Onomedit/config.json`。
- Linux：`${XDG_CONFIG_HOME:-~/.config}/Onomedit/config.json`。
- 缺失字段补默认，未知字段忽略；损坏文件尽力替换为 `config.json.bak` 后写默认配置。
- 保存继续采用同目录临时文件 `config.json.tmp` 后替换，避免半写入。
- `version = 1` 和所有字段名、默认值不变，Rust 可新增内部默认但不可擅自写入新字段。

### 6.2 日志

- 分隔符保持 `<-->`，读取时从右侧分割，允许旧路径自身包含分隔符。
- `history.log` 超过 1 MiB 时在下一次追加前轮转，保留 `history.1.log` 至 `history.5.log`。
- 日志 I/O 继续是最佳努力：失败不阻断成功重命名。
- Rust 版必须能读取 Python 版历史并恢复；Python 版也应能读取 Rust 版产生的日志，直到正式切换完成。

### 6.3 产物

维持两个 Windows 发布物：

- `onomedit.exe`：带 GUI，双击或无参数启动 GUI，同时支持完整 CLI。
- `onomedit-cli.exe`：不链接 GUI；执行 `gui` 或无参数时返回清晰的 GUI 不可用提示。

Rust workspace 使用 `gui` feature 控制 GUI 依赖。CI 除 Windows 发布外，建议增加 Windows/macOS/Linux 的 core/CLI 测试矩阵；GUI 做编译测试和少量自动化 smoke test。

## 7. GUI 重构原则

推荐使用即时模式 GUI，但保持业务状态与界面状态分离：

- `AppState` 只保存原始输入、当前配置、展开后的显示项、忙碌状态和最近结果。
- 后台线程执行 `prepare/plan` 和编辑器等待，通过 channel 向 UI 线程发送状态事件；不从工作线程直接操作控件。
- 确认页使用稳定的行 ID 和显式 `checked` 布尔值，不用控件选中态隐式代表勾选。
- dry-run 总是进入确认/预览页且不执行；普通开始由 `skip_confirmation` 决定直接执行还是确认。
- 确认页按 `preview.diff`、`preview.distance` 动态显示列，真正执行始终使用完整路径。
- 配置保存成功后重新加载并刷新排序；“重置默认”要明确保存语义，迁移时需用测试确认现有窗口行为后再决定是否修复。
- 文件拖拽是完整版能力；不可用时按钮、文件对话框和剪贴板仍可工作。

## 8. 测试策略

现有 207 个 Python 测试是最低基线，但不能直接等价成“Rust 已兼容”。建议四层验证：

### 8.1 纯函数移植测试

把 path、safe name、transform、template、rules、diff、config coercion 的每个 Python 用例一一移植为 Rust 单元测试。随机数、时间和文件元数据通过固定源注入。

### 8.2 共享 fixture/golden 测试

使用 JSON/JSONL 保存语言无关案例：输入、平台标记、配置、期望计划、期望错误。Python 和 Rust 都读取同一文件，重点覆盖：

- Unicode、点文件、多扩展名、尾随点/空格、保留名；
- glob、重复/相对路径、父子目录重叠、符号链接；
- Python 正则条件与替换串；
- 占位符组合、格式不完整和同组计数；
- CLI 帮助、错误输出、退出码和补全脚本字节内容；
- 配置损坏、缺失字段、未知字段和日志轮转。

### 8.3 文件系统场景差分

测试驱动分别在隔离临时目录运行 Python 和 Rust：先复制完全相同的目录树，再比较最终树、文件内容、日志、stdout/stderr 和退出码。覆盖普通改名、真实冲突、交换、三节点环、链、目标目录创建、部分失败、restore last/all/partial。

### 8.4 平台与 GUI 验证

- Windows/macOS/Linux 分别跑 core 与 CLI；大小写敏感行为不能只在一个平台模拟。
- Windows 专测 CF_HDROP、隐藏/系统/只读位、`.cmd/.bat` 编辑器和窗口聚焦。
- GUI 测试核心状态转换，人工 smoke 只负责原生对话框、拖拽、焦点和视觉可用性。

兼容判定以“同输入、同平台得到同计划、同文件树和同退出语义”为准；Rust 内部结构是否与 Python 相似不作为判定标准。

## 9. 主要风险与对策

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| Rust 正则方言与 Python `re` 不同 | 自动规则静默改名错误 | 封装引擎、替换串适配、差分语料；不支持案例阻断发布 |
| `Path`/Unicode/大小写语义不同 | 去重、排序、冲突判断错误 | 平台路径键集中实现，真实 Windows/POSIX CI 验证 |
| 遍历和 glob 默认行为不同 | 临时文件项目或顺序变化 | 不依赖库默认值，共享目录树 golden 测试 |
| 编辑器进程模型不同 | 提前执行或等待过久 | 逐项复刻阈值和状态机，假编辑器端到端测试 |
| diff 分块算法不同 | CLI/GUI 预览变化 | 移植兼容算法并做文本快照 |
| GUI 异步竞态 | 重复执行、冻结或错误退出 | 单向事件 channel、明确 busy 状态、核心操作幂等保护 |
| 日志兼容遗漏 | 无法恢复旧改名 | 双向读写兼容测试，切换前备份真实样例验证 |
| 一次性替换范围过大 | 难以定位偏差 | 按模块小步迁移，每阶段有进入/退出门槛 |

## 10. 完成定义

满足以下条件才认为 Rust 重构完成：

- Python 现有 207 个测试保持通过，Rust 中存在对应覆盖；
- 共享 golden 和文件系统差分套件在支持平台全部通过；
- CLI 命令、配置与日志可与 v0.1.6 互操作；
- 所有安全闸门在执行任何破坏性操作前生效；
- 完整版 GUI 完成全部核心工作流，CLI-only 版不携带 GUI 依赖；
- Windows 发布物通过 rename/history/restore/dry-run 的打包后 E2E；
- 发布文档说明 GUI 外观变化，但不要求用户迁移配置或日志；
- Python 实现仅在上述条件满足后移除，不在差分验证完成前删除 oracle。

## 11. 选型参考

- [`eframe` 官方 API 文档](https://docs.rs/eframe/latest/eframe/)：原生 `egui` 应用框架和入口模型。
- [`fancy-regex` 官方 API 文档](https://docs.rs/fancy-regex/latest/fancy_regex/)：反向引用、环视、限制和回溯模型。
- [`windows-rs` 官方文档](https://microsoft.github.io/windows-docs-rs/)：Microsoft 提供的 Win32/COM/WinRT Rust 投影。
