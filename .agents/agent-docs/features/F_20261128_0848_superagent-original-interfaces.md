---
id: F_20261128_0848_superagent-original-interfaces
title: SuperAgent 原界面接入 WorkSwarm
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway/extensions/superagent, jiuwenswarm/channels/web/frontend]
files: [gateway/extensions/superagent/extension.py, gateway/extensions/superagent/workbench.py, gateway/extensions/superagent/frontend/build.mjs, gateway/extensions/superagent/frontend/conversation.ts, jiuwenswarm/channels/web/frontend/src/applicationPlugins/managedConversation.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts]
designs: []
design_note: 用户在任务会话中批准原界面接入方案，原设计 PNG 与任务台账保存在管理仓。
---

## 实施

Gateway 从固定来源装配 SuperAgent 原管理面板及独立 Workbench。管理面板沿用原组件和页面，Workbench 在构建时添加宿主桥接。配置由 WorkSwarm 管理。原宿主的配置写入、持久 Router 主会话、原渠道回报和主动触发留待后续。临时工单页由验收开关控制。

Workbench 新话题由已有 Router 和 Core 接单，跟进沿用绑定的 Ticket 和 OpenCode 会话。Workbench 和平台原输入框共用跟进路径。业务裁定按 Worker 报告的等待项处理，OpenCode 工具审批复用平台原生审批卡和 Runtime 控制入口。

检视时补齐了发布清单的会话接入条件、网关查询故障隔离、原生审批卡恢复，以及普通 HTTP 和回执丢失时的跟进重试。新增回归使用原 WebSocket Hook 检查离开后重进会话、同一提交的处理和停用插件时的行为。

## 验收

安装包来源、固定文件核验、Chrome 与真实 OpenCode 证据保存在管理工作区 `artifacts/superagent-original-interfaces-20261128/evidence/REPORT.md`。按 [插件契约](../specs/gateway/S_05_superagent-web-tickets.md) 解释工单、会话和审批的所有权。

[原管理面板](../../../docs/assets/images/superagent-workswarm-panel.png) · [原 Workbench](../../../docs/assets/images/superagent-workswarm-workbench.png) · [原生审批](../../../docs/assets/images/superagent-workswarm-approval.png)
