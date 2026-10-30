# Repository Guidelines

## 项目结构

JiuwenSwarm 是多智能体协作系统，Python 包发布名为 `workswarm`。

- `jiuwenswarm/agents/`：智能体与 Harness；`server/`、`gateway/`：服务与接入层；`channels/`：各端入口。
- `jiuwenswarm/channels/web/frontend/`：React、TypeScript、Vite 前端；静态资源位于 `src/assets/` 和 `public/`。
- `jiuwenbox/`：沙箱；`sdks/`：Python/TypeScript SDK；`packages/jiuwenswarm-tui/`：TUI 包。
- `tests/`：单元、集成和系统测试；`scripts/`：开发与构建脚本；`docs/`、`deploy/`：文档与部署配置；`jiuwenswarm/resources/`：运行配置模板。

## 安装、运行与构建

使用 Python 3.11–3.14 和 `uv`，从仓库根目录执行：

```bash
uv sync                          # 安装依赖，默认包含测试与开发工具
source .venv/bin/activate         # Windows 使用 .venv\Scripts\activate
export PYTHONPATH=.:$PYTHONPATH    # POSIX 环境设置源码路径
make init                        # 初始化 ~/.jiuwenswarm
make start-debug-rebuild          # 构建前端并启动调试服务
make start-debug                  # 复用已有前端构建
make stop                        # 停止调试服务
make build                       # 构建 wheel/sdist
```

前端独立开发时进入前端目录，执行 `npm ci`、`npm run dev`；`npm run build` 执行 TypeScript 编译与 Vite 构建。

## 代码风格与命名

Python 使用四空格缩进、`snake_case` 函数与模块、`PascalCase` 类；参数声明类型，优先 `X | None` 和 `list[X]`。注释使用英文，docstring 遵循 Google 风格；多行参数保留尾逗号，避免海象运算符与动态扩展 `**kwargs`。

前端遵循 `.prettierrc.cjs`：两空格、单引号、分号、120 列；组件使用 `PascalCase`。仓库配置了 Ruff、Pylint、mypy、ESLint 和 Prettier，但本地协作约束禁止运行格式化与静态检查工具。保持修改处的现有风格。

## 测试要求

使用 pytest、pytest-asyncio、pytest-mock 和 pytest-cov。新增测试采用纯函数，文件命名 `test_*.py` 或 `*_test.py`，函数命名 `test_*`；覆盖正常、失败与回归路径。

- `make test-unit`：运行 `tests/unit_tests/`；`make test-integration`：运行 `tests/integration/`。
- `make test`：运行完整测试；`uv run pytest tests/路径/test_example.py`：定向验证。
- pytest 默认生成终端、`htmlcov/`、`coverage.xml` 报告；`TESTING.md` 总体目标为 80%，当前配置未设置强制阈值。
- 前端使用 Node 测试运行器，按 `package.json` 选择 `npm run test:<功能>`，例如 `npm run test:a4p-settings`。

## 提交与 Pull Request

近期历史以 `feat(scope): ...`、`fix(scope): ...`、`refactor(scope): ...` 为主。新增提交使用简洁英文 Conventional Commits，例如 `fix(gateway): preserve session order`。

PR 面向 `develop`，遵循 `.gitcode/` 模板，说明问题、变更与测试结果，关联 Issue（如 `Closes #123`）；UI 修改附截图或录屏，行为变化同步中英文文档。仅提交本次任务相关文件。

检视人、合并人分派及飞书通知由根目录的 `CODEREVIEWER`、`COMMITTER`、`USER.json` 配置，格式与约束见 `.claude/rules/ownership-files.md`。

## 运行时数据位置

排查某个 session 的行为（轨迹、工具调用、团队状态）时直接到这些位置取数，不要在源码或家目录里反复搜索。

- **数据根 `<root>`**：环境变量 `JIUWENSWARM_DATA_DIR`；未设置时为 `JIUWENSWARM_HOME`（默认用户家目录）下的 `.jiuwenswarm`。取值函数集中在 `jiuwenswarm/common/utils.py`（`get_user_workspace_dir()` / `get_agent_root_dir()` / `get_agent_sessions_dir()` / `get_runtime_state_path()` 等），新增路径一律走这些函数。
- **会话轨迹** `<root>/agent/sessions/<session_id>/`：
  - `metadata.json`：`mode`、`team_name`、`session_team_dispatch_mode`（autonomous / scheduled）、`model_selection`、`work_mode` 等会话级事实。
  - `history.jsonl`：每行一条事件。`chat.tool_call` 带 `tool_call.arguments` 与 `reasoning_content`；`chat.tool_result` 的 `rendered_result` 就是模型实际看到的工具返回文本；另有 `team.task`（看板事件）、`context.usage`、`chat.final`。
  - 归档会话在 `<root>/agent/sessions_archived/`。
- **会话运行态** `<root>/config/runtime_state/<session_id>.yaml`（当前模型、可用模型、语言、git 上下文），同目录 `<session_id>.<digest>.skill-retrieval.json` 是 skill 检索预算快照。
- **团队数据** `<root>/.agent_teams/`：
  - `team.db`：所有团队的成员名册、任务、消息（SQLite，由 agent-core `openjiuwen.agent_teams` 维护）。
  - `<team_name>/`（web 会话默认 `jiuwen_team_<session_id>`）：`sessions/<session_id>/tasks/task-*.md` 任务正文；`team-workspace/prompts/` 是 `build_team` 时物化的全部系统提示词与工具描述（`system/`、`tool/<domain>/`、`tool/fragments/`、`tool/tool.param.<lang>.md`），**不按 dispatch_mode 过滤**，成员可用文件工具读到；`team-workspace/artifacts/` 交付物；`workspaces/<member>_workspace/` 成员私有工作区。
- **日志** `<root>/agent/.logs/`：`agent_server.log`（agents / server）、`gateway.log`、`full.log`（汇总）、`context_usage.jsonl`，按时间轮转为 `*_YYYYMMDD_HHMMSS.log`；openjiuwen core 的日志在 `<root>/logs/jiuwen.log` 与 `jiuwen_details.log`。gateway 日志目录可由 `AGENTOS_GATEWAY_LOG_DIR` 单独指定。
- **观测轨迹库**（`trajectory_ui.enabled` 开启时）：`<root>/.trace/` 下每 session 一个 SQLite，路径解析见 `jiuwenswarm/observability/config.py`。

快速定位一个 session 的全部落点：

```bash
grep -rl "<session_id>" "<root>/agent/sessions" "<root>/config/runtime_state" "<root>/agent/.logs"
```

## 配置与智能体协作

始终使用中文交流。修改子目录前阅读其中的 `AGENTS.md`；同时遵守 `AGENTS.local.md` 的本地约束。不要提交 API 密钥、真实 `.env`、运行日志或覆盖率产物；配置模板放入 `resources/`。涉及文件与进程操作时兼顾 Windows、macOS 和 Linux。


## AI coding 流程与文档资产

项目级技能位于 `.agents/skills/`，按当前任务阶段读取：

- `jw-coding-flow`：需求、设计、开发、检视与交付的流程入口。
- `jw-design`：需求分析、架构/特性方案、日期评审及设计生命周期。
- `jw-dev`：实现、行为测试、契约同步及 feature / bugfix 开发记忆。
- `jw-review`：统一代码检视入口，按 JiuwenSwarm 技术方向、模块 AGENTS/spec 与协议依据，重点审视工作区、提交或分支的行为差异及跨端影响，执行证据核对与复查交接，不限定 PR 场景。
- `jw-testing`：独立撰写转测资料，本地输出 `designs/testing/`，不进入设计索引。
- `project-maintainer`：按需维护项目知识库。

实际资产位于 `.agents/agent-docs/` 的 `designs/`、`specs/`、`features/`、`bugfix/`。
新设计使用 `D-YYYYMMDD-HHMM-<slug>`，feature / bugfix 使用 `F_` / `B_` 加 `YYYYMMDD_HHMM` 和主题。
时间采用 Asia/Singapore、精确到分钟，历史编号不调整。模块使用真实仓库相对路径，跨仓模块保留完整路径。
流程、模板和索引工具见各技能；现有与迁入设计从 `.agents/agent-docs/designs/README.md` 进入。
core 的底层设计/spec 继续在 core 维护，不因依赖关系复制到本仓。提交、推送和 PR 遵循既有授权规则。


## D / F / B / S 文档约定

文档根目录为 `.agents/agent-docs/`；元数据、作者与索引规则见 `.agents/skills/jw-design/references/document-metadata.md`。

| 类型 | 用途 | 位置 |
|---|---|---|
| D | 开发前方案、取舍与真实评审/确认 | `designs/proposals/` → `active/` → `archive/`，保留 D/SDD 标识 |
| F | 实际实施、开发决策、设计偏差、验证与遗留 | 新文件直接放 `features/F_YYYYMMDD_HHMM_<slug>.md`，不再分模块子目录 |
| B | 故障现象、根因、修复决策与回归证据 | `bugfix/<module>/B_YYYYMMDD_HHMM_<slug>.md` |
| S | 当前有效契约、接口、状态与不变量 | `specs/<module>/S_NN_<slug>.md`，沿用已有编号 |

受管文档（含说明与生成索引）必须有 YAML frontmatter。author 使用创建时仓库有效的 Git user.name，author_email 使用对应 user.email；后续普通修改不覆盖原作者。
不再使用 owner 字段；历史 owner 就是 author，迁移时优先将原值保留为 author，不丢失或用 Git 推断值覆盖。只有原 owner/author 均不存在且无法可靠追溯时才以 null 和 author_note 明示；模板占位在创建时由工具填入。
F/B 必须显式声明 designs；有 D 填完整标识列表，无独立 D 填 [] 并写 design_note，历史待核实用 null 并说明。
modules/files 记录实际模块和代码范围，不能用作者表示长期维护权或把历史设计当成当前实现事实。
写作、修改、迁移文档后在本任务中自动执行：

```bash
python .agents/skills/jw-design/scripts/sync_documents.py --document <本次新建文档路径>
```

执行 Python 前按本仓要求初始化环境；仅刷新索引时省略 --document。工具维护根总索引及 D/F/B/S 分类索引，F 平铺后通过作者、模块、文件和关联 D 定位，不手工改索引。
这项同步是写作收尾，不安装 watcher/Git hook，不授权提交；检视阶段保持候选只读。转测资料继续由 jw-testing 独立管理，不进入正式索引。


# swarm 统一执行规约片段

部署位置：补入 swarm 根 AGENTS.md；不得覆盖已有模块规约。该片段不依赖管理仓路径，部署随 R1 首个 swarm 提交执行。

- 普通 Single/Team 使用 core/harness 统一入口；Projects 仅提供配置候选、权限上下文和固定快照。
- 复用现有 Runtime 的会话执行、generation、控制投递与生产者生命周期，避免第二调度器；保留原 Team 协作权威。
- 绑定包含 Provider、实际配置版本、主体与 Workspace；旧会话恢复不得被新默认配置覆盖。
- 事件单路消费后分派原 stream/history/UI。通用模式/Step/子 Agent 与专有扩展分开；保留原工具结果、父子关联、revision、轨迹及用量。
- 输出流结束不代表任务完成；等待提问时保留控制关联；重复回答、断线、取消、迟到事件和历史重放分别验证。
- 沿用原审批与用户提问界面，不额外打印能力提示，不重复授权，不静默回退 Native。
- 前端遵循现有 web 与 frontend AGENTS.md，只修改任务范围；新模块先登记 testid 前缀。
- 测试记录实际导入的 core 路径/版本，不能仅看锁文件。验证各受影响渠道，环境缺失如实标记；复用 testctl 和本仓变更/验证记录结构。

## Python CI 执行策略（2026-09-29）

- 每次提交/PR 和合入后的自动检查使用 `pr-stable`，本地按影响面运行确定性测试及所需真实验收；不逐提交、逐候选或逐合入 SHA 触发全量 Python CI。
- `full-python` 只由每日 `schedule` 在默认分支执行。`workflow_dispatch` 只跑 stable；不要为每个提交额外手动补跑全量。
- 全量是每日回归巡检，不是每个 PR 的必经门禁。保留完整归档、准确 SHA、失败/跳过/未运行与分片闭合审计；已知相关失败须调查修复，不能因降低频率忽略失败。
- 合入后核验 stable、依赖来源和受影响范围；不得把旧 SHA 的每日全量结果记作新 SHA 已通过全量。

## 外部 Provider 源码边界（2026-10-12）

- 不修改 OpenCode、Codex、Claude Code、iCode 等外部 Provider 原生源码、CLI／SDK 源码、打包产物、二进制或安装文件；不通过维护 fork、热补丁或替换已安装依赖绕过此约束。
- 允许只读排查、公开 API／事件和正常配置。修复限于本工程 Core／Swarm 接入、映射、统计和展示；Core 依赖变更仍按既有先合入后固定 SHA／生成锁的规则，不擅自升级固定外部版本。
- 原生接口未暴露或已丢失的信息，标为未返回、来源不完整或待验证，记录限制及本工程内替代方案，不猜测补值，不把修改外部源码作为默认方案。

## 本地 checkout 与任务工作区管理（2026-10-20）

- 区分仓库目录、当前分支、本地 `develop` 与 `origin/develop`。`origin/develop` 仅是最近一次 fetch 的远端引用；fetch 不更新当前分支或工作区。声称“最新”须记录获取时间、远端 SHA 和实际 HEAD。
- 指定的主线目录默认检出本地 `develop`，保持已跟踪文件与远端主线一致、无任务遗留修改；文档和规约改动也在任务分支处理。保留环境、配置及数据，Git clean 不等于运行环境已验证。
- 开工记录绝对路径、分支、HEAD、dirty、upstream 和 worktree 占用，先 `git fetch origin`。新任务从刷新后的 `origin/develop` 在独立 worktree 创建 `codex/<task>` 分支；已有任务按影响决定是否合入新主线，不将自动 rebase／逐提交同步作为前置。
- 同一目录同一时间由一个任务负责写入。测试和启动记录实际 cwd、解释器、源码与依赖导入路径，不从分支名或锁文件推断运行来源；不在仍被运行实例读取的目录直接换版本。
- 主线目录只在已妥善处理 dirty 后用 `git switch develop`、`git merge --ff-only origin/develop` 更新，并核对 HEAD、upstream、ahead/behind 与 clean 状态。遇到分叉、未合入工作或占用应先调查；不得用 `reset --hard`、`clean -fd`、强制切换或自动 stash/pop 掩盖冲突。
- 未提交工作先保存原始文件、包含暂存区差异的补丁／stash 和 untracked 清单，记录原 SHA 与文件摘要；在原基线的独立工作区恢复并校验后才能释放原目录。比较主线的补丁与语义，区分已合入、后续修复、仍需迁移；不能只因文件同名就删除旧候选。归档不得收录凭据、私有配置或缓存到 Git。
- 本地 `develop` 若被另一 worktree 占用，先核对该目录用途、dirty 与运行者；需释放时将其切到保留分支或固定 SHA，保留原 HEAD、全部文件及环境，不强占或删除验证目录。
- 合入后检查实际远端提交和相关验证，推进主线目录；确认未提交内容、独有提交和证据均已保存后再归档任务 worktree。固定 SHA 的验收目录不自动追主线；不得把它的成功结论转记给新 SHA。任务分支未合入时须明确记录位置和剩余交付。
- 跨 Core／Swarm 配对仍以 Swarm 声明和锁定 Core SHA 为准，不因两个 checkout 都是最新就判为兼容。联合开发的 editable 来源单独标记；正式交付依旧使用干净按锁安装、实际来源核验和受影响验证。仅文档更新不要求无关依赖追新。
- 复用 Git 原生命令、现有任务台账、stable 与每日 full-python；不增加独立配对系统、自定义同步工具或逐提交全量门禁。管理仓 main 的同步和资料提交单独处理，不与子仓清理混做，不批量提交其他任务的 dirty。


## 当前隔离验证范围

用户已授权基于官方上游验证 AgentAdapter 外部 Provider 接入，允许本任务候选通过现有 AgentAdapter 对接官方接口；不要求该验证经过 fork Core harness。保留原 Runtime 生命周期与原生功能，生产未支持的能力明确拒绝，不复制协议、授权或执行队列。本轮仅验证，未授权提交或发布。
