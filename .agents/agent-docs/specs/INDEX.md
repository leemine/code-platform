---
title: 当前规约 S索引
author: leemine
author_email: leewanlong@gmail.com
generated: true
---

# 当前规约 S索引

由 sync_documents.py 从文档 frontmatter 自动生成；请修改源文档后重新生成，不手工维护。

共 5 篇文档，按模块分组；跨模块文档在各相关分组展示，总数按文档去重。

## 模块导航

| 模块 | 文档数 |
|---|---|
| [agent_adapter](#module-1) | 1 |
| [gateway](#module-2) | 2 |
| [gateway/extensions/data_sync](#module-3) | 1 |
| [gateway/services/data_sync](#module-4) | 1 |
| [jiuwenswarm/channels/web](#module-5) | 1 |
| [jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace](#module-6) | 1 |
| [jiuwenswarm/data_sync](#module-7) | 1 |
| [jiuwenswarm/server](#module-8) | 1 |
| [jiuwenswarm/server/control](#module-9) | 1 |
| [runtime](#module-10) | 1 |
| [server/front](#module-11) | 1 |
| [未分类](#module-12) | 1 |

<a id="module-1"></a>

## agent_adapter

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [S_02_external-adapter-boundary](jiuwenswarm/server/runtime/agent_adapter/S_02_external-adapter-boundary.md) | S | 外部 AgentAdapter 单 Agent 边界规约 | leemine | agent_adapter, runtime | jiuwenswarm/runtime/session/coordinator.py, jiuwenswarm/runtime/plan.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/control/config_service.py, jiuwenswarm/common/model_routing_registry.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/runtime/service.py, jiuwenswarm/server/runtime/agent_adapter/execution_input.py, jiuwenswarm/server/runtime/agent_adapter/equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py | — |

<a id="module-2"></a>

## gateway

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [S-02-code-workspace-entry](gateway/S_02_code-workspace-entry.md) | S | Code 工作区入口与目录操作 | leemine | gateway, jiuwenswarm/server, jiuwenswarm/channels/web | gateway/routing/workspace_locations.py, jiuwenswarm/server/runtime/gateway_adapter/project_workspace.py | — |
| [S_01_cloud-account-instance](gateway/S_01_cloud-account-instance.md) | S | 云账号与原实例链契约 | leemine | gateway, server/front | gateway/services/cloud_environments.py, gateway/services/cloud_instance_policy.py, gateway/auth/account_authenticator.py, gateway/extensions/agentos/agentos_router/router_client.py, gateway/common/security/service_auth.py | — |

<a id="module-3"></a>

## gateway/extensions/data_sync

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [S_03_data-sync-directory](gateway/S_03_data-sync-directory.md) | S | 显式项目目录同步契约 | leemine | gateway/extensions/data_sync, gateway/services/data_sync, jiuwenswarm/data_sync, jiuwenswarm/server/control, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace | gateway/extensions/data_sync/extension.py, gateway/services/data_sync/store.py, jiuwenswarm/data_sync/contract.py, jiuwenswarm/data_sync/connector.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/server/runtime/session/project_store.py, gateway/services/data_sync/cloud_source.py, jiuwenswarm/data_sync/cloud_export.py, gateway/services/cloud_environments.py, gateway/extensions/agentos/agentos_router/router_client.py, jiuwenswarm/server/control/repositories/project_repository.py, gateway/extensions/data_sync/ui_extension.py, gateway/services/data_sync/ui.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts | — |

<a id="module-4"></a>

## gateway/services/data_sync

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [S_03_data-sync-directory](gateway/S_03_data-sync-directory.md) | S | 显式项目目录同步契约 | leemine | gateway/extensions/data_sync, gateway/services/data_sync, jiuwenswarm/data_sync, jiuwenswarm/server/control, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace | gateway/extensions/data_sync/extension.py, gateway/services/data_sync/store.py, jiuwenswarm/data_sync/contract.py, jiuwenswarm/data_sync/connector.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/server/runtime/session/project_store.py, gateway/services/data_sync/cloud_source.py, jiuwenswarm/data_sync/cloud_export.py, gateway/services/cloud_environments.py, gateway/extensions/agentos/agentos_router/router_client.py, jiuwenswarm/server/control/repositories/project_repository.py, gateway/extensions/data_sync/ui_extension.py, gateway/services/data_sync/ui.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts | — |

<a id="module-5"></a>

## jiuwenswarm/channels/web

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [S-02-code-workspace-entry](gateway/S_02_code-workspace-entry.md) | S | Code 工作区入口与目录操作 | leemine | gateway, jiuwenswarm/server, jiuwenswarm/channels/web | gateway/routing/workspace_locations.py, jiuwenswarm/server/runtime/gateway_adapter/project_workspace.py | — |

<a id="module-6"></a>

## jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [S_03_data-sync-directory](gateway/S_03_data-sync-directory.md) | S | 显式项目目录同步契约 | leemine | gateway/extensions/data_sync, gateway/services/data_sync, jiuwenswarm/data_sync, jiuwenswarm/server/control, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace | gateway/extensions/data_sync/extension.py, gateway/services/data_sync/store.py, jiuwenswarm/data_sync/contract.py, jiuwenswarm/data_sync/connector.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/server/runtime/session/project_store.py, gateway/services/data_sync/cloud_source.py, jiuwenswarm/data_sync/cloud_export.py, gateway/services/cloud_environments.py, gateway/extensions/agentos/agentos_router/router_client.py, jiuwenswarm/server/control/repositories/project_repository.py, gateway/extensions/data_sync/ui_extension.py, gateway/services/data_sync/ui.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts | — |

<a id="module-7"></a>

## jiuwenswarm/data_sync

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [S_03_data-sync-directory](gateway/S_03_data-sync-directory.md) | S | 显式项目目录同步契约 | leemine | gateway/extensions/data_sync, gateway/services/data_sync, jiuwenswarm/data_sync, jiuwenswarm/server/control, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace | gateway/extensions/data_sync/extension.py, gateway/services/data_sync/store.py, jiuwenswarm/data_sync/contract.py, jiuwenswarm/data_sync/connector.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/server/runtime/session/project_store.py, gateway/services/data_sync/cloud_source.py, jiuwenswarm/data_sync/cloud_export.py, gateway/services/cloud_environments.py, gateway/extensions/agentos/agentos_router/router_client.py, jiuwenswarm/server/control/repositories/project_repository.py, gateway/extensions/data_sync/ui_extension.py, gateway/services/data_sync/ui.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts | — |

<a id="module-8"></a>

## jiuwenswarm/server

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [S-02-code-workspace-entry](gateway/S_02_code-workspace-entry.md) | S | Code 工作区入口与目录操作 | leemine | gateway, jiuwenswarm/server, jiuwenswarm/channels/web | gateway/routing/workspace_locations.py, jiuwenswarm/server/runtime/gateway_adapter/project_workspace.py | — |

<a id="module-9"></a>

## jiuwenswarm/server/control

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [S_03_data-sync-directory](gateway/S_03_data-sync-directory.md) | S | 显式项目目录同步契约 | leemine | gateway/extensions/data_sync, gateway/services/data_sync, jiuwenswarm/data_sync, jiuwenswarm/server/control, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace | gateway/extensions/data_sync/extension.py, gateway/services/data_sync/store.py, jiuwenswarm/data_sync/contract.py, jiuwenswarm/data_sync/connector.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/server/runtime/session/project_store.py, gateway/services/data_sync/cloud_source.py, jiuwenswarm/data_sync/cloud_export.py, gateway/services/cloud_environments.py, gateway/extensions/agentos/agentos_router/router_client.py, jiuwenswarm/server/control/repositories/project_repository.py, gateway/extensions/data_sync/ui_extension.py, gateway/services/data_sync/ui.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts | — |

<a id="module-10"></a>

## runtime

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [S_02_external-adapter-boundary](jiuwenswarm/server/runtime/agent_adapter/S_02_external-adapter-boundary.md) | S | 外部 AgentAdapter 单 Agent 边界规约 | leemine | agent_adapter, runtime | jiuwenswarm/runtime/session/coordinator.py, jiuwenswarm/runtime/plan.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/control/config_service.py, jiuwenswarm/common/model_routing_registry.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/runtime/service.py, jiuwenswarm/server/runtime/agent_adapter/execution_input.py, jiuwenswarm/server/runtime/agent_adapter/equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py | — |

<a id="module-11"></a>

## server/front

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [S_01_cloud-account-instance](gateway/S_01_cloud-account-instance.md) | S | 云账号与原实例链契约 | leemine | gateway, server/front | gateway/services/cloud_environments.py, gateway/services/cloud_instance_policy.py, gateway/auth/account_authenticator.py, gateway/extensions/agentos/agentos_router/router_client.py, gateway/common/security/service_auth.py | — |

<a id="module-12"></a>

## 未分类

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [S_01_multimodal-tool-loading](jiuwenswarm/server/runtime/agent_adapter/S_01_multimodal-tool-loading.md) | S | Work / Code 多模态工具加载契约 | 待确认 | — | — | — |
