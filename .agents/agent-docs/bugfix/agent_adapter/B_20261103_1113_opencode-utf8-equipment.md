---
id: B_20261103_1113_opencode-utf8-equipment
title: OpenCode equipment 跨平台 UTF-8 编码修复
type: B
author: leewanlong
author_email: 68536087@qq.com
modules:
  - jiuwenswarm/server/runtime/agent_adapter
files:
  - jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py
  - jiuwenswarm/server/runtime/agent_adapter/providers/opencode_equipment.py
  - tests/unit_tests/agentserver/test_opencode_equipment_encoding.py
designs: []
design_note: 现有适配层文件编码的小范围修复，无独立设计。
---

# OpenCode equipment 跨平台 UTF-8 编码修复

## 现象与根因

2026-11-03 10:55 Windows 桌面会话 `web_1a19f54e7b6_2853ef4902b1`
使用 opencode-direct，约 1.62 秒后失败，用户看到 GBK 无法编码 U+26D4。
现场临时目录 session-62u4cohl 的 skills/2/SKILL.md 为零字节，
对应 baoyu-image-gen，安装包原文包含该字符。现场未取得异常堆栈。

适配层 configure 复制 Skill 后重新写入规范化文档，未指定编码，
Windows 的 GBK 默认编码无法保存该字符。清单、persona 的默认编码读取亦有同类风险。

## 修复决策

Skill 与配置写入、清单与 persona 读取均显式指定 UTF-8。
保持 Skill 选择、权限、会话生命周期及原始二进制资源复制行为。
不删除文档字符，不修改系统区域设置或外部 Provider 源码。

## 回归证据

候选基线 504254ba27b46fce37c0f1189354496f8c5265ae，分支 codex/opencode-utf8。
cwd 为 D:/work_leewanlong/code-platform/.worktrees/opencode-utf8；
解释器为该目录 .venv/Scripts/python.exe，基于 C:/Python314/python.exe（3.14.0）。
测试直接从该 worktree 加载实际 equipment/service 模块；模型配置及 Provider 启动使用替身，未导入 Core。

在 Path.open 边界模拟默认 GBK，输入中文、U+26D4、emoji：
旧基线两个用例均失败，分别为 Skill 写入 UnicodeEncodeError 和清单读取 UnicodeDecodeError；
修复候选两个用例通过，核验 Skill 原文、二进制资源、配置及 persona 内容。

命令：`.venv/Scripts/python.exe -m pytest tests/unit_tests/agentserver/test_opencode_equipment_encoding.py --confcutdir=tests/unit_tests/agentserver -q -o addopts=''`。
默认 conftest 依赖 portalocker，本次隔离测试通过 confcutdir 排除应用环境初始化。
未运行格式化或静态检查；未进行真实 OpenCode 模型调用、macOS/Linux 实机验证、桌面重打包与安装验收。

## 防错模式与遗留

适配层可移植文本文件读写固定 UTF-8，不依赖平台默认编码。
本次未改变公开接口，无需更改渠道协议。桌面安装版需重新构建交付后验证原会话场景；
未授权提交或发布，安装目录保持原状。

## Windows 桌面项目目录真实回归（2026-11-03 11:25–11:26）

经用户授权，在 Code 模式通过目录选择器选择 `D:/work_leewanlong/agentscope`，
执行引擎 OpenCode、模型 deepseek-v4-flash，原样输入“请分析整体架构和功能”。
会话 `web_1a19f70dc07_c1cd9bf04da4` 的 metadata 确认 project_dir 与 opencode-direct。
界面展示对该目录的实际 read 工具结果，随后输出 AgentScope 分层架构、核心模块和功能分析。
history 包含 33 条 chat.tool_call、33 条 chat.tool_result、1 条 chat.final，
最终 chat.request_completed.status 为 success。
临时目录 session-vh1h5xo6/skills/2/SKILL.md 为完整 UTF-8 文本，20682 字符，
U+26D4 位于 1830，与原始报错位置一致；不再发生 GBK 写入错误。

验收方式为隔离桌面副本 `validation/desktop/WorkSwarm.exe`，
复用安装版冻结 Python 3.13 运行依赖，以其既有 .py 入口加载本任务两个适配模块，
原生 OpenCode CLI 未修改。Front 与独立 Runtime Worker 均经 candidate_agent.py 启动；
进程核对 Worker PID 19916，profile 为 opencode-utf8-validation，避免旧 Worker 复用。
候选模块 SHA256：equipment `6772f44b02a07ad3f8765edce5bbcf37a931cda14046bb58d6d35237937018af`，
service `9b4d5065ce4d98503bf84b185520acb4ee5934793a8cd18f9653ecd491dba147`。
验收启动器和桌面副本属于本地验证产物，不进入提交；正式安装包尚未重新构建。

保留失败事实：11:20 的 archon 会话仍由旧独立 Worker 执行，出现同一 GBK 错误；
该次不算候选回归，随后修正验收运行来源。桌面曾由用户 Esc 中断，
取得明确恢复授权后继续完成上述 agentscope 场景。
