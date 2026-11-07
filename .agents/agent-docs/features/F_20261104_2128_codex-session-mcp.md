---
id: F_20261104_2128_codex-session-mcp
title: Codex 会话显式选择 Streamable HTTP MCP
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/common]
files: [jiuwenswarm/common/external_adapter_factories.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex_mcp.py]
designs: []
design_note: 用户批准管理仓 PROVIDER_PLUGIN_DEPENDENCY_AUDIT_20261031 中 Codex 会话 MCP 方案，宿主只声明能力。
---

# Codex 会话显式选择 Streamable HTTP MCP

原 Web 扩展选择、Facade 装备解析、凭据与会话快照继续使用。Swarm 共享产品代码只增加工厂能力声明。适配器将选中连接转为原生配置，凭据经每会话 App Server 环境传入。原生运行端读回工具成功后，原宿主保存选择；切换时关闭旧连接并恢复同一个原生 thread。清空用原显式空列表。确认型原生 elicitation 使用原批准／拒绝通道，状态与工具结果进入原 Web 和历史。首批限已连接且提供工具的 Streamable HTTP，HTTPS 或回环 HTTP，静态请求头。OAuth、URL/复杂交互和插件／专家附带装备后续另议。

## 初始候选和验证（2026-11-04，历史）

基线 code-platform `1a9bc541e6d3d3f6e29c810eba1a3972e12b7679`，Python 3.13.15，锁定 Codex Python SDK／配套 CLI 0.163.0。无 Core 与 Native 均按原锁非 editable 安装，产品模块安装字节与工作树一致。Native 组合读取锁定 Core `e089198835426cd7681761b0cc278670cd83031f`。

- 两个环境用 `python -P -m pytest --import-mode=importlib -o pythonpath= --no-cov -q --tb=short`。外部 Provider、Facade、会话入口和不支持配置 300 项通过；Native 会话与资产兼容 219 项通过。
- `timeout -k 90 -s INT 350 .venv/bin/python -P ../verify_mcp_channel.py` 在 Linux 经原 Web WebSocket、Gateway、Front 与真实 Worker，使用锁定官方 Codex 和真实回环 HTTP MCP。受控 Responses 模型下逐轮验证未选无工具、批准一次产生一次调用、拒绝零调用、装载失败不请求模型且保留旧选择、清空后工具不在模型清单，Worker 重启后同一 thread、原角色与历史上下文仍可用。清空状态在再次重启后保持。
- 同一脚本加 `--real-model` 使用现有真实 Responses 模型。实收一次 MCP 调用，回复包含工具独有标记，实时和持久化工具结果均匹配。安装及两种渠道证据位于管理仓任务目录 `artifacts/codex-mcp-design-20261104/evidence/`。测试连接器用隔离状态中已连接记录预置；未重验连接器市场或桌面安装包。
- 免 Core Worker 关闭时原生宿主仍记录 `No module named 'openjiuwen'`，原提交在相同本地模型和普通聊天对照中复现。真实验收中 Worker PID 已退出、IPC 已关闭，后续新 Worker 能恢复，隔离模型配置与凭据已删除。该既有关闭缺口独立于本次 MCP 接入。

当日状态为本地候选和 Linux Web/Worker 验收完成，尚未提交；当前发布进度见下节。


## main 同步及发布验证（2026-11-07）

原候选全部改动、暂存区补丁、未跟踪文件与摘要已保存，原工作区不修改。新分支 `codex/codex-mcp-release-20261107` 从 fetch 后的 main `39da4768851630edf63c4f5de3590cc2b35b7b1e` 创建，迁移相同产品补丁，未升级依赖。无 Core 环境以 `uv sync --locked --offline --no-default-groups --group test --no-editable --extra codex-direct --extra claude-direct` 安装；Native 另装 native/codex 组合，Core 仍锁定 `e089198835426cd7681761b0cc278670cd83031f`。Python 3.13.15，官方 Codex SDK／CLI 0.163.0，实际产品来自各环境 site-packages，非本地 editable Core。

原 Web WebSocket → Gateway → Front／Worker → 官方 Codex 路径重新验收通过。真实 Responses 模型调用真实 HTTP MCP 一次，回复含服务端独有标记，实时和持久化工具结果匹配。受控模型仅负责稳定驱动边界输入，SDK、CLI、MCP、原权限与会话链仍真实：默认权限批准一次调用、拒绝零调用；装载失败零模型请求且保留旧选择和原 thread；随后原选择仍可用；清空后旧工具从模型清单消失，重启后保持清空；Worker 重启恢复同一 thread、原角色和上下文。

本轮基线已包含独立交付的 KV Cache／官方 IPC 关停补丁。三次受控模型阶段和一次真实模型阶段的桌面 shutdown helper 均退出 0，shutdown.done 为 true，Worker 原生退出码 0 且 IPC endpoint 关闭；初始候选记录的免 Core 退出缺口不再代表当前 main。验证脚本按真实 Worker PID 核验，隔离模型配置／凭据均已删除。

验证命令与原始日志保留在管理工程 `artifacts/codex-mcp-release-20261107/evidence/`：`test-external.sh`、`test-native.sh`、`real-model/report.json`、`web-fixture/report.json`。连接器用隔离已连接记录预置；未验连接器市场注册、桌面点击、Windows/macOS MCP 实机。该范围不包含 OAuth、stdio、旧 SSE 或专家／插件附带 MCP。


CI 对应范围按锁回归：External 446 项通过，Native 567 项通过、3 项 Windows CLI 专属测试在 Linux 按已有标记跳过。新增 CI 用例经原 Facade 聊天入口固定成功选择、装载失败不启动 Turn／保留旧选择、恢复、清空以及清空后释放／恢复同一 thread；凭据和不支持输入另有负向用例。SDK 替身仅供确定性回归，真实验收不使用该替身。新用例首次在本地受限沙箱因 asyncio 线程回执无法唤醒而超时，同原按锁测试的允许执行环境下通过，未修改生产代码绕过或跳过测试。
