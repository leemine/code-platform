---
id: F_20261031_1714_claude-main-agent-and-model-settings
title: Claude 主 Agent 与无 Core 模型配置发布收尾
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, gateway/common, jiuwenswarm/channels/web/frontend, jiuwenswarm/server]
files: [jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/external_adapter_factories.py, gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, pyproject.toml, uv.lock, .github/workflows/stable.yml]
designs: []
design_note: 用户已确认原AgentAdapter直接接官方SDK的实施方向，并授权任务1～2发布收尾；本次未另建独立设计。
---

# Claude 主 Agent 与配置、会话恢复实施归档

## 依据与来源

基于main 5d7fba08d85679421ccb783ccc44f5064b31e48e，在独立codex/claude-main-agent-release恢复既有P1工作。原31份dirty/untracked源文件、staged/unstaged补丁及摘要完整保留并复核，原UI和环境不切换。当前契约见S_02_external-adapter-boundary。

沿B_20261031_1122_model-config-without-core、B_20261031_1142_claude-tool-result-metadata与B_20261031_1418_session-recovery-lifecycle实施；这些旧记录保留原候选证据，本文件承接最新主线上的集成及兼容验证。已合入Codex取消修复逐字节保留，不从旧P1覆盖。

## 实际决策与接口

- 原entry point新增claude-direct。轻量工厂和启用/路径快照不导入SDK或Runtime，模型仍取Swarm原ModelSelectionResolver。官方ClaudeAgentSDK管理CLI、消息和resume；本工程仅转换原AgentAdapter接口、事件与原交互通道。
- 原Runtime/Facade持有会话绑定、producer、排队、审批投递和历史；Adapter无第二调度器、业务状态机或审批中心。SDK AnyIO上下文由同一producer打开/关闭，初始化后的native_id保留，下一Turn使用官方resume。取消不复制历史文本；冷重启恢复仍明确不支持。
- 支持单Agent/Code文本、Default与Full Access。原UI选择新会话执行器，旧会话不随默认配置改绑。Claude复用原模型服务，仅接Anthropic Messages兼容接口；配置错误明确拒绝，不把OpenAI URL自动转换或回退其他引擎。
- 厂商预设是Swarm静态数据，Core仅提供Native推理丰富信息。无Core返回reasoning_available=false/null；原模型弹窗使用既有字段与组件完成基础新增/编辑/测试/保存。已有显式推理值保留，不能校验时提示，不伪造固定能力目录。
- 原config.validate_model probe扩展Anthropic，仍经原models.upsert/get及reload，不增加第二模型存储。Native存在时继续原Core校验/模型客户端；安装内部异常不被当作缺席吞掉。
- 无Core历史跳过Native专属workflow查询，原响应协议和基本历史保留。Web元数据快照不得覆盖请求期间更晚的同会话实时状态；恢复订阅返回原重附着结果，历史加载期间仍维护活动状态。
- Bash命令退出码仅取原生字典的整数；无字段/文本/列表保留未知。流关闭不当完成，工具保护错误沿原工具事件展示。

## 未采用的方案

没有重写Provider Loop、创建公共执行框架、全局终端管理器、第二模型目录或新设置页；没有通过Core包装外部SDK。原生差异只在Adapter内处理。没有修改外部SDK/CLI、关闭TLS/权限或添加精确版本白名单；Core和三份外部SDK/CLI锁条目与旧P1一致。

## 验证

- 新主线固定工作区真实UI完成Codex/OpenCode的Work与Code、审批刷新/允许/拒绝、工具运行取消和同会话上下文；独立文件确认无迟到写入。
- 新候选无Core、按锁非editable安装205项相关Python回归通过；固定Core e089198下100项模型/工作流兼容回归通过。前端原模型/请求恢复/输入/执行器选择20+17+64+4项通过，原Vite构建通过。
- 基线vendors导入实际失败missing_module=openjiuwen；候选返回11项厂商预设、reasoning_available=false/null。真实原模型弹窗完成OpenAI/Anthropic修改、Anthropic新增和刷新重读，新模型随后用于Claude主Agent。
- 真实默认DeepAgent经原Runtime返回NATIVE_RELEASE_OK，Core仍为e089198，关闭并删除临时配置。
- 真实Claude已完成正常业务文本、刷新审批/允许写入、待审批取消后原会话回忆京都四晚、运行中Bash取消与原会话回忆；命令开始122秒后仍无迟到写入。Code读取真实夹具及Bash exit7映射错误已通过；SDK没有结构化退出码时保留None，UI正文中的7不被解析补值。新候选Codex也已真实读取同一夹具；OpenCode验证保留首次审批超时并在原会话重新授权读取，原会话最终返回夹具内容及OPENCODE_RELEASE_COMPAT，完整记录见管理验证资料。

验收中的无效夹具也保留：复制UI的密钥占位符导致新增连接失败，改用同一隔离服务的真实配置后正常测试保存，未选择忽略测试；token记忆请求被模型保护拒绝，另开正常行程业务会话验收，未关闭保护。Native脚本最初误将native当SDK/Adapter ID，按真实默认harness纠正并保留失败日志。

## 遗留与发布边界

Skill/MCP/模板/附件、Team、完整用量、冷重启恢复及Windows/macOS桌面包另行交付。真实UI基于同字节源码与按锁环境，不替代干净CI；stable沿既有workflow增加Claude和模型配置回归，未绕过或修改检查结论。PR#1/#2的用户豁免不自动扩展至本PR。任务状态与全部证据在管理仓DEVELOPMENT_TASK_TRACKER及MAIN_UI_CLAUDE_RELEASE_20261031验证记录维护。
