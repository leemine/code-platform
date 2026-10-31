---
id: B_20261031_1142_claude-tool-result-metadata
title: Claude 工具保护错误的非结构化结果兼容
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/runtime/agent_adapter]
files: [jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, tests/unit_tests/agentserver/test_claude_direct_adapter.py]
designs: []
design_note: 用户授权真实Runtime验收发现的适配缺陷，最小修复不改变已确认架构。
---

# 现象与根因

真实Bash命令被官方工具保护拒绝，原生附加结果不是字典，宿主读取exit_code触发AttributeError并关闭SDK；后续cancel遇到CLIConnectionError。不能把这个映射失败当TLS错误，也不能把正常原生拒绝判成外部保护问题。SDK注解没有保证原始消息的运行时形态。

# 修复与验证

仅对dict读取原生整数退出码；其他形态保留unknown，正文/is_error照常进入历史。官方源码、SDK、CLI和保护不变。产品+2/-1，测试+24/-1。新增Facade回归修复前2失败/2通过，修复后全14通过；最终真实Runtime7项预定场景及保护错误后取消通过。已启动命令取消先核对STARTED副作用，再观察32秒无迟到写入，历史cancelled。

候选8910f05+dirty、Python3.13.15、官方SDK0.2.115/CLI2.1.206、无Core；来源和全部旧失败保留于管理候选docs/verification/CLAUDE_MAIN_AGENT_TASK1_20261031.md及对应evidence目录。本轮是Runtime入口验收，不代表UI/按锁发布/安装包已验。任务前dirty保留，未提交推送。
