---
id: F_20261122_0955_managed-runtime-devices
title: 运行时创建独立 OpenCode 设备
type: F
author: null
author_email: null
author_note: 当前任务 worktree 缺少有效的 Git 署名。
modules: [gateway/extensions/cloud_workspace, gateway/services, jiuwenswarm/runtime, jiuwenswarm/server, jiuwenswarm/channels/web/frontend]
files:
  - gateway/services/cloud_opencode_pool.py
  - gateway/services/cloud_opencode_relay.py
  - gateway/services/cloud_provider_allocation.py
  - gateway/services/cloud_codex_pool.py
  - jiuwenswarm/server/runtime/agent_adapter/providers/opencode_managed.py
  - gateway/extensions/cloud_workspace/extension.py
  - jiuwenswarm/runtime/session_provisioner.py
  - jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py
  - jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudRuntimePanel.tsx
  - jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ExecutionPicker.tsx
designs: [D-20261122-0920-managed-runtime-devices]
---

# 运行时创建独立 OpenCode 设备

现有任务分支 `codex/opencode-cloud-runtime-ui` 从 `edbcaca624b29c267f39841328239027bab55daf` 继续，在保留前序未提交改动的工作树上实现。实际项目属于 Code 会话的访问上下文，命名设备不归项目所有。从「运行时」新建设备时复用部署提供的 OpenCode 镜像和资源档位，账号数据库记录稳定设备 ID，账号 Worker 同步模型并走原分配池的认证就绪链。旧默认设备继续保留原绑定。跨设备隔离的是 OpenCode 自身的配置和会话状态，账号工作区文件沿用已有共享范围。

普通 Code 会话从原 Provider 下拉框按名选用。Session 创建时校验并固化设备 ID，运行中与恢复时均使用该绑定。设备启动未确认时可在列表重试。较旧的 Worker 未回传设备 ID 时，Web 不提交首条消息。

## 验证

- 前端源码组件在 Chrome 中以受控 RPC 完成项目无关的创建，表单无项目控件，创建请求只有模板、名称、幂等标识。在两种项目上下文中从原 Provider 下拉框选中「OpenCode · 日常开发」，两次使用同一设备 ID。证据为同级任务目录的 `evidence/runtime-devices-chrome.log`、`evidence/runtime-devices-create.png` 和 `evidence/runtime-devices-provider-menu.png`。
- 真实 Worker、签名中继、OpenCode 和本地 Qwen2.5-0.5B-Instruct 验证。Bubblewrap 进程是元戎接口的本地替身。设备在创建项目及会话前启动，首发与追问收到真实回复并继续使用同一设备、第 1 代分配和原生会话。停止时实验 SSE 由服务器关闭超时触发取消，Provider、Worker 和模型进程均回收。见 `evidence/runtime-devices-local-opencode.log`。
- Gateway 分配、签名中继、账户 API、路由、模型准入与端云桥定向回归 116 项通过。范围覆盖并发登记、同名拒绝、跨账号拒绝、两项目共用设备、不同设备的原生会话边界和旧绑定。早先一次更广的云工作区测试在物理资源套件阶段超时，定向复跑通过。见 `evidence/runtime-devices-focused.log`。
- 前端原 Provider、会话创建和云工作区 3 个测试文件通过，生产构建通过。会话创建、恢复及元数据定向回归 56 项通过。首轮在独立 Provider 环境因缺 Native Core 发生 13 项安装前提错误，在已有锁定 Core 与 Protocol 环境完整复跑通过。见 `evidence/runtime-devices-web-build.log`、`evidence/runtime-devices-session-locked.log` 和 `evidence/runtime-devices-session-source.log`。
- 测试解释器使用 `platform-opencode-model-admission-release-20261121/platform/.venv/bin/python`。实际导入 Platform 源码来自本任务工作树，Protocol 安装来源核对为 `2a0457e5e01152e9ca5f8afdffd84716227046ca`。Native Core 锁定 `e089198835426cd7681761b0cc278670cd83031f`，实际 Provider 独立环境没有安装 Native Core。依赖锁保持原样。管理工作区旁的 Core 与 Swarm 检出分别为 `de8d4f38bb624b608af4a5c76b5c5c82d47d3360` 和 `24f29148193b5b590fe9f4b3e21f779c87253e5e`，两者已跟踪文件干净，未作为本次运行依赖。
- 本地阶段的工作区改动未提交或推送。尝试读取远端时本地 DNS 无法解析 GitHub，继续沿用既有任务分支。正式复验见下文。
- 设计与功能归档已更新。同步工具因仓库缺少 Git 署名未刷新索引，记录在 `evidence/runtime-devices-doc-index.log`。

## 正式节点复验中的工作区重连修复

第一轮在独立元戎/Docker 环境中，Chrome 成功创建设备并完成第一个项目的真实双轮会话。重载页面后，账号工作区的 `environment/ensure` 返回 401。验收账号的私有 `agent` 父目录仍为 `0700`，但 Worker 在初始化项目时已将 `agent/workspace` 改为 `0755`。Gateway 在重复准备环境时误将该子目录当作必须为 `0700` 的私有控制目录。第一次浏览器失败与原始回复记录在 `evidence/runtime3-formal-browser-initial.log`。

修复保留账号与 `agent` 等控制目录的私有检查，仅在缺失时创建 Worker 的工作区子目录。命名设备仍在分配前校验挂载源的规范路径。新增回归复现 Worker 调整子目录权限后通过原 `ensure` 重连，并确认仍使用原 Worker。包括该项在内的 117 项定向回归通过。见 `evidence/runtime4-formal-regression.log`。

## 修订候选的正式节点隔离验收

2026-11-22 在正式调度节点的独立作用域 `oc-named-devices-r2-20261122` 完成浏览器与物理容器对账。运行环境为元戎 SDK 与 Runtime 0.10.3、Docker 29.1.3、Chrome 146。Gateway 和 Worker 均安装来自此分支工作树的 Wheel，各核验 1661 个 Python 源文件与锁定 Protocol 来源。专用 Web 入口核对生产构建指纹。真实模型通过验收专用通道连接本地 Qwen2.5-0.5B-Instruct。部署、打包和推理记录见 `evidence/runtime4-formal-deploy.log`、`evidence/runtime4-formal-package.json`、`evidence/runtime4-formal-model-inference.log`。

| 场景 | 通过结果 | 证据 |
| --- | --- | --- |
| 浏览器独立创建设备 | 「运行时 → 新建设备」仅显示 OpenCode 模板与设备名称。创建请求仅提交名称、模板、幂等标识。Docker 容器到达就绪时，测试项目、平台会话和原生会话均为 0。 | `evidence/runtime4-formal-new-device.png`、`evidence/runtime4-formal-prepared.log` |
| 两个普通 Code 项目选用 | 在 `runtime-proof-alpha` 与 `runtime-proof-beta` 的原 Provider 下拉框均选择「OpenCode · 独立验收设备」。两次 `session.create` 的请求与回执确认同一设备 ID。第一个项目完成后重载浏览器，账号工作区通过原就绪链恢复。 | `evidence/runtime4-formal-provider-menu-1.png`、`evidence/runtime4-formal-provider-menu-2.png`、`evidence/runtime4-formal-browser.log` |
| 真实回复、续聊与物理对账 | 两个项目各两轮真实回复，追问分别回忆出 `cobalt blue` 与 `lime green`。同项目两轮保持同一平台会话和同一原生会话。两个项目的原生会话彼此独立，四轮共用创建时的同一个第 1 代 Docker 容器。 | `evidence/runtime4-formal-browser-receipt.json`、`evidence/runtime4-formal-after.log` |
| 验收资源回收 | 两次验收的 Provider、账号 Worker 和专用网络均已回收。隔离监听、浏览器代理和模型隧道已关闭。现网容器标识、镜像和配置摘要与验收前一致。 | `evidence/runtime3-formal-cleanup.log`、`evidence/runtime3-formal-cleanup-recovery.log`、`evidence/runtime4-formal-cleanup.log` |

## 与主线的 Codex 分配兼容

基于主线 `03ebde885443adcd7ffab890cffe10f367db39cd`，四处三方冲突同时保留两种 Provider 的路由和共用 TLS。命名、默认和已有项目中继均从部署 CA 建立证书验证。旧 12 列分配表由两种 Provider 调用的共用初始化器以单一事务升级，原绑定、分配代次、实例 ID 与会话归属保留。Codex 使用显式列名插入，空名称允许旧绑定和新建 Codex 分配共存。同账号 OpenCode 设备名仍唯一。回退 Gateway 使用兼容升级结构的版本。

候选定向回归覆盖带两种旧绑定的 SQLite、重启后新分配、保留原会话归属和回收后重用状态目录。云工作区与端云桥 426 项通过，另外 3 项验证中继 TLS 和三类 OpenCode 路径，Session 与两种 Provider 适配器 420 项通过，前端三组定向测试和生产构建通过。依赖仍固定 Core `e089198835426cd7681761b0cc278670cd83031f`、Protocol `2a0457e5e01152e9ca5f8afdffd84716227046ca` 和 Codex SDK 0.163.0，实际从既有锁定环境加载。

2026-11-22 本机 Docker 29.1.3 隔离验收在同一份升级后的旧库上完成 OpenCode 命名设备和 Codex 冷分配。真实账号 Worker 通过同一私有 CA 使用 OpenCode HTTPS 与 Codex WSS。两种 Provider 各用官方运行时和本地 Qwen 完成真实流式回复。回收后各启动第 2 代容器，沿用原状态卷、平台会话和原生会话 ID，并正确回忆首轮输入。测试适配器提供元戎分配接口并调用实际 Docker，未使用生产元戎调度或浏览器端到端入口。验收记录位于管理工作区 `artifacts/platform-opencode-device-integration-20261122/evidence`。
