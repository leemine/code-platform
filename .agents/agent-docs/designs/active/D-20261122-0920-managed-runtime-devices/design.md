---
id: D-20261122-0920-managed-runtime-devices
title: 运行时页面新增独立 OpenCode 设备
slug: managed-runtime-devices
type: D
status: in-development
stage: active
author: null
author_email: null
author_note: 当前仓库缺少有效的 Git 署名。
reviewers: []
created: 2026-11-22
updated: 2026-11-22
approved-date: 2026-11-22
domain: harness
modules:
  - gateway/extensions/cloud_workspace
  - gateway/services
  - jiuwenswarm/server/control
  - jiuwenswarm/server/runtime/agent_adapter/providers
  - jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace
  - jiuwenswarm/channels/web/frontend/src/components/ChatPanel
  - deploy/cloud-workspace
tags: [cloud-workspace, runtime, opencode]
scope: 在运行时页创建账号级 OpenCode 设备，并在 Code 普通会话复用原 Provider 下拉框
plan: PLATFORM-OPENCODE-CLOUD-RUNTIME-DEVICES
related: [D-20261122-0144-opencode-cloud-runtime-ui]
files: []
---

# 运行时页面新增独立 OpenCode 设备

## 交互

「运行时」保留在左侧「专家」与「技能」之间。右上「新建设备」显示部署提供的 OpenCode 模板和规格，用户填写设备名称后创建并启动。设备列表显示名称、Provider 与运行状态；已就绪设备可以跳转到 Code 草稿并预选。在原 Provider 下拉框可按显示名选设备，同一账号切换已授权的云端项目仍可选用。

设备的登记和启动以账号环境为范围。Code 项目继续决定会话的文件工作区与授权，不参与设备的登记或名称唯一性。设备只挂当前账号的工作区根与各自的 Provider 状态及配置，沿用账号共享执行的物理挂载边界。两个设备各自持有原生会话状态，通过已授权的 Code 项目访问相同账号下的项目文件。

## 接入契约

- `cloud.runtime.list` 返回账号默认运行时、有名设备及部署模板。设备有稳定的 `runtime_id`，同一个创建标识在当前账号环境重试时指向同一设备。公开返回值包含名称、资源规格、准入、状态等展示字段。
- `cloud.runtime.create` 接收名称、模板标识与创建标识。登记记入现有 Provider 绑定库，启动委托账号 Worker，同步模型后走既有分配池和认证健康检查。容器启动失败可在列表重试同一绑定。Gateway 的设备专用中继在无项目启动时只接收模型同步和健康检查。
- `cloud.runtime.start` 以设备 ID 重试启动。设备回收后仍保留登记、名称及 Provider 状态。Code 发送可按需恢复设备，分配、并发、对账和回收沿用既有每绑定锁和代次语义。
- `session.create` 沿用执行 Provider、模型和项目字段，额外提交设备 ID。Worker 在账号签名中继校验当前设备、项目与目录，再把设备 ID 写入会话元数据。前端在发送前确认响应携带同一 ID，续聊与恢复复用持久绑定。
- 旧默认设备与旧会话沿用既有中继路径。新设备需要匹配版本的 Gateway 与 Worker。第一阶段使用现有 OpenCode 部署配置中的唯一模板。

## 验收条件

1. 浏览器在「运行时」创建有名 OpenCode 设备。创建请求不包含项目标识，弹窗仅显示模板和设备名称。
2. Code 普通会话的原 Provider 下拉框在两个云端项目中显示并可选同一设备 ID，发送后会话记录该设备。
3. 独立启动无需先创建项目或会话。重复/并发登记不重复分配，首次发送与准备好的设备复用同一绑定，历史续聊保留同一原生会话。
4. 不同设备拥有各自的原生状态。跨账号选用和不受权项目中继被拒绝。

## 2026-11-22 方案确认

用户确认运行时页面使用「新建设备」，Provider 沙箱作为独立资源管理，本设计据此将登记与启动改为账号级。前序方案的项目菜单快捷申请由运行时页面的创建入口接替。首批对接 OpenCode，沿用现有会话和项目授权。

## Codex 扩展（2026-11-22）

用户确认 Codex 与 OpenCode 使用同一弹窗和「创建并启动」按钮。选择 Codex 模板时，复用 Code 的模型下拉框和当前登录账号的模型目录。Worker 按 Codex 模型协议和部署端点准入筛选可选模型，账号默认模型符合条件时预选。用户可以改选账号里的其他兼容模型。

创建只提交所选模型的目录 ID。Worker 在登记前验证模型归属与兼容性，登记后重试同一绑定时沿用所选 ID。成功准备后，Code 普通会话按设备名称选用时自动应用该模型。旧客户端省略模型 ID 时沿用账号默认模型。

Codex 复用账号签名 WSS、既有固定路由和元戎生命周期。无项目请求仅可准备当前账号已登记的设备，分配与健康探测不创建聊天会话或回合。选择和发送仍检查项目目录；会话及状态卷按设备隔离。历史 Codex 会话继续按原账号绑定恢复。

发布验收覆盖两个云端 Code 项目选用同一命名 Codex 设备、首次真实回复、元戎和 Docker 物理回收后的原会话续聊，以及存量 Codex 与 OpenCode 会话回归。
