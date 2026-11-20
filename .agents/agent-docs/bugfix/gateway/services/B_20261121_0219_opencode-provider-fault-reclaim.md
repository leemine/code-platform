---
id: B_20261121_0219_opencode-provider-fault-reclaim
title: OpenCode 服务退出后的独立实例回收
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway/services, deploy/cloud-workspace]
files: [gateway/services/cloud_opencode_pool.py, gateway/services/cloud_opencode_relay.py, gateway/services/resource_reconciler.py, deploy/cloud-workspace/physical_resources.py]
designs: []
design_note: 用户确认补齐当前 S_02 托管 OpenCode 回收契约，无独立设计。
---

## 现象与根因

元戎的 Python 引导进程仍在，OpenCode 已退出，旧回收器因无法读取原生会话状态而保留实例。重试继续命中旧代。真实 YuanRong 0.10.0 的健康转发曾关闭连接，也曾返回 `502 failed to dial sandbox`。第一轮故障注入脚本遇到连接关闭后提前退出，未验到删除和恢复。

## 修复决策

参考 Multica 对失联的多次观察和宽限期，复用 Gateway 已有回收循环。无请求或 SSE 持有时，跨轮观察元戎失败信号，经过 `max(30 秒, ready_timeout)` 再请求宿主确认同代容器仍运行且其 4096 端口明确拒绝连接。宿主从 Docker 检查结果取默认 bridge 地址。一般超时、未知拓扑或监听仍在时保留实例。

元戎先执行删除；单实例 API 返回 404 后，受限宿主接口确认 Docker 容器 ID 不再存在。新一代由下次请求按原分配键创建，并挂载同一个 `/state`。会话绑定和历史仍由原 WorkSwarm 路径恢复。

当前契约见 [S_02](../../../specs/jiuwenswarm/server/runtime/agent_adapter/S_02_external-adapter-boundary.md)。首轮覆盖 OpenCode 退出导致监听消失的情形，端口仍监听的情形在下文补充。

## 回归与证据

基线 `68b653d` 加独立工作树修复，159 项定向回归通过。真实隔离 YuanRong 0.10.0、Docker、OpenCode 1.18.18 和 WorkSwarm Worker 用确定性模型替身完成故障前、恢复后各一轮。注入只结束 OpenCode 子进程。宽限期内旧容器继续运行，之后旧代经元戎删除和 Docker 按 ID 确认后退役。新容器挂载同一状态卷，Worker 及 Swarm 和 OpenCode 的会话 ID 均相同，原生会话数保持 1 → 1，续接回合读取了前一轮上下文。

实际候选文件摘要、导入来源与日志索引保存在管理工作区 `artifacts/platform-opencode-yuanrong-fault-recovery-20261121/evidence/summary.md`。未做真实业务负载或容量验证，部署配额沿用已决定的 4 GiB。

## 端口仍监听的后续修复

基于首轮提交 `dd3f04a`，区分监听停止和 HTTP 卡死。TCP 建连可以成功而 OpenCode 已停止处理 HTTP。新增宿主只读探测，限定已核实的同代容器、bridge 地址、固定端口及固定健康请求，只有成功发送后等待首字节超时才确认当前观测。累计每次同时得到元戎读取超时与宿主探测超时，至少经过 60 秒和配置的就绪超时后，才能走同一元戎删除和 Docker 物理确认。收到响应、未获得证据或故障类型变化会重置卡死窗口。

真实隔离池中对同一 OpenCode 进程先短暂停住再恢复，原实例、代次、Docker 容器和会话保留，卡死计时清零。第二次暂停保留 TCP 监听并持续失去 HTTP 响应，满足宽限期后经原生命周期删除。Docker 确认旧容器消失后重建，同一 Worker 使用原状态卷和原会话继续，原生会话数保持 1 → 1。172 项定向回归通过，未进行真实业务负载。证据在管理工作区 `artifacts/platform-opencode-yuanrong-stalled-recovery-20261121/evidence/summary.md`。
