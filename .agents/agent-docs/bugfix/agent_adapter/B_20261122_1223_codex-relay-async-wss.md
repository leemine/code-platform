---
id: B_20261122_1223_codex-relay-async-wss
title: Codex 托管中继的 WSS 升级竞态
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/runtime/agent_adapter]
files: [jiuwenswarm/server/runtime/agent_adapter/providers/codex_managed_stdio.py, tests/unit_tests/cloud_workspace/test_codex_managed_stdio.py]
designs: []
design_note: 用户确认在现有 S_01 托管 Codex 中继契约内修复 Worker 的 TLS 套接字访问方式。
---

## 现象和根因

正式 Edge 偶发 Codex WSS 升级超时。出现超时时 Worker 已建立 TCP 和 TLS，升级请求未产生 TCP 出站应用数据，Edge 和 Gateway 同时段未收到该请求。使用同版本同步客户端和 TLS 1.3 的隔离复现中，启动接收线程后立即发送升级请求，36 次出现 1 次零字节超时。将首次读延后到首次写之后，同样的 36 次全部成功。同步客户端的收发线程可能同时操作同一 TLS 套接字。

## 修复

按 [账号实例契约](../../specs/gateway/S_01_cloud-account-instance.md) 将签名握手、分配确认和长连接收发统一到一个 asyncio 事件循环。SDK 仍以管道交换逐行 JSON-RPC。向 SDK 输出遵循管道背压，远端关闭时取消仍在读 SDK 输入的任务。继续按原配置校验证书链和主机名，并沿用原握手超时、分配时限和帧大小边界。

## 回归

定向覆盖 SDK 输入管道保持打开时的双向转发及远端关闭、超长及截断帧拒绝。实际元戎验收记录见管理仓任务 `PLATFORM-CODEX-ASYNC-WSS-20261122`。
