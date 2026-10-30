---
id: B_20261030_1455_opencode-session-workspace-binding
title: OpenCode 会话项目目录绑定修复
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [agent_adapter]
files: [jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py]
designs: []
design_note: 用户确认对当前 S_02 会话目录契约的小范围修复，无独立设计。
---

# OpenCode 会话项目目录绑定修复

## 现象与根因

40657 Web Code 会话选择 deer-flow，Extensions/聊天报 `OpenCode session workspace must match its configured binding`。旧试点无条件要求 project_dir 等于启动 opencode.directory；N01～N04 自有服务已支持每会话目录，但保留了借用服务校验，且 HTTP 请求与装备解析仍回退全局目录。此前测试目录与启动配置一致，未覆盖原 UI 选择不同项目。

## 修复与契约

只修改 providers/opencode.py。自有 CLI 新会话以原 Swarm 传入 project_dir 创建，未指定时回退配置目录；已有会话省略目录沿用原绑定，显式换目录拒绝。路径必须为存在的绝对目录，按 resolve 规范化。借用 URL 模式继续要求匹配配置。HTTP（创建、审批、prompt、abort、delete）、SSE、Skill/MCP 解析及进程 cwd 使用同一会话目录；不重设全局默认，不关闭权限，不新增宿主接口、队列、UI 或 Core 依赖。冷恢复仍不在范围。用户已确认修复，无独立 D，依据 S_02 及原会话生命周期。

## 回归与版本

基线 Swarm 88fbdd2a1e771045118b1eabd493b071e5b64b69 加既有候选，修改前快照 workspace-binding-before-20261030。固定 Core e089198835426cd7681761b0cc278670cd83031f 不变。Python3.13.15；实际命令 cwd 为本任务 swarm。

- `.venv/bin/python -m pytest -q --no-cov -o log_cli=false`：原协调器、OpenCode、Plan、Provider选择、session_provisioner/provision_contract 六个文件146通过。日志 ../logs/workspace-binding-regression.log。
- `../venv-without-core/bin/python -m pytest -q --no-cov -o log_cli=false tests/unit_tests/agentserver/test_opencode_direct_adapter.py`：39通过。模拟传输验证两项目交错、省略目录、所有 HTTP 请求目录、装备目录、关闭、已有绑定拒绝变化、借用服务与非法目录。日志 ../logs/workspace-binding-nocore.log。
- `PYTHONPATH=. ../venv-without-core/bin/python ../workspace_binding_live.py`：真实官方 OpenCode1.18.18/glm-5.3，原 AgentRuntime.stream/控制入口，两个合成项目 A→B→A 的 pwd 和随机文件值均正确，工具原始结果独立断言，无 Core 导入，关闭后服务目录0。证据 ../evidence/workspace-binding-live-d61590f3.json；日志 ../logs/workspace-binding-live.log。
- 真实 Web→Gateway→Front→Worker→OpenCode：在原 Code UI 选择已有 deer-flow 项目及 OpenCode，下发仅 pwd 的只读请求，经允许一次后返回 /home/leewanlong/work_leewanlong/deer-flow 和 WORKSPACE_BINDING_OK。会话 web_1a18b9d5d7a_64a953596c26；同会话 Add file→Extensions 能展开（空安装列表 No results），没有绑定报错。这不替代完整插件安装验收。截图 ../evidence/workspace-binding-web.png、workspace-binding-extensions.png。

## 检视与边界

对开工文件逐项检视目录解析、HTTP/SSE、装备与删除路由、现有会话不变性；所有权仍属 Runtime，未发现本次范围未闭合问题。146为受影响回归，不代表全量或 stable。曾误用不存在的 AX 输入节点，未发送输入，随后按实际可见输入框发送；首次脚本写入路径错误未运行 Provider，修正路径后上述运行通过。修复已加载40657，保留原配置/历史，45277旧实例未升级。未提交、未发布。完整原生能力、冷恢复、Code Diff/撤销、第二 Provider 仍保持原边界。

防错模式：固定服务的默认目录不是所有新会话的授权目录；项目选择、装备、传输与进程应共享会话绑定，不能只放开一处比较。S_02 和中英文说明已同步。

文档检查：sync_documents.py 成功更新22份源文档索引，专项HTML成功生成20节。全仓 check-docs.py 仍因候选既有缺失 docs/design/PLUGIN_ARCHITECTURE_PRODUCT_FEATURES_V3.md 失败，不记为通过；未扩大范围修复。
