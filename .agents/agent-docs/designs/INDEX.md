---
title: 设计文档索引
author: leemine
author_email: leewanlong@gmail.com
generated: true
---

<!-- 本文件由 .agents/skills/jw-design/scripts/generate_index.py 自动生成，请勿手改。重新生成：python .agents/skills/jw-design/scripts/generate_index.py -->
<!-- generated-at: 2026-11-23T00:48+08:00 -->

# 设计文档索引 (INDEX)

> 开发前 3 · 开发中 3 · 开发后 3 · 已否决 0

按模块目录分组，组内按生命周期展示；跨模块设计在各相关模块下列出，全局统计按文档去重。

## 模块目录

| 模块 | 设计数 |
|---|---|
| [agent_teams](#module-1) | 1 |
| [agent_teams/workflow](#module-2) | 3 |
| [deploy/cloud-workspace](#module-3) | 1 |
| [gateway/extensions/cloud_workspace](#module-4) | 3 |
| [gateway/services](#module-5) | 3 |
| [jiuwenswarm](#module-6) | 3 |
| [jiuwenswarm/channels/web/frontend](#module-7) | 3 |
| [jiuwenswarm/channels/web/frontend/src/components/ChatPanel](#module-8) | 1 |
| [jiuwenswarm/channels/web/frontend/src/components/SessionSidebar](#module-9) | 1 |
| [jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace](#module-10) | 1 |
| [jiuwenswarm/gateway/channel_manager/web](#module-11) | 1 |
| [jiuwenswarm/observability](#module-12) | 1 |
| [jiuwenswarm/server/control](#module-13) | 3 |
| [jiuwenswarm/server/runtime/agent_adapter/providers](#module-14) | 2 |

<a id="module-1"></a>

## agent_teams

### 开发前 (proposals)

| ID | 标题 | 状态 | 作者 | 领域 | 更新日期 |
|---|---|---|---|---|---|
| [SDD-0029](proposals/SDD-0029-team-session-runtime-integration/design.md) | Team 模式接入统一 Session Runtime | draft | @zhanglongmin | core | 2026-10-09 |

<a id="module-2"></a>

## agent_teams/workflow

### 开发后 (archive)

| ID | 标题 | 状态 | 作者 | 领域 | 更新日期 |
|---|---|---|---|---|---|
| [SDD-0009](archive/SDD-0009-jiuwen-tui-swarmflow-human-session-adaptation/design.md) | jiuwen TUI 适配 SwarmFlow 三算子（human / human_session / agent_session） | shipped | @chenchunzhou | core | 2026-07-28 |
| [SDD-0010](archive/SDD-0010-jiuwen-tui-nested-workflow-and-budget-observability/design.md) | jiuwen TUI 嵌套 Workflow 与 Budget 可观测性 | shipped | @chenchunzhou | observability | 2026-08-06 |
| [SDD-0028](archive/SDD-0028-swarmflow-verify-fork-observability/design.md) | swarmflow verify / fork 可观测与前端呈现 | shipped | @xiajing | observability | 2026-09-29 |

<a id="module-3"></a>

## deploy/cloud-workspace

### 开发中 (active)

| ID | 标题 | 状态 | 作者 | 领域 | 更新日期 |
|---|---|---|---|---|---|
| [D-20261122-0920-managed-runtime-devices](active/D-20261122-0920-managed-runtime-devices/design.md) | 运行时页面新增独立 OpenCode 设备 | in-development | 待确认 | harness | 2026-11-22 |

<a id="module-4"></a>

## gateway/extensions/cloud_workspace

### 开发中 (active)

| ID | 标题 | 状态 | 作者 | 领域 | 更新日期 |
|---|---|---|---|---|---|
| [D-20261116-1851-github-cloud-environment-alignment](active/D-20261116-1851-github-cloud-environment-alignment/design.md) | 对齐 codeswarm 的 GitHub 云端项目环境流程 | in-development | leemine | core | 2026-11-16 |
| [D-20261122-0144-opencode-cloud-runtime-ui](active/D-20261122-0144-opencode-cloud-runtime-ui/design.md) | OpenCode 云端运行时申请与 Code 聊天接入 | in-development | 待确认 | harness | 2026-11-22 |
| [D-20261122-0920-managed-runtime-devices](active/D-20261122-0920-managed-runtime-devices/design.md) | 运行时页面新增独立 OpenCode 设备 | in-development | 待确认 | harness | 2026-11-22 |

<a id="module-5"></a>

## gateway/services

### 开发中 (active)

| ID | 标题 | 状态 | 作者 | 领域 | 更新日期 |
|---|---|---|---|---|---|
| [D-20261116-1851-github-cloud-environment-alignment](active/D-20261116-1851-github-cloud-environment-alignment/design.md) | 对齐 codeswarm 的 GitHub 云端项目环境流程 | in-development | leemine | core | 2026-11-16 |
| [D-20261122-0144-opencode-cloud-runtime-ui](active/D-20261122-0144-opencode-cloud-runtime-ui/design.md) | OpenCode 云端运行时申请与 Code 聊天接入 | in-development | 待确认 | harness | 2026-11-22 |
| [D-20261122-0920-managed-runtime-devices](active/D-20261122-0920-managed-runtime-devices/design.md) | 运行时页面新增独立 OpenCode 设备 | in-development | 待确认 | harness | 2026-11-22 |

<a id="module-6"></a>

## jiuwenswarm

### 开发后 (archive)

| ID | 标题 | 状态 | 作者 | 领域 | 更新日期 |
|---|---|---|---|---|---|
| [SDD-0009](archive/SDD-0009-jiuwen-tui-swarmflow-human-session-adaptation/design.md) | jiuwen TUI 适配 SwarmFlow 三算子（human / human_session / agent_session） | shipped | @chenchunzhou | core | 2026-07-28 |
| [SDD-0010](archive/SDD-0010-jiuwen-tui-nested-workflow-and-budget-observability/design.md) | jiuwen TUI 嵌套 Workflow 与 Budget 可观测性 | shipped | @chenchunzhou | observability | 2026-08-06 |
| [SDD-0028](archive/SDD-0028-swarmflow-verify-fork-observability/design.md) | swarmflow verify / fork 可观测与前端呈现 | shipped | @xiajing | observability | 2026-09-29 |

<a id="module-7"></a>

## jiuwenswarm/channels/web/frontend

### 开发前 (proposals)

| ID | 标题 | 状态 | 作者 | 领域 | 更新日期 |
|---|---|---|---|---|---|
| [SDD-0026](proposals/SDD-0026-trajectory-observability-web-ui/design.md) | 轨迹观测前端：单 Agent、Subagent 与 Team 多 Agent 轨迹 UI | draft | @alan_cheng | observability | 2026-09-15 |

### 开发中 (active)

| ID | 标题 | 状态 | 作者 | 领域 | 更新日期 |
|---|---|---|---|---|---|
| [D-20261116-1851-github-cloud-environment-alignment](active/D-20261116-1851-github-cloud-environment-alignment/design.md) | 对齐 codeswarm 的 GitHub 云端项目环境流程 | in-development | leemine | core | 2026-11-16 |
| [D-20261122-0144-opencode-cloud-runtime-ui](active/D-20261122-0144-opencode-cloud-runtime-ui/design.md) | OpenCode 云端运行时申请与 Code 聊天接入 | in-development | 待确认 | harness | 2026-11-22 |

<a id="module-8"></a>

## jiuwenswarm/channels/web/frontend/src/components/ChatPanel

### 开发中 (active)

| ID | 标题 | 状态 | 作者 | 领域 | 更新日期 |
|---|---|---|---|---|---|
| [D-20261122-0920-managed-runtime-devices](active/D-20261122-0920-managed-runtime-devices/design.md) | 运行时页面新增独立 OpenCode 设备 | in-development | 待确认 | harness | 2026-11-22 |

<a id="module-9"></a>

## jiuwenswarm/channels/web/frontend/src/components/SessionSidebar

### 开发中 (active)

| ID | 标题 | 状态 | 作者 | 领域 | 更新日期 |
|---|---|---|---|---|---|
| [D-20261122-0144-opencode-cloud-runtime-ui](active/D-20261122-0144-opencode-cloud-runtime-ui/design.md) | OpenCode 云端运行时申请与 Code 聊天接入 | in-development | 待确认 | harness | 2026-11-22 |

<a id="module-10"></a>

## jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace

### 开发中 (active)

| ID | 标题 | 状态 | 作者 | 领域 | 更新日期 |
|---|---|---|---|---|---|
| [D-20261122-0920-managed-runtime-devices](active/D-20261122-0920-managed-runtime-devices/design.md) | 运行时页面新增独立 OpenCode 设备 | in-development | 待确认 | harness | 2026-11-22 |

<a id="module-11"></a>

## jiuwenswarm/gateway/channel_manager/web

### 开发前 (proposals)

| ID | 标题 | 状态 | 作者 | 领域 | 更新日期 |
|---|---|---|---|---|---|
| [SDD-0025](proposals/SDD-0025-trajectory-session-store-and-serving/design.md) | 轨迹数据面：会话级 SQLite 存储、实时变更提示与读取 API | draft | @alan_cheng | observability | 2026-09-15 |

<a id="module-12"></a>

## jiuwenswarm/observability

### 开发前 (proposals)

| ID | 标题 | 状态 | 作者 | 领域 | 更新日期 |
|---|---|---|---|---|---|
| [SDD-0025](proposals/SDD-0025-trajectory-session-store-and-serving/design.md) | 轨迹数据面：会话级 SQLite 存储、实时变更提示与读取 API | draft | @alan_cheng | observability | 2026-09-15 |

<a id="module-13"></a>

## jiuwenswarm/server/control

### 开发中 (active)

| ID | 标题 | 状态 | 作者 | 领域 | 更新日期 |
|---|---|---|---|---|---|
| [D-20261116-1851-github-cloud-environment-alignment](active/D-20261116-1851-github-cloud-environment-alignment/design.md) | 对齐 codeswarm 的 GitHub 云端项目环境流程 | in-development | leemine | core | 2026-11-16 |
| [D-20261122-0144-opencode-cloud-runtime-ui](active/D-20261122-0144-opencode-cloud-runtime-ui/design.md) | OpenCode 云端运行时申请与 Code 聊天接入 | in-development | 待确认 | harness | 2026-11-22 |
| [D-20261122-0920-managed-runtime-devices](active/D-20261122-0920-managed-runtime-devices/design.md) | 运行时页面新增独立 OpenCode 设备 | in-development | 待确认 | harness | 2026-11-22 |

<a id="module-14"></a>

## jiuwenswarm/server/runtime/agent_adapter/providers

### 开发中 (active)

| ID | 标题 | 状态 | 作者 | 领域 | 更新日期 |
|---|---|---|---|---|---|
| [D-20261122-0144-opencode-cloud-runtime-ui](active/D-20261122-0144-opencode-cloud-runtime-ui/design.md) | OpenCode 云端运行时申请与 Code 聊天接入 | in-development | 待确认 | harness | 2026-11-22 |
| [D-20261122-0920-managed-runtime-devices](active/D-20261122-0920-managed-runtime-devices/design.md) | 运行时页面新增独立 OpenCode 设备 | in-development | 待确认 | harness | 2026-11-22 |
