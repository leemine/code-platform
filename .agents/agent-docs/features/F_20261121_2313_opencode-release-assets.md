---
id: F_20261121_2313_opencode-release-assets
title: OpenCode 发布与共享启动栈预置
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [deploy/cloud-workspace]
files:
  - deploy/cloud-workspace/release_opencode.py
  - deploy/cloud-workspace/OPENCODE_RELEASE.md
  - tests/unit_tests/cloud_workspace/test_opencode_release.py
designs: []
design_note: 沿独立 OpenCode 的固定镜像、节点 Docker 边界与原回收迁移流程扩展发布步骤。
---

# OpenCode 发布与共享启动栈预置

同一个发布包清单记录新镜像 ID、封存启动栈树 SHA-256 和旧镜像 ID。控制机经受信 SSH 向明确列出的元戎节点分发发布包。节点复用运行边界的目录摘要算法，验证镜像和启动栈，按树摘要原子发布版本目录。预置阶段不切换 Gateway 或节点边界。所有目标回执一致后才输出部署参数。损坏归档或已存在的异常版本会被拒绝，正确资产可重复预置。新节点先执行预置，再依照发布参数装配并加入元戎；旧镜像保留在发布包和节点本地，可用于绑定的离线回滚。

部署说明见 `deploy/cloud-workspace/OPENCODE_RELEASE.md`。

## 验证

392 项云工作区单元测试通过，含 6 项发布工具测试。隔离调度使用元戎 0.10.3 和 Docker 29.1.3 的 containerd／overlayfs 镜像存储。空镜像仓成功导入新版与回滚镜像并核对实际镜像 ID。同一台宿主上的两个元戎节点分别使用独立资产目录和 Docker 边界。损坏的启动栈归档在新增节点接入前被拦截，未生成切换参数。正确发布包在两个节点启动的新版 Provider 均通过原生健康检查。新节点确认物理回收后以旧完整镜像启动原绑定的下一代，并在同一状态卷读回同一个 OpenCode 会话。
