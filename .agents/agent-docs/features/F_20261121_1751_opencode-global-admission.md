---
id: F_20261121_1751_opencode-global-admission
title: 托管 OpenCode 固定中继与新绑定开关
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway, gateway/extensions/cloud_workspace, gateway/services, jiuwenswarm/server/runtime/agent_adapter/providers]
files:
  - gateway/common/security/opencode_relay_auth.py
  - gateway/extensions/cloud_workspace/config.py
  - gateway/extensions/cloud_workspace/extension.py
  - gateway/services/cloud_opencode_pool.py
  - gateway/services/cloud_workspace_assembly.py
  - jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py
designs: []
design_note: 延续共池方案与原账号准入契约，用户已确认改用全局开关和固定入口。
---

# 托管 OpenCode 固定中继与新绑定开关

## 配置与路由

在 Gateway 私有配置的 `opencode_provider` 中显式设置 `admit_new_bindings`。使用 `true` 时，已认证账号的 Worker 可在首次申请或模型同步时创建持久化绑定。使用 `false` 时，无绑定的请求返回 403，已有绑定可获取原状态卷并在容器回收后重建。普通账号注册继续由 `registration_enabled` 控制。新旧准入字段只能选择一个。

固定中继入口位于部署的 API 前缀下，分别为 `/provider/managed/opencode-worker` 和 `/provider/managed/opencode`。反向代理把该固定前缀转发至对应执行池的 Gateway，保留签名所覆盖的完整路径和请求头。校验仍使用当前 Worker 代次、账号和项目身份。用新配置启动的 Worker 始终获得固定中继地址和模型策略。Gateway 重启读取开关，已取得固定地址的 Worker 可以原地继续使用。尚未取得中继配置的旧 Worker 需要升级启动配置。

已有部署仍可读取 `account_allowlist` 并使用原地址。恢复已托管会话时，同一源站及 API 前缀下的固定入口和原入口可用于校验原配置指纹，账号、项目和其他设置继续参与校验。旧 CLI 会话兼容不在本次范围。详见 [云工作区配置契约](../specs/gateway/S_01_cloud-account-instance.md)。

## 验证

候选基于 `844078bbe163989fc6aa1140ac732123a743d3eb`。定向回归 222 项通过，覆盖开关配置、固定中继的认证接线、新绑定拒绝、模型同步及原卷续接、旧托管入口切换与配置指纹校验。

2026-11-21 使用真实隔离元戎 Runtime／SDK 0.10.3、每个 Provider 4 GiB 复验。开关关闭时，真实 Worker 签名的建会话和模型同步返回 403，无绑定。打开后第一个已有测试账号沿用原 Worker，双项目首发 2/2，共用一个 Provider。再次关闭后，第二个已有测试账号不能创建绑定，普通注册仍返回 201。第一个账号的旧 Provider 经元戎和 Docker 确认空闲回收后，双项目在开关关闭状态下首条续聊 2/2 接回原卷及两条原生会话。验证记录保存在管理仓任务 PLATFORM-OPENCODE-GLOBAL-ADMISSION-20261121 下。

原卷 OpenCode 数据库实读仅有两条会话，每条保存两轮已完成对话。隔离 Worker 和 Provider 均完成物理回收，隔离服务已停止。正式 Gateway 和 Edge 运行容器与挂载配置经前后只读核对一致。
