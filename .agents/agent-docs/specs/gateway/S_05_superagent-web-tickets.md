---
id: S_05_superagent-web-tickets
title: SuperAgent Web 工单插件契约
type: S
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway/extensions/superagent]
files: [gateway/extensions/superagent/extension.py, gateway/extensions/superagent/api.py, gateway/extensions/superagent/workbench.py, gateway/extensions/superagent/service.py, gateway/extensions/superagent/platform_executor.py, gateway/extensions/superagent/orchestrator/main.ts]
---

## 装配与所有权

- Gateway 显式启用应用插件，登记一个非默认 Code 项目及其可信账号清单。Web 写接口校验同源，所有读写逐次校验身份、试点成员与目标工单的归属。
- SQLite 由每个 Gateway 数据目录内单一协调进程写入。固定版本的 SuperAgent Engine 管理 Trigger、Ticket、Assignment 和输入投递，事务同时持久化领域状态和执行意图。平台 Session 和 OpenCode 原生 Session 的关系由平台 Runtime 保存。
- Router 通过平台声明式 Agent Process CLI 使用配置模型和空工具清单。输出通过结构校验后才能接单、忽略或关联。关联目标来自当前用户的候选工单，再由 Core 校验有效委托。
- 创建 Worker 会话时绑定 `opencode-direct`，并读取平台返回的项目 ID 和目录。属于该工单的每个执行轮都显式带回该目录，Worker 复用同一会话。项目目录由服务端绑定。Workbench 首条消息可引用服务端目录中的资产版本、章节和用例，Worker 收到提交时固定的正文。

## 原界面与会话

- 网关发布原管理面板和 Workbench 两个入口。原管理面板展示当前账号的编排记录、线程及工单。原管理面板和 Workbench 均链接到 Ticket 已绑定的 WorkSwarm Session。工单验收入口仅随 `superagent.acceptance_page: true` 发布。
- Workbench 新话题按正文送 Router。已有话题根据账号和话题记录定位到原 Ticket，显式追问由 Core 直接投递。WorkSwarm 已绑定会话的人工文本走相同跟进接口。Router 只处理新请求，已绑定的跟进保持原平台 Session 和 OpenCode 原生 Session。
- Workbench 业务裁定属于 Worker 报告中的等待项，绑定有效的资产引用和注意事项 ID。工具许可和提问仍由 WorkSwarm 原生控件处理。
- 原面板和 Workbench 输入固定来源。Build 生成宿主适配产物。插件构建与运行使用 WorkSwarm、Node 和平台 OpenCode Provider。

## 执行与恢复

- 同一身份以同一请求键和相同正文重试时返回已登记结果，复用键提交不同正文返回冲突。首版每个试点目录最多允许一个 Worker 执行。
- 原生审批按身份、Ticket、Session 和交互 ID 关联。答复请求是单独的控制输入。原生审批卡按平台交互标识同步。重新进入会话会更新该插件的待处理卡，保留其他原生交互。Worker 完成依据原执行流的终态与合规结果；控制确认和流结束各自保留原语义。
- 停止请求撤回工单委托。Gateway 在派发前重查委托，等待 Runtime 的首条业务响应再并发停止已发出的执行。收到 Runtime 停妥确认后显示已确认停妥。控制应答失败或执行状态未知时保留核对状态。重启后继续派发已排队操作，已派发的未知 Worker 操作等待核对。已知原 Session 时，用户可显式重试未知的停止请求。
- Worker 报告通过原工单与 Workbench 话题展示。原渠道回报与主动规则触发属于后续范围。
