---
id: F_20261122_0213_opencode-cloud-runtime-ui
title: Code 普通会话显示 OpenCode 云运行时名称
type: F
author: null
author_email: null
author_note: 当前任务 worktree 尚未配置有效的 Git 署名。
modules: [gateway/extensions/cloud_workspace, gateway/services, jiuwenswarm/channels/web/frontend]
files:
  - gateway/extensions/cloud_workspace/extension.py
  - gateway/services/cloud_opencode_pool.py
  - gateway/services/cloud_opencode_relay.py
  - jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/useProjectRuntime.ts
  - jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ExecutionPicker.tsx
designs: [D-20261122-0144-opencode-cloud-runtime-ui]
---

# Code 普通会话的 OpenCode 云运行时

2026-11-22 第一批实施。Gateway 为当前账号的具体云项目读取独立 OpenCode 的名称和绑定准入。Web 在 Code 普通会话的原 Provider 下拉框补充名称，选择值保持 `opencode-direct`。项目切换、账号切换和重连刷新显示。旧 Gateway 维持原选项。已创建的会话继续使用原绑定与历史。

在现有 `opencode_provider` 配置下用可选 `display_name` 提供名称。缺省值由客户端本地化。查看选项只读现有账号、项目及绑定，首发沿用原有 `session.create`、`chat.send`、账号 Worker 和 OpenCode 中继。名额、就绪、容器与物理回收规则由已存在的池负责。侧栏「专家」和「技能」之间的入口、云项目菜单的显式设备申请留在后续阶段。

[已确认设计](../designs/active/D-20261122-0144-opencode-cloud-runtime-ui/design.md) · [Gateway 契约](../specs/gateway/S_01_cloud-account-instance.md)

## 实际执行与证据

候选为本地 `codex/opencode-cloud-runtime-ui` 的工作区改动和基线 `edbcaca624b29c267f39841328239027bab55daf`。Python 3.13.15 使用同一 `uv.lock` 的已有独立 Provider 环境。实际 Platform 代码来自候选工作树，安装的 Protocol 固定于 `2a0457e5e01152e9ca5f8afdffd84716227046ca`，此环境未安装 Native Core。前端复制同锁定 npm 依赖到任务目录。

| 范围 | 命令或证据 | 结果 |
| --- | --- | --- |
| Web Provider、云环境和工作区回归 | `node --test tests/executionProviderSelection.test.mjs tests/cloudEnvironment.test.mjs tests/cloudWorkspace.test.mjs` | 3 个测试文件通过，覆盖命名、原 Provider ID、关闭准入及旧 Gateway 回退 |
| 前端生产构建 | `npm run build` | 通过 |
| Gateway OpenCode 分配池、中继与云工作区 | `pytest -o addopts= -q test_cloud_opencode_pool.py test_cloud_opencode_relay.py test_cloud_workspace.py` | 85 项通过，确认跨账号拒绝、关闭准入允许原绑定、读取无分配 |
| 隔离 Worker 与真实模型 | `evidence/local_acceptance_plaintext.py`、`evidence/local-acceptance-plaintext.log` | 本地签名中继调用 OpenCode 1.18.18。查询状态和创建平台会话时启动次数为 0。首条 `chat.send` 启动 1 个实例并取得真实回复。第二条沿用同一平台 ID、原生会话 ID 和第 1 代绑定，回答「Your favorite color is cobalt blue.」。原 `history.get` 查到两轮回复 |

证据位于任务目录同级的 `evidence/`。真实模型使用 llama.cpp b9354 与 Qwen2.5-0.5B-Instruct Q4_K_M，模型文件 SHA-256 为 `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`。小模型验证使用纯文本 ChatML 模板，OpenCode 沿用原审批配置。初次本机验收以 Bubblewrap 隔离进程提供元戎接口，复用真实候选 Worker、E2A 请求和签名中继。

最初使用带 `..` 的数据目录触发现有私有存储路径检查，基线同样复现。规范化路径后整组通过。文档索引工具因本仓缺少 Git 署名而中止。

## 正式节点的隔离部署验收

2026-11-22 在正式调度节点 DS7449 的专用作用域 `oc-runtime-ui-20261122` 部署候选。元戎 SDK 与 Runtime 0.10.3，Docker 29.1.3。使用正式部署当前的独立 OpenCode 镜像 `sha256:ace00f88cd7e23d607254c6fbc3602c2ceba9a9369d5c1bbfbc1de6051f543bb`。Gateway 和 Worker 从本分支工作树制作 Wheel 装入依赖锁一致的镜像，装盘后逐个核验 1,659 个应用 Python 文件，并核对实际 Web 根页面指纹。公开入口继续由原部署服务。浏览器经任务专用 HTTPS 监听访问候选，真实模型由本地 Qwen 推理服务通过受控隧道提供。

| 验收项 | 实际结果 | 证据 |
| --- | --- | --- |
| 真实浏览器打开 Code 普通会话 | Chrome 146 在原 Provider 下拉框及选择后显示「OpenCode · 正式验收沙箱」 | `formal-provider-menu.png`、`formal-browser.log` |
| 首次发送冷启动 | 发送前独立账号有 Worker，Provider 绑定和容器均为 0。浏览器发出第一条消息后约 2.7 秒，Docker 创建独立镜像容器，绑定为第 1 代 | `formal-pre.log`、`formal-after.log`、`formal-browser-receipt.json` |
| 两轮真实回复和同会话续聊 | 浏览器收到 44 个 `chat.delta`，第二轮回复记住 `cobalt blue`。两次发送使用同一个 Web 会话 ID，OpenCode 原生数据库只有一个会话，其中两轮均完成。容器和绑定代次一致 | `formal-continuation.png`、`formal-browser.log`、`formal-after.log`、`formal-model-inference.log` |
| 资源回收和正式入口复核 | 元戎与 Docker 确认测试 Provider 已删除，Worker 确认物理删除，独立网络已移除。现网 Gateway 与 Edge 的实例和配置摘要与验收前一致 | `formal-cleanup.log` |

首个部署包补齐了现行 Docker 边界需要的运行时资产模块，随后通过独立 Web 进程承载实际生产构建。早期浏览器尝试发生在发送前。候选包、启动日志和原生数据库核对见任务证据目录。

## 第二批：左栏运行时与新建云端设备

按已确认方案，左栏在「专家」和「技能」之间展示当前云账号的「运行时」。页面读取名称、Provider 和当前绑定状态。Code 新对话选定云端项目后，原项目菜单提供「新建云端设备」。Gateway 验证账号、项目和准入，Worker 复用首发的模型同步、签名中继及健康确认。新设备与首发使用同一账号共享绑定和原分配锁。申请状态通过原 Provider 元数据刷新，设备与会话历史不增加独立存储。

| 验证 | 结果 |
| --- | --- |
| 定向回归 | Gateway、OpenCode 与模型准入 102 项通过。端云桥 9 项通过，覆盖无选择器的运行时列表和带项目地址的申请。3 个前端测试文件与生产构建通过。 |
| 真实 Worker | 本地签名 E2A 用真实 OpenCode 1.18.18 和 Qwen 验证显式申请后原生会话数量为 0。随后创建并发送的两轮沿用同一绑定、同一代实例和原生会话。 |
| 正式节点隔离浏览器 | 专用范围 `oc-runtime-devices-20261122`，元戎 0.10.3，沿用正式部署当前的 Docker Provider 镜像。候选 Wheel 检查 1,661 个应用 Python 文件与 Web 根页面指纹。真实 Chrome 确认导航顺序、返回聊天保留项目与已输入草稿，并从云端项目菜单启动设备。启动后原生会话与平台会话均为 0，运行时概览显示「已就绪」。 |
| 选用与真实发送 | 浏览器再申请同一项目复用第 1 代 Docker 容器。原 Provider 下拉框可选「OpenCode · 正式验收沙箱」。两轮真实回复使用同一个 Web 会话和原生会话，Docker ID、绑定和代次与设备申请时一致。 |
| 回收 | 元戎和 Docker 确认测试 Provider 已删除，Worker 完成物理删除，专用网络移除。正式 Gateway 与 Edge 实例及配置摘要复核通过。 |

第二批证据位于同级 `evidence/` 的 `runtime2-*` 文件。菜单测试在返回聊天后等待原目录加载完成再选择。挂载范围、发布边界和回收仍沿用原元戎分配链。
