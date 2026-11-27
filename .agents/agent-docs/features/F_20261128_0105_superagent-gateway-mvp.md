---
id: F_20261128_0105_superagent-gateway-mvp
title: SuperAgent Gateway 工单与 OpenCode Worker
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway/extensions/superagent]
files: [gateway/extensions/superagent/extension.py, gateway/extensions/superagent/platform_executor.py, gateway/extensions/superagent/router_adapter.py, gateway/extensions/superagent/service.py, gateway/extensions/superagent/orchestrator/main.ts, gateway/extensions/superagent/orchestrator/sqlite.ts, pyproject.toml, MANIFEST.in]
designs: []
design_note: 用户在任务会话中批准实施，任务台账和 PNG 保存在管理仓。
---

## 实施

在 code-platform `6b1c9e73c54147253481657732a64e3caf34df0f` 的独立 worktree 实施。Gateway 应用插件装配 SuperAgent Engine、策略和 SQLite 端口。上游来源固定为 `6337fc823ce20251c8de8085948165c81aaa701e`，来源清单逐文件保留 SHA256。平台现有 Code Session 管理 OpenCode 的 Provider、模型、项目和原生会话生命周期。

Router 使用平台声明式 Process CLI。该入口可以为独立角色指定空工具清单和结构化输出，也保留平台模型解析和 Runtime 执行。Worker 使用 Gateway 原 Agent Client。平台审批一边提交独立控制输入，一边保持原 Worker 执行流；继续从同一流消费第二次审批和最终报告。项目目录取自平台创建会话的回执，首轮和续接都显式携带。

会话创建回执丢失时，协调器把操作和试点执行槽保留给核对。拿到原会话绑定时允许用户请求原 Runtime 确认停妥。没有已证实的会话 ID 时由试点管理员查平台记录。原渠道回报与主动规则触发后续实施。

提交前检视补上了两处停妥边界。Worker 派发前重查委托，停妥等待 Runtime 接手已发请求。协调器重启后，回执未知的停止操作允许对相同 Session 重试，Worker 执行仍保留待核对状态。Native stable 加入 Python 定向用例，Web stable 构建并测试 Node 协调器，同时核对 wheel 的插件资产。

## 验证证据

候选安装包、定向回归、浏览器场景和已经确认的执行副作用见管理工作区 `artifacts/superagent-gateway-mvp-20261128/evidence/summary.md`。测试环境使用隔离 Code 项目、平台锁定依赖、真实模型和系统安装的 OpenCode。审批面板由工单页面呈现，交互事件及工具授权由原有 Runtime 提供。

[完成态浏览器截图](../../../docs/assets/images/superagent-gateway-tickets.png)

[当前插件契约](../specs/gateway/S_05_superagent-web-tickets.md)
