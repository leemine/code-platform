---
id: F_20261121_0233_opencode-worker-shared-provider
title: 同一 Worker 的 OpenCode 共享实例与旧会话兼容
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway/services, gateway/extensions/cloud_workspace, deploy/cloud-workspace, jiuwenswarm/server/runtime/agent_adapter/providers]
files: [gateway/services/cloud_opencode_pool.py, gateway/services/cloud_opencode_relay.py, gateway/extensions/cloud_workspace/extension.py, deploy/cloud-workspace/physical_resources.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/session_recovery.py]
designs: []
design_note: 用户确认 Worker 内共享与旧会话沿用原状态卷，设计边界登记在管理仓任务表。
---

## 实现与决策

新会话按账号、稳定 Worker 环境和 Provider 分配。已有 SQL 项目行和宿主版本 1 回执继续用于旧线路，内部保留键区分共享绑定。宿主版本 2 准入只允许该 Worker 的项目根、Provider 状态卷、本代只读配置和既有受限日志挂载。

Gateway 在公开给 Worker 之前登记共享会话的归属，只记录 Provider 绑定、项目、目录和原生 ID。内容仍由 OpenCode 保存，Swarm 延续自身会话绑定。列表与状态按归属过滤，详情及命令检查对应 ID，SSE 丢弃无项目归属的会话事件。审批请求通过同一 Provider 的待处理请求解析会话归属。 [OpenCode 1.18.18 SDK 定义](https://raw.githubusercontent.com/anomalyco/opencode/v1.18.18/packages/sdk/js/src/v2/gen/sdk.gen.ts)

Worker 把共享线路标记和相应配置摘要写入既有远端会话绑定。旧记录保留原摘要和线路，原状态卷不移动。普通回收先确认共享绑定的各项目空闲，再沿用元戎和 Docker 的删除确认，同一状态卷随下一代挂载。 [当前接入契约](../specs/jiuwenswarm/server/runtime/agent_adapter/S_02_external-adapter-boundary.md)

## 定向验证

基于 `15d98ac` 与独立工作树改动，310 项回归通过。真实隔离 YuanRong 0.10.0、Docker、官方 OpenCode 1.18.18 和 WorkSwarm Worker 定向验收通过。一个升级后 Worker 的两个项目并发创建会话，只产生一个共享容器。另一账号使用同项目 ID 得到独立容器与状态卷。跨项目会话列表和五类直接访问已验证，SSE 和审批归属通过定向回归。

旧版 Worker 创建的会话由升级 Worker 沿用原项目容器、状态卷和原生 ID。共享容器经元戎删除及 Docker 旧 ID 确认后，两个项目在挂载同一共享卷的替代容器各自接回原会话，原生会话数 2 → 2，两个确定性恢复回合分别读到各自的先前上下文。首轮隔离池无法同时调度第三个容器，复验先确认旧卷并按正常生命周期回收旧容器，再同时运行两个账号的共享容器。未测真实负载。

实际依赖、命令、日志及候选来源见管理工作区 `artifacts/platform-opencode-worker-sharing-20261121/evidence/summary.md`。
