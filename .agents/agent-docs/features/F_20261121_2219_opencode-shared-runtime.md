---
id: F_20261121_2219_opencode-shared-runtime
title: 独立 OpenCode 复用宿主启动栈
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [deploy/cloud-workspace, gateway/services, gateway/extensions/cloud_workspace]
files:
  - deploy/cloud-workspace/docker_log_boundary.py
  - deploy/cloud-workspace/opencode_runtime_asset.py
  - deploy/cloud-workspace/physical_resources.py
  - gateway/common/opencode_runtime.py
  - gateway/extensions/cloud_workspace/config.py
  - gateway/services/cloud_opencode_pool.py
  - gateway/services/migrate_opencode_binding.py
designs: []
design_note: 沿现有元戎调度、Docker 物理围栏和绑定回收流程扩展。
---

# 独立 OpenCode 复用宿主启动栈

Python 3.11、元戎容器 Runtime 和 Agent DX Executor 作为单独的版本资产发布。Provider 镜像保留 OpenCode 和系统工具。节点 Docker 边界将镜像 ID 与资产路径配对授权，并在容器创建前核对根目录、树摘要和只读挂载。Gateway 固定绑定使用的镜像与路径。绑定锚点确认原项目与状态卷归属，分配代次记录当前实际镜像和挂载。

迁移使用现有环境库写锁。物理回收确认、下一代尚未计划，且当前镜像仍匹配时，维护命令允许替换镜像和启动栈路径。继续复用原状态卷、原生会话 ID 和 Worker 会话 ID。回滚使用同一入口。

基线为 `2987c300321e8741babe0b4da7a27d44224a04da`。同一隔离宿主上的两个元戎 0.10.3 节点分别预置同一树摘要，各自启动了真实 OpenCode 1.18.18。未预置时，节点 B 拒绝 Docker 创建，元戎最终返回 `FATAL`。随后用真实账号 Worker 将一条已在完整镜像上创建的会话迁移到 265.6 MB 镜像，再回滚到完整镜像。三个独立容器对应绑定的三代，两次冷启动都成功续聊，三代的原状态卷 inode、OpenCode 会话 ID 和 Worker 会话 ID 一致。模型后端使用隔离固定响应。
