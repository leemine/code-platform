---
id: B_20261102_1543_provider-subagent-content
title: 外部子智能体卡片缺少内部活动与结果
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/runtime/agent_adapter/providers]
files: [jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/subagent_projection.py, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_codex_direct_adapter.py]
designs: []
design_note: 用户确认Provider适配模块最小修复；沿原生命周期候选续作，无新宿主执行架构。OpenCode经用户确认后置。
---

# 子智能体卡片内容缺失

## 根因与实施边界

上一轮Claude候选只投影名册/生命周期，未投影子Agent工具事件或写入子桶结果；前端在活动和结果都为空时显示“暂无活动”。Codex原适配仅处理父Turn文本/命令/文件，忽略官方collabAgentToolCall。Native已有活动/历史链路，不通过导入其私有实现重新引入Core。

本次只改Claude/Codex及providers内的事实投影/历史写入函数，保留原Runtime、唯一事件读者、审批/取消、前端/协议。公共历史接口负责存储，不新建库/目录规则/执行状态机。工具阶段身份与递增序列明确；缺码/未知、失败/取消不补作成功。原始事件中无法归属的子消息不录入，不按输出文字猜子Agent或伪造详情。

Claude保留当前producer的原生task_started关联，接入TaskProgress、带parent_tool_use_id的真实工具调用/返回、TaskNotification.summary；摘要来源与官方能力限制保留。进度并不是一条新的工具调用，避免重复计数；真正工具调用/返回保留同一tool_call_id，活动ID区分阶段。

Codex只接受父thread发出的spawnAgent所证明的目标，在实际协作事件中读取公开thread_read快照，无新增订阅/定时查询；原生未可读时保留限制。真实首轮spawn后一次快照InternalRpcError，后续wait完成快照可读，已经留证，不把初始化回执代替子工具执行。结果归属子桶，父总结不被子正文替换。

## OpenCode范围调整

初次真实小目录验证未产生子会话，父回答虽包含测试标记也不算通过。源码确认自有CLI有明确task=deny，旧规约说明尚未支持子Agent。用户选择保留原限制，本轮仅交付Claude/Codex。OpenCode两个试作文件精确恢复任务基线，草稿补丁仅在私有任务资料保留；不是新增默认能力或已验收特性。后续先补权限继承、子审批/提问路由、取消和异常终态，再讨论开放task，不能为了展示绕过现有保护。

## 候选、依赖和验证

独立工作区artifacts/claude-background-lifecycle-20261102/swarm-final，codex/claude-background-ui-20261102，基线与fetch后的origin/main均13d17136610c80d342bd621371ede3e43e7e1d84。保留上一轮生命周期修改；本轮开工完整差异和未跟踪故障文档已另存。主目录、已安装beta3、57335/50821界面不改。SDK/Core/锁未升级；CLI/SDK只读使用，无外部源码补丁。

证据目录artifacts/provider-subagent-activity-20261102/evidence；上轮251/取消结论仅对应旧候选，不直接当成本次通过。

- 上一轮真实安装候选执行同一新增Facade测试5失败，确实捕获缺少活动/子快照，不是靠缺依赖失败（baseline-red-tests.txt）。
- 本轮早期新测试发现Codex父协作结果夹带未绑定目标信息；限定已证明目标后通过。原始1失败3通过保留，不删用例/扩大白名单。
- 第一版按锁范围256通过；撤出OpenCode试作、补工具身份、不可变历史ID后，两Provider候选256通过（final-tests.txt）。最终进度投影精简版在final2-venv重装后256通过/32.59秒；源/安装文件摘要逐项相等（final2-source.json），无Core、依赖声明/锁无差异。
- 真实Codex第二次59.605秒通过：一个子Agent、8条活动、实际工具读取与父子结果标记、子桶发现/读取、Runtime关闭、私有配置移除；无Core。首轮83.037秒另存，不覆盖失败诊断。
- 原Code UI使用sql2java-workflow，输入精确原文“请分析整体架构和功能”，已实际显示三个Explore的终端、Read和工具正文；claude-ui-activities-running.png。本次请求最终success，三个Explore均completed/closed，子活动98/89/122条，原生结果20926/10316/23348字；刷新原页面后名册、活动、工具参数/正文仍可展开，claude-ui-history-restored.png及claude-ui-report.json。sql2java HEAD/2079条dirty/差异摘要与开工相等，未修改工程。旧429失败保留。

### 最终代码与渠道证据适用范围

完整sql2java UI任务使用final-venv（Claude摘要022393a4）；随后仅调整Claude进度事件kind=thinking和稳定progress活动ID，避免把进度重复当作工具调用。没有修改生命周期、工具实际执行、Runtime、配置或SDK。不能把该完整UI任务宣称为final2字节完全一致验收。

最终final2-venv真实Runtime.stream/web小目录49.920秒通过：一个真实Explore，14条发出活动、父子文件事实标记、子桶发现与读取、正常Runtime关闭、配置移除、无Core。Codex适配/投影依赖、装配和SDK均未变化，final-venv的59.605秒真实结果仍对应最终相同字节。二者原生真实事件和持久历史再交原前端normalizer/store/historyRestore消费：Claude11条去重活动/15条历史回放，Codex8/9，结果均可恢复（real-event-consumers.json）；原有前端store/history/status三个测试文件通过。

确定性完整命令为：final2-venv/bin/python -P -m pytest tests/unit_tests/common/test_external_cli_config_read.py tests/unit_tests/common/test_external_cli_runtime.py tests/unit_tests/agentserver/test_codex_direct_adapter.py tests/unit_tests/agentserver/test_claude_direct_adapter.py tests/unit_tests/agentserver/test_opencode_direct_adapter.py tests/unit_tests/agentserver/test_provider_session_selection.py tests/unit_tests/test_external_model_settings.py tests/unit_tests/agentserver/test_command_workflows_handler.py::test_external_only_workflow_query_uses_same_empty_snapshot_without_native --import-mode=importlib -o pythonpath= -q --no-cov --tb=short -rs。cwd为swarm-final，独立JIUWENSWARM_DATA_DIR；uv sync --locked --no-editable --no-default-groups --group test --extra claude-direct --extra codex-direct --python 3.13 --reinstall-package workswarm，日志final2-install.txt。真实脚本verify_provider.py及消费脚本verify_consumers.mjs在任务资料，模型复用用户已有Anthropic/OpenAI别名，只在私有600配置保存，不入Git。

## 交付与剩余

本轮源码及上述验证完成，设计/HTML/文档链接与生成新鲜度校验通过（docs-check.txt）。未使用54993验收实例的四个自有进程及私有模型配置已限定回收；首次清理脚本因系统Python缺少psutil未执行，改用任务按锁环境正常完成。47501作为本轮已完成UI证据保留；57335/50821与已安装程序未动。

本轮尚未提交/推送/PR/合入/打包。OpenCode委派仍是后续任务；完整独立插件拆包、Windows/macOS真机、已安装Electron GUI和异常退出接管不在本轮通过范围。当前界面验证为原Web/AgentServer/常驻Worker/Gateway，不冒称完整Electron GUI验收。


## 2026-11-02 发布候选检视

用户已授权提交PR、合入和Linux安装包验收。主线fetch仍13d1713，完整tracked/index差异及3个untracked文件在subagent-release-20261102/private先保留。按jw-review核对生产者/控制所有权、原生事实与历史/UI消费者，范围内未发现可确认的阻塞缺陷；非完整平台认证。版本升0.2.5.beta4，只同步产品/TUI元数据，uv离线锁只改两个本地包版本，Provider/Core未升。beta4非editable候选源/安装一致，external256通过/33.42秒，构建契约74通过/1.22秒。首次构建测试命令错引用不存在模块，未收集任何测试，原日志保留，按现有模块重跑通过。PR/stable、合入后冻结包真实调用待本轮发布执行，不将源码结果当作安装包通过。
