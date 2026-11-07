---
title: 实施与决策 F索引
author: leemine
author_email: leewanlong@gmail.com
generated: true
---

# 实施与决策 F索引

由 sync_documents.py 从文档 frontmatter 自动生成；请修改源文档后重新生成，不手工维护。

共 8 篇文档，按模块分组；跨模块文档在各相关分组展示，总数按文档去重。

## 模块导航

| 模块 | 文档数 |
|---|---|
| [.github/workflows](#module-1) | 1 |
| [agent_adapter](#module-2) | 4 |
| [desktop](#module-3) | 1 |
| [gateway](#module-4) | 1 |
| [gateway/common](#module-5) | 1 |
| [jiuwenswarm/channels/web/frontend](#module-6) | 3 |
| [jiuwenswarm/common](#module-7) | 2 |
| [jiuwenswarm/server](#module-8) | 1 |
| [jiuwenswarm/server/runtime/agent_adapter](#module-9) | 4 |
| [jiuwenswarm/server/runtime/session](#module-10) | 1 |
| [scripts](#module-11) | 1 |

<a id="module-1"></a>

## .github/workflows

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261104_1430_provider-beta5-release](F_20261104_1430_provider-beta5-release.md) | F | Provider beta5 发布收尾与验证边界 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/channels/web/frontend, scripts, .github/workflows | .github/workflows/stable.yml, .github/workflows/windows-external.yml, scripts/build_config.py, pyproject.toml, uv.lock, tests/unit_tests/agentserver/test_opencode_equipment_encoding.py | 无独立 D：用户在输出保护、P1 和 OBS-01 之后明确授权执行提交合并、三平台打包与发布任务 2～6；任务 1 的 Claude 真实验收独立保留。 |

<a id="module-2"></a>

## agent_adapter

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261029_2258_agent-adapter-boundary-validation](F_20261029_2258_agent-adapter-boundary-validation.md) | F | AgentAdapter 无 Core 边界实验 | leemine | agent_adapter | jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ExecutionPicker.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ExecutionPicker.css, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx, jiuwenswarm/channels/web/frontend/src/stores/sessionStore.ts, jiuwenswarm/runtime/session/coordinator.py, jiuwenswarm/runtime/plan.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/control/config_service.py, jiuwenswarm/common/model_routing_registry.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/runtime/service.py | 无独立 D：用户授权的隔离验证；设计及证据在管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 第10节，初轮事实见第10节，后续第1～2阶段见第11节及当前 S_02 规约；未发布。 |
| [F_20261030_1939_external-desktop-builds](F_20261030_1939_external-desktop-builds.md) | F | 可选 Native 与外部 Provider 桌面测试包 | leemine | agent_adapter, desktop, gateway | pyproject.toml, uv.lock, scripts/jiuwenswarm.spec, scripts/build-electron-linux.sh, scripts/assemble-electron-linux.py, scripts/verify_external_bundle.py, jiuwenswarm/common/native_integration.py, gateway/extensions/registry.py, .github/workflows/windows-external.yml, .github/scripts/transfer-release-assets.py, .github/workflows/stable.yml, tests/unit_tests/test_release_asset_transfer.py | 无独立 D：用户确认两种安装组合和先 Linux 后 Windows/macOS 的实施范围；管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 第24节及 EXTERNAL_DESKTOP_BUILD_20261030 记录来源与验证。 |
| [F_20261104_1030_provider-input-ownership](F_20261104_1030_provider-input-ownership.md) | F | P1 执行输入与装备所有权收敛 | leemine | agent_adapter | jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/execution_input.py, jiuwenswarm/server/runtime/agent_adapter/equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/common/codex_adapter_config.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py | 无独立 D：用户授权先执行 P1；范围依据管理仓 PROVIDER_PLUGIN_DEPENDENCY_AUDIT_20261031 的 P1/P2 划分。本记录细化接入职责，不将设计当成已验证实现。 |
| [F_20261104_1720_main-agent-role](F_20261104_1720_main-agent-role.md) | F | P2 主 Agent 角色指令 | leemine | agent_adapter | jiuwenswarm/server/runtime/agent_adapter/equipment.py, jiuwenswarm/runtime/session_provisioner.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/server/runtime/session/session_metadata.py, jiuwenswarm/server/runtime/extension_package_manager.py, jiuwenswarm/server/runtime/agent_adapter/main_agent_role.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/execution_input.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py | 无独立 D：用户批准按管理仓 PROVIDER_PLUGIN_DEPENDENCY_AUDIT_20261031 第 10.2 节 PROMPT-01 实施，复用会话入口并按配置传角色引用。任务看板试点单独延期。 |

<a id="module-3"></a>

## desktop

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261030_1939_external-desktop-builds](F_20261030_1939_external-desktop-builds.md) | F | 可选 Native 与外部 Provider 桌面测试包 | leemine | agent_adapter, desktop, gateway | pyproject.toml, uv.lock, scripts/jiuwenswarm.spec, scripts/build-electron-linux.sh, scripts/assemble-electron-linux.py, scripts/verify_external_bundle.py, jiuwenswarm/common/native_integration.py, gateway/extensions/registry.py, .github/workflows/windows-external.yml, .github/scripts/transfer-release-assets.py, .github/workflows/stable.yml, tests/unit_tests/test_release_asset_transfer.py | 无独立 D：用户确认两种安装组合和先 Linux 后 Windows/macOS 的实施范围；管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 第24节及 EXTERNAL_DESKTOP_BUILD_20261030 记录来源与验证。 |

<a id="module-4"></a>

## gateway

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261030_1939_external-desktop-builds](F_20261030_1939_external-desktop-builds.md) | F | 可选 Native 与外部 Provider 桌面测试包 | leemine | agent_adapter, desktop, gateway | pyproject.toml, uv.lock, scripts/jiuwenswarm.spec, scripts/build-electron-linux.sh, scripts/assemble-electron-linux.py, scripts/verify_external_bundle.py, jiuwenswarm/common/native_integration.py, gateway/extensions/registry.py, .github/workflows/windows-external.yml, .github/scripts/transfer-release-assets.py, .github/workflows/stable.yml, tests/unit_tests/test_release_asset_transfer.py | 无独立 D：用户确认两种安装组合和先 Linux 后 Windows/macOS 的实施范围；管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 第24节及 EXTERNAL_DESKTOP_BUILD_20261030 记录来源与验证。 |

<a id="module-5"></a>

## gateway/common

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261031_1714_claude-main-agent-and-model-settings](F_20261031_1714_claude-main-agent-and-model-settings.md) | F | Claude 主 Agent 与无 Core 模型配置发布收尾 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, gateway/common, jiuwenswarm/channels/web/frontend, jiuwenswarm/server | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/external_adapter_factories.py, gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, pyproject.toml, uv.lock, .github/workflows/stable.yml | 无独立 D：用户已确认原AgentAdapter直接接官方SDK的实施方向，并授权任务1～2发布收尾；本次未另建独立设计。 |

<a id="module-6"></a>

## jiuwenswarm/channels/web/frontend

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261031_1714_claude-main-agent-and-model-settings](F_20261031_1714_claude-main-agent-and-model-settings.md) | F | Claude 主 Agent 与无 Core 模型配置发布收尾 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, gateway/common, jiuwenswarm/channels/web/frontend, jiuwenswarm/server | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/external_adapter_factories.py, gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, pyproject.toml, uv.lock, .github/workflows/stable.yml | 无独立 D：用户已确认原AgentAdapter直接接官方SDK的实施方向，并授权任务1～2发布收尾；本次未另建独立设计。 |
| [F_20261104_1230_codex-native-usage-observation](F_20261104_1230_codex-native-usage-observation.md) | F | Provider 原生用量只读观测（Codex、Claude、OpenCode） | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex_usage.py, jiuwenswarm/server/runtime/session/session_history.py, jiuwenswarm/channels/web/frontend/src/types/sessionTokenUsage.ts, jiuwenswarm/channels/web/frontend/src/types/message.ts, jiuwenswarm/channels/web/frontend/src/features/historyRestore.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.css, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude_usage.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_usage.py | 无独立 D：用户确认管理仓 OBS-01 只读方案后授权先做 Codex 原生事件试点；无独立 D 文档，不扩展到压缩或发布；同日用户授权将只读方案续接 Claude/OpenCode。 |
| [F_20261104_1430_provider-beta5-release](F_20261104_1430_provider-beta5-release.md) | F | Provider beta5 发布收尾与验证边界 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/channels/web/frontend, scripts, .github/workflows | .github/workflows/stable.yml, .github/workflows/windows-external.yml, scripts/build_config.py, pyproject.toml, uv.lock, tests/unit_tests/agentserver/test_opencode_equipment_encoding.py | 无独立 D：用户在输出保护、P1 和 OBS-01 之后明确授权执行提交合并、三平台打包与发布任务 2～6；任务 1 的 Claude 真实验收独立保留。 |

<a id="module-7"></a>

## jiuwenswarm/common

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261031_1714_claude-main-agent-and-model-settings](F_20261031_1714_claude-main-agent-and-model-settings.md) | F | Claude 主 Agent 与无 Core 模型配置发布收尾 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, gateway/common, jiuwenswarm/channels/web/frontend, jiuwenswarm/server | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/external_adapter_factories.py, gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, pyproject.toml, uv.lock, .github/workflows/stable.yml | 无独立 D：用户已确认原AgentAdapter直接接官方SDK的实施方向，并授权任务1～2发布收尾；本次未另建独立设计。 |
| [F_20261104_2128_codex-session-mcp](F_20261104_2128_codex-session-mcp.md) | F | Codex 会话显式选择 Streamable HTTP MCP | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common | jiuwenswarm/common/external_adapter_factories.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex_mcp.py | 无独立 D：用户批准管理仓 PROVIDER_PLUGIN_DEPENDENCY_AUDIT_20261031 中 Codex 会话 MCP 方案，宿主只声明能力。 |

<a id="module-8"></a>

## jiuwenswarm/server

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261031_1714_claude-main-agent-and-model-settings](F_20261031_1714_claude-main-agent-and-model-settings.md) | F | Claude 主 Agent 与无 Core 模型配置发布收尾 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, gateway/common, jiuwenswarm/channels/web/frontend, jiuwenswarm/server | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/external_adapter_factories.py, gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, pyproject.toml, uv.lock, .github/workflows/stable.yml | 无独立 D：用户已确认原AgentAdapter直接接官方SDK的实施方向，并授权任务1～2发布收尾；本次未另建独立设计。 |

<a id="module-9"></a>

## jiuwenswarm/server/runtime/agent_adapter

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261031_1714_claude-main-agent-and-model-settings](F_20261031_1714_claude-main-agent-and-model-settings.md) | F | Claude 主 Agent 与无 Core 模型配置发布收尾 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, gateway/common, jiuwenswarm/channels/web/frontend, jiuwenswarm/server | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/external_adapter_factories.py, gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, pyproject.toml, uv.lock, .github/workflows/stable.yml | 无独立 D：用户已确认原AgentAdapter直接接官方SDK的实施方向，并授权任务1～2发布收尾；本次未另建独立设计。 |
| [F_20261104_1230_codex-native-usage-observation](F_20261104_1230_codex-native-usage-observation.md) | F | Provider 原生用量只读观测（Codex、Claude、OpenCode） | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex_usage.py, jiuwenswarm/server/runtime/session/session_history.py, jiuwenswarm/channels/web/frontend/src/types/sessionTokenUsage.ts, jiuwenswarm/channels/web/frontend/src/types/message.ts, jiuwenswarm/channels/web/frontend/src/features/historyRestore.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.css, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude_usage.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_usage.py | 无独立 D：用户确认管理仓 OBS-01 只读方案后授权先做 Codex 原生事件试点；无独立 D 文档，不扩展到压缩或发布；同日用户授权将只读方案续接 Claude/OpenCode。 |
| [F_20261104_1430_provider-beta5-release](F_20261104_1430_provider-beta5-release.md) | F | Provider beta5 发布收尾与验证边界 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/channels/web/frontend, scripts, .github/workflows | .github/workflows/stable.yml, .github/workflows/windows-external.yml, scripts/build_config.py, pyproject.toml, uv.lock, tests/unit_tests/agentserver/test_opencode_equipment_encoding.py | 无独立 D：用户在输出保护、P1 和 OBS-01 之后明确授权执行提交合并、三平台打包与发布任务 2～6；任务 1 的 Claude 真实验收独立保留。 |
| [F_20261104_2128_codex-session-mcp](F_20261104_2128_codex-session-mcp.md) | F | Codex 会话显式选择 Streamable HTTP MCP | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common | jiuwenswarm/common/external_adapter_factories.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex_mcp.py | 无独立 D：用户批准管理仓 PROVIDER_PLUGIN_DEPENDENCY_AUDIT_20261031 中 Codex 会话 MCP 方案，宿主只声明能力。 |

<a id="module-10"></a>

## jiuwenswarm/server/runtime/session

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261104_1230_codex-native-usage-observation](F_20261104_1230_codex-native-usage-observation.md) | F | Provider 原生用量只读观测（Codex、Claude、OpenCode） | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex_usage.py, jiuwenswarm/server/runtime/session/session_history.py, jiuwenswarm/channels/web/frontend/src/types/sessionTokenUsage.ts, jiuwenswarm/channels/web/frontend/src/types/message.ts, jiuwenswarm/channels/web/frontend/src/features/historyRestore.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.css, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude_usage.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_usage.py | 无独立 D：用户确认管理仓 OBS-01 只读方案后授权先做 Codex 原生事件试点；无独立 D 文档，不扩展到压缩或发布；同日用户授权将只读方案续接 Claude/OpenCode。 |

<a id="module-11"></a>

## scripts

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261104_1430_provider-beta5-release](F_20261104_1430_provider-beta5-release.md) | F | Provider beta5 发布收尾与验证边界 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/channels/web/frontend, scripts, .github/workflows | .github/workflows/stable.yml, .github/workflows/windows-external.yml, scripts/build_config.py, pyproject.toml, uv.lock, tests/unit_tests/agentserver/test_opencode_equipment_encoding.py | 无独立 D：用户在输出保护、P1 和 OBS-01 之后明确授权执行提交合并、三平台打包与发布任务 2～6；任务 1 的 Claude 真实验收独立保留。 |
