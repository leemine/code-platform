---
id: B_20261105_1239_kvc-shutdown-without-core
title: 无 Core Worker 的 KV Cache 退出修复
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/worker]
files: [jiuwenswarm/server/worker/runtime_host.py, jiuwenswarm/server/agent_ws_server.py, tests/unit_tests/agentserver/test_worker_runtime_ownership.py]
designs: []
design_note: 用户确认只修 KV Cache 的退出路径，保留 Native 释放流程，分别验证三家外部 Provider。
---

无 Core Worker 在最终退出时导入依赖 Core 的 KV Cache 模块，触发 `ModuleNotFoundError`。该错误发生在历史和元数据落盘后，随后触发 Worker 强制退出。修复由 Worker 在原关闭顺序中委托 AgentServer 关闭已绑定的 KV Cache owner。无 Core 没有 owner，流程继续进入后续 Runtime 清理。Native 仍调用原 owner 的 `close()`。Symphony 警告留在原流程。

基线为 code-platform `1a9bc541e6d3d3f6e29c810eba1a3972e12b7679`。以 Python 3.13.15 按锁非 editable 安装验证，Core 来源为 `e089198835426cd7681761b0cc278670cd83031f`。Worker 资源顺序、关闭时限、常驻退出入口和 Native 缓存生命周期共 38 项通过。

- Linux Web／Gateway／Front／Worker 使用原 Worker SIGTERM 入口。Codex 和 OpenCode 使用已配置的真实模型，Claude 使用真实 SDK／CLI 和本地 Anthropic Messages 端点。三家重启前后 Worker 退出码为 0，IPC 已关闭，原生线程、角色和原对话上下文均恢复。原 Claude 模型端点独立探测返回 429／1113。
- Native 用真实 Core SDK 和受控 HTTP 推理端点，预置同一根下的两条绑定。AgentServer 停止时收到 0 次释放请求，Worker 最终退出时收到 1 次正确的根缓存释放请求。亲和禁用时收到 0 次。
- Linux 下桌面同款 `--shutdown-worker` 仍会等待回执超时。Worker 在发回执前等待 Unix 监听器关闭，监听器同时等待尚在等回执的 IPC 连接关闭。最小 socket 对照也复现该等待。该项与 KV Cache 清理异常独立，桌面关停验收未通过。

验收脚本与日志在管理仓 `artifacts/worker-kvc-shutdown-20261105/evidence/`，续聊报告在 `evidence/signal/`。工作区尚未提交。

## IPC 关停回执补验

在同一候选上单独移植 [官方 IPC 关停补丁 17625e5d](https://github.com/openJiuwen-ai/jiuwenswarm/commit/17625e5dd94550deec395af9865a96db4959a924)。`IpcServer` 先停止接收新连接，Worker 完成 Runtime 清理后保留已接入的连接发回执，再关闭连接并释放 IPC 所有权。原落盘与 KV Cache 清理仍在回执之前。

Linux 下从候选源码和既有按锁依赖运行，IPC 与 Worker 相关用例 126 项通过、10 项跳过。Native 和三种无 Core Provider 均收到桌面关停回执并在重启后恢复原会话。Native 与 Claude 使用本机模型协议测试端点，Codex 与 OpenCode 使用已配置模型。独立 Native 缓存检查再次确认启用亲和时最终退出驱逐一次，关闭亲和时不驱逐。证据位于 `evidence/ipc-backport/`。此次补验覆盖桌面关停助手，安装包与其他平台未验。
