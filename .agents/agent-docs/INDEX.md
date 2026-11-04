---
title: D/F/B/S 文档总索引
author: leemine
author_email: leewanlong@gmail.com
generated: true
---

# D/F/B/S 文档总索引

由 sync_documents.py 从文档 frontmatter 自动生成；请修改源文档后重新生成，不手工维护。

共 44 篇文档，按模块分组；跨模块文档在各相关分组展示，总数按文档去重。

## 模块导航

| 模块 | 文档数 |
|---|---|
| [.github/workflows](#module-1) | 2 |
| [agent_adapter](#module-2) | 7 |
| [agent_teams](#module-3) | 1 |
| [agent_teams/workflow](#module-4) | 3 |
| [channels/web/frontend](#module-5) | 1 |
| [config_panel](#module-6) | 1 |
| [desktop](#module-7) | 2 |
| [docs](#module-8) | 1 |
| [gateway](#module-9) | 1 |
| [gateway/channel_manager/im_platforms/xiaoyi](#module-10) | 1 |
| [gateway/common](#module-11) | 2 |
| [gateway/message_handler](#module-12) | 1 |
| [jiuwenswarm](#module-13) | 3 |
| [jiuwenswarm/channels/web](#module-14) | 1 |
| [jiuwenswarm/channels/web/frontend](#module-15) | 5 |
| [jiuwenswarm/channels/web/frontend/src/features/settings/modules/models](#module-16) | 1 |
| [jiuwenswarm/common](#module-17) | 3 |
| [jiuwenswarm/common/config_panel](#module-18) | 1 |
| [jiuwenswarm/gateway/channel_manager/web](#module-19) | 1 |
| [jiuwenswarm/observability](#module-20) | 1 |
| [jiuwenswarm/server](#module-21) | 2 |
| [jiuwenswarm/server/runtime/agent_adapter](#module-22) | 9 |
| [jiuwenswarm/server/runtime/agent_adapter/providers](#module-23) | 6 |
| [jiuwenswarm/server/runtime/session](#module-24) | 1 |
| [runtime](#module-25) | 1 |
| [scripts](#module-26) | 2 |
| [server/worker](#module-27) | 1 |
| [settings](#module-28) | 1 |
| [未分类](#module-29) | 12 |

<a id="module-1"></a>

## .github/workflows

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261104_1430_provider-beta5-release](features/F_20261104_1430_provider-beta5-release.md) | F | Provider beta5 发布收尾与验证边界 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/channels/web/frontend, scripts, .github/workflows | .github/workflows/stable.yml, .github/workflows/windows-external.yml, scripts/build_config.py, pyproject.toml, uv.lock, tests/unit_tests/agentserver/test_opencode_equipment_encoding.py | 无独立 D：用户在输出保护、P1 和 OBS-01 之后明确授权执行提交合并、三平台打包与发布任务 2～6；任务 1 的 Claude 真实验收独立保留。 |
| [B_20261101_2056_missing-lfs-demo-videos](bugfix/docs/B_20261101_2056_missing-lfs-demo-videos.md) | B | Remove unavailable LFS demo video references | leemine | docs, .github/workflows | tests/unit_tests/agentserver/test_provider_session_selection.py, .github/workflows/stable.yml, .gitattributes, README.md, docs/assets/videos, docs/en/ChinaChannels.md, docs/en/TaskPlanning.md, docs/zh/国内频道.md, docs/zh/任务规划.md | 无独立 D：User-approved documentation asset cleanup; no independent architecture design. |

<a id="module-2"></a>

## agent_adapter

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261029_2258_agent-adapter-boundary-validation](features/F_20261029_2258_agent-adapter-boundary-validation.md) | F | AgentAdapter 无 Core 边界实验 | leemine | agent_adapter | jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ExecutionPicker.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ExecutionPicker.css, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx, jiuwenswarm/channels/web/frontend/src/stores/sessionStore.ts, jiuwenswarm/runtime/session/coordinator.py, jiuwenswarm/runtime/plan.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/control/config_service.py, jiuwenswarm/common/model_routing_registry.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/runtime/service.py | 无独立 D：用户授权的隔离验证；设计及证据在管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 第10节，初轮事实见第10节，后续第1～2阶段见第11节及当前 S_02 规约；未发布。 |
| [F_20261030_1939_external-desktop-builds](features/F_20261030_1939_external-desktop-builds.md) | F | 可选 Native 与外部 Provider 桌面测试包 | leemine | agent_adapter, desktop, gateway | pyproject.toml, uv.lock, scripts/jiuwenswarm.spec, scripts/build-electron-linux.sh, scripts/assemble-electron-linux.py, scripts/verify_external_bundle.py, jiuwenswarm/common/native_integration.py, gateway/extensions/registry.py, .github/workflows/windows-external.yml, .github/scripts/transfer-release-assets.py, .github/workflows/stable.yml, tests/unit_tests/test_release_asset_transfer.py | 无独立 D：用户确认两种安装组合和先 Linux 后 Windows/macOS 的实施范围；管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 第24节及 EXTERNAL_DESKTOP_BUILD_20261030 记录来源与验证。 |
| [F_20261104_1030_provider-input-ownership](features/F_20261104_1030_provider-input-ownership.md) | F | P1 执行输入与装备所有权收敛 | leemine | agent_adapter | jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/execution_input.py, jiuwenswarm/server/runtime/agent_adapter/equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/common/codex_adapter_config.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py | 无独立 D：用户授权先执行 P1；范围依据管理仓 PROVIDER_PLUGIN_DEPENDENCY_AUDIT_20261031 的 P1/P2 划分。本记录细化接入职责，不将设计当成已验证实现。 |
| [F_20261104_1720_main-agent-role](features/F_20261104_1720_main-agent-role.md) | F | P2 主 Agent 角色指令 | leemine | agent_adapter | jiuwenswarm/server/runtime/agent_adapter/equipment.py, jiuwenswarm/runtime/session_provisioner.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/server/runtime/session/session_metadata.py, jiuwenswarm/server/runtime/extension_package_manager.py, jiuwenswarm/server/runtime/agent_adapter/main_agent_role.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/execution_input.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py | 无独立 D：用户批准按管理仓 PROVIDER_PLUGIN_DEPENDENCY_AUDIT_20261031 第 10.2 节 PROMPT-01 实施，复用会话入口并按配置传角色引用。任务看板试点单独延期。 |
| [B_20261030_1455_opencode-session-workspace-binding](bugfix/agent_adapter/B_20261030_1455_opencode-session-workspace-binding.md) | B | OpenCode 会话项目目录绑定修复 | leemine | agent_adapter | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py | 无独立 D：用户确认对当前 S_02 会话目录契约的小范围修复，无独立设计。 |
| [B_20261030_1607_opencode-permission-profiles](bugfix/agent_adapter/B_20261030_1607_opencode-permission-profiles.md) | B | OpenCode Full Access 与原生权限、生效状态接入 | leemine | agent_adapter, server/worker, channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/worker/dispatcher.py, jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/config/permissionProfiles.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx | 无独立 D：用户确认复用既有 reload/Runtime/权限下拉的最小接入方案，无独立子仓设计。 |
| [S_02_external-adapter-boundary](specs/jiuwenswarm/server/runtime/agent_adapter/S_02_external-adapter-boundary.md) | S | 外部 AgentAdapter 单 Agent 边界规约 | leemine | agent_adapter, runtime | jiuwenswarm/runtime/session/coordinator.py, jiuwenswarm/runtime/plan.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/control/config_service.py, jiuwenswarm/common/model_routing_registry.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/runtime/service.py, jiuwenswarm/server/runtime/agent_adapter/execution_input.py, jiuwenswarm/server/runtime/agent_adapter/equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py | — |

<a id="module-3"></a>

## agent_teams

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [SDD-0029](designs/proposals/SDD-0029-team-session-runtime-integration/design.md) | D | Team 模式接入统一 Session Runtime | @zhanglongmin | agent_teams | — | — |

<a id="module-4"></a>

## agent_teams/workflow

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [SDD-0009](designs/archive/SDD-0009-jiuwen-tui-swarmflow-human-session-adaptation/design.md) | D | jiuwen TUI 适配 SwarmFlow 三算子（human / human_session / agent_session） | @chenchunzhou | agent_teams/workflow, jiuwenswarm | — | — |
| [SDD-0010](designs/archive/SDD-0010-jiuwen-tui-nested-workflow-and-budget-observability/design.md) | D | jiuwen TUI 嵌套 Workflow 与 Budget 可观测性 | @chenchunzhou | agent_teams/workflow, jiuwenswarm | — | — |
| [SDD-0028](designs/archive/SDD-0028-swarmflow-verify-fork-observability/design.md) | D | swarmflow verify / fork 可观测与前端呈现 | @xiajing | agent_teams/workflow, jiuwenswarm | — | — |

<a id="module-5"></a>

## channels/web/frontend

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_1607_opencode-permission-profiles](bugfix/agent_adapter/B_20261030_1607_opencode-permission-profiles.md) | B | OpenCode Full Access 与原生权限、生效状态接入 | leemine | agent_adapter, server/worker, channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/worker/dispatcher.py, jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/config/permissionProfiles.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx | 无独立 D：用户确认复用既有 reload/Runtime/权限下拉的最小接入方案，无独立子仓设计。 |

<a id="module-6"></a>

## config_panel

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261031_1930_optional-provider-menu](bugfix/desktop/B_20261031_1930_optional-provider-menu.md) | B | 桌面安装 SDK 后执行引擎不可选 | leemine | desktop, config_panel, settings | jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/features/settings/modules/agent/useExternalCliInstallCompletion.ts, jiuwenswarm/channels/web/frontend/src/features/settings/modules/agent/ExternalCliAgentsSettings.tsx, jiuwenswarm/channels/web/frontend/src/components/ExternalCliAgentsSection.tsx | 无独立 D：沿原 Third-party Agents 配置/安装和 Front 执行器目录职责修复；不增加执行流程。 |

<a id="module-7"></a>

## desktop

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261030_1939_external-desktop-builds](features/F_20261030_1939_external-desktop-builds.md) | F | 可选 Native 与外部 Provider 桌面测试包 | leemine | agent_adapter, desktop, gateway | pyproject.toml, uv.lock, scripts/jiuwenswarm.spec, scripts/build-electron-linux.sh, scripts/assemble-electron-linux.py, scripts/verify_external_bundle.py, jiuwenswarm/common/native_integration.py, gateway/extensions/registry.py, .github/workflows/windows-external.yml, .github/scripts/transfer-release-assets.py, .github/workflows/stable.yml, tests/unit_tests/test_release_asset_transfer.py | 无独立 D：用户确认两种安装组合和先 Linux 后 Windows/macOS 的实施范围；管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 第24节及 EXTERNAL_DESKTOP_BUILD_20261030 记录来源与验证。 |
| [B_20261031_1930_optional-provider-menu](bugfix/desktop/B_20261031_1930_optional-provider-menu.md) | B | 桌面安装 SDK 后执行引擎不可选 | leemine | desktop, config_panel, settings | jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/features/settings/modules/agent/useExternalCliInstallCompletion.ts, jiuwenswarm/channels/web/frontend/src/features/settings/modules/agent/ExternalCliAgentsSettings.tsx, jiuwenswarm/channels/web/frontend/src/components/ExternalCliAgentsSection.tsx | 无独立 D：沿原 Third-party Agents 配置/安装和 Front 执行器目录职责修复；不增加执行流程。 |

<a id="module-8"></a>

## docs

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261101_2056_missing-lfs-demo-videos](bugfix/docs/B_20261101_2056_missing-lfs-demo-videos.md) | B | Remove unavailable LFS demo video references | leemine | docs, .github/workflows | tests/unit_tests/agentserver/test_provider_session_selection.py, .github/workflows/stable.yml, .gitattributes, README.md, docs/assets/videos, docs/en/ChinaChannels.md, docs/en/TaskPlanning.md, docs/zh/国内频道.md, docs/zh/任务规划.md | 无独立 D：User-approved documentation asset cleanup; no independent architecture design. |

<a id="module-9"></a>

## gateway

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261030_1939_external-desktop-builds](features/F_20261030_1939_external-desktop-builds.md) | F | 可选 Native 与外部 Provider 桌面测试包 | leemine | agent_adapter, desktop, gateway | pyproject.toml, uv.lock, scripts/jiuwenswarm.spec, scripts/build-electron-linux.sh, scripts/assemble-electron-linux.py, scripts/verify_external_bundle.py, jiuwenswarm/common/native_integration.py, gateway/extensions/registry.py, .github/workflows/windows-external.yml, .github/scripts/transfer-release-assets.py, .github/workflows/stable.yml, tests/unit_tests/test_release_asset_transfer.py | 无独立 D：用户确认两种安装组合和先 Linux 后 Windows/macOS 的实施范围；管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 第24节及 EXTERNAL_DESKTOP_BUILD_20261030 记录来源与验证。 |

<a id="module-10"></a>

## gateway/channel_manager/im_platforms/xiaoyi

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261028_1445_xiaoyi-team-join-delivery](bugfix/gateway/channel_manager/im_platforms/xiaoyi/B_20261028_1445_xiaoyi-team-join-delivery.md) | B | 小艺成员加入团队后仅在通知栏收到 Team Leader 消息 | zhongxiaotian | gateway/channel_manager/im_platforms/xiaoyi, gateway/message_handler | gateway/channel_manager/im_platforms/xiaoyi/xiaoyi_connect.py, gateway/message_handler/join_exit_handlers.py, tests/unit_tests/gateway/test_xiaoyi_team_delivery.py | 无独立 D：当前团队席位和 fan-out 契约未变化，本次仅修复小艺平台任务生命周期。 |

<a id="module-11"></a>

## gateway/common

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261031_1714_claude-main-agent-and-model-settings](features/F_20261031_1714_claude-main-agent-and-model-settings.md) | F | Claude 主 Agent 与无 Core 模型配置发布收尾 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, gateway/common, jiuwenswarm/channels/web/frontend, jiuwenswarm/server | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/external_adapter_factories.py, gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, pyproject.toml, uv.lock, .github/workflows/stable.yml | 无独立 D：用户已确认原AgentAdapter直接接官方SDK的实施方向，并授权任务1～2发布收尾；本次未另建独立设计。 |
| [B_20261031_1122_model-config-without-core](bugfix/jiuwenswarm/common/config_panel/B_20261031_1122_model-config-without-core.md) | B | 无 Core 安装的模型配置加载与保存修复 | leemine | gateway/common, jiuwenswarm/common/config_panel, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models | gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/modelAdapters.ts, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/modelValidation.ts, jiuwenswarm/channels/web/frontend/src/types/index.ts, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/channels/web/frontend/tests/modelReasoning.test.mjs, tests/unit_tests/test_external_model_settings.py | 无独立 D：用户确认的最小配置缺陷修复，不统一 Provider 推理能力，无独立设计。 |

<a id="module-12"></a>

## gateway/message_handler

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261028_1445_xiaoyi-team-join-delivery](bugfix/gateway/channel_manager/im_platforms/xiaoyi/B_20261028_1445_xiaoyi-team-join-delivery.md) | B | 小艺成员加入团队后仅在通知栏收到 Team Leader 消息 | zhongxiaotian | gateway/channel_manager/im_platforms/xiaoyi, gateway/message_handler | gateway/channel_manager/im_platforms/xiaoyi/xiaoyi_connect.py, gateway/message_handler/join_exit_handlers.py, tests/unit_tests/gateway/test_xiaoyi_team_delivery.py | 无独立 D：当前团队席位和 fan-out 契约未变化，本次仅修复小艺平台任务生命周期。 |

<a id="module-13"></a>

## jiuwenswarm

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [SDD-0009](designs/archive/SDD-0009-jiuwen-tui-swarmflow-human-session-adaptation/design.md) | D | jiuwen TUI 适配 SwarmFlow 三算子（human / human_session / agent_session） | @chenchunzhou | agent_teams/workflow, jiuwenswarm | — | — |
| [SDD-0010](designs/archive/SDD-0010-jiuwen-tui-nested-workflow-and-budget-observability/design.md) | D | jiuwen TUI 嵌套 Workflow 与 Budget 可观测性 | @chenchunzhou | agent_teams/workflow, jiuwenswarm | — | — |
| [SDD-0028](designs/archive/SDD-0028-swarmflow-verify-fork-observability/design.md) | D | swarmflow verify / fork 可观测与前端呈现 | @xiajing | agent_teams/workflow, jiuwenswarm | — | — |

<a id="module-14"></a>

## jiuwenswarm/channels/web

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261031_1418_session-recovery-lifecycle](bugfix/jiuwenswarm/server/runtime/agent_adapter/B_20261031_1418_session-recovery-lifecycle.md) | B | 外部主Agent取消续聊与历史恢复活动状态收敛 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server, jiuwenswarm/channels/web | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/services/runtimeResume.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_command_workflows_handler.py, jiuwenswarm/channels/web/frontend/tests/webClientRuntimeAck.test.mjs, jiuwenswarm/channels/web/frontend/tests/sessionInput.test.mjs | 无独立 D：用户要求修复现有流程遗留，不新增旁路；沿既有Runtime、SDK resume、Native可选边界和Web订阅修复。 |

<a id="module-15"></a>

## jiuwenswarm/channels/web/frontend

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [SDD-0026](designs/proposals/SDD-0026-trajectory-observability-web-ui/design.md) | D | 轨迹观测前端：单 Agent、Subagent 与 Team 多 Agent 轨迹 UI | @alan_cheng | jiuwenswarm/channels/web/frontend | — | — |
| [F_20261031_1714_claude-main-agent-and-model-settings](features/F_20261031_1714_claude-main-agent-and-model-settings.md) | F | Claude 主 Agent 与无 Core 模型配置发布收尾 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, gateway/common, jiuwenswarm/channels/web/frontend, jiuwenswarm/server | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/external_adapter_factories.py, gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, pyproject.toml, uv.lock, .github/workflows/stable.yml | 无独立 D：用户已确认原AgentAdapter直接接官方SDK的实施方向，并授权任务1～2发布收尾；本次未另建独立设计。 |
| [F_20261104_1230_codex-native-usage-observation](features/F_20261104_1230_codex-native-usage-observation.md) | F | Provider 原生用量只读观测（Codex、Claude、OpenCode） | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex_usage.py, jiuwenswarm/server/runtime/session/session_history.py, jiuwenswarm/channels/web/frontend/src/types/sessionTokenUsage.ts, jiuwenswarm/channels/web/frontend/src/types/message.ts, jiuwenswarm/channels/web/frontend/src/features/historyRestore.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.css, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude_usage.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_usage.py | 无独立 D：用户确认管理仓 OBS-01 只读方案后授权先做 Codex 原生事件试点；无独立 D 文档，不扩展到压缩或发布；同日用户授权将只读方案续接 Claude/OpenCode。 |
| [F_20261104_1430_provider-beta5-release](features/F_20261104_1430_provider-beta5-release.md) | F | Provider beta5 发布收尾与验证边界 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/channels/web/frontend, scripts, .github/workflows | .github/workflows/stable.yml, .github/workflows/windows-external.yml, scripts/build_config.py, pyproject.toml, uv.lock, tests/unit_tests/agentserver/test_opencode_equipment_encoding.py | 无独立 D：用户在输出保护、P1 和 OBS-01 之后明确授权执行提交合并、三平台打包与发布任务 2～6；任务 1 的 Claude 真实验收独立保留。 |
| [B_20261031_2104_tool-result-and-codex-tls](bugfix/agent_adapter/B_20261031_2104_tool-result-and-codex-tls.md) | B | Claude 工具结果展示与 Codex TLS 配置接缝修复 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, jiuwenswarm/channels/web/frontend | jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ToolCallDisplay.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ToolGroupDisplay.tsx, jiuwenswarm/channels/web/frontend/src/features/historyRestore.ts, jiuwenswarm/channels/web/frontend/src/features/tool-events/toolEventNormalizer.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/channels/web/frontend/src/stores/toolResultLifecycle.ts, jiuwenswarm/channels/web/frontend/src/types/message.ts, jiuwenswarm/channels/web/frontend/tests/subagentHistoryRestore.test.mjs, jiuwenswarm/channels/web/frontend/tests/toolEventNormalizer.test.mjs, jiuwenswarm/channels/web/frontend/tests/toolGroupDisplayOrder.test.mjs, jiuwenswarm/common/codex_adapter_config.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_codex_direct_adapter.py | 无独立 D：用户确认已核对根因的最小修复；Codex 范围明确为模型 verify_ssl:false 配置拦截，不涉及取消或新增执行流程。 |

<a id="module-16"></a>

## jiuwenswarm/channels/web/frontend/src/features/settings/modules/models

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261031_1122_model-config-without-core](bugfix/jiuwenswarm/common/config_panel/B_20261031_1122_model-config-without-core.md) | B | 无 Core 安装的模型配置加载与保存修复 | leemine | gateway/common, jiuwenswarm/common/config_panel, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models | gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/modelAdapters.ts, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/modelValidation.ts, jiuwenswarm/channels/web/frontend/src/types/index.ts, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/channels/web/frontend/tests/modelReasoning.test.mjs, tests/unit_tests/test_external_model_settings.py | 无独立 D：用户确认的最小配置缺陷修复，不统一 Provider 推理能力，无独立设计。 |

<a id="module-17"></a>

## jiuwenswarm/common

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261031_1714_claude-main-agent-and-model-settings](features/F_20261031_1714_claude-main-agent-and-model-settings.md) | F | Claude 主 Agent 与无 Core 模型配置发布收尾 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, gateway/common, jiuwenswarm/channels/web/frontend, jiuwenswarm/server | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/external_adapter_factories.py, gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, pyproject.toml, uv.lock, .github/workflows/stable.yml | 无独立 D：用户已确认原AgentAdapter直接接官方SDK的实施方向，并授权任务1～2发布收尾；本次未另建独立设计。 |
| [B_20261031_2104_tool-result-and-codex-tls](bugfix/agent_adapter/B_20261031_2104_tool-result-and-codex-tls.md) | B | Claude 工具结果展示与 Codex TLS 配置接缝修复 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, jiuwenswarm/channels/web/frontend | jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ToolCallDisplay.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ToolGroupDisplay.tsx, jiuwenswarm/channels/web/frontend/src/features/historyRestore.ts, jiuwenswarm/channels/web/frontend/src/features/tool-events/toolEventNormalizer.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/channels/web/frontend/src/stores/toolResultLifecycle.ts, jiuwenswarm/channels/web/frontend/src/types/message.ts, jiuwenswarm/channels/web/frontend/tests/subagentHistoryRestore.test.mjs, jiuwenswarm/channels/web/frontend/tests/toolEventNormalizer.test.mjs, jiuwenswarm/channels/web/frontend/tests/toolGroupDisplayOrder.test.mjs, jiuwenswarm/common/codex_adapter_config.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_codex_direct_adapter.py | 无独立 D：用户确认已核对根因的最小修复；Codex 范围明确为模型 verify_ssl:false 配置拦截，不涉及取消或新增执行流程。 |
| [B_20261102_1123_provider-native-timeouts](bugfix/agent_adapter/B_20261102_1123_provider-native-timeouts.md) | B | 外部 Provider 模型超时与整轮时限职责修复 | leemine | jiuwenswarm/server/runtime/agent_adapter/providers, jiuwenswarm/common | jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/codex_adapter_config.py, jiuwenswarm/common/config_panel/config_set_handlers.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py | 无独立 D：用户在本会话确认超时职责修正与官方配置复用方案，无独立 D 文档；续写当前外部适配器契约，不修改已归档设计。 |

<a id="module-18"></a>

## jiuwenswarm/common/config_panel

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261031_1122_model-config-without-core](bugfix/jiuwenswarm/common/config_panel/B_20261031_1122_model-config-without-core.md) | B | 无 Core 安装的模型配置加载与保存修复 | leemine | gateway/common, jiuwenswarm/common/config_panel, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models | gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/modelAdapters.ts, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/modelValidation.ts, jiuwenswarm/channels/web/frontend/src/types/index.ts, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/channels/web/frontend/tests/modelReasoning.test.mjs, tests/unit_tests/test_external_model_settings.py | 无独立 D：用户确认的最小配置缺陷修复，不统一 Provider 推理能力，无独立设计。 |

<a id="module-19"></a>

## jiuwenswarm/gateway/channel_manager/web

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [SDD-0025](designs/proposals/SDD-0025-trajectory-session-store-and-serving/design.md) | D | 轨迹数据面：会话级 SQLite 存储、实时变更提示与读取 API | @alan_cheng | jiuwenswarm/observability, jiuwenswarm/gateway/channel_manager/web | — | — |

<a id="module-20"></a>

## jiuwenswarm/observability

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [SDD-0025](designs/proposals/SDD-0025-trajectory-session-store-and-serving/design.md) | D | 轨迹数据面：会话级 SQLite 存储、实时变更提示与读取 API | @alan_cheng | jiuwenswarm/observability, jiuwenswarm/gateway/channel_manager/web | — | — |

<a id="module-21"></a>

## jiuwenswarm/server

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261031_1714_claude-main-agent-and-model-settings](features/F_20261031_1714_claude-main-agent-and-model-settings.md) | F | Claude 主 Agent 与无 Core 模型配置发布收尾 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, gateway/common, jiuwenswarm/channels/web/frontend, jiuwenswarm/server | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/external_adapter_factories.py, gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, pyproject.toml, uv.lock, .github/workflows/stable.yml | 无独立 D：用户已确认原AgentAdapter直接接官方SDK的实施方向，并授权任务1～2发布收尾；本次未另建独立设计。 |
| [B_20261031_1418_session-recovery-lifecycle](bugfix/jiuwenswarm/server/runtime/agent_adapter/B_20261031_1418_session-recovery-lifecycle.md) | B | 外部主Agent取消续聊与历史恢复活动状态收敛 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server, jiuwenswarm/channels/web | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/services/runtimeResume.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_command_workflows_handler.py, jiuwenswarm/channels/web/frontend/tests/webClientRuntimeAck.test.mjs, jiuwenswarm/channels/web/frontend/tests/sessionInput.test.mjs | 无独立 D：用户要求修复现有流程遗留，不新增旁路；沿既有Runtime、SDK resume、Native可选边界和Web订阅修复。 |

<a id="module-22"></a>

## jiuwenswarm/server/runtime/agent_adapter

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261031_1714_claude-main-agent-and-model-settings](features/F_20261031_1714_claude-main-agent-and-model-settings.md) | F | Claude 主 Agent 与无 Core 模型配置发布收尾 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, gateway/common, jiuwenswarm/channels/web/frontend, jiuwenswarm/server | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/external_adapter_factories.py, gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, pyproject.toml, uv.lock, .github/workflows/stable.yml | 无独立 D：用户已确认原AgentAdapter直接接官方SDK的实施方向，并授权任务1～2发布收尾；本次未另建独立设计。 |
| [F_20261104_1230_codex-native-usage-observation](features/F_20261104_1230_codex-native-usage-observation.md) | F | Provider 原生用量只读观测（Codex、Claude、OpenCode） | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex_usage.py, jiuwenswarm/server/runtime/session/session_history.py, jiuwenswarm/channels/web/frontend/src/types/sessionTokenUsage.ts, jiuwenswarm/channels/web/frontend/src/types/message.ts, jiuwenswarm/channels/web/frontend/src/features/historyRestore.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.css, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude_usage.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_usage.py | 无独立 D：用户确认管理仓 OBS-01 只读方案后授权先做 Codex 原生事件试点；无独立 D 文档，不扩展到压缩或发布；同日用户授权将只读方案续接 Claude/OpenCode。 |
| [F_20261104_1430_provider-beta5-release](features/F_20261104_1430_provider-beta5-release.md) | F | Provider beta5 发布收尾与验证边界 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/channels/web/frontend, scripts, .github/workflows | .github/workflows/stable.yml, .github/workflows/windows-external.yml, scripts/build_config.py, pyproject.toml, uv.lock, tests/unit_tests/agentserver/test_opencode_equipment_encoding.py | 无独立 D：用户在输出保护、P1 和 OBS-01 之后明确授权执行提交合并、三平台打包与发布任务 2～6；任务 1 的 Claude 真实验收独立保留。 |
| [B_20261030_1646_opencode-tls-error-diagnostics](bugfix/agent_adapter/B_20261030_1646_opencode-tls-error-diagnostics.md) | B | OpenCode TLS 原生错误原因丢失与同环境复验 | leemine | jiuwenswarm/server/runtime/agent_adapter | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py | 无独立 D：用户授权定位并修复既有接入错误；不扩展执行框架或修改外部源码。 |
| [B_20261031_1142_claude-tool-result-metadata](bugfix/jiuwenswarm/server/runtime/agent_adapter/B_20261031_1142_claude-tool-result-metadata.md) | B | Claude 工具保护错误的非结构化结果兼容 | leemine | jiuwenswarm/server/runtime/agent_adapter | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, tests/unit_tests/agentserver/test_claude_direct_adapter.py | 无独立 D：用户授权真实Runtime验收发现的适配缺陷，最小修复不改变已确认架构。 |
| [B_20261031_1418_session-recovery-lifecycle](bugfix/jiuwenswarm/server/runtime/agent_adapter/B_20261031_1418_session-recovery-lifecycle.md) | B | 外部主Agent取消续聊与历史恢复活动状态收敛 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server, jiuwenswarm/channels/web | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/services/runtimeResume.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_command_workflows_handler.py, jiuwenswarm/channels/web/frontend/tests/webClientRuntimeAck.test.mjs, jiuwenswarm/channels/web/frontend/tests/sessionInput.test.mjs | 无独立 D：用户要求修复现有流程遗留，不新增旁路；沿既有Runtime、SDK resume、Native可选边界和Web订阅修复。 |
| [B_20261031_1459_codex-cancel-session](bugfix/jiuwenswarm/server/runtime/agent_adapter/B_20261031_1459_codex-cancel-session.md) | B | Codex取消确认本轮终端停止并保留原生Thread | leemine | jiuwenswarm/server/runtime/agent_adapter | jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, tests/unit_tests/agentserver/test_codex_direct_adapter.py, docs/zh/FAQ.md, docs/en/FAQ.md | 无独立 D：用户确认继续修复已复现的取消后续聊问题，沿原Runtime和官方SDK，不扩展冷恢复或新执行流程。 |
| [B_20261031_2104_tool-result-and-codex-tls](bugfix/agent_adapter/B_20261031_2104_tool-result-and-codex-tls.md) | B | Claude 工具结果展示与 Codex TLS 配置接缝修复 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, jiuwenswarm/channels/web/frontend | jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ToolCallDisplay.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ToolGroupDisplay.tsx, jiuwenswarm/channels/web/frontend/src/features/historyRestore.ts, jiuwenswarm/channels/web/frontend/src/features/tool-events/toolEventNormalizer.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/channels/web/frontend/src/stores/toolResultLifecycle.ts, jiuwenswarm/channels/web/frontend/src/types/message.ts, jiuwenswarm/channels/web/frontend/tests/subagentHistoryRestore.test.mjs, jiuwenswarm/channels/web/frontend/tests/toolEventNormalizer.test.mjs, jiuwenswarm/channels/web/frontend/tests/toolGroupDisplayOrder.test.mjs, jiuwenswarm/common/codex_adapter_config.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_codex_direct_adapter.py | 无独立 D：用户确认已核对根因的最小修复；Codex 范围明确为模型 verify_ssl:false 配置拦截，不涉及取消或新增执行流程。 |
| [B_20261103_1113_opencode-utf8-equipment](bugfix/agent_adapter/B_20261103_1113_opencode-utf8-equipment.md) | B | OpenCode equipment 跨平台 UTF-8 编码修复 | leewanlong | jiuwenswarm/server/runtime/agent_adapter | jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_equipment.py, tests/unit_tests/agentserver/test_opencode_equipment_encoding.py | 无独立 D：现有适配层文件编码的小范围修复，无独立设计。 |

<a id="module-23"></a>

## jiuwenswarm/server/runtime/agent_adapter/providers

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_2041_opencode-cli-discovery](bugfix/agent_adapter/B_20261030_2041_opencode-cli-discovery.md) | B | OpenCode 桌面 PATH 缺口与传输边界收敛 | leemine | jiuwenswarm/server/runtime/agent_adapter/providers, scripts | jiuwenswarm/server/runtime/agent_adapter/providers/cli.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_transport.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py, scripts/assemble-electron-linux.py | 无独立 D：用户确认保留官方 HTTP/SSE 并隔离传输边界；延续管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 的外部 Provider 桌面候选。 |
| [B_20261102_1123_provider-native-timeouts](bugfix/agent_adapter/B_20261102_1123_provider-native-timeouts.md) | B | 外部 Provider 模型超时与整轮时限职责修复 | leemine | jiuwenswarm/server/runtime/agent_adapter/providers, jiuwenswarm/common | jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/codex_adapter_config.py, jiuwenswarm/common/config_panel/config_set_handlers.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py | 无独立 D：用户在本会话确认超时职责修正与官方配置复用方案，无独立 D 文档；续写当前外部适配器契约，不修改已归档设计。 |
| [B_20261102_1436_claude-background-lifecycle](bugfix/agent_adapter/B_20261102_1436_claude-background-lifecycle.md) | B | Claude 后台探索的原生完成边界 | leemine | jiuwenswarm/server/runtime/agent_adapter/providers | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, tests/unit_tests/agentserver/test_claude_direct_adapter.py | 无独立 D：用户明确确认的最小缺陷修复，沿现有 S_02_external-adapter-boundary 契约，无新增执行架构。 |
| [B_20261102_1543_provider-subagent-content](bugfix/agent_adapter/B_20261102_1543_provider-subagent-content.md) | B | 外部子智能体卡片缺少内部活动与结果 | leemine | jiuwenswarm/server/runtime/agent_adapter/providers | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/subagent_projection.py, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_codex_direct_adapter.py | 无独立 D：用户确认Provider适配模块最小修复；沿原生命周期候选续作，无新宿主执行架构。OpenCode经用户确认后置。 |
| [B_20261103_2148_codex-output-bound](bugfix/agent_adapter/B_20261103_2148_codex-output-bound.md) | B | Codex 大工具返回的有界投影 | leemine | jiuwenswarm/server/runtime/agent_adapter/providers | jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, tests/unit_tests/agentserver/test_codex_direct_adapter.py | 无独立 D：用户已确认 Provider 内最小修复；不增强宿主、不新增共用模块，不另立设计。 |
| [B_20261103_2208_claude-opencode-output-bound](bugfix/agent_adapter/B_20261103_2208_claude-opencode-output-bound.md) | B | Claude 与 OpenCode 大工具结果及元数据投影 | leemine | jiuwenswarm/server/runtime/agent_adapter/providers | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py | 无独立 D：用户确认继续按现有Codex方案在各Provider内修复，不增强宿主或新增公共流程。 |

<a id="module-24"></a>

## jiuwenswarm/server/runtime/session

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261104_1230_codex-native-usage-observation](features/F_20261104_1230_codex-native-usage-observation.md) | F | Provider 原生用量只读观测（Codex、Claude、OpenCode） | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex_usage.py, jiuwenswarm/server/runtime/session/session_history.py, jiuwenswarm/channels/web/frontend/src/types/sessionTokenUsage.ts, jiuwenswarm/channels/web/frontend/src/types/message.ts, jiuwenswarm/channels/web/frontend/src/features/historyRestore.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.css, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude_usage.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_usage.py | 无独立 D：用户确认管理仓 OBS-01 只读方案后授权先做 Codex 原生事件试点；无独立 D 文档，不扩展到压缩或发布；同日用户授权将只读方案续接 Claude/OpenCode。 |

<a id="module-25"></a>

## runtime

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [S_02_external-adapter-boundary](specs/jiuwenswarm/server/runtime/agent_adapter/S_02_external-adapter-boundary.md) | S | 外部 AgentAdapter 单 Agent 边界规约 | leemine | agent_adapter, runtime | jiuwenswarm/runtime/session/coordinator.py, jiuwenswarm/runtime/plan.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/control/config_service.py, jiuwenswarm/common/model_routing_registry.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/runtime/service.py, jiuwenswarm/server/runtime/agent_adapter/execution_input.py, jiuwenswarm/server/runtime/agent_adapter/equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py | — |

<a id="module-26"></a>

## scripts

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261104_1430_provider-beta5-release](features/F_20261104_1430_provider-beta5-release.md) | F | Provider beta5 发布收尾与验证边界 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/channels/web/frontend, scripts, .github/workflows | .github/workflows/stable.yml, .github/workflows/windows-external.yml, scripts/build_config.py, pyproject.toml, uv.lock, tests/unit_tests/agentserver/test_opencode_equipment_encoding.py | 无独立 D：用户在输出保护、P1 和 OBS-01 之后明确授权执行提交合并、三平台打包与发布任务 2～6；任务 1 的 Claude 真实验收独立保留。 |
| [B_20261030_2041_opencode-cli-discovery](bugfix/agent_adapter/B_20261030_2041_opencode-cli-discovery.md) | B | OpenCode 桌面 PATH 缺口与传输边界收敛 | leemine | jiuwenswarm/server/runtime/agent_adapter/providers, scripts | jiuwenswarm/server/runtime/agent_adapter/providers/cli.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_transport.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py, scripts/assemble-electron-linux.py | 无独立 D：用户确认保留官方 HTTP/SSE 并隔离传输边界；延续管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 的外部 Provider 桌面候选。 |

<a id="module-27"></a>

## server/worker

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_1607_opencode-permission-profiles](bugfix/agent_adapter/B_20261030_1607_opencode-permission-profiles.md) | B | OpenCode Full Access 与原生权限、生效状态接入 | leemine | agent_adapter, server/worker, channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/worker/dispatcher.py, jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/config/permissionProfiles.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx | 无独立 D：用户确认复用既有 reload/Runtime/权限下拉的最小接入方案，无独立子仓设计。 |

<a id="module-28"></a>

## settings

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261031_1930_optional-provider-menu](bugfix/desktop/B_20261031_1930_optional-provider-menu.md) | B | 桌面安装 SDK 后执行引擎不可选 | leemine | desktop, config_panel, settings | jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/features/settings/modules/agent/useExternalCliInstallCompletion.ts, jiuwenswarm/channels/web/frontend/src/features/settings/modules/agent/ExternalCliAgentsSettings.tsx, jiuwenswarm/channels/web/frontend/src/components/ExternalCliAgentsSection.tsx | 无独立 D：沿原 Third-party Agents 配置/安装和 Front 执行器目录职责修复；不增加执行流程。 |

<a id="module-29"></a>

## 未分类

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [README](designs/README.md) | D | 设计资产 | 待确认 | — | — | — |
| [REGISTRY](designs/REGISTRY.md) | D | SDD 编号台账 (REGISTRY) | 待确认 | — | — | — |
| [legacy-documents](designs/legacy-documents.md) | D | 旧格式设计资料 | 待确认 | — | — | — |
| [migration-20261026](designs/migration-20261026.md) | D | 设计文档迁移与跨仓引用 | 待确认 | — | — | — |
| [team_expert_group_manifest_design](designs/archive/team_expert_group_manifest_design.md) | D | Team 模式接入专家团 Manifest 加载设计 | 待确认 | — | — | — |
| [team_permission_design](designs/archive/team_permission_design.md) | D | Team 模式 Permissions 设计方案 | 待确认 | — | — | — |
| [team_plan_design](designs/archive/team_plan_design.md) | D | Team Plan 模式设计文档 | 待确认 | — | — | — |
| [team_worktree_isolation_agenttool_cn](designs/archive/team_worktree_isolation_agenttool_cn.md) | D | Team Teammate Worktree Isolation 设计文档 | 待确认 | — | — | — |
| [B_20261026_1602_code-multimodal-loading](bugfix/jiuwenswarm/server/runtime/agent_adapter/B_20261026_1602_code-multimodal-loading.md) | B | 配置多模态模型后，Code 未按 Work 规则加载工具 | 待确认 | — | — | 待核实 |
| [B_20261026_1606_issue-5753-session-project-binding](bugfix/jiuwenswarm/server/runtime/session/B_20261026_1606_issue-5753-session-project-binding.md) | B | Issue #5753：普通会话发送消息后混入全局项目目录 | 待确认 | — | — | 待核实 |
| [B_20261026_2035_gateway-contract-collection](bugfix/tests/unit_tests/common/B_20261026_2035_gateway-contract-collection.md) | B | Gateway 拆包后协议契约测试无法收集 | 待确认 | — | — | 待核实 |
| [S_01_multimodal-tool-loading](specs/jiuwenswarm/server/runtime/agent_adapter/S_01_multimodal-tool-loading.md) | S | Work / Code 多模态工具加载契约 | 待确认 | — | — | — |
