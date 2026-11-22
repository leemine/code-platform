---
id: F_20261122_1125_provider-relay-tls
title: 统一 Worker 的 Provider 中继与 CA 信任
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway, deploy/cloud-workspace, jiuwenswarm/server/runtime/agent_adapter]
files: [gateway/extensions/cloud_workspace/config.py, gateway/services/cloud_workspace_assembly.py, gateway/services/cloud_instance_policy.py, gateway/common/security/provider_relay_tls.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex_managed_stdio.py]
designs: []
design_note: 用户在 OpenCode 与 Codex 独立部署验证后确认统一中继和 CA，先在隔离元戎验收。
---

# 统一 Worker 的 Provider 中继与 CA 信任

OpenCode 的 HTTP 客户端和 Codex 的 WebSocket 客户端此前各用默认信任来源。内部 Edge 的 CA 必须同时获得两者信任，才可在一个 Worker 使用两个托管 Provider。

Gateway 现在从一个 HTTPS origin 生成两类地址，只为获得中继的 Worker 挂载一份公开 CA PEM。两类客户端都从系统信任追加同一份只读文件，证书链和主机名验证交给 TLS 库。部署配置在原 Worker 启动入口下发，账号持久化配置、既有签名、模型目录、OpenCode 会话恢复标识和 Codex stdio 协议沿用原实现。

相关约束见 [S_01_cloud-account-instance](../specs/gateway/S_01_cloud-account-instance.md)。运维说明见[云工作区部署](../../../deploy/cloud-workspace/README.md)。本候选以 main `b85dbcc` 为基线，锁定依赖与基线一致。定向验收记录见管理仓任务 `PLATFORM-PROVIDER-RELAY-TLS-20261122`。

隔离元戎 0.10.3 上，同一份只读 CA 和同一个 Worker 完成了 OpenCode 回收后原卷原会话续聊、Codex 冷启动首发流式及原生上报 996,147 token。两客户端均拒绝了错误 CA 和错误主机名。定向回归 78 项通过。
