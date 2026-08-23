# Onomedit Rust 重构实施计划

## 1. 实施策略

采用旁路重写（parallel implementation），而不是直接逐文件翻译：迁移期间保留 Python 实现可运行，在同一仓库增加 Rust workspace；每完成一个能力，就用共享 fixture 比较两个实现。最后才切换默认构建和删除 Python 运行时代码。

阶段顺序遵守两个原则：

1. 先移植确定性纯逻辑，再处理文件系统、进程和 GUI。
2. 每个阶段都能独立验收和回退，不让“应用能启动”代替行为兼容。

## 2. 分支与提交组织

当前工作分支：`rust`。

建议保持小而可审查的提交序列：

1. `docs: define Rust parity contract and migration plan`
2. `build: add Cargo workspace and CI checks`
3. `test: add shared compatibility fixtures`
4. `feat(core): port config path and safe-name semantics`
5. `feat(core): port rules templates and preview`
6. `feat(core): port collection and planning pipeline`
7. `feat(core): port renamer journal and restore`
8. `feat(platform): port editor clipboard and file attributes`
9. `feat(cli): implement compatible command surface`
10. `feat(gui): implement Rust desktop workflow`
11. `build: replace release packaging with Rust artifacts`
12. `chore: remove Python runtime after parity gate`

不要在同一提交里同时改行为契约和实现；若确需修复旧行为，先新增能说明差异的测试并单独评审。

## 3. 阶段计划

### 阶段 0：冻结兼容基线

任务：

- 记录当前 Python 测试基线和支持平台。
- 从现有测试提取语言无关 fixture，建立 `tests-rust/fixtures`。
- 为所有 CLI 子命令采集 stdout、stderr、退出码和帮助文本快照。
- 建立隔离配置目录、固定时钟/随机源和假编辑器驱动。
- 补齐目前主要依赖 README 描述、但缺少自动化覆盖的行为。

优先补测项：

- 无参数启动 GUI、CLI-only 缺 GUI 的提示和退出码；
- `config`、`reset`、`history`、`restore --all/--partial` 的完整 CLI 输出；
- 配置 JSON 的原子替换、`.bak`、日志轮转边界；
- glob 前导点、遍历顺序、目录 symlink 不跟随；
- `title`/Unicode/URL 解码和复杂 Python 正则；
- 编辑器命令带空格、引号、`.cmd/.bat` 和超时边界；
- GUI 设置窗口重置后是否持久化，先锁定事实再讨论修复。

退出门槛：Python 回归保持全绿；共享 fixture 可由 Python runner 读取；每项兼容行为都有明确期望或明确列为待决。

### 阶段 1：建立 Rust workspace 与质量门禁

任务：

- 新增 workspace、`onomedit-core`、`onomedit-platform` 和应用 crate。
- 配置 `rustfmt`、`clippy -D warnings`、单元测试和最小支持 Rust 版本策略。
- CI 增加 Windows、macOS、Linux 的 format/check/test；Windows 增加完整和 CLI-only 编译。
- 建立统一错误类型和应用层退出码映射。
- 引入依赖审计与许可证检查，生成并提交 `Cargo.lock`。

退出门槛：空骨架在三平台编译；CLI-only 构建不解析或链接 GUI 依赖；CI 可缓存但不依赖本地工具状态。

### 阶段 2：移植确定性核心逻辑

范围：

- `PathItem` 四字段和平台路径键；
- 安全名称清理与自动编号候选；
- 全半角、大小写、title、URL decode；
- Levenshtein 和兼容 diff；
- 配置数据结构、默认值、反序列化容错和 `config set` 类型推断；
- 规则结构、条件、替换、插入和序列化；
- 占位符解析状态机及日期 token。

实施顺序：先让 Rust 单测复刻 Python 测试，再让两个 runner 读取共享 fixture。时间、UUID 和随机数不得直接写死为全局调用。

退出门槛：纯逻辑共享 fixture 零差异；Python 风格替换串 `\1` 和无效正则跳过行为通过；Unicode 差异已消除或有经确认的兼容决策。

### 阶段 3：移植收集与计划流水线

范围：

- 参数、glob、剪贴板文本输入的路径收集模型；
- 目录深度展开、排除、去重、排序和 reverse；
- UTF-8/LF 临时文件、签名和严格行数校验；
- `prepare -> plan` 顺序与 dry-run preview。

测试使用固定目录树，同时在 Python 与 Rust 临时目录副本中运行。对遍历顺序不要做跨平台统一化，目标是同平台与当前 Python 一致。

退出门槛：对相同配置和目录树，两边生成完全相同的项目顺序、临时文件行、rename pairs、预览文本和错误类别。

### 阶段 4：移植执行器、日志与恢复

范围：

- 重复目标整批预检；
- 外部占用自动编号；
- 两节点交换、长链和多节点环；
- 缺失目标父目录创建；
- 单项失败继续和结果统计；
- 三类日志、1 MiB/5 份轮转、last/all/partial 恢复。

为每个场景创建两份相同目录树，执行后比较路径集合、文件内容和日志字节。测试中验证内部临时名不会出现在用户日志中。

退出门槛：文件系统差分零差异；Rust 可恢复 Python 日志，Python 可读取 Rust 日志；预检失败确认目录树和日志均未变化。

### 阶段 5：移植平台能力与外部编辑器协议

范围：

- 系统配置目录和默认编辑器探测；
- Windows CF_HDROP/CF_UNICODETEXT，macOS `pbpaste`，Linux `xclip/xsel`；
- Windows 文件属性和 POSIX 降级；
- 编辑器命令拆分、可执行文件解析、批处理启动；
- 进程等待、2 秒快速退出判断、0.3 秒保存轮询、总超时和 Windows 聚焦。

沿用 `tests/fakeditor.py` 或新增等价的小型 Rust 假编辑器，分别模拟保存、立即退出、延迟保存、删行和超时。窗口聚焦属于最佳努力能力，失败不能改变主流程结果。

退出门槛：当前编辑器测试场景全部等价；三个桌面平台完成真实编辑器 smoke；Windows 剪贴板文件列表优先于文本。

### 阶段 6：实现兼容 CLI

范围：

- `help`、`config`、`rename`、`restore`、`history`、`gui`、`version`、`completion`；
- 无参数入口、stdin TTY 判断、管道错误提示；
- 参数临时覆盖但不污染持久配置；
- 中文 UTF-8 输出、stdout/stderr 分流和退出码；
- bash、zsh、pwsh、fish、psc 补全脚本。

优先复刻参数解析结果和退出语义，再对帮助文本做 snapshot。补全脚本如改由 `clap` 生成，产出仍必须满足现有命令、选项和候选值契约；若字节级内容变化，应通过行为测试证明兼容后单独评审。

退出门槛：原 `scripts/e2e_cli.ps1` 的 Rust 等价流程通过；所有 CLI golden case 在支持平台通过；完整和 CLI-only 两种 feature 组合均可构建。

### 阶段 7：实现 Rust GUI

建议分三步：

1. 主窗口：添加、拖拽、剪贴板、展开列表、排序、路径类型和状态栏。
2. 工作流：后台 prepare/plan、编辑器等待、直接执行、强制预览、重复目标提示。
3. 确认与设置：逐项勾选、全选/全不选、差异/距离、执行、恢复、保存配置、完成后退出。

GUI 可以改变布局，但不得复制一份核心算法；所有计划与执行必须调用同一个 `onomedit-core` API。用消息 channel 驱动状态变化，窗口销毁时明确处理后台结果，避免回调访问已销毁 UI。

退出门槛：README 的 GUI 核心流程逐项通过；编辑器等待时界面可交互；取消确认不写日志、不改文件；全部成功和部分失败时的退出行为符合配置。

### 阶段 8：打包、性能与切换

任务：

- GitHub Actions 改为 Cargo release 构建，产出 `onomedit.exe` 和 `onomedit-cli.exe`。
- 对打包后二进制运行 version/help/config/rename/dry-run/history/restore E2E。
- 测量大目录收集、1 万项计划、长路径和大日志读取；优化不能改变稳定顺序。
- 在真实 Python v0.1.6 配置和日志副本上做升级验证。
- 更新安装、开发和发布文档，说明 GUI 外观变化及配置无需迁移。
- 达成所有门禁后，移除 Python 包、uv/Nuitka 构建与仅服务旧实现的依赖。

退出门槛：发布产物在干净 Windows 环境无需 Python 即可运行；三平台 CI 全绿；兼容矩阵签字确认；保留回滚到上一 Python release 的发布说明。

## 4. 行为兼容矩阵

实现过程中维护下表；只有对应自动化和平台验证通过后才标记完成。

| 能力 | 单元 | 共享 golden | 文件系统 E2E | Windows | macOS | Linux |
| --- | --- | --- | --- | --- | --- | --- |
| PathItem / safe name | 必需 | 必需 | - | 必需 | 必需 | 必需 |
| 规则 / 正则 / 占位符 | 必需 | 必需 | 选做 | 必需 | 必需 | 必需 |
| 收集 / glob / 展开 | 必需 | 必需 | 必需 | 必需 | 必需 | 必需 |
| 排除 / 文件属性 | 必需 | 必需 | 必需 | 必需 | 必需 | 必需 |
| 排序 / 去重 | 必需 | 必需 | 必需 | 必需 | 必需 | 必需 |
| 临时文件 / 编辑器 | 必需 | 必需 | 必需 | 必需 | 必需 | 必需 |
| 冲突 / 链 / 环 | 必需 | 必需 | 必需 | 必需 | 必需 | 必需 |
| 日志 / restore | 必需 | 必需 | 必需 | 必需 | 必需 | 必需 |
| CLI / completion | 必需 | 必需 | 必需 | 必需 | 必需 | 必需 |
| GUI / 拖拽 | 状态测试 | - | smoke | 必需 | 建议 | 建议 |

## 5. 每阶段通用检查清单

- 新 Rust 测试先覆盖成功、无变化、错误和平台差异，不只覆盖 happy path。
- 运行 Python 全套测试，确保 oracle 未被迁移辅助代码破坏。
- 运行 Rust format、clippy、unit/integration/doc tests。
- 运行本阶段共享差分，不用“结果看起来合理”替代零差异。
- 检查未在 core 引入 GUI 或不可替换的全局状态。
- 检查错误是否在应用层映射到原退出码和输出流。
- 检查临时目录、配置目录和日志目录完全隔离，不污染开发机真实数据。
- 检查失败路径是否遗留临时名、半写配置或错误的 `last.log`。
- 更新兼容矩阵、风险记录和用户文档。

## 6. 建议的首个实现迭代

第一个可合并迭代只做以下内容：

1. 建立 Cargo workspace 和 CI 基础。
2. 加入共享 fixture runner。
3. 移植 `PathItem`、`sanitize_name`、`unique_path`、Levenshtein。
4. 用当前 Python 测试案例构造 Rust 对应测试和跨语言 golden。

这个切片不触碰真实重命名、用户配置或 GUI，却能尽早验证 workspace 边界、平台路径语义和差分测试方法。验证方法可靠后，再进入规则/占位符和文件系统流水线。

## 7. 最终验收清单

- [ ] 当前 Python 207 个测试继续通过。
- [ ] Rust 对应单元、集成和差分测试全部通过。
- [ ] 现有配置无需转换即可读取、修改和写回。
- [ ] 现有日志可 history、restore last/all/partial。
- [ ] CLI 子命令、参数、输出流和退出码兼容。
- [ ] stdin、剪贴板、glob、目录展开和排除行为兼容。
- [ ] 规则、Python 风格替换串、占位符和安全清理兼容。
- [ ] dry-run 与 GUI 预览绝不修改文件。
- [ ] 重复目标预检、真实冲突、链、环和部分失败兼容。
- [ ] 编辑器快速退出、多标签、保存和超时状态机兼容。
- [ ] GUI 核心流程完整，后台操作不冻结界面。
- [ ] 完整版和 CLI-only 发布物在干净环境通过 E2E。
- [ ] Windows/macOS/Linux 平台矩阵达到约定范围。
- [ ] 达到全部门禁后才删除 Python oracle 和 Nuitka 构建。

