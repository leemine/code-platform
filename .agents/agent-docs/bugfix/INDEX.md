---
title: 故障修复 B索引
author: leemine
author_email: leewanlong@gmail.com
generated: true
---

# 故障修复 B索引

由 sync_documents.py 从文档 frontmatter 自动生成；请修改源文档后重新生成，不手工维护。

共 9 篇文档，按模块分组；跨模块文档在各相关分组展示，总数按文档去重。

## 模块导航

| 模块 | 文档数 |
|---|---|
| [agent_adapter](#module-1) | 2 |
| [channels/web/frontend](#module-2) | 1 |
| [gateway/channel_manager/im_platforms/xiaoyi](#module-3) | 1 |
| [gateway/message_handler](#module-4) | 1 |
| [jiuwenswarm/server/runtime/agent_adapter](#module-5) | 2 |
| [jiuwenswarm/server/runtime/agent_adapter/providers](#module-6) | 1 |
| [scripts](#module-7) | 1 |
| [server/worker](#module-8) | 1 |
| [未分类](#module-9) | 3 |

<a id="module-1"></a>

## agent_adapter

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_1455_opencode-session-workspace-binding](agent_adapter/B_20261030_1455_opencode-session-workspace-binding.md) | B | OpenCode 会话项目目录绑定修复 | leemine | agent_adapter | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py | 无独立 D：用户确认对当前 S_02 会话目录契约的小范围修复，无独立设计。 |
| [B_20261030_1607_opencode-permission-profiles](agent_adapter/B_20261030_1607_opencode-permission-profiles.md) | B | OpenCode Full Access 与原生权限、生效状态接入 | leemine | agent_adapter, server/worker, channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/worker/dispatcher.py, jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/config/permissionProfiles.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx | 无独立 D：用户确认复用既有 reload/Runtime/权限下拉的最小接入方案，无独立子仓设计。 |

<a id="module-2"></a>

## channels/web/frontend

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_1607_opencode-permission-profiles](agent_adapter/B_20261030_1607_opencode-permission-profiles.md) | B | OpenCode Full Access 与原生权限、生效状态接入 | leemine | agent_adapter, server/worker, channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/worker/dispatcher.py, jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/config/permissionProfiles.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx | 无独立 D：用户确认复用既有 reload/Runtime/权限下拉的最小接入方案，无独立子仓设计。 |

<a id="module-3"></a>

## gateway/channel_manager/im_platforms/xiaoyi

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261028_1445_xiaoyi-team-join-delivery](gateway/channel_manager/im_platforms/xiaoyi/B_20261028_1445_xiaoyi-team-join-delivery.md) | B | 小艺成员加入团队后仅在通知栏收到 Team Leader 消息 | zhongxiaotian | gateway/channel_manager/im_platforms/xiaoyi, gateway/message_handler | gateway/channel_manager/im_platforms/xiaoyi/xiaoyi_connect.py, gateway/message_handler/join_exit_handlers.py, tests/unit_tests/gateway/test_xiaoyi_team_delivery.py | 无独立 D：当前团队席位和 fan-out 契约未变化，本次仅修复小艺平台任务生命周期。 |

<a id="module-4"></a>

## gateway/message_handler

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261028_1445_xiaoyi-team-join-delivery](gateway/channel_manager/im_platforms/xiaoyi/B_20261028_1445_xiaoyi-team-join-delivery.md) | B | 小艺成员加入团队后仅在通知栏收到 Team Leader 消息 | zhongxiaotian | gateway/channel_manager/im_platforms/xiaoyi, gateway/message_handler | gateway/channel_manager/im_platforms/xiaoyi/xiaoyi_connect.py, gateway/message_handler/join_exit_handlers.py, tests/unit_tests/gateway/test_xiaoyi_team_delivery.py | 无独立 D：当前团队席位和 fan-out 契约未变化，本次仅修复小艺平台任务生命周期。 |

<a id="module-5"></a>

## jiuwenswarm/server/runtime/agent_adapter

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_1646_opencode-tls-error-diagnostics](agent_adapter/B_20261030_1646_opencode-tls-error-diagnostics.md) | B | OpenCode TLS 原生错误原因丢失与同环境复验 | leemine | jiuwenswarm/server/runtime/agent_adapter | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py | 无独立 D：用户授权定位并修复既有接入错误；不扩展执行框架或修改外部源码。 |
| [B_20261031_1459_codex-cancel-session](jiuwenswarm/server/runtime/agent_adapter/B_20261031_1459_codex-cancel-session.md) | B | Codex取消确认本轮终端停止并保留原生Thread | leemine | jiuwenswarm/server/runtime/agent_adapter | jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, tests/unit_tests/agentserver/test_codex_direct_adapter.py, docs/zh/FAQ.md, docs/en/FAQ.md | 无独立 D：用户确认继续修复已复现的取消后续聊问题，沿原Runtime和官方SDK，不扩展冷恢复或新执行流程。 |

<a id="module-6"></a>

## jiuwenswarm/server/runtime/agent_adapter/providers

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_2041_opencode-cli-discovery](agent_adapter/B_20261030_2041_opencode-cli-discovery.md) | B | OpenCode 桌面 PATH 缺口与传输边界收敛 | leemine | jiuwenswarm/server/runtime/agent_adapter/providers, scripts | jiuwenswarm/server/runtime/agent_adapter/providers/cli.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_transport.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py, scripts/assemble-electron-linux.py | 无独立 D：用户确认保留官方 HTTP/SSE 并隔离传输边界；延续管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 的外部 Provider 桌面候选。 |

<a id="module-7"></a>

## scripts

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_2041_opencode-cli-discovery](agent_adapter/B_20261030_2041_opencode-cli-discovery.md) | B | OpenCode 桌面 PATH 缺口与传输边界收敛 | leemine | jiuwenswarm/server/runtime/agent_adapter/providers, scripts | jiuwenswarm/server/runtime/agent_adapter/providers/cli.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_transport.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py, scripts/assemble-electron-linux.py | 无独立 D：用户确认保留官方 HTTP/SSE 并隔离传输边界；延续管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 的外部 Provider 桌面候选。 |

<a id="module-8"></a>

## server/worker

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261030_1607_opencode-permission-profiles](agent_adapter/B_20261030_1607_opencode-permission-profiles.md) | B | OpenCode Full Access 与原生权限、生效状态接入 | leemine | agent_adapter, server/worker, channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/worker/dispatcher.py, jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/config/permissionProfiles.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx | 无独立 D：用户确认复用既有 reload/Runtime/权限下拉的最小接入方案，无独立子仓设计。 |

<a id="module-9"></a>

## 未分类

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [B_20261026_1602_code-multimodal-loading](jiuwenswarm/server/runtime/agent_adapter/B_20261026_1602_code-multimodal-loading.md) | B | 配置多模态模型后，Code 未按 Work 规则加载工具 | 待确认 | — | — | 待核实 |
| [B_20261026_1606_issue-5753-session-project-binding](jiuwenswarm/server/runtime/session/B_20261026_1606_issue-5753-session-project-binding.md) | B | Issue #5753：普通会话发送消息后混入全局项目目录 | 待确认 | — | — | 待核实 |
| [B_20261026_2035_gateway-contract-collection](tests/unit_tests/common/B_20261026_2035_gateway-contract-collection.md) | B | Gateway 拆包后协议契约测试无法收集 | 待确认 | — | — | 待核实 |
