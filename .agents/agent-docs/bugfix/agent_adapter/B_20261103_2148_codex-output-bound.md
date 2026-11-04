---
id: B_20261103_2148_codex-output-bound
title: Codex 大工具返回的有界投影
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/runtime/agent_adapter/providers]
files: [jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, tests/unit_tests/agentserver/test_codex_direct_adapter.py]
designs: []
design_note: 用户已确认 Provider 内最小修复；不增强宿主、不新增共用模块，不另立设计。
---

# Codex 大工具返回的有界投影

## 现象与根因

Windows 用户日志：chat.tool_result/shell 的 e2a.chunk 达6931038字节，超过 AgentServer 原6291456字节预算。相关工具通过 PowerShell Get-Content -Raw 读取 opencode.exe；content/result 各1048610字节且完全相同，原生 exit_code=0。这不是生成大文件，而是把大工具文本实时发送。JSON 转义可进一步放大控制字符；没有完整原始帧，不能精确分摊该次6931038字节的各项贡献，也不据此认定官方 SDK 有缺陷。

Codex 的 command_result 将 aggregatedOutput 原样复制进两个兼容字段，缺少 Swarm 显示约束；_child_snapshot 的命令活动摘要同样无界。Web/结构化CLI/飞书读取 result，人工CLI读取 content，因此保留两个长期兼容别名，不借此删除消费者依赖。Native stream_event_rail 的 result/rendered_result 已有60000字符显示上限，子活动默认2000；但其 raw_output 仍可能更大，不能说 Native 所有事件均已完全受限。

## 修复决策与当前契约

产品仅修改 providers/codex.py：私有字符上限与 _bounded_output，原映射使用同一裁剪结果，子命令活动使用2000字符摘要。60000/2000都包含提示。仅截断时增加 provider.codex 计数，received 只表示SDK已返回文本，displayed包含提示，不推断命令全部输出或缺失退出码。短输出和原权限拒绝文字保持；task_acceptance仍unknown。官方 aggregatedOutput 可空，子摘要按空字符串投影。

不改 Runtime/Facade/历史格式/前端/协议/6MiB预算，不新增调度、二次存储、重试、看门狗或共享工具模块；不修改 Core 和外部源码。rendered_result 代表模型实际读取文本，不能拿显示预览冒充。裁剪后的 Swarm 历史不保存被裁去全文；原生模型上下文未被裁剪。其它 Provider 及其它大事件不是此修复的覆盖承诺。当前 spec S_02 和中英文指南同步。

## 来源与环境

候选 artifacts/codex-output-bound-20261103/swarm，分支 codex/codex-output-bound-20261103，基线0fc0e316a33ffbdd44b2ae2ba72969ae23d0f410（创建前fetch，初始clean）。产品主目录main仍504254ba、clean，未切换或覆盖；候选已包含新的会话恢复/UTF8/Claude loopback修复。本轮只对两份代码/测试文件写入，未提交。

Core可选固定e089198835426cd7681761b0cc278670cd83031f、协议2a0457e5e01152e9ca5f8afdffd84716227046ca；声明与uv.lock不变。本机code-core checkout为de8d4f38bb624b608af4a5c76b5c5c82d47d3360、clean，不用它替代按锁来源；旧codeswarm主目录9fa49bf126421a3e8307c756600fe5e7f4225290、clean，均未修改。

本任务 .venv 是 uv sync --locked --no-default-groups --group test --no-editable --extra codex-direct --extra claude-direct 的非editable安装；native-venv另加 --extra native。Python3.13.15、openai-codex0.163.0、claude-agent-sdk0.2.115；真实配置选定的CLI为codex-cli0.166.0，SDK负责兼容，不加版本白名单；实际source、哈希、direct_url与锁摘要写入 evidence/*-install-source.json。恢复模块现有测试会显式加载候选provider文件，其余Facade/消费测试及真实运行使用安装包。数据隔离用JIUWENSWARM_DATA_DIR，不改用户配置、不覆盖HOME；真实配置退出删除，只保留本任务私有会话数据。仅回收任务自有进程。

## 验证与失败保留

证据根为管理工作区 artifacts/codex-output-bound-20261103/evidence。旧代码先运行新增回归：10 failed/3 passed（baseline-red.txt），失败为超过显示上限。首次完整回归因新测试误把数据类当Pydantic调用model_copy出现3失败，修正夹具为原AgentResponseChunk构造器；不修改生产协议或跳过该场景。原始失败日志保留。

- locked-external-final.txt：三家 direct adapter、原ws_send、人工/JSON CLI及恢复确定性回归；排除3个需显式联网配置的可选live恢复测试，真实Codex另跑，不把排除当通过。最终307 passed / 3 deselected。
- locked-native-final.txt：同一Codex回归及原生rendered_result/参数重写消费；最终76 passed；原生组合Core实际Git来源核验为上述e089198，非editable。
- 原Facade回归覆盖空/59999/60000/60001字符、逾1MiB控制字符/Unicode/引号换行、exit0/7/缺码、原历史分页、codec roundtrip、既有6MiB保护负向对照、CLI文本/JSON以及同线程下一轮；子线程覆盖长/短/null摘要、外来线程排除、失败/缺码和子桶历史。
- frontend-normalizer-direct.txt：原Web toolEventNormalizer测试；frontend-live-history.json：本轮真实历史直接交给现有Web解析器，截断内容、命令失败与非未知状态保持。node --test 的文件级摘要没有展开用例，另以直接运行同一测试文件获得10项明确通过；非新增界面或浏览器桌面验收。
- live-report.json / verify_live.py：原AgentRuntime→原Facade→官方Codex SDK/CLI→实际本地WebSocket，复用原codec/ws_send，独立项目输出90028字符并退出7。Swarm双别名/历史均60000字符、有截断标记，退出7/false/任务未知保留，最大帧121481字节；模型报告了原输出尾标记，而Swarm预览不含尾标记。随后同一会话命令退出0并返回CONTINUED_42。无chat.error、Runtime关闭、私有config删除、未加载Core。模型为Swarm原配置gpt-6.1-sol-1，不泄露密钥、不改变TLS。此真实运行在最终子摘要null兼容的一行调整前进行；主命令映射未再改变，子摘要调整另由最终回归验证。

真实网络/SDK与受控工具只在该入口验证；本轮没有Windows/macOS实机、完整Gateway/浏览器/冻结桌面聊天、真实子Agent大输出或其它Provider真实模型回归，不把模拟覆盖称为这些入口成功。未运行格式化/静态检查；未扩大白名单。自动审批曾拒绝覆盖HOME的测试命令，随后使用原独立数据目录安全完成，不关闭保护。

## 交付边界

本地修复及验证，尚未提交/推送/PR/stable/合并/打包/替换beta4资产或用户安装版。发布时应复验新包及Windows用户配置；不能沿用旧安装包结论。content/result长期兼容保留，不列为未来必须删除项；独立插件分发与其它Provider输出治理另列任务。


复验命令（cwd 为本候选 swarm，原生测试同用独立 JIUWENSWARM_DATA_DIR；外层 timeout -k 5 -s INT 150 控制任务自有测试进程）：

```bash
.venv/bin/python -P -m pytest tests/unit_tests/agentserver/test_codex_direct_adapter.py tests/unit_tests/agentserver/test_claude_direct_adapter.py tests/unit_tests/agentserver/test_opencode_direct_adapter.py tests/unit_tests/agentserver/test_ws_send.py tests/unit_tests/process_cli/test_ui.py jiuwenswarm/server/runtime/agent_adapter/providers/test_session_recovery.py -k 'not live_native_context' --import-mode=importlib -o pythonpath= --no-cov -q --tb=short -rs
../native-venv/bin/python -P -m pytest tests/unit_tests/agentserver/test_codex_direct_adapter.py tests/unit_tests/agentserver/test_stream_event_rail_rendered_result.py tests/unit_tests/agentserver/test_stream_event_rail_rewritten_args.py --import-mode=importlib -o pythonpath= --no-cov -q --tb=short -rs
.venv/bin/python -P ../verify_live.py
```

前端用已有 esbuild 编译当前 toolEventNormalizer.ts 至本任务忽略的node_modules/.cache，再在frontend目录执行 `node tests/toolEventNormalizer.test.mjs`；没有格式化或静态检查。真实私有配置需从已配置的模型目录按当前原流程读取，verify_live.py只在本地证据中保留，不进入运行产品。

收尾：管理仓check-docs通过，HTML由源设计生成；代码与锁来源证据已留档。合成1048610字节控制字符负对照的双字段帧12584682字节，修复后720524字节（wire-measure.json），仅证明该夹具，不能当作原Windows帧重建。process-check.json未发现任务自有Codex/pytest残留进程；未触碰其它进程。
