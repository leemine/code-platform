---
id: F_20261121_1554_managed-opencode-account-admission
title: 共池部署的托管 OpenCode 账号准入
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway, gateway/extensions/cloud_workspace, gateway/services]
files:
  - gateway/extensions/cloud_workspace/config.py
  - gateway/services/cloud_instance_policy.py
  - gateway/services/cloud_opencode_pool.py
designs: []
design_note: 依据已确认的原生产元戎池共池方案及边界只读预检，无独立 D 文档。
---

# 共池部署的托管 OpenCode 账号准入

## 实施

Gateway 私有配置的 `opencode_provider.account_allowlist` 使用账号权威分配的账号 ID。中继仍校验当前 Worker 的签名、账号、项目和代次。新建 Provider 绑定时，从当前 Worker 绑定取账号 ID 查询名单，模型同步与会话申请共用这一检查。拒绝时沿用中继 403，状态库、卷和元戎均无创建副作用。

名单的空列表可停止新增绑定，已有项目级和 Worker 级绑定继续沿用原归属、卷及回收流程。未入名单且无已有绑定的 Worker 在启动时不下发托管 OpenCode 中继和模型策略。旧专用环境可省略名单，普通账号注册及非托管执行路径继续使用原入口。名单启动时读取。已经启动的 Worker 在下次启动前不会收到新加入名单后才下发的中继配置。

## 决策与适用范围

准入使用原绑定表和现有单写者。无额外账号存储或元戎分配器。计划中的原池部署复用现行账号和 Worker 路径，由同一边界下的 OpenCode 专用分支核对独立镜像、私有状态根、账号工作区和物理确认。原有 Worker 的镜像名单、策略清单、AppArmor、seccomp、日志规则及持久回执均需保留。现有两个独立灰度账号继续使用各自原池。现行契约见 [S_01](../specs/gateway/S_01_cloud-account-instance.md)。

## 验证

基于已刷新 `origin/main` 的 `df2e35a030b1e5402162040d9e738910a990fb77` 创建本地候选。测试使用真实 Gateway 校验逻辑、Worker 签名、临时 SQLite 及元戎测试替身，Docker 边界回归另有临时 Unix 传输。定向回归 226 项通过，覆盖签名后的拒绝、普通注册、绑定及卷复用。

2026-11-21 在真实隔离元戎 0.10.3 与现有生产 AppArmor、seccomp 策略下复验。普通 Worker 能自动分配并创建项目，带有效签名的非白名单请求被拒绝。一个 4 GiB OpenCode 容器服务同一 Worker 的两个项目，两个项目首发均收到流式结果。关闭新 OpenCode 接入后普通注册仍成功，旧容器经元戎与 Docker 确认回收，两个项目首条续聊 2/2 命中原卷和原生会话。隔离的两个 Worker 沿原流程物理回收。管理记录为 PLATFORM-OPENCODE-ORIGINAL-POOL-ADMISSION-20261121 的补验。正式共池发布仍待交付。
