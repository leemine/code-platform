---
id: B-20261119-0957-cloud-conversation-previous-scope
title: 本机 App 云目录新会话的旧会话引用校验
type: B
author: leemine
author_email: leewanlong@gmail.com
designs: []
design_note: 沿用既有 Code 工作区入口与目录操作契约。
modules: [jiuwenswarm/channels/web]
files: [jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/resourceAddress.ts]
---

# 现象与根因

2026-11-19（UTC+8）beta10 Linux App 在云目录选择 Codex 或 OpenCode 后弹出“创建对话失败”。09:57 的复现帧中，所选项目和旧会话引用的云作用域不同，本地执行桥记录 `address_session.create` 的 `PermissionError`。地址拒绝发生在向云端转发之前。

# 候选修复

选择原执行路由后，只在旧会话与项目的账号、入口作用域一致时附带会话生命周期提示。会话创建继续沿用当前项目及 Provider，云桥校验保持。参见 [Code 工作区入口契约](../../specs/gateway/S_02_code-workspace-entry.md)。

# 验证

验收账号使用现有生产镜像，保持目录一致。两种 Provider 带跨作用域旧引用均返回 WebSocket 1008，删除旧引用或使用同作用域旧引用后可创建并回读会话。目标项目作用域错误时仍返回 1008。候选前端路由、目录和会话创建单测通过。证据位于管理工作区 `artifacts/platform-leebot-dialog-failure-20261119/evidence/`。

接入候选请求模块后，两种 Provider 都通过原 beta10 Linux App 的本地连接创建新会话并回读，原会话仍可访问。候选生产构建通过。验证止于会话写入及回读，未发布安装包。
