---
title: D/F/B/S 文档总索引
author: leemine
author_email: leewanlong@gmail.com
generated: true
---

# D/F/B/S 文档总索引

由 sync_documents.py 从文档 frontmatter 自动生成；请修改源文档后重新生成，不手工维护。

共 26 篇文档，按模块分组；跨模块文档在各相关分组展示，总数按文档去重。

## 模块导航

| 模块 | 文档数 |
|---|---|
| [agent_adapter](#module-1) | 5 |
| [agent_teams](#module-2) | 1 |
| [agent_teams/workflow](#module-3) | 3 |
| [channels/web/frontend](#module-4) | 1 |
| [desktop](#module-5) | 1 |
| [gateway](#module-6) | 1 |
| [gateway/channel_manager/im_platforms/xiaoyi](#module-7) | 1 |
| [gateway/message_handler](#module-8) | 1 |
| [jiuwenswarm](#module-9) | 3 |
| [jiuwenswarm/channels/web/frontend](#module-10) | 1 |
| [jiuwenswarm/gateway/channel_manager/web](#module-11) | 1 |
| [jiuwenswarm/observability](#module-12) | 1 |
| [jiuwenswarm/server/runtime/agent_adapter](#module-13) | 1 |
| [jiuwenswarm/server/runtime/agent_adapter/providers](#module-14) | 1 |
| [runtime](#module-15) | 1 |
| [scripts](#module-16) | 1 |
| [server/worker](#module-17) | 1 |
| [未分类](#module-18) | 12 |

<a id="module-1"></a>

## agent_adapter

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261029_2258_agent-adapter-boundary-validation](features/F_20261029_2258_agent-adapter-boundary-validation.md) | F | AgentAdapter 无 Core 边界实验 | leemine | agent_adapter | jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ExecutionPicker.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ExecutionPicker.css, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx, jiuwenswarm/channels/web/frontend/src/stores/sessionStore.ts, jiuwenswarm/runtime/session/coordinator.py, jiuwenswarm/runtime/plan.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/control/config_service.py, jiuwenswarm/common/model_routing_registry.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/runtime/service.py | 无独立 D：用户授权的隔离验证；设计及证据在管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 第10节，初轮事实见第10节，后续第1～2阶段见第11节及当前 S_02 规约；未发布。 |
| [F_20261030_1939_external-desktop-builds](features/F_20261030_1939_external-desktop-builds.md) | F | 可选 Native 与外部 Provider 桌面测试包 | leemine | agent_adapter, desktop, gateway | pyproject.toml, uv.lock, scripts/jiuwenswarm.spec, scripts/build-electron-linux.sh, scripts/assemble-electron-linux.py, scripts/verify_external_bundle.py, jiuwenswarm/common/native_integration.py, gateway/extensions/registry.py | 无独立 D：用户确认两种安装组合和先 Linux 后 Windows/macOS 的实施范围；管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 第24节及 EXTERNAL_DESKTOP_BUILD_20261030 记录来源与验证。 |
| [B_20261030_1455_opencode-session-workspace-binding](bugfix/agent_adapter/B_20261030_1455_opencode-session-workspace-binding.md) | B | OpenCode 会话项目目录绑定修复 | leemine | agent_adapter | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py | 无独立 D：用户确认对当前 S_02 会话目录契约的小范围修复，无独立设计。 |
| [B_20261030_1607_opencode-permission-profiles](bugfix/agent_adapter/B_20261030_1607_opencode-permission-profiles.md) | B | OpenCode Full Access 与原生权限、生效状态接入 | leemine | agent_adapter, server/worker, channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/worker/dispatcher.py, jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/config/permissionProfiles.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx | 无独立 D：用户确认复用既有 reload/Runtime/权限下拉的最小接入方案，无独立子仓设计。 |
| [S_02_external-adapter-boundary](specs/jiuwenswarm/server/runtime/agent_adapter/S_02_external-adapter-boundary.md) | S | 外部 AgentAdapter 单 Agent 边界规约 | leemine | agent_adapter, runtime | jiuwenswarm/runtime/session/coordinator.py, jiuwenswarm/runtime/plan.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/control/config_service.py, jiuwenswarm/common/model_routing_registry.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/runtime/service.py | — |

<a id="module-2"></a>

## agent_teams

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [SDD-0029](designs/proposals/SDD-0029-team-session-runtime-integration/design.md) | D | Team 模式接入统一 Session Runtime | @zhanglongmin | agent_teams | — | — |

<a id="module-3"></a>

## agent_teams/workflow

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [SDD-0009](designs/archive/SDD-0009-jiuwen-tui-swarmflow-human-session-adaptation/design.md) | D | jiuwen TUI 适配 SwarmFlow 三算子（human / human_session / agent_session） | @chenchunzhou | agent_teams/workflow, jiuwenswarm | — | — |
| [SDD-0010](designs/archive/SDD-0010-jiuwen-tui-nested-workflow-and-budget-observability/design.md) | D | jiuwen TUI 嵌套 Workflow 与 Budget 可观测性 | @chenchunzhou | agent_teams/workflow, jiuwenswarm | — | — |
| [SDD-0028](designs/archive/SDD-0028-swarmflow-verify-fork-observability/design.md) | D | swarmflow verify / fork 可观测与前端呈现 | @xiajing | agent_teams/workflow, jiuwenswarm | — | — |

<a id="module-4"></a>

## channels/web/frontend

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_1607_opencode-permission-profiles](bugfix/agent_adapter/B_20261030_1607_opencode-permission-profiles.md) | B | OpenCode Full Access 与原生权限、生效状态接入 | leemine | agent_adapter, server/worker, channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/worker/dispatcher.py, jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/config/permissionProfiles.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx | 无独立 D：用户确认复用既有 reload/Runtime/权限下拉的最小接入方案，无独立子仓设计。 |

<a id="module-5"></a>

## desktop

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261030_1939_external-desktop-builds](features/F_20261030_1939_external-desktop-builds.md) | F | 可选 Native 与外部 Provider 桌面测试包 | leemine | agent_adapter, desktop, gateway | pyproject.toml, uv.lock, scripts/jiuwenswarm.spec, scripts/build-electron-linux.sh, scripts/assemble-electron-linux.py, scripts/verify_external_bundle.py, jiuwenswarm/common/native_integration.py, gateway/extensions/registry.py | 无独立 D：用户确认两种安装组合和先 Linux 后 Windows/macOS 的实施范围；管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 第24节及 EXTERNAL_DESKTOP_BUILD_20261030 记录来源与验证。 |

<a id="module-6"></a>

## gateway

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261030_1939_external-desktop-builds](features/F_20261030_1939_external-desktop-builds.md) | F | 可选 Native 与外部 Provider 桌面测试包 | leemine | agent_adapter, desktop, gateway | pyproject.toml, uv.lock, scripts/jiuwenswarm.spec, scripts/build-electron-linux.sh, scripts/assemble-electron-linux.py, scripts/verify_external_bundle.py, jiuwenswarm/common/native_integration.py, gateway/extensions/registry.py | 无独立 D：用户确认两种安装组合和先 Linux 后 Windows/macOS 的实施范围；管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 第24节及 EXTERNAL_DESKTOP_BUILD_20261030 记录来源与验证。 |

<a id="module-7"></a>

## gateway/channel_manager/im_platforms/xiaoyi

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261028_1445_xiaoyi-team-join-delivery](bugfix/gateway/channel_manager/im_platforms/xiaoyi/B_20261028_1445_xiaoyi-team-join-delivery.md) | B | 小艺成员加入团队后仅在通知栏收到 Team Leader 消息 | zhongxiaotian | gateway/channel_manager/im_platforms/xiaoyi, gateway/message_handler | gateway/channel_manager/im_platforms/xiaoyi/xiaoyi_connect.py, gateway/message_handler/join_exit_handlers.py, tests/unit_tests/gateway/test_xiaoyi_team_delivery.py | 无独立 D：当前团队席位和 fan-out 契约未变化，本次仅修复小艺平台任务生命周期。 |

<a id="module-8"></a>

## gateway/message_handler

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261028_1445_xiaoyi-team-join-delivery](bugfix/gateway/channel_manager/im_platforms/xiaoyi/B_20261028_1445_xiaoyi-team-join-delivery.md) | B | 小艺成员加入团队后仅在通知栏收到 Team Leader 消息 | zhongxiaotian | gateway/channel_manager/im_platforms/xiaoyi, gateway/message_handler | gateway/channel_manager/im_platforms/xiaoyi/xiaoyi_connect.py, gateway/message_handler/join_exit_handlers.py, tests/unit_tests/gateway/test_xiaoyi_team_delivery.py | 无独立 D：当前团队席位和 fan-out 契约未变化，本次仅修复小艺平台任务生命周期。 |

<a id="module-9"></a>

## jiuwenswarm

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [SDD-0009](designs/archive/SDD-0009-jiuwen-tui-swarmflow-human-session-adaptation/design.md) | D | jiuwen TUI 适配 SwarmFlow 三算子（human / human_session / agent_session） | @chenchunzhou | agent_teams/workflow, jiuwenswarm | — | — |
| [SDD-0010](designs/archive/SDD-0010-jiuwen-tui-nested-workflow-and-budget-observability/design.md) | D | jiuwen TUI 嵌套 Workflow 与 Budget 可观测性 | @chenchunzhou | agent_teams/workflow, jiuwenswarm | — | — |
| [SDD-0028](designs/archive/SDD-0028-swarmflow-verify-fork-observability/design.md) | D | swarmflow verify / fork 可观测与前端呈现 | @xiajing | agent_teams/workflow, jiuwenswarm | — | — |

<a id="module-10"></a>

## jiuwenswarm/channels/web/frontend

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [SDD-0026](designs/proposals/SDD-0026-trajectory-observability-web-ui/design.md) | D | 轨迹观测前端：单 Agent、Subagent 与 Team 多 Agent 轨迹 UI | @alan_cheng | jiuwenswarm/channels/web/frontend | — | — |

<a id="module-11"></a>

## jiuwenswarm/gateway/channel_manager/web

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [SDD-0025](designs/proposals/SDD-0025-trajectory-session-store-and-serving/design.md) | D | 轨迹数据面：会话级 SQLite 存储、实时变更提示与读取 API | @alan_cheng | jiuwenswarm/observability, jiuwenswarm/gateway/channel_manager/web | — | — |

<a id="module-12"></a>

## jiuwenswarm/observability

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [SDD-0025](designs/proposals/SDD-0025-trajectory-session-store-and-serving/design.md) | D | 轨迹数据面：会话级 SQLite 存储、实时变更提示与读取 API | @alan_cheng | jiuwenswarm/observability, jiuwenswarm/gateway/channel_manager/web | — | — |

<a id="module-13"></a>

## jiuwenswarm/server/runtime/agent_adapter

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_1646_opencode-tls-error-diagnostics](bugfix/agent_adapter/B_20261030_1646_opencode-tls-error-diagnostics.md) | B | OpenCode TLS 原生错误原因丢失与同环境复验 | leemine | jiuwenswarm/server/runtime/agent_adapter | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py | 无独立 D：用户授权定位并修复既有接入错误；不扩展执行框架或修改外部源码。 |

<a id="module-14"></a>

## jiuwenswarm/server/runtime/agent_adapter/providers

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_2041_opencode-cli-discovery](bugfix/agent_adapter/B_20261030_2041_opencode-cli-discovery.md) | B | OpenCode 桌面 PATH 缺口与传输边界收敛 | leemine | jiuwenswarm/server/runtime/agent_adapter/providers, scripts | jiuwenswarm/server/runtime/agent_adapter/providers/cli.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_transport.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py, scripts/assemble-electron-linux.py | 无独立 D：用户确认保留官方 HTTP/SSE 并隔离传输边界；延续管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 的外部 Provider 桌面候选。 |

<a id="module-15"></a>

## runtime

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [S_02_external-adapter-boundary](specs/jiuwenswarm/server/runtime/agent_adapter/S_02_external-adapter-boundary.md) | S | 外部 AgentAdapter 单 Agent 边界规约 | leemine | agent_adapter, runtime | jiuwenswarm/runtime/session/coordinator.py, jiuwenswarm/runtime/plan.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/control/config_service.py, jiuwenswarm/common/model_routing_registry.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/runtime/service.py | — |

<a id="module-16"></a>

## scripts

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_2041_opencode-cli-discovery](bugfix/agent_adapter/B_20261030_2041_opencode-cli-discovery.md) | B | OpenCode 桌面 PATH 缺口与传输边界收敛 | leemine | jiuwenswarm/server/runtime/agent_adapter/providers, scripts | jiuwenswarm/server/runtime/agent_adapter/providers/cli.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_transport.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py, scripts/assemble-electron-linux.py | 无独立 D：用户确认保留官方 HTTP/SSE 并隔离传输边界；延续管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 的外部 Provider 桌面候选。 |

<a id="module-17"></a>

## server/worker

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_1607_opencode-permission-profiles](bugfix/agent_adapter/B_20261030_1607_opencode-permission-profiles.md) | B | OpenCode Full Access 与原生权限、生效状态接入 | leemine | agent_adapter, server/worker, channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/worker/dispatcher.py, jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/config/permissionProfiles.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx | 无独立 D：用户确认复用既有 reload/Runtime/权限下拉的最小接入方案，无独立子仓设计。 |

<a id="module-18"></a>

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
