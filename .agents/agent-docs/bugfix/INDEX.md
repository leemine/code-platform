---
title: 故障修复 B索引
author: leemine
author_email: leewanlong@gmail.com
generated: true
---

# 故障修复 B索引

由 sync_documents.py 从文档 frontmatter 自动生成；请修改源文档后重新生成，不手工维护。

共 15 篇文档，按模块分组；跨模块文档在各相关分组展示，总数按文档去重。

## 模块导航

| 模块 | 文档数 |
|---|---|
| [.github/workflows](#module-1) | 1 |
| [agent_adapter](#module-2) | 2 |
| [channels/web/frontend](#module-3) | 1 |
| [config_panel](#module-4) | 1 |
| [desktop](#module-5) | 1 |
| [docs](#module-6) | 1 |
| [gateway/channel_manager/im_platforms/xiaoyi](#module-7) | 1 |
| [gateway/common](#module-8) | 1 |
| [gateway/message_handler](#module-9) | 1 |
| [jiuwenswarm/channels/web](#module-10) | 1 |
| [jiuwenswarm/channels/web/frontend](#module-11) | 1 |
| [jiuwenswarm/channels/web/frontend/src/features/settings/modules/models](#module-12) | 1 |
| [jiuwenswarm/common](#module-13) | 1 |
| [jiuwenswarm/common/config_panel](#module-14) | 1 |
| [jiuwenswarm/server](#module-15) | 1 |
| [jiuwenswarm/server/runtime/agent_adapter](#module-16) | 5 |
| [jiuwenswarm/server/runtime/agent_adapter/providers](#module-17) | 1 |
| [scripts](#module-18) | 1 |
| [server/worker](#module-19) | 1 |
| [settings](#module-20) | 1 |
| [未分类](#module-21) | 3 |

<a id="module-1"></a>

## .github/workflows

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261101_2056_missing-lfs-demo-videos](docs/B_20261101_2056_missing-lfs-demo-videos.md) | B | Remove unavailable LFS demo video references | leemine | docs, .github/workflows | .github/workflows/stable.yml, .gitattributes, README.md, docs/assets/videos, docs/en/ChinaChannels.md, docs/en/TaskPlanning.md, docs/zh/国内频道.md, docs/zh/任务规划.md | 无独立 D：User-approved documentation asset cleanup; no independent architecture design. |

<a id="module-2"></a>

## agent_adapter

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_1455_opencode-session-workspace-binding](agent_adapter/B_20261030_1455_opencode-session-workspace-binding.md) | B | OpenCode 会话项目目录绑定修复 | leemine | agent_adapter | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py | 无独立 D：用户确认对当前 S_02 会话目录契约的小范围修复，无独立设计。 |
| [B_20261030_1607_opencode-permission-profiles](agent_adapter/B_20261030_1607_opencode-permission-profiles.md) | B | OpenCode Full Access 与原生权限、生效状态接入 | leemine | agent_adapter, server/worker, channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/worker/dispatcher.py, jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/config/permissionProfiles.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx | 无独立 D：用户确认复用既有 reload/Runtime/权限下拉的最小接入方案，无独立子仓设计。 |

<a id="module-3"></a>

## channels/web/frontend

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_1607_opencode-permission-profiles](agent_adapter/B_20261030_1607_opencode-permission-profiles.md) | B | OpenCode Full Access 与原生权限、生效状态接入 | leemine | agent_adapter, server/worker, channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/worker/dispatcher.py, jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/config/permissionProfiles.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx | 无独立 D：用户确认复用既有 reload/Runtime/权限下拉的最小接入方案，无独立子仓设计。 |

<a id="module-4"></a>

## config_panel

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261031_1930_optional-provider-menu](desktop/B_20261031_1930_optional-provider-menu.md) | B | 桌面安装 SDK 后执行引擎不可选 | leemine | desktop, config_panel, settings | jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/features/settings/modules/agent/useExternalCliInstallCompletion.ts, jiuwenswarm/channels/web/frontend/src/features/settings/modules/agent/ExternalCliAgentsSettings.tsx, jiuwenswarm/channels/web/frontend/src/components/ExternalCliAgentsSection.tsx | 无独立 D：沿原 Third-party Agents 配置/安装和 Front 执行器目录职责修复；不增加执行流程。 |

<a id="module-5"></a>

## desktop

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261031_1930_optional-provider-menu](desktop/B_20261031_1930_optional-provider-menu.md) | B | 桌面安装 SDK 后执行引擎不可选 | leemine | desktop, config_panel, settings | jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/features/settings/modules/agent/useExternalCliInstallCompletion.ts, jiuwenswarm/channels/web/frontend/src/features/settings/modules/agent/ExternalCliAgentsSettings.tsx, jiuwenswarm/channels/web/frontend/src/components/ExternalCliAgentsSection.tsx | 无独立 D：沿原 Third-party Agents 配置/安装和 Front 执行器目录职责修复；不增加执行流程。 |

<a id="module-6"></a>

## docs

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261101_2056_missing-lfs-demo-videos](docs/B_20261101_2056_missing-lfs-demo-videos.md) | B | Remove unavailable LFS demo video references | leemine | docs, .github/workflows | .github/workflows/stable.yml, .gitattributes, README.md, docs/assets/videos, docs/en/ChinaChannels.md, docs/en/TaskPlanning.md, docs/zh/国内频道.md, docs/zh/任务规划.md | 无独立 D：User-approved documentation asset cleanup; no independent architecture design. |

<a id="module-7"></a>

## gateway/channel_manager/im_platforms/xiaoyi

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261028_1445_xiaoyi-team-join-delivery](gateway/channel_manager/im_platforms/xiaoyi/B_20261028_1445_xiaoyi-team-join-delivery.md) | B | 小艺成员加入团队后仅在通知栏收到 Team Leader 消息 | zhongxiaotian | gateway/channel_manager/im_platforms/xiaoyi, gateway/message_handler | gateway/channel_manager/im_platforms/xiaoyi/xiaoyi_connect.py, gateway/message_handler/join_exit_handlers.py, tests/unit_tests/gateway/test_xiaoyi_team_delivery.py | 无独立 D：当前团队席位和 fan-out 契约未变化，本次仅修复小艺平台任务生命周期。 |

<a id="module-8"></a>

## gateway/common

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261031_1122_model-config-without-core](jiuwenswarm/common/config_panel/B_20261031_1122_model-config-without-core.md) | B | 无 Core 安装的模型配置加载与保存修复 | leemine | gateway/common, jiuwenswarm/common/config_panel, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models | gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/modelAdapters.ts, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/modelValidation.ts, jiuwenswarm/channels/web/frontend/src/types/index.ts, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/channels/web/frontend/tests/modelReasoning.test.mjs, tests/unit_tests/test_external_model_settings.py | 无独立 D：用户确认的最小配置缺陷修复，不统一 Provider 推理能力，无独立设计。 |

<a id="module-9"></a>

## gateway/message_handler

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261028_1445_xiaoyi-team-join-delivery](gateway/channel_manager/im_platforms/xiaoyi/B_20261028_1445_xiaoyi-team-join-delivery.md) | B | 小艺成员加入团队后仅在通知栏收到 Team Leader 消息 | zhongxiaotian | gateway/channel_manager/im_platforms/xiaoyi, gateway/message_handler | gateway/channel_manager/im_platforms/xiaoyi/xiaoyi_connect.py, gateway/message_handler/join_exit_handlers.py, tests/unit_tests/gateway/test_xiaoyi_team_delivery.py | 无独立 D：当前团队席位和 fan-out 契约未变化，本次仅修复小艺平台任务生命周期。 |

<a id="module-10"></a>

## jiuwenswarm/channels/web

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261031_1418_session-recovery-lifecycle](jiuwenswarm/server/runtime/agent_adapter/B_20261031_1418_session-recovery-lifecycle.md) | B | 外部主Agent取消续聊与历史恢复活动状态收敛 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server, jiuwenswarm/channels/web | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/services/runtimeResume.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_command_workflows_handler.py, jiuwenswarm/channels/web/frontend/tests/webClientRuntimeAck.test.mjs, jiuwenswarm/channels/web/frontend/tests/sessionInput.test.mjs | 无独立 D：用户要求修复现有流程遗留，不新增旁路；沿既有Runtime、SDK resume、Native可选边界和Web订阅修复。 |

<a id="module-11"></a>

## jiuwenswarm/channels/web/frontend

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261031_2104_tool-result-and-codex-tls](agent_adapter/B_20261031_2104_tool-result-and-codex-tls.md) | B | Claude 工具结果展示与 Codex TLS 配置接缝修复 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, jiuwenswarm/channels/web/frontend | jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ToolCallDisplay.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ToolGroupDisplay.tsx, jiuwenswarm/channels/web/frontend/src/features/historyRestore.ts, jiuwenswarm/channels/web/frontend/src/features/tool-events/toolEventNormalizer.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/channels/web/frontend/src/stores/toolResultLifecycle.ts, jiuwenswarm/channels/web/frontend/src/types/message.ts, jiuwenswarm/channels/web/frontend/tests/subagentHistoryRestore.test.mjs, jiuwenswarm/channels/web/frontend/tests/toolEventNormalizer.test.mjs, jiuwenswarm/channels/web/frontend/tests/toolGroupDisplayOrder.test.mjs, jiuwenswarm/common/codex_adapter_config.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_codex_direct_adapter.py | 无独立 D：用户确认已核对根因的最小修复；Codex 范围明确为模型 verify_ssl:false 配置拦截，不涉及取消或新增执行流程。 |

<a id="module-12"></a>

## jiuwenswarm/channels/web/frontend/src/features/settings/modules/models

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261031_1122_model-config-without-core](jiuwenswarm/common/config_panel/B_20261031_1122_model-config-without-core.md) | B | 无 Core 安装的模型配置加载与保存修复 | leemine | gateway/common, jiuwenswarm/common/config_panel, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models | gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/modelAdapters.ts, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/modelValidation.ts, jiuwenswarm/channels/web/frontend/src/types/index.ts, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/channels/web/frontend/tests/modelReasoning.test.mjs, tests/unit_tests/test_external_model_settings.py | 无独立 D：用户确认的最小配置缺陷修复，不统一 Provider 推理能力，无独立设计。 |

<a id="module-13"></a>

## jiuwenswarm/common

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261031_2104_tool-result-and-codex-tls](agent_adapter/B_20261031_2104_tool-result-and-codex-tls.md) | B | Claude 工具结果展示与 Codex TLS 配置接缝修复 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, jiuwenswarm/channels/web/frontend | jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ToolCallDisplay.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ToolGroupDisplay.tsx, jiuwenswarm/channels/web/frontend/src/features/historyRestore.ts, jiuwenswarm/channels/web/frontend/src/features/tool-events/toolEventNormalizer.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/channels/web/frontend/src/stores/toolResultLifecycle.ts, jiuwenswarm/channels/web/frontend/src/types/message.ts, jiuwenswarm/channels/web/frontend/tests/subagentHistoryRestore.test.mjs, jiuwenswarm/channels/web/frontend/tests/toolEventNormalizer.test.mjs, jiuwenswarm/channels/web/frontend/tests/toolGroupDisplayOrder.test.mjs, jiuwenswarm/common/codex_adapter_config.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_codex_direct_adapter.py | 无独立 D：用户确认已核对根因的最小修复；Codex 范围明确为模型 verify_ssl:false 配置拦截，不涉及取消或新增执行流程。 |

<a id="module-14"></a>

## jiuwenswarm/common/config_panel

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261031_1122_model-config-without-core](jiuwenswarm/common/config_panel/B_20261031_1122_model-config-without-core.md) | B | 无 Core 安装的模型配置加载与保存修复 | leemine | gateway/common, jiuwenswarm/common/config_panel, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models | gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/modelAdapters.ts, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/modelValidation.ts, jiuwenswarm/channels/web/frontend/src/types/index.ts, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/channels/web/frontend/tests/modelReasoning.test.mjs, tests/unit_tests/test_external_model_settings.py | 无独立 D：用户确认的最小配置缺陷修复，不统一 Provider 推理能力，无独立设计。 |

<a id="module-15"></a>

## jiuwenswarm/server

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261031_1418_session-recovery-lifecycle](jiuwenswarm/server/runtime/agent_adapter/B_20261031_1418_session-recovery-lifecycle.md) | B | 外部主Agent取消续聊与历史恢复活动状态收敛 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server, jiuwenswarm/channels/web | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/services/runtimeResume.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_command_workflows_handler.py, jiuwenswarm/channels/web/frontend/tests/webClientRuntimeAck.test.mjs, jiuwenswarm/channels/web/frontend/tests/sessionInput.test.mjs | 无独立 D：用户要求修复现有流程遗留，不新增旁路；沿既有Runtime、SDK resume、Native可选边界和Web订阅修复。 |

<a id="module-16"></a>

## jiuwenswarm/server/runtime/agent_adapter

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_1646_opencode-tls-error-diagnostics](agent_adapter/B_20261030_1646_opencode-tls-error-diagnostics.md) | B | OpenCode TLS 原生错误原因丢失与同环境复验 | leemine | jiuwenswarm/server/runtime/agent_adapter | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py | 无独立 D：用户授权定位并修复既有接入错误；不扩展执行框架或修改外部源码。 |
| [B_20261031_1142_claude-tool-result-metadata](jiuwenswarm/server/runtime/agent_adapter/B_20261031_1142_claude-tool-result-metadata.md) | B | Claude 工具保护错误的非结构化结果兼容 | leemine | jiuwenswarm/server/runtime/agent_adapter | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, tests/unit_tests/agentserver/test_claude_direct_adapter.py | 无独立 D：用户授权真实Runtime验收发现的适配缺陷，最小修复不改变已确认架构。 |
| [B_20261031_1418_session-recovery-lifecycle](jiuwenswarm/server/runtime/agent_adapter/B_20261031_1418_session-recovery-lifecycle.md) | B | 外部主Agent取消续聊与历史恢复活动状态收敛 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server, jiuwenswarm/channels/web | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/services/runtimeResume.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_command_workflows_handler.py, jiuwenswarm/channels/web/frontend/tests/webClientRuntimeAck.test.mjs, jiuwenswarm/channels/web/frontend/tests/sessionInput.test.mjs | 无独立 D：用户要求修复现有流程遗留，不新增旁路；沿既有Runtime、SDK resume、Native可选边界和Web订阅修复。 |
| [B_20261031_1459_codex-cancel-session](jiuwenswarm/server/runtime/agent_adapter/B_20261031_1459_codex-cancel-session.md) | B | Codex取消确认本轮终端停止并保留原生Thread | leemine | jiuwenswarm/server/runtime/agent_adapter | jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, tests/unit_tests/agentserver/test_codex_direct_adapter.py, docs/zh/FAQ.md, docs/en/FAQ.md | 无独立 D：用户确认继续修复已复现的取消后续聊问题，沿原Runtime和官方SDK，不扩展冷恢复或新执行流程。 |
| [B_20261031_2104_tool-result-and-codex-tls](agent_adapter/B_20261031_2104_tool-result-and-codex-tls.md) | B | Claude 工具结果展示与 Codex TLS 配置接缝修复 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, jiuwenswarm/channels/web/frontend | jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ToolCallDisplay.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ToolGroupDisplay.tsx, jiuwenswarm/channels/web/frontend/src/features/historyRestore.ts, jiuwenswarm/channels/web/frontend/src/features/tool-events/toolEventNormalizer.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/channels/web/frontend/src/stores/toolResultLifecycle.ts, jiuwenswarm/channels/web/frontend/src/types/message.ts, jiuwenswarm/channels/web/frontend/tests/subagentHistoryRestore.test.mjs, jiuwenswarm/channels/web/frontend/tests/toolEventNormalizer.test.mjs, jiuwenswarm/channels/web/frontend/tests/toolGroupDisplayOrder.test.mjs, jiuwenswarm/common/codex_adapter_config.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_codex_direct_adapter.py | 无独立 D：用户确认已核对根因的最小修复；Codex 范围明确为模型 verify_ssl:false 配置拦截，不涉及取消或新增执行流程。 |

<a id="module-17"></a>

## jiuwenswarm/server/runtime/agent_adapter/providers

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_2041_opencode-cli-discovery](agent_adapter/B_20261030_2041_opencode-cli-discovery.md) | B | OpenCode 桌面 PATH 缺口与传输边界收敛 | leemine | jiuwenswarm/server/runtime/agent_adapter/providers, scripts | jiuwenswarm/server/runtime/agent_adapter/providers/cli.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_transport.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py, scripts/assemble-electron-linux.py | 无独立 D：用户确认保留官方 HTTP/SSE 并隔离传输边界；延续管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 的外部 Provider 桌面候选。 |

<a id="module-18"></a>

## scripts

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_2041_opencode-cli-discovery](agent_adapter/B_20261030_2041_opencode-cli-discovery.md) | B | OpenCode 桌面 PATH 缺口与传输边界收敛 | leemine | jiuwenswarm/server/runtime/agent_adapter/providers, scripts | jiuwenswarm/server/runtime/agent_adapter/providers/cli.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_transport.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py, scripts/assemble-electron-linux.py | 无独立 D：用户确认保留官方 HTTP/SSE 并隔离传输边界；延续管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 的外部 Provider 桌面候选。 |

<a id="module-19"></a>

## server/worker

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_1607_opencode-permission-profiles](agent_adapter/B_20261030_1607_opencode-permission-profiles.md) | B | OpenCode Full Access 与原生权限、生效状态接入 | leemine | agent_adapter, server/worker, channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/worker/dispatcher.py, jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/config/permissionProfiles.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx | 无独立 D：用户确认复用既有 reload/Runtime/权限下拉的最小接入方案，无独立子仓设计。 |

<a id="module-20"></a>

## settings

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261031_1930_optional-provider-menu](desktop/B_20261031_1930_optional-provider-menu.md) | B | 桌面安装 SDK 后执行引擎不可选 | leemine | desktop, config_panel, settings | jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/features/settings/modules/agent/useExternalCliInstallCompletion.ts, jiuwenswarm/channels/web/frontend/src/features/settings/modules/agent/ExternalCliAgentsSettings.tsx, jiuwenswarm/channels/web/frontend/src/components/ExternalCliAgentsSection.tsx | 无独立 D：沿原 Third-party Agents 配置/安装和 Front 执行器目录职责修复；不增加执行流程。 |

<a id="module-21"></a>

## 未分类

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261026_1602_code-multimodal-loading](jiuwenswarm/server/runtime/agent_adapter/B_20261026_1602_code-multimodal-loading.md) | B | 配置多模态模型后，Code 未按 Work 规则加载工具 | 待确认 | — | — | 待核实 |
| [B_20261026_1606_issue-5753-session-project-binding](jiuwenswarm/server/runtime/session/B_20261026_1606_issue-5753-session-project-binding.md) | B | Issue #5753：普通会话发送消息后混入全局项目目录 | 待确认 | — | — | 待核实 |
| [B_20261026_2035_gateway-contract-collection](tests/unit_tests/common/B_20261026_2035_gateway-contract-collection.md) | B | Gateway 拆包后协议契约测试无法收集 | 待确认 | — | — | 待核实 |
