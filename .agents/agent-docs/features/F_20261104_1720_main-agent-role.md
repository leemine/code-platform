---
id: F_20261104_1720_main-agent-role
title: P2 主 Agent 角色指令
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [agent_adapter]
files: [jiuwenswarm/server/runtime/agent_adapter/equipment.py, jiuwenswarm/runtime/session_provisioner.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/server/runtime/session/session_metadata.py, jiuwenswarm/server/runtime/extension_package_manager.py, jiuwenswarm/server/runtime/agent_adapter/main_agent_role.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/execution_input.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py]
designs: []
design_note: 用户批准按管理仓 PROVIDER_PLUGIN_DEPENDENCY_AUDIT_20261031 第 10.2 节 PROMPT-01 实施，复用会话入口并按配置传角色引用。任务看板试点单独延期。
---

# P2 主 Agent 角色指令

初版实现：原 `session.create` 在单 Agent 会话接受 `role_template_ref`。引用来自既有已安装专家目录。宿主只解析可移植 persona，将模板 ID 和 SHA-256 固定在会话元数据，沿 P1 的执行输入传可信角色文本。模板未安装、有额外执行资源、模板指纹变动或客户端试图在一轮内重绑时明确拒绝。角色会话当前不能分叉，避免旧分叉复制历史后丢失角色和原生会话身份。普通纯文本模板的安装仍由原资产服务负责，无运行时声明时无需导入 Core。

Claude Code 使用 Claude Agent SDK 的 preset append，Codex 使用原生 thread start/resume 的 developerInstructions，OpenCode 使用原生 prompt_async.system。原审批、模型选择和聊天历史契约继续适用。角色不注入用户消息，不替换已有角色以继续原会话。P2 范围为主 Agent 角色，不扩展装备、子 Agent 或 Team。

## 验证来源

候选基线为 code-platform `ad51d6eb3db06f4813c38bd41348a76db70ed30c`。Python 3.13.15，两个按原锁非 editable 安装组合。外部组合无 Core，Codex SDK 0.163.0、Claude Agent SDK 0.2.115。Native 组合使用锁定 Core `e089198835426cd7681761b0cc278670cd83031f`，两组协议固定 `2a0457e5e01152e9ca5f8afdffd84716227046ca`。两组产品模块哈希与工作树一致。按产品测试、真实渠道和历史证据分别记结果。

- 按锁安装：`uv sync --locked --offline --no-default-groups --group test --no-editable --reinstall-package workswarm`。外部组合追加 `--extra codex-direct --extra claude-direct`，Native 组合追加 `--extra native --extra codex`，使用不同虚拟环境。安装证据为任务目录 `evidence/locked-external.txt`、`evidence/locked-native.txt` 和 `evidence/installed-sources.txt`。
- 回归命令使用安装环境的 `python -P -m pytest --import-mode=importlib -o pythonpath= --no-cov -q --tb=short`。外部组合覆盖三家 direct、能力、会话 Provider 选择和角色配置入口，290 通过。Native 组合覆盖会话创建、分叉、切换、provision 契约、AgentServer 创建边界和专家包管理，217 通过。首轮把含 Native 用例投到无 Core 环境的 7 项配置不匹配单列，在有 Core 对应组合中通过。无 Core 原安装入口的真实导入缺口已修，普通专家创建→安装→绑定回归通过。没有扩大跳过条件。
- 在 Linux 本机用锁定外部环境运行 `timeout -k 100 -s INT 255 .venv/bin/python -P ../verify_role_channel.py codex opencode claude`。通过原 Web WebSocket、Gateway、AgentServer Front 和真实 Worker 创建单 Agent 会话，使用原专家创建和安装入口。同一会话连续发两条不含目标标记的用户消息，以实时回复和持久化助手历史分别核对。Codex 和 OpenCode 两轮均通过，无用户消息注入。早期脚本误把无正文的 final 当作目标输出，最终独立核对有内容的 final 与历史。保留 `evidence/channel-report.json`，退出两服务、关闭 Worker IPC 并删除隔离模型配置。
- Claude Code 原 `glm-5.2-anthropic` 第一轮 85 秒内无终态，未运行第二轮。同配置一次独立 Anthropic Messages 请求返回 HTTP 429、`rate_limit_error`、服务码 `1113`。这是端点证据，未取得 SDK 同轮 HTTP 轨迹。Claude 的 SDK 参数与同原生会话续聊回归通过，真实渠道待原服务可用后复验。未更换模型或关闭保护。

状态为候选代码完成、Claude 真实渠道待验。未提交、合并或发布。真实复验范围为 Linux Web/Worker，Windows/macOS 桌面未验。

## 宿主能力声明收敛

`session.create` 从已注册入口读取工厂的 `AdapterCapabilities.main_instructions`。宿主使用同一能力声明类型，三家随项目提供的工厂和执行适配器共享各自的声明。创建会话沿原 provision 路径，读取声明时不创建执行器。执行阶段校验实际适配器的能力和执行输入接口，防止错误声明导致绑定角色被静默丢弃。当时角色指纹、旧会话和续聊语义沿用初版约定，现已由下节更新。可通过注册具备该能力的 Provider 扩展，宿主无需维护名字列表。

纯角色模板安装免 Core 修复及回归单独提交为 `1012ea3`。在只含该提交的 Git 快照中，用无 Core 环境运行实际安装入口，测试通过。保留同一测试并替回父提交的资产模块时复现缺少 Core 的异常。

收敛候选使用与上节相同的离线按锁安装和 pytest 参数，三家直连、Provider 选择、能力和模板安装等外部回归 293 通过，Native 的创建、切换、分叉和专家模板回归 219 通过。两个安装环境各有 12 个产品模块与工作区 SHA-256 一致。新增覆盖了额外注册的 Provider 声明能力前后的会话创建行为，以及执行器缺失输入接口时的拒绝。证据位于任务目录 `evidence/host-convergence/`。

收敛候选复用前述真实 Web/Gateway/Worker 脚本。Codex、OpenCode 各两轮原会话实时回复及持久化历史通过。OpenCode 首次读取第二轮历史时写盘尚未完成，随后从同一会话的落盘记录独立核对两轮，原即时报告保留。Claude Code 成功建立角色绑定，首轮 85 秒无终态。独立模型端点探测再次返回 429 / 1113，SDK 同轮的 HTTP 状态仍未取得。回归脚本已关闭 Worker IPC 并移除隔离配置。P2 收敛保留为本地工作区候选。


## 模板更新与原会话续聊（2026-11-04）

对齐 Native 的模板引用语义：宿主只以原模板 ID 与执行 Provider 核对创建重试。每轮沿 P1 输入读取当前已安装角色，不将创建时的 SHA-256 用作续聊门禁。创建记录和 Provider 绑定不重写，不保存新版本角色快照。模板已卸载或无效时拒绝执行；不同模板 ID 不能用原令牌改绑。仍使用既有会话、专家资产和 Runtime，P1 装备流程不变。

Codex 初轮通过原生 thread/start developerInstructions。实测向 thread/resume 传新正文仍返回旧角色，原生线程只保留初次指令。适配器改用官方 thread/inject_items 附加明确替换此前 Swarm 角色的开发者指令。在同一连接正文不变时去重；恢复连接时补一次。不改变用户输入，不修改外部 CLI/SDK 或权限逻辑。原生接口未确认时终止该轮启动，避免沿用旧角色。OpenCode 继续每轮用 prompt_async.system，Claude 继续使用原 SDK preset append。

验证使用两种原锁非 editable 安装及原 Web→Gateway→AgentServer Front/Worker 路径。证据位于任务目录 `evidence/template-reload/`；`verify_role_reload.py` 使用原模板保存/卸载 RPC，核对本轮原生 ID、实时回复和持久化历史，停止并重新启动 Worker，最后清理隔离配置和进程。Codex 验证新版在原会话生效、重启后仍生效且保留原上下文，创建重试返回原会话，改绑和卸载拒绝。OpenCode 三次真实运行中两次通过，另一次热续聊的原生模型回复沿用旧角色标记。原生数据库确认该次系统参数按 V1→V2→V2 正确写入，旧标记来自原生回复而非 Swarm 历史映射。失败和复跑报告一并保留，不承诺模型每轮都遵循角色指令。Claude 首轮 85 秒无终态；独立同配置探测返回 HTTP 429 / rate_limit_error / 1113，未观察到 SDK 同轮 HTTP 状态，真实续聊和重启待验。未提交本轮改动，未发布。

按锁非 editable 回归：外部 293 通过、Native 219 通过，见 `tests-external-final.txt`、`tests-native-final.txt` 与 `installed-sources.txt`。一次将 Native 专属节点误放入无 Core 环境的结果单独保留；两种组合按原范围验证，无新增跳过。


## 原会话切换专家（2026-11-04）

继续沿用已批准的 P2 边界。Web 选择器用原 `chat.send.agent_template_name` 发起切换，宿主通过已有 `session_equipment` 恢复并提交生效 ID。创建参数只提供初始选择及重试校验。相同 ID 每轮读取现有模板正文。Provider 继续拥有原生装载和会话，宿主在本轮得到原生接受后核对执行所有权和装备状态，再写入专家 ID。无效模板、原生拒绝和过期回执均保留旧选择。OpenCode 已有完整装备路径保留。

真实 Claude CLI 2.1.274 配合锁定 SDK 0.2.115 的本地 Messages 抓取复现了旧角色。CLI 默认在会话第一次请求记录系统提示词，resume 沿用该快照。可切换专家时由 Claude Adapter 通过 SDK 的既有 `extra_args` 传入官方 `--system-prompt-snapshot off`，保留原 preset、会话与对话记录。此选项要求原生 CLI 支持，可能影响提示词缓存。依据见 [Claude Code 系统提示词文档](https://code.claude.com/docs/en/agent-sdk/modifying-system-prompts#change-the-prompt-of-an-existing-session)。

真实 Web→Gateway→AgentServer→Worker 验收脚本为 `verify_expert_switch.py`。Codex 与 OpenCode 使用原模型服务通过同 ID 更新、原会话跨 ID 切换、失败保留 A、创建重试保留 B、落盘及 Worker 重启后继续用 B。Codex 还通过普通创建后从原 chat.send 首次选择专家的同场景。Claude 官方 SDK 与 CLI 走本地受控 Anthropic Messages 端点，通过同一链路，直接核对进入模型请求的系统指令与原始上下文。原 Claude 模型服务独立探测仍返回 HTTP 429 / 1113，真实模型回复待验。验收报告、原生快照故障对照和测试命令位于 `evidence/expert-switch/`。

最终按锁回归无 Core 302 项、Native 222 项通过，包含真实 Facade 的原生拒绝以及延迟回执到达已取消生产者和过期会话 generation 的覆盖。两组实际安装文件与候选源码哈希核对通过。运行日志分别为 `tests-external-final.txt`、`tests-native-final.txt`，来源见 `installed-sources.txt`。未执行提交、PR、stable 或发布。
