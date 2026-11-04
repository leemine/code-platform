---
id: F_20261104_1030_provider-input-ownership
title: P1 执行输入与装备所有权收敛
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [agent_adapter]
files: [jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/execution_input.py, jiuwenswarm/server/runtime/agent_adapter/equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/common/codex_adapter_config.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py]
designs: []
design_note: 用户授权先执行 P1；范围依据管理仓 PROVIDER_PLUGIN_DEPENDENCY_AUDIT_20261031 的 P1/P2 划分。本记录细化接入职责，不将设计当成已验证实现。
---

# P1 执行输入与装备所有权收敛

## 目标与边界

原 Facade 构建输入时解析有效模型、目录与宿主历史恢复事实，作为仅进程内的可信输入交给可选接缝。Provider 不从准备好的执行中重新读取全局模型或解释宿主历史；保留官方协议校验、模型指纹、原生会话绑定和资源所有权。旧直接调用及公开模型转换函数兼容保留，委托相同的宿主解析函数，不再复制解析规则。Native 必需接口和默认行为不变。

宿主原 reconcile_session_mcp 边界解析安装/启用状态及凭据，Provider 只转换并挂载可移植装备。装备快照由宿主在原 Runtime generation 仍有效、当前任务未取消且原生核验成功后提交；失败/取消/过期不提交。复用既有 Runtime 和 Provider 配置锁，不新增调度、Turn 状态机、队列或旁路。借用服务仍不被全局重配/关闭。

能力准入仅声明本次实际支持的装备入口；不把模板/Skill/MCP 支持推断为所有 Provider 通用。Claude/Codex 继续拒绝尚未实现的装备，OpenCode task=deny 保留。

P2 主 Agent 角色提示词、子 Agent 配置、分包/市场、异常接管及 Core/SDK 升级不在范围。继承的三家有界输出修复单独保留，不能记作 P1 新增。

## 验收

覆盖原 Facade request 的准备与消费、模型/目录/恢复事实一致性、旧直接 API、Native 与无 Core 组合；装备成功提交及失败、取消、原 Runtime generation 失效不提交；原审批、取消后续聊、关闭与恢复回归。按现有锁正常安装并核验实际来源；真实 Provider 与渠道独立记录，mock 通过不代替端到端成功。缺少必需真实验证时标为待验证。

## 实施状态

代码已完成，真实 Claude 仍待验证；未提交/发布。最终无 Core 按锁非 editable 322 通过，Native 同锁组合244通过，Web工具事件归一化10通过；已核验所有改动 Python 模块与安装来源哈希一致、无 Core 环境未安装 openjiuwen、Native 固定 Core e089198835426cd7681761b0cc278670cd83031f，声明/锁/SDK未升级。首次19项失败属于旧模型替身/旧解析监听入口，迁移到真实宿主模型解析及原生转换后通过；新 generation 测试初版误用了可变快照，改为真实不可变 RuntimeSessionSnapshot，未放宽产品断言或跳过用例。

接入能力声明只描述实际集成：原生提问与角色支持不从 SDK 特性猜测；实际装备准入及缺失的上下文统计/手动压缩在原 Facade 入口检查，未给 UI 新增页面或控件。角色文本扩展仍是 P2。产品变更与继承的三家输出保护分开统计，详见管理仓验证记录 PROVIDER_INPUT_OWNERSHIP_P1_20261104。

中间候选的真实完整 Web→Gateway→Front/Worker→官方 Provider：Codex/OpenCode 两轮和原目录/退出0/上下文沿用通过；OpenCode 原模板 persona 生效，省略选择沿用，宿主快照已保存。最终能力准入候选从新 Worker 重验 Codex/OpenCode 两轮通过，原历史分页独立核对工具目录/token/退出0/绑定通过；同任务 evidence/channel-report.json、channel-history-verification.json 留档。原退出 API 已关闭验收 Worker/IPC；Frontend 工具归一化10通过。首次最终复验因常驻旧代码版本被原保护拒绝，退出旧验收 Worker 后重新验证，未绕过版本检查。Claude 原 Swarm glm-5.2-anthropic 渠道150秒无终态；同配置独立最小端点请求返回429/rate_limit_error/1113。未获取该轮 SDK 内部 HTTP 轨迹，不把独立429当作 SDK 同轮错误证据；没有转 CC-Switch、改模型或绕过保护。当前验收状态为待服务可用后重验 Claude。

复用现有正常原生恢复（主线 #12），不新增异常接管；无 P2/子 Agent/独立分包、Core/SDK 升级。尚未提交 PR/stable、构建或更换桌面安装包；Windows/macOS/浏览器视觉与真实异常接管不在本轮已验收范围。

P1 独立增量：产品12文件 +475/-172，测试5文件 +220/-6（不含继承输出保护）；原候选 diff 未变化。管理仓验证记录是命令、版本、原失败与最终证据的唯一详细来源。
