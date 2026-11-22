---
id: F_20261122_1551_named-codex-devices
title: 运行时创建并启动命名 Codex 设备
type: F
author: null
author_email: null
author_note: 当前任务 worktree 缺少有效的 Git 署名。
modules: [gateway/extensions/cloud_workspace, gateway/services, jiuwenswarm/runtime, jiuwenswarm/server, jiuwenswarm/channels/web/frontend]
files:
  - gateway/services/cloud_provider_allocation.py
  - gateway/services/cloud_codex_pool.py
  - gateway/services/cloud_codex_relay.py
  - gateway/extensions/cloud_workspace/extension.py
  - jiuwenswarm/server/runtime/agent_adapter/providers/codex_device.py
  - jiuwenswarm/server/runtime/agent_adapter/providers/codex.py
  - jiuwenswarm/runtime/session_provisioner.py
  - jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudRuntimePanel.tsx
  - jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ExecutionPicker.tsx
designs: [D-20261122-0920-managed-runtime-devices]
---

# 运行时创建并启动命名 Codex 设备

基于 PR #61 合入树 `eb8ea50f1f368f704684d2a27602c2337326b69e` 在独立分支 `codex/named-codex-runtime-20261122` 实施。[当前契约](../specs/gateway/S_01_cloud-account-instance.md) 记录公共目录、绑定和回收规则。[原 OpenCode 实施记录](F_20261122_0955_managed-runtime-devices.md) 保留其发布证据。

## 实施决策

- 复用运行时弹窗和 Provider 下拉框；模板由各 Provider 从部署配置和账号准入投影。登记共用同一 SQLite 表和事务，名称按账号及 Provider 唯一。旧绑定和原生会话 ID 沿用现有记录。
- Codex 延用现有签名 WSS 路径，区分项目无关的设备准备、项目校验和会话流。Worker 使用账号模型目录解析默认模型，Gateway 复用模型端点准入、就绪探测和元戎分配。创建不产生原生会话；同一设备后续会话复用准备时确定的模型、独立状态卷和分配锁。失败可以从列表重新启动同一登记。
- Code 会话固化 `runtime_id`，选择命名 Codex 时自动应用设备模型。Gateway 限制同一平台会话在同账号下只能占用一个 Codex 绑定。适配器恢复也按设备和原生线程确认归属。空闲回收沿用物理确认与代次推进，传统 Codex 选项继续使用原账号环境绑定。

## 验证

- Python 3.13，运行候选源码。外部环境加载锁定 Protocol `2a0457e5e01152e9ca5f8afdffd84716227046ca` 和离线核对哈希的 Codex SDK/CLI 0.163.0。带 Core 环境核对实际非 editable 来源为 `e089198835426cd7681761b0cc278670cd83031f`。
- 回归覆盖 Gateway 目录与重试、签名中继、两项目选用、跨设备约束、旧分配表升级、回收后的绑定和状态卷复用、旧 Codex 选项及会话恢复。端到端验收使用正式元戎和真实模型，属于独立发布关口。
- 本地 React/jsdom 验证共用弹窗选择 Codex 发起无项目创建，以及原下拉框在两个项目按名称选用设备并设置绑定模型。Provider、运行时应答和会话模型前端定向套件及生产构建通过。

外部接入与回归 247 项通过，带 Core 会话创建 30 项通过。外部用例用受控分配和模型数据核对实际绑定、路由、状态及回收；本候选的真实元戎和模型回复属于正式验收。原始记录位于本任务工作区上级目录中的 `regression.log`、`session-provision-native.log` 和 `web-regression.log`。

索引工具执行时发现本地 Git 缺少有效作者配置，当前特性记录保留未署名说明，生成索引待有正式身份后刷新。

本地 `code-platform/main` 工作区干净，HEAD 与上述基线一致；候选尚在开发 worktree。管理仓的 `code-core` HEAD 为 `de8d4f38bb624b608af4a5c76b5c5c82d47d3360`，`codeswarm` HEAD 为 `24f29148193b5b590fe9f4b3e21f779c87253e5e`，两者跟踪文件均干净。这两份源码 checkout 未作为候选依赖来源。管理仓文档校验仍发现历史条目缺失的归档链接，本次记录保存在候选工作区。

## 创建时选择账号模型

Codex 设备模板声明模型选择能力时，运行时弹窗复用 Code 的 `ModelPicker`。模型名称和厂商来自当前账号的 `models.list`，兼容范围由账号 Worker 按 Codex 协议与 Gateway 端点准入确认。可用的账号默认模型预选。创建请求传模型 ID，登记及后续启动沿用此 ID，选用设备的 Code 会话继承绑定。旧设备继续读取已持久化的模型 ID，旧客户端省略 ID 时按原默认模型路径启动。

候选工作区上级目录保留本次日志。Python 3.13 在原锁定 Protocol 和 Codex SDK 下运行 Gateway、Worker、两种分配池及会话协议的 248 项回归，通过结果见 `model-picker-regression.log`。使用锁定 Core 的会话创建 30 项通过，见 `model-picker-native.log`。Web 通过 `npm run test:execution-provider`、`npm run test:web-client-runtime-ack`、`npm run test:agent-group-runtime-selection` 以及 `npm run build`，见 `model-picker-web.log`、`model-picker-build.log`。最终 Provider 套件单独复跑 8 项，见 `model-picker-provider-selection.log`。

本地 Chrome 146 加载候选 UI，通过模拟账号目录验证原生弹窗内模型默认值、兼容项、改选和无项目创建请求，见 `model-picker-browser.log`。带下拉框的候选尚待正式元戎部署和真实模型验收。
