---
id: B_20261031_1459_codex-cancel-session
title: Codex用户取消保留原生Thread并复用中断回执
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/runtime/agent_adapter]
files: [jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, tests/unit_tests/agentserver/test_codex_direct_adapter.py, docs/zh/FAQ.md, docs/en/FAQ.md]
designs: []
design_note: 用户确认继续修复已复现的取消后续聊问题，沿原Runtime和官方SDK，不扩展冷恢复或新执行流程。
---

# 现象与根因

AgentRuntime.cancel_request先发送原生turn_interrupt，随后原coordinator收敛生产任务。原Codex适配器在未消费到terminal时总是清理整个Session：关闭客户端、删除私有CODEX_HOME、移除Thread映射。等待授权或工具已运行两场景都能停止，但下一轮因已有历史且无Session被明确拒绝。

旧FakeClient取消后立即给interrupted终态，测试只断言审批释放，没有通过真实Runtime取消再续聊。原验证108项通过仍遗漏该时序。

# 修复与取舍

在现有Session增加本轮cancel_acknowledged回执标记，每个Turn开始重置；仅原生turn_interrupt成功返回后置true。finally复用已经确认的用户中断，避免第二次中断未获确认导致误清Session；已确认用户取消保留原客户端、Thread和私有目录。Reader、原生通知订阅、待批Future仍按原流程释放，active恢复false。

中断失败、非用户取消的异常流退出不保留Session；显式关闭/驱逐仍执行原cleanup。未返回turn_id时不假定已停止。不新增重连/调度/持久化映射，不重放文本冒充上下文，不修改外部SDK或改变权限/TLS。

第一版仅在finally重新中断成功时保留会话，确定性测试通过但真实39d5f1cd仍失败；首次中断成功不意味着第二次必然能确认，最终必须复用首次回执。该失败保留，未冒充成功。新回归模拟第二次中断拒绝，并断言每次取消仅发送一次中断。

# 验证

- 新增两项真实AgentRuntime入口确定性用例，旧实现均在client已关闭断言失败；修复后通过，验证原Thread下一Turn、close删除目录。
- SDK传输fake按原生SDK订阅关闭语义唤醒reader，避免旧reader窃取新Turn通知；不是修改SDK源码。
- 中断失败时用户取消/非用户关闭、以及中断成功但无用户取消的关闭均保留原清理保护。
- 最终Codex/OpenCode/Claude定向127通过（13.94s）。未改公共Runtime、其他适配器、前端或依赖锁。
- 真实Codex官方SDK0.163.0、无Core、TLS开启、默认权限：报告516e1165两场景均保留原Thread并无工具复述随机口令，待批目标未写，工具确已开始后取消，32秒后无迟到写入；close后临时会话目录和任务进程0，凭据副本已删。

候选artifacts/codex-cancel-session-fix-20261031 / codex/codex-cancel-session-fix，8910f059+继承P1/生命周期31文件。产品改动仅codex.py +10/-3；另有测试和文档。本次为Runtime入口验收，未升级原UI/桌面，冷重启和非editable按锁发布尚未验证，未提交推送。完整证据见管理候选docs/verification/CODEX_CANCEL_SESSION_FIX_20261031.md。

# 独立发布候选复验：阻断合入

本次从远端前置PR#1的8910f059提取独立发布候选，不含Claude/模型配置等P1改动。重新真实验收44ef5401：两场景原Thread续聊成功，待授权目标未写；但工具已运行取消后late_write_absent=false，命令在取消后仍完成迟到写入。当前不能证明中断回执足以保证底层命令停止；先前516e1165通过不能推广到所有时序。此问题尚待定位和修复，不应合入或发布当前候选。

前置PR#1 stable重跑也受GitHub付款/Actions额度阻塞，steps=0。独立PR保持draft，不绕过CI、不混入未发布P1、不将本地测试当作发布门禁通过。
