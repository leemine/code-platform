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

真实隔离 UI 已在 113.207.105.228 新镜像 58a9f1f0、专用 ui-c 通过：Full Access 收紧到 Default 后原审批卡出现；拒绝时文件不存在，单次允许后合成文件为 17 字节；原生 turn_aborted/interrupted 后同线程继续回复 CODEX_RECOVERED，页面刷新保留历史。原生线程始终为 01a1c62a-cc02-7d93-808d-9245740ead5e，原生上下文明确由 never/danger-full-access 变为 on-request/workspace-write。真实探针、原生上下文与完整 UI 验收记录位于管理仓 PLATFORM_CLOUD_UI_ACCEPTANCE_20261110。

边界：当前隔离容器的 bwrap 无法创建用户命名空间，普通沙箱命令会失败并转原生单次审批；本轮只批准合成文件写入和无文件/网络访问的 sleep，不修改内核或容器特权，不能宣称该环境已验证 workspace-write 沙箱执行。账号探测此前偶发失败仍未复现；本轮公网只读 90 次均 200，计划内 Gateway 重启触发 502 后 UI 明确重试恢复，不等于历史根因已闭合。完整上线验收仍保留这些限制。
