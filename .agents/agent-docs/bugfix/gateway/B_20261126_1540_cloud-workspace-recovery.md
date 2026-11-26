---
id: B-20261126-1540-cloud-workspace-recovery
title: 云工作区旧 Worker 回收对账和重试
type: B
author: leemine
author_email: leewanlong@gmail.com
designs: []
design_note: 复用 Gateway ensure、已有物理确认接口及持久工作区。
modules: [gateway, deploy/cloud-workspace, jiuwenswarm/channels/web]
files: [deploy/cloud-workspace/physical_resources.py, gateway/extensions/agentos/agentos_router/router_client.py, gateway/extensions/cloud_workspace/extension.py, gateway/services/cloud_environments.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudWorkspaceGate.tsx, jiuwenswarm/channels/web/frontend/tests/cloudWorkspace.test.mjs, tests/unit_tests/cloud_workspace/test_physical_resources.py, tests/unit_tests/cloud_workspace/test_cloud_workspace.py]
---

# 现象与原因

元戎已删除原实例且查询返回 404，但 Docker 仍保留已退出的旧 Worker。物理确认只补偿从未启动的容器，导致有效 `CREATED` 回执无法闭合，绑定持续处于 `DELETING`。此前每次 ensure 都会在共享创建流程外重复执行删除对账，多个请求可能同时处理旧代次。

# 修复

物理确认在原槽位锁下校验元戎 404、持久回执完整容器 ID 和容器归属。满足条件的已退出 Worker 使用非强制、不移除卷的 Docker 删除。确认原名称和 ID 均不存在后才允许原绑定推进代次。Gateway 合并同账号的并发 ensure。页面保留现有入口，在等待回收或 Worker 就绪时自动退避重试，分配失败时保留重试按钮。

测试覆盖真实 Unix 确认接口、物理归属边界、并发请求和浏览器入口。部署及验证条件见[云账号实例契约](../../specs/gateway/S_01_cloud-account-instance.md)与[物理确认部署契约](../../../../deploy/cloud-workspace/LOG_BOUNDARY_CONTRACT.md)。

在隔离的元戎 0.10.3 和 Docker 中复现了元戎 404、已退出 Worker 与 `DELETING` 绑定同时存在。8 个并发 ensure 均返回 READY，物理回执确认只创建了 1 个替代 Worker。替代 Worker 挂载原目录，项目列表和同一会话历史保持可读。浏览器以受控 HTTP 响应核对了三态显示及重试入口。

云工作区、AgentOS Router、元戎客户端 608 项组合回归在隔离 Docker 中通过。首次运行的超时未复现，原取消等待用例单进程重复 20 次通过。诊断运行中 8 项项目导入失败来自容器工作目录中的 Git worktree 指针指向宿主机元数据。回归从容器内可写目录启动，以绝对路径读取候选源码和测试，修正后项目导入和组合回归均通过。
