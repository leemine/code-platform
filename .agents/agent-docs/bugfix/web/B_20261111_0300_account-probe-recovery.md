---
id: B_20261111_0300_account-probe-recovery
title: 账号探测短暂故障容错与串行自动恢复
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/channels/web]
files: [jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudWorkspaceGate.tsx, jiuwenswarm/channels/web/frontend/src/services/organizationCredentialEvents.ts, jiuwenswarm/channels/web/frontend/tests/cloudWorkspace.test.mjs]
designs: []
design_note: 补回 codeswarm 既有恢复行为，不新增账号或执行链。
---

# 根因与范围

平台登录提炼遗漏 codeswarm App 中已有的探测失败串行自动重试。一次传输失败即卸载工作界面并停在手动重试页，是已确认的恢复缺陷。此前非计划内公网探测失败的底层触发原因未复现，不能把此缺陷当成该网络故障的确定根因。

# 修复

同一 10 秒期限内对网络错误及 502/503/504 重试一次，成功保留工作界面；持续失败后每次完成再等待 2 秒自动探测。延迟响应受原 generation 保护。恢复仍以服务器新身份决定同账号原路由或换账号根路由。已确认云模式遇到 404 不回退本地；准备完成后的账号复核失败也进入账号自动恢复，环境创建失败仍保留显式重试。诊断不含凭据、身份、响应正文或原异常内容。服务端逐请求鉴权、SDK、Runtime、Router 和创建回收流程不变。

# 验证

原候选 3a68ffa 上修改。前端 24 项云入口测试、5 项账号 store 测试通过；覆盖瞬态故障保持原 DOM、长响应不重叠、持续故障自动重试、超时 abort、401/403 与非法身份不重试、已知云端点消失不降级及原退出/就绪约束。生产构建通过。真实隔离 UI 的最终版本、故障注入证据与 stable/按锁核验结果统一见管理仓 PLATFORM_CLOUD_UI_ACCEPTANCE_20261110；单测不替代端到端验收。
