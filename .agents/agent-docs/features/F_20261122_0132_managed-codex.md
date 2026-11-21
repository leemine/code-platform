---
id: F_20261122_0132_managed-codex
title: 元戎托管的独立 Codex 执行容器
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway, deploy/cloud-workspace, jiuwenswarm/server/runtime/agent_adapter]
files: [gateway/services/cloud_codex_pool.py, gateway/services/cloud_codex_relay.py, deploy/cloud-workspace/physical_resources.py, deploy/cloud-workspace/Dockerfile.codex, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py]
designs: []
design_note: 用户确认独立 Codex 接入、逐节点发布及灰度任务。宿主契约续写 S_01_cloud-account-instance。
---

# 元戎托管的独立 Codex 执行容器

Worker 继续通过原模型目录和 Codex 适配器准备会话，官方 SDK 经等价 stdio 流连接 Gateway。Gateway 保留元戎创建及对账，依据绑定和物理确认维护原卷。Docker 边界核对项目、代次、镜像及共享启动栈，返回已确认容器的私有地址。Web 继续沿用原选择器、消息、审批和历史。

原型的 457.1 MB 只覆盖 CLI 与共享栈导入。实际启动还依赖 Debian 的 `libcurl.so.4` 及元戎初始化可写的 HOME，最终候选按相同解包口径约 466.5 MB。元戎通用 HTTP 路径在同一隔离池的原生 WebSocket 对照返回 502。Gateway 因此使用现有物理边界确认的私有地址，原元戎 API 继续负责分配及回收。

Gateway 仅为 allowlist 中当前 Worker 验证签名。应用连接令牌按代次生成，容器只见摘要。模型 API Key 仅供控制侧的单模型 Responses 代理使用。独立执行容器复用封存的共享启动栈。配置、预置及回滚见[部署说明](../../../deploy/cloud-workspace/CODEX_RELEASE.md)。
