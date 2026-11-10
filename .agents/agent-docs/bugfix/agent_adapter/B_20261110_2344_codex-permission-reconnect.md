---
id: B_20261110_2344_codex-permission-reconnect
title: Codex 已加载线程权限变更通过自有客户端重连确认
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/runtime/agent_adapter]
files: [jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, tests/unit_tests/agentserver/test_codex_direct_adapter.py]
designs: []
design_note: 修复既有权限契约，沿用原 Runtime 和官方恢复入口，无新增架构设计。
---

# 现象与根因

隔离 UI 的既有 Codex 线程从 Full Access 切回 Default 后，下一轮报 permission update was not confirmed。锁定官方 SDK/CLI 0.163.0 的独立真实探针执行一次无工具模型调用后，确认同客户端 thread/resume 仍返回 never/dangerFullAccess；新客户端以同一 CODEX_HOME 恢复同一线程则返回 on-request/workspaceWrite。此前 fake 总是接受热 resume 的新参数，未模拟此原生语义。

# 修复与边界

平台适配器在下一轮启动前，复用既有客户端关闭和 _connect 恢复路径，保留 native ID、工作区、历史及已选择 MCP。仍确认线程/目录/idle/权限/MCP，失败拒绝执行。原 Runtime 队列、取消确认、角色刷新与权限配置源不变，不修改 SDK/CLI、不升级依赖、不新增创建链。

# 回归证据

原候选 47b2b28 上实施；Python 3.13.15，Core 固定 e0891988，SDK/CLI 0.163.0。定向 test_codex_direct_adapter.py：96 passed（25.14 秒），覆盖双向权限切换、保持线程/私有目录、错误权限不执行且可重试、MCP 保留及原取消/角色/恢复消费者。沙箱首次测试因日志目录只读未收集，隔离 HOME 后沙箱首例停滞；宿主隔离 HOME 有界执行通过，不能把环境问题记作产品失败。

真实探针与完整 UI 验收记录位于管理仓 PLATFORM_CLOUD_UI_ACCEPTANCE_20261110；当前新版容器/UI 验证待补，不能将单测或独立 SDK 探针记作端到端通过。账号探测偶发失败独立排查。
