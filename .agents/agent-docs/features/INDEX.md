---
title: 实施与决策 F索引
author: leemine
author_email: leewanlong@gmail.com
generated: true
---

# 实施与决策 F索引

由 sync_documents.py 从文档 frontmatter 自动生成；请修改源文档后重新生成，不手工维护。

共 14 篇文档，按模块分组；跨模块文档在各相关分组展示，总数按文档去重。

## 模块导航

| 模块 | 文档数 |
|---|---|
| [.github/workflows](#module-1) | 1 |
| [agent_adapter](#module-2) | 4 |
| [channels/web](#module-3) | 1 |
| [deploy/cloud-workspace](#module-4) | 1 |
| [deploy/tls](#module-5) | 1 |
| [desktop](#module-6) | 1 |
| [gateway](#module-7) | 3 |
| [gateway/channel_manager/web](#module-8) | 1 |
| [gateway/common](#module-9) | 1 |
| [gateway/extensions/data_sync](#module-10) | 3 |
| [gateway/services](#module-11) | 2 |
| [gateway/services/data_sync](#module-12) | 1 |
| [jiuwenswarm/channels/web](#module-13) | 2 |
| [jiuwenswarm/channels/web/frontend](#module-14) | 4 |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel](#module-15) | 1 |
| [jiuwenswarm/common](#module-16) | 2 |
| [jiuwenswarm/data_sync](#module-17) | 2 |
| [jiuwenswarm/server](#module-18) | 2 |
| [jiuwenswarm/server/runtime/agent_adapter](#module-19) | 4 |
| [jiuwenswarm/server/runtime/session](#module-20) | 2 |
| [scripts](#module-21) | 1 |
| [server/front](#module-22) | 1 |

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

## channels/web

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261109_2205_cloud-original-instance-chain](F_20261109_2205_cloud-original-instance-chain.md) | F | 云账号提炼与原实例链收敛 | leemine | gateway, server/front, deploy/cloud-workspace, channels/web | deploy/cloud-workspace/runtime_security.py, deploy/cloud-workspace/codex_sandbox_probe.py, tests/unit_tests/cloud_workspace/test_runtime_security.py, tests/unit_tests/cloud_workspace/test_codex_sandbox_probe.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudWorkspaceGate.tsx, jiuwenswarm/channels/web/frontend/src/features/auth/LoginPage.tsx, jiuwenswarm/channels/web/frontend/src/services/organizationCredentialEvents.ts, jiuwenswarm/channels/web/frontend/tests/cloudWorkspace.test.mjs, deploy/cloud-workspace/CANDIDATE_HANDOFF.md, deploy/cloud-workspace/physical_resources.py, gateway/services/resource_reconciler.py, tests/unit_tests/cloud_workspace/test_physical_resources.py, deploy/cloud-workspace/LOG_BOUNDARY_CONTRACT.md, deploy/cloud-workspace/docker_log_boundary.py, tests/unit_tests/cloud_workspace/test_docker_log_boundary.py, gateway/extensions/cloud_workspace/config.py, tests/unit_tests/cloud_workspace/test_cloud_workspace.py, gateway/channel_manager/web/web_channel_app.py, gateway/channel_manager/web/web_connect.py, gateway/extensions/application_host.py, deploy/cloud-workspace/Dockerfile, deploy/cloud-workspace/Dockerfile.yuanrong, gateway/services/cloud_environments.py, gateway/services/cloud_instance_policy.py, gateway/services/cloud_workspace_assembly.py, gateway/auth/account_http.py, gateway/auth/account_authenticator.py, gateway/auth/request_scope.py, gateway/extensions/agentos/agentos_router/router_client.py, tests/unit_tests/cloud_workspace/test_integration_boundaries.py, tests/unit_tests/server/test_gateway_adapter.py | 无独立 D：依据管理仓 PLATFORM_CANDIDATE_DISPOSITION_20261109（M01-M12/C01-C22）及用户本会话授权；无独立D编号。 |

<a id="module-4"></a>

## deploy/cloud-workspace

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261109_2205_cloud-original-instance-chain](F_20261109_2205_cloud-original-instance-chain.md) | F | 云账号提炼与原实例链收敛 | leemine | gateway, server/front, deploy/cloud-workspace, channels/web | deploy/cloud-workspace/runtime_security.py, deploy/cloud-workspace/codex_sandbox_probe.py, tests/unit_tests/cloud_workspace/test_runtime_security.py, tests/unit_tests/cloud_workspace/test_codex_sandbox_probe.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudWorkspaceGate.tsx, jiuwenswarm/channels/web/frontend/src/features/auth/LoginPage.tsx, jiuwenswarm/channels/web/frontend/src/services/organizationCredentialEvents.ts, jiuwenswarm/channels/web/frontend/tests/cloudWorkspace.test.mjs, deploy/cloud-workspace/CANDIDATE_HANDOFF.md, deploy/cloud-workspace/physical_resources.py, gateway/services/resource_reconciler.py, tests/unit_tests/cloud_workspace/test_physical_resources.py, deploy/cloud-workspace/LOG_BOUNDARY_CONTRACT.md, deploy/cloud-workspace/docker_log_boundary.py, tests/unit_tests/cloud_workspace/test_docker_log_boundary.py, gateway/extensions/cloud_workspace/config.py, tests/unit_tests/cloud_workspace/test_cloud_workspace.py, gateway/channel_manager/web/web_channel_app.py, gateway/channel_manager/web/web_connect.py, gateway/extensions/application_host.py, deploy/cloud-workspace/Dockerfile, deploy/cloud-workspace/Dockerfile.yuanrong, gateway/services/cloud_environments.py, gateway/services/cloud_instance_policy.py, gateway/services/cloud_workspace_assembly.py, gateway/auth/account_http.py, gateway/auth/account_authenticator.py, gateway/auth/request_scope.py, gateway/extensions/agentos/agentos_router/router_client.py, tests/unit_tests/cloud_workspace/test_integration_boundaries.py, tests/unit_tests/server/test_gateway_adapter.py | 无独立 D：依据管理仓 PLATFORM_CANDIDATE_DISPOSITION_20261109（M01-M12/C01-C22）及用户本会话授权；无独立D编号。 |

<a id="module-5"></a>

## deploy/tls

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261114_2029_certificate-lifecycle](F_20261114_2029_certificate-lifecycle.md) | F | 部署证书自动续期、加载确认与到期告警 | leemine | deploy/tls | deploy/tls/certificate_lifecycle.py, deploy/tls/Caddyfile.internal.example, deploy/tls/Caddyfile.public.example, deploy/tls/alerts.yml, deploy/tls/systemd/code-platform-caddy-internal.service, deploy/tls/systemd/code-platform-tls@.service, deploy/tls/systemd/code-platform-tls@.timer, tests/unit_tests/cloud_workspace/test_certificate_lifecycle.py | 无独立 D：用户明确要求补齐现有部署证书生命周期，复用标准Caddy签发与原实时身份契约，无新增产品执行协议。 |

<a id="module-6"></a>

## desktop

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261030_1939_external-desktop-builds](F_20261030_1939_external-desktop-builds.md) | F | 可选 Native 与外部 Provider 桌面测试包 | leemine | agent_adapter, desktop, gateway | pyproject.toml, uv.lock, scripts/jiuwenswarm.spec, scripts/build-electron-linux.sh, scripts/assemble-electron-linux.py, scripts/verify_external_bundle.py, jiuwenswarm/common/native_integration.py, gateway/extensions/registry.py, .github/workflows/windows-external.yml, .github/scripts/transfer-release-assets.py, .github/workflows/stable.yml, tests/unit_tests/test_release_asset_transfer.py | 无独立 D：用户确认两种安装组合和先 Linux 后 Windows/macOS 的实施范围；管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 第24节及 EXTERNAL_DESKTOP_BUILD_20261030 记录来源与验证。 |

<a id="module-7"></a>

## gateway

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F-20261112-1320-platform-code-workspace](F_20261112_1320_platform-code-workspace.md) | F | P1S-01 Code 三段式工作区入口 | leemine | gateway, jiuwenswarm/channels/web, jiuwenswarm/server | gateway/routing/workspace_locations.py, gateway/channel_manager/web/app_web_handlers.py, jiuwenswarm/server/runtime/gateway_adapter/project_workspace.py, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/CodeWorkspaceControls.tsx | code-projects:D-20261112-1120-platform-workspace-sync（非本仓或待定位） |
| [F_20261030_1939_external-desktop-builds](F_20261030_1939_external-desktop-builds.md) | F | 可选 Native 与外部 Provider 桌面测试包 | leemine | agent_adapter, desktop, gateway | pyproject.toml, uv.lock, scripts/jiuwenswarm.spec, scripts/build-electron-linux.sh, scripts/assemble-electron-linux.py, scripts/verify_external_bundle.py, jiuwenswarm/common/native_integration.py, gateway/extensions/registry.py, .github/workflows/windows-external.yml, .github/scripts/transfer-release-assets.py, .github/workflows/stable.yml, tests/unit_tests/test_release_asset_transfer.py | 无独立 D：用户确认两种安装组合和先 Linux 后 Windows/macOS 的实施范围；管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 第24节及 EXTERNAL_DESKTOP_BUILD_20261030 记录来源与验证。 |
| [F_20261109_2205_cloud-original-instance-chain](F_20261109_2205_cloud-original-instance-chain.md) | F | 云账号提炼与原实例链收敛 | leemine | gateway, server/front, deploy/cloud-workspace, channels/web | deploy/cloud-workspace/runtime_security.py, deploy/cloud-workspace/codex_sandbox_probe.py, tests/unit_tests/cloud_workspace/test_runtime_security.py, tests/unit_tests/cloud_workspace/test_codex_sandbox_probe.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudWorkspaceGate.tsx, jiuwenswarm/channels/web/frontend/src/features/auth/LoginPage.tsx, jiuwenswarm/channels/web/frontend/src/services/organizationCredentialEvents.ts, jiuwenswarm/channels/web/frontend/tests/cloudWorkspace.test.mjs, deploy/cloud-workspace/CANDIDATE_HANDOFF.md, deploy/cloud-workspace/physical_resources.py, gateway/services/resource_reconciler.py, tests/unit_tests/cloud_workspace/test_physical_resources.py, deploy/cloud-workspace/LOG_BOUNDARY_CONTRACT.md, deploy/cloud-workspace/docker_log_boundary.py, tests/unit_tests/cloud_workspace/test_docker_log_boundary.py, gateway/extensions/cloud_workspace/config.py, tests/unit_tests/cloud_workspace/test_cloud_workspace.py, gateway/channel_manager/web/web_channel_app.py, gateway/channel_manager/web/web_connect.py, gateway/extensions/application_host.py, deploy/cloud-workspace/Dockerfile, deploy/cloud-workspace/Dockerfile.yuanrong, gateway/services/cloud_environments.py, gateway/services/cloud_instance_policy.py, gateway/services/cloud_workspace_assembly.py, gateway/auth/account_http.py, gateway/auth/account_authenticator.py, gateway/auth/request_scope.py, gateway/extensions/agentos/agentos_router/router_client.py, tests/unit_tests/cloud_workspace/test_integration_boundaries.py, tests/unit_tests/server/test_gateway_adapter.py | 无独立 D：依据管理仓 PLATFORM_CANDIDATE_DISPOSITION_20261109（M01-M12/C01-C22）及用户本会话授权；无独立D编号。 |

<a id="module-8"></a>

## gateway/channel_manager/web

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F-20261112-1545-platform-directory-sync](F_20261112_1545_platform-directory-sync.md) | F | P1S-02 显式项目目录同步首轮候选 | leemine | gateway/extensions/data_sync, gateway/services/data_sync, jiuwenswarm/data_sync, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend/src/components/ChatPanel, gateway/channel_manager/web | gateway/extensions/data_sync/extension.py, gateway/services/data_sync/store.py, jiuwenswarm/data_sync/connector.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/data_sync/__main__.py, jiuwenswarm/server/runtime/session/project_store.py, tests/unit_tests/data_sync, tests/unit_tests/cloud_workspace/test_data_sync_cloud_role.py, gateway/services/data_sync/cloud_source.py, jiuwenswarm/data_sync/cloud_export.py, gateway/services/cloud_environments.py, gateway/extensions/agentos/agentos_router/router_client.py, gateway/common/security/service_auth.py, jiuwenswarm/server/runtime/gateway_adapter/project_adapter.py, .github/workflows/stable.yml, gateway/services/data_sync/ui.py, gateway/extensions/data_sync/ui_extension.py, gateway/auth/account_authenticator.py, gateway/extensions/auth/common.py, gateway/channel_manager/web/web_connect.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudWorkspaceGate.tsx, jiuwenswarm/channels/web/frontend/tests/directorySyncDialog.test.mjs, jiuwenswarm/server/control/repositories/project_repository.py | code-projects:D-20261112-1120-platform-workspace-sync（非本仓或待定位） |

<a id="module-9"></a>

## gateway/common

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261031_1714_claude-main-agent-and-model-settings](F_20261031_1714_claude-main-agent-and-model-settings.md) | F | Claude 主 Agent 与无 Core 模型配置发布收尾 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, gateway/common, jiuwenswarm/channels/web/frontend, jiuwenswarm/server | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/external_adapter_factories.py, gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, pyproject.toml, uv.lock, .github/workflows/stable.yml | 无独立 D：用户已确认原AgentAdapter直接接官方SDK的实施方向，并授权任务1～2发布收尾；本次未另建独立设计。 |

<a id="module-10"></a>

## gateway/extensions/data_sync

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F-20261112-1545-platform-directory-sync](F_20261112_1545_platform-directory-sync.md) | F | P1S-02 显式项目目录同步首轮候选 | leemine | gateway/extensions/data_sync, gateway/services/data_sync, jiuwenswarm/data_sync, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend/src/components/ChatPanel, gateway/channel_manager/web | gateway/extensions/data_sync/extension.py, gateway/services/data_sync/store.py, jiuwenswarm/data_sync/connector.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/data_sync/__main__.py, jiuwenswarm/server/runtime/session/project_store.py, tests/unit_tests/data_sync, tests/unit_tests/cloud_workspace/test_data_sync_cloud_role.py, gateway/services/data_sync/cloud_source.py, jiuwenswarm/data_sync/cloud_export.py, gateway/services/cloud_environments.py, gateway/extensions/agentos/agentos_router/router_client.py, gateway/common/security/service_auth.py, jiuwenswarm/server/runtime/gateway_adapter/project_adapter.py, .github/workflows/stable.yml, gateway/services/data_sync/ui.py, gateway/extensions/data_sync/ui_extension.py, gateway/auth/account_authenticator.py, gateway/extensions/auth/common.py, gateway/channel_manager/web/web_connect.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudWorkspaceGate.tsx, jiuwenswarm/channels/web/frontend/tests/directorySyncDialog.test.mjs, jiuwenswarm/server/control/repositories/project_repository.py | code-projects:D-20261112-1120-platform-workspace-sync（非本仓或待定位） |
| [F_20261113_1044_local-cloud-inline](F_20261113_1044_local-cloud-inline.md) | F | Local/Cloud 即时选择与本地同页云目录访问 | leemine | gateway/services, gateway/extensions/data_sync, jiuwenswarm/data_sync, jiuwenswarm/channels/web/frontend | gateway/auth/account_transport.py, jiuwenswarm/channels/web/frontend/src/features/auth/AccountLoginForm.tsx, jiuwenswarm/channels/web/frontend/src/features/auth/LoginPage.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/AccountControl.tsx, gateway/services/cloud_workspace_client.py, gateway/services/data_sync/ui.py, gateway/extensions/data_sync/ui_extension.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/CodeWorkspaceControls.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts | code-projects:D-20261112-1120-platform-workspace-sync（非本仓或待定位） |
| [F_20261113_2015_local-cloud-execution](F_20261113_2015_local-cloud-execution.md) | F | 本地页面云会话执行与目录请求期限 | leemine | gateway/services, gateway/extensions/data_sync, jiuwenswarm/channels/web | gateway/services/cloud_execution_bridge.py, gateway/services/cloud_resource_address.py, gateway/extensions/data_sync/ui_extension.py, jiuwenswarm/channels/web/app_web.py, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/useCloudCatalog.ts | 无独立 D：用户明确授权定位旧目录失败并沿用三段式UI接通本地页面云会话，验证后提交CI和合入；本记录保存实施事实，当前契约归S_02_code-workspace-entry。 |

<a id="module-11"></a>

## gateway/services

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261113_1044_local-cloud-inline](F_20261113_1044_local-cloud-inline.md) | F | Local/Cloud 即时选择与本地同页云目录访问 | leemine | gateway/services, gateway/extensions/data_sync, jiuwenswarm/data_sync, jiuwenswarm/channels/web/frontend | gateway/auth/account_transport.py, jiuwenswarm/channels/web/frontend/src/features/auth/AccountLoginForm.tsx, jiuwenswarm/channels/web/frontend/src/features/auth/LoginPage.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/AccountControl.tsx, gateway/services/cloud_workspace_client.py, gateway/services/data_sync/ui.py, gateway/extensions/data_sync/ui_extension.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/CodeWorkspaceControls.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts | code-projects:D-20261112-1120-platform-workspace-sync（非本仓或待定位） |
| [F_20261113_2015_local-cloud-execution](F_20261113_2015_local-cloud-execution.md) | F | 本地页面云会话执行与目录请求期限 | leemine | gateway/services, gateway/extensions/data_sync, jiuwenswarm/channels/web | gateway/services/cloud_execution_bridge.py, gateway/services/cloud_resource_address.py, gateway/extensions/data_sync/ui_extension.py, jiuwenswarm/channels/web/app_web.py, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/useCloudCatalog.ts | 无独立 D：用户明确授权定位旧目录失败并沿用三段式UI接通本地页面云会话，验证后提交CI和合入；本记录保存实施事实，当前契约归S_02_code-workspace-entry。 |

<a id="module-12"></a>

## gateway/services/data_sync

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F-20261112-1545-platform-directory-sync](F_20261112_1545_platform-directory-sync.md) | F | P1S-02 显式项目目录同步首轮候选 | leemine | gateway/extensions/data_sync, gateway/services/data_sync, jiuwenswarm/data_sync, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend/src/components/ChatPanel, gateway/channel_manager/web | gateway/extensions/data_sync/extension.py, gateway/services/data_sync/store.py, jiuwenswarm/data_sync/connector.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/data_sync/__main__.py, jiuwenswarm/server/runtime/session/project_store.py, tests/unit_tests/data_sync, tests/unit_tests/cloud_workspace/test_data_sync_cloud_role.py, gateway/services/data_sync/cloud_source.py, jiuwenswarm/data_sync/cloud_export.py, gateway/services/cloud_environments.py, gateway/extensions/agentos/agentos_router/router_client.py, gateway/common/security/service_auth.py, jiuwenswarm/server/runtime/gateway_adapter/project_adapter.py, .github/workflows/stable.yml, gateway/services/data_sync/ui.py, gateway/extensions/data_sync/ui_extension.py, gateway/auth/account_authenticator.py, gateway/extensions/auth/common.py, gateway/channel_manager/web/web_connect.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudWorkspaceGate.tsx, jiuwenswarm/channels/web/frontend/tests/directorySyncDialog.test.mjs, jiuwenswarm/server/control/repositories/project_repository.py | code-projects:D-20261112-1120-platform-workspace-sync（非本仓或待定位） |

<a id="module-13"></a>

## jiuwenswarm/channels/web

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F-20261112-1320-platform-code-workspace](F_20261112_1320_platform-code-workspace.md) | F | P1S-01 Code 三段式工作区入口 | leemine | gateway, jiuwenswarm/channels/web, jiuwenswarm/server | gateway/routing/workspace_locations.py, gateway/channel_manager/web/app_web_handlers.py, jiuwenswarm/server/runtime/gateway_adapter/project_workspace.py, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/CodeWorkspaceControls.tsx | code-projects:D-20261112-1120-platform-workspace-sync（非本仓或待定位） |
| [F_20261113_2015_local-cloud-execution](F_20261113_2015_local-cloud-execution.md) | F | 本地页面云会话执行与目录请求期限 | leemine | gateway/services, gateway/extensions/data_sync, jiuwenswarm/channels/web | gateway/services/cloud_execution_bridge.py, gateway/services/cloud_resource_address.py, gateway/extensions/data_sync/ui_extension.py, jiuwenswarm/channels/web/app_web.py, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/useCloudCatalog.ts | 无独立 D：用户明确授权定位旧目录失败并沿用三段式UI接通本地页面云会话，验证后提交CI和合入；本记录保存实施事实，当前契约归S_02_code-workspace-entry。 |

<a id="module-14"></a>

## jiuwenswarm/channels/web/frontend

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261031_1714_claude-main-agent-and-model-settings](F_20261031_1714_claude-main-agent-and-model-settings.md) | F | Claude 主 Agent 与无 Core 模型配置发布收尾 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, gateway/common, jiuwenswarm/channels/web/frontend, jiuwenswarm/server | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/external_adapter_factories.py, gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, pyproject.toml, uv.lock, .github/workflows/stable.yml | 无独立 D：用户已确认原AgentAdapter直接接官方SDK的实施方向，并授权任务1～2发布收尾；本次未另建独立设计。 |
| [F_20261104_1230_codex-native-usage-observation](F_20261104_1230_codex-native-usage-observation.md) | F | Provider 原生用量只读观测（Codex、Claude、OpenCode） | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex_usage.py, jiuwenswarm/server/runtime/session/session_history.py, jiuwenswarm/channels/web/frontend/src/types/sessionTokenUsage.ts, jiuwenswarm/channels/web/frontend/src/types/message.ts, jiuwenswarm/channels/web/frontend/src/features/historyRestore.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.css, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude_usage.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_usage.py | 无独立 D：用户确认管理仓 OBS-01 只读方案后授权先做 Codex 原生事件试点；无独立 D 文档，不扩展到压缩或发布；同日用户授权将只读方案续接 Claude/OpenCode。 |
| [F_20261104_1430_provider-beta5-release](F_20261104_1430_provider-beta5-release.md) | F | Provider beta5 发布收尾与验证边界 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/channels/web/frontend, scripts, .github/workflows | .github/workflows/stable.yml, .github/workflows/windows-external.yml, scripts/build_config.py, pyproject.toml, uv.lock, tests/unit_tests/agentserver/test_opencode_equipment_encoding.py | 无独立 D：用户在输出保护、P1 和 OBS-01 之后明确授权执行提交合并、三平台打包与发布任务 2～6；任务 1 的 Claude 真实验收独立保留。 |
| [F_20261113_1044_local-cloud-inline](F_20261113_1044_local-cloud-inline.md) | F | Local/Cloud 即时选择与本地同页云目录访问 | leemine | gateway/services, gateway/extensions/data_sync, jiuwenswarm/data_sync, jiuwenswarm/channels/web/frontend | gateway/auth/account_transport.py, jiuwenswarm/channels/web/frontend/src/features/auth/AccountLoginForm.tsx, jiuwenswarm/channels/web/frontend/src/features/auth/LoginPage.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/AccountControl.tsx, gateway/services/cloud_workspace_client.py, gateway/services/data_sync/ui.py, gateway/extensions/data_sync/ui_extension.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/CodeWorkspaceControls.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts | code-projects:D-20261112-1120-platform-workspace-sync（非本仓或待定位） |

<a id="module-15"></a>

## jiuwenswarm/channels/web/frontend/src/components/ChatPanel

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F-20261112-1545-platform-directory-sync](F_20261112_1545_platform-directory-sync.md) | F | P1S-02 显式项目目录同步首轮候选 | leemine | gateway/extensions/data_sync, gateway/services/data_sync, jiuwenswarm/data_sync, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend/src/components/ChatPanel, gateway/channel_manager/web | gateway/extensions/data_sync/extension.py, gateway/services/data_sync/store.py, jiuwenswarm/data_sync/connector.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/data_sync/__main__.py, jiuwenswarm/server/runtime/session/project_store.py, tests/unit_tests/data_sync, tests/unit_tests/cloud_workspace/test_data_sync_cloud_role.py, gateway/services/data_sync/cloud_source.py, jiuwenswarm/data_sync/cloud_export.py, gateway/services/cloud_environments.py, gateway/extensions/agentos/agentos_router/router_client.py, gateway/common/security/service_auth.py, jiuwenswarm/server/runtime/gateway_adapter/project_adapter.py, .github/workflows/stable.yml, gateway/services/data_sync/ui.py, gateway/extensions/data_sync/ui_extension.py, gateway/auth/account_authenticator.py, gateway/extensions/auth/common.py, gateway/channel_manager/web/web_connect.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudWorkspaceGate.tsx, jiuwenswarm/channels/web/frontend/tests/directorySyncDialog.test.mjs, jiuwenswarm/server/control/repositories/project_repository.py | code-projects:D-20261112-1120-platform-workspace-sync（非本仓或待定位） |

<a id="module-16"></a>

## jiuwenswarm/common

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261031_1714_claude-main-agent-and-model-settings](F_20261031_1714_claude-main-agent-and-model-settings.md) | F | Claude 主 Agent 与无 Core 模型配置发布收尾 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, gateway/common, jiuwenswarm/channels/web/frontend, jiuwenswarm/server | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/external_adapter_factories.py, gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, pyproject.toml, uv.lock, .github/workflows/stable.yml | 无独立 D：用户已确认原AgentAdapter直接接官方SDK的实施方向，并授权任务1～2发布收尾；本次未另建独立设计。 |
| [F_20261104_2128_codex-session-mcp](F_20261104_2128_codex-session-mcp.md) | F | Codex 会话显式选择 Streamable HTTP MCP | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common | jiuwenswarm/common/external_adapter_factories.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex_mcp.py | 无独立 D：用户批准管理仓 PROVIDER_PLUGIN_DEPENDENCY_AUDIT_20261031 中 Codex 会话 MCP 方案，宿主只声明能力。 |

<a id="module-17"></a>

## jiuwenswarm/data_sync

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F-20261112-1545-platform-directory-sync](F_20261112_1545_platform-directory-sync.md) | F | P1S-02 显式项目目录同步首轮候选 | leemine | gateway/extensions/data_sync, gateway/services/data_sync, jiuwenswarm/data_sync, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend/src/components/ChatPanel, gateway/channel_manager/web | gateway/extensions/data_sync/extension.py, gateway/services/data_sync/store.py, jiuwenswarm/data_sync/connector.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/data_sync/__main__.py, jiuwenswarm/server/runtime/session/project_store.py, tests/unit_tests/data_sync, tests/unit_tests/cloud_workspace/test_data_sync_cloud_role.py, gateway/services/data_sync/cloud_source.py, jiuwenswarm/data_sync/cloud_export.py, gateway/services/cloud_environments.py, gateway/extensions/agentos/agentos_router/router_client.py, gateway/common/security/service_auth.py, jiuwenswarm/server/runtime/gateway_adapter/project_adapter.py, .github/workflows/stable.yml, gateway/services/data_sync/ui.py, gateway/extensions/data_sync/ui_extension.py, gateway/auth/account_authenticator.py, gateway/extensions/auth/common.py, gateway/channel_manager/web/web_connect.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudWorkspaceGate.tsx, jiuwenswarm/channels/web/frontend/tests/directorySyncDialog.test.mjs, jiuwenswarm/server/control/repositories/project_repository.py | code-projects:D-20261112-1120-platform-workspace-sync（非本仓或待定位） |
| [F_20261113_1044_local-cloud-inline](F_20261113_1044_local-cloud-inline.md) | F | Local/Cloud 即时选择与本地同页云目录访问 | leemine | gateway/services, gateway/extensions/data_sync, jiuwenswarm/data_sync, jiuwenswarm/channels/web/frontend | gateway/auth/account_transport.py, jiuwenswarm/channels/web/frontend/src/features/auth/AccountLoginForm.tsx, jiuwenswarm/channels/web/frontend/src/features/auth/LoginPage.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/AccountControl.tsx, gateway/services/cloud_workspace_client.py, gateway/services/data_sync/ui.py, gateway/extensions/data_sync/ui_extension.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/CodeWorkspaceControls.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts | code-projects:D-20261112-1120-platform-workspace-sync（非本仓或待定位） |

<a id="module-18"></a>

## jiuwenswarm/server

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F-20261112-1320-platform-code-workspace](F_20261112_1320_platform-code-workspace.md) | F | P1S-01 Code 三段式工作区入口 | leemine | gateway, jiuwenswarm/channels/web, jiuwenswarm/server | gateway/routing/workspace_locations.py, gateway/channel_manager/web/app_web_handlers.py, jiuwenswarm/server/runtime/gateway_adapter/project_workspace.py, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/CodeWorkspaceControls.tsx | code-projects:D-20261112-1120-platform-workspace-sync（非本仓或待定位） |
| [F_20261031_1714_claude-main-agent-and-model-settings](F_20261031_1714_claude-main-agent-and-model-settings.md) | F | Claude 主 Agent 与无 Core 模型配置发布收尾 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, gateway/common, jiuwenswarm/channels/web/frontend, jiuwenswarm/server | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/external_adapter_factories.py, gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, pyproject.toml, uv.lock, .github/workflows/stable.yml | 无独立 D：用户已确认原AgentAdapter直接接官方SDK的实施方向，并授权任务1～2发布收尾；本次未另建独立设计。 |

<a id="module-19"></a>

## jiuwenswarm/server/runtime/agent_adapter

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261031_1714_claude-main-agent-and-model-settings](F_20261031_1714_claude-main-agent-and-model-settings.md) | F | Claude 主 Agent 与无 Core 模型配置发布收尾 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common, gateway/common, jiuwenswarm/channels/web/frontend, jiuwenswarm/server | jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/external_adapter_factories.py, gateway/common/model_vendor_registry.py, jiuwenswarm/common/native_integration.py, jiuwenswarm/common/reasoning_config.py, jiuwenswarm/common/config_panel/models_handlers.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, pyproject.toml, uv.lock, .github/workflows/stable.yml | 无独立 D：用户已确认原AgentAdapter直接接官方SDK的实施方向，并授权任务1～2发布收尾；本次未另建独立设计。 |
| [F_20261104_1230_codex-native-usage-observation](F_20261104_1230_codex-native-usage-observation.md) | F | Provider 原生用量只读观测（Codex、Claude、OpenCode） | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex_usage.py, jiuwenswarm/server/runtime/session/session_history.py, jiuwenswarm/channels/web/frontend/src/types/sessionTokenUsage.ts, jiuwenswarm/channels/web/frontend/src/types/message.ts, jiuwenswarm/channels/web/frontend/src/features/historyRestore.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.css, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude_usage.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_usage.py | 无独立 D：用户确认管理仓 OBS-01 只读方案后授权先做 Codex 原生事件试点；无独立 D 文档，不扩展到压缩或发布；同日用户授权将只读方案续接 Claude/OpenCode。 |
| [F_20261104_1430_provider-beta5-release](F_20261104_1430_provider-beta5-release.md) | F | Provider beta5 发布收尾与验证边界 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/channels/web/frontend, scripts, .github/workflows | .github/workflows/stable.yml, .github/workflows/windows-external.yml, scripts/build_config.py, pyproject.toml, uv.lock, tests/unit_tests/agentserver/test_opencode_equipment_encoding.py | 无独立 D：用户在输出保护、P1 和 OBS-01 之后明确授权执行提交合并、三平台打包与发布任务 2～6；任务 1 的 Claude 真实验收独立保留。 |
| [F_20261104_2128_codex-session-mcp](F_20261104_2128_codex-session-mcp.md) | F | Codex 会话显式选择 Streamable HTTP MCP | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common | jiuwenswarm/common/external_adapter_factories.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex_mcp.py | 无独立 D：用户批准管理仓 PROVIDER_PLUGIN_DEPENDENCY_AUDIT_20261031 中 Codex 会话 MCP 方案，宿主只声明能力。 |

<a id="module-20"></a>

## jiuwenswarm/server/runtime/session

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F-20261112-1545-platform-directory-sync](F_20261112_1545_platform-directory-sync.md) | F | P1S-02 显式项目目录同步首轮候选 | leemine | gateway/extensions/data_sync, gateway/services/data_sync, jiuwenswarm/data_sync, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend/src/components/ChatPanel, gateway/channel_manager/web | gateway/extensions/data_sync/extension.py, gateway/services/data_sync/store.py, jiuwenswarm/data_sync/connector.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/data_sync/__main__.py, jiuwenswarm/server/runtime/session/project_store.py, tests/unit_tests/data_sync, tests/unit_tests/cloud_workspace/test_data_sync_cloud_role.py, gateway/services/data_sync/cloud_source.py, jiuwenswarm/data_sync/cloud_export.py, gateway/services/cloud_environments.py, gateway/extensions/agentos/agentos_router/router_client.py, gateway/common/security/service_auth.py, jiuwenswarm/server/runtime/gateway_adapter/project_adapter.py, .github/workflows/stable.yml, gateway/services/data_sync/ui.py, gateway/extensions/data_sync/ui_extension.py, gateway/auth/account_authenticator.py, gateway/extensions/auth/common.py, gateway/channel_manager/web/web_connect.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudWorkspaceGate.tsx, jiuwenswarm/channels/web/frontend/tests/directorySyncDialog.test.mjs, jiuwenswarm/server/control/repositories/project_repository.py | code-projects:D-20261112-1120-platform-workspace-sync（非本仓或待定位） |
| [F_20261104_1230_codex-native-usage-observation](F_20261104_1230_codex-native-usage-observation.md) | F | Provider 原生用量只读观测（Codex、Claude、OpenCode） | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend | jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex_usage.py, jiuwenswarm/server/runtime/session/session_history.py, jiuwenswarm/channels/web/frontend/src/types/sessionTokenUsage.ts, jiuwenswarm/channels/web/frontend/src/types/message.ts, jiuwenswarm/channels/web/frontend/src/features/historyRestore.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.css, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude_usage.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_usage.py | 无独立 D：用户确认管理仓 OBS-01 只读方案后授权先做 Codex 原生事件试点；无独立 D 文档，不扩展到压缩或发布；同日用户授权将只读方案续接 Claude/OpenCode。 |

<a id="module-21"></a>

## scripts

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261104_1430_provider-beta5-release](F_20261104_1430_provider-beta5-release.md) | F | Provider beta5 发布收尾与验证边界 | leemine | jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/channels/web/frontend, scripts, .github/workflows | .github/workflows/stable.yml, .github/workflows/windows-external.yml, scripts/build_config.py, pyproject.toml, uv.lock, tests/unit_tests/agentserver/test_opencode_equipment_encoding.py | 无独立 D：用户在输出保护、P1 和 OBS-01 之后明确授权执行提交合并、三平台打包与发布任务 2～6；任务 1 的 Claude 真实验收独立保留。 |

<a id="module-22"></a>

## server/front

| ID / 文档 | 类型 | 标题 | 作者 | 模块 | 代码文件 | 关联 D |
|---|---|---|---|---|---|---|
| [F_20261109_2205_cloud-original-instance-chain](F_20261109_2205_cloud-original-instance-chain.md) | F | 云账号提炼与原实例链收敛 | leemine | gateway, server/front, deploy/cloud-workspace, channels/web | deploy/cloud-workspace/runtime_security.py, deploy/cloud-workspace/codex_sandbox_probe.py, tests/unit_tests/cloud_workspace/test_runtime_security.py, tests/unit_tests/cloud_workspace/test_codex_sandbox_probe.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudWorkspaceGate.tsx, jiuwenswarm/channels/web/frontend/src/features/auth/LoginPage.tsx, jiuwenswarm/channels/web/frontend/src/services/organizationCredentialEvents.ts, jiuwenswarm/channels/web/frontend/tests/cloudWorkspace.test.mjs, deploy/cloud-workspace/CANDIDATE_HANDOFF.md, deploy/cloud-workspace/physical_resources.py, gateway/services/resource_reconciler.py, tests/unit_tests/cloud_workspace/test_physical_resources.py, deploy/cloud-workspace/LOG_BOUNDARY_CONTRACT.md, deploy/cloud-workspace/docker_log_boundary.py, tests/unit_tests/cloud_workspace/test_docker_log_boundary.py, gateway/extensions/cloud_workspace/config.py, tests/unit_tests/cloud_workspace/test_cloud_workspace.py, gateway/channel_manager/web/web_channel_app.py, gateway/channel_manager/web/web_connect.py, gateway/extensions/application_host.py, deploy/cloud-workspace/Dockerfile, deploy/cloud-workspace/Dockerfile.yuanrong, gateway/services/cloud_environments.py, gateway/services/cloud_instance_policy.py, gateway/services/cloud_workspace_assembly.py, gateway/auth/account_http.py, gateway/auth/account_authenticator.py, gateway/auth/request_scope.py, gateway/extensions/agentos/agentos_router/router_client.py, tests/unit_tests/cloud_workspace/test_integration_boundaries.py, tests/unit_tests/server/test_gateway_adapter.py | 无独立 D：依据管理仓 PLATFORM_CANDIDATE_DISPOSITION_20261109（M01-M12/C01-C22）及用户本会话授权；无独立D编号。 |
