---
id: B_20261103_2208_claude-opencode-output-bound
title: Claude 与 OpenCode 大工具结果及元数据投影
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/runtime/agent_adapter/providers]
files: [jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py]
designs: []
design_note: 用户确认继续按现有Codex方案在各Provider内修复，不增强宿主或新增公共流程。
---

# Claude/OpenCode 大工具返回修复

## 现象与根因

续查B_20261103_2148_codex-output-bound：Claude将ToolResultBlock内容（字符串或序列化后的内容块）无界重复放入content/result，子工具活动摘要无界；OpenCode同样重复state.output/error，并透传完整metadata。单字段被原生限制不构成整份metadata及JSON转义后的6MiB发送保证。两家此前没有用户提供的真实超限日志，不能把静态缺口记成已真实触发。

新增原Facade/SSE/历史回归在旧实现上29 failed/4 passed，失败来自正文或子摘要超过边界、缺失metadata投影诊断。独立仅metadata超大的用例说明正文短仍可能经另一条通道放大。正常现有回归通过不覆盖这些新场景。

## 决策与当前契约

产品只新增修改claude.py（+26/-3）与opencode.py（+48/-3）；原Codex修复保持。各自私有文本投影沿既有工具结果映射执行，正文60000、Claude子工具活动2000字符，含提示，保留content/result兼容别名。短输出不变。provider.claude保留is_error并附截断诊断；缺失退出码不补0，Read不增加命令字段。received计数对象是映射为字符串的已取得正文，不是全部命令输出或原始网络包。OpenCode提示写Provider返回，不冒称使用SDK。

OpenCode正常metadata完全保留；JSON序列化长度超过60000字符时，优先exit/truncated/outputPath，再在预算内保留其它完整字段。省略字段及received/displayed字节数明确标记于provider.opencode；原生metadata.truncated不改含义。路径保持完整、不拼造文件链接；单字段本身无法纳入预算则整项省略并诊断，不以被切断路径冒充引用。提取原生退出码早于metadata显示投影。当前消费方没有按provider.opencode.metadata的大正文执行功能；原Web、CLI、历史分别消费result/content和原状态，保持双别名。正常未知小字段保留，只有超过显示预算的结构才省略。

仅文件/字段投影，不导入Core，不修改Runtime/Facade/协议/历史schema/UI生产代码/6MiB保护，不新增共享模块、重试或第二结果存储；不修改外部源码/SDK/CLI/用户配置。原生模型上下文保持。外部能力不同，不机械把Claude的is_error等同命令退出0。其它事件、任务最终正文及工具输入不在此容量承诺内。

官方当前源码中的原生文件引用/截断机制作为语义对照：[tool.ts](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/tool/tool.ts)、[session/tools.ts](https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/session/tools.ts)。它们不是本机锁定CLI的版本证据；本机实际1.18.18的元数据及文件通过下述真实入口核对。

## 基线、环境与验证入口

续用artifacts/codex-output-bound-20261103/swarm、codex/codex-output-bound-20261103，HEAD/fetch后origin/main均0fc0e316a33ffbdd44b2ae2ba72969ae23d0f410。原Codex dirty和未跟踪B在实施前以补丁、文件及摘要保留于evidence/claude-opencode；未换基线/移动用户目录。主目录仍main504254ba、clean。Core锁e089198835426cd7681761b0cc278670cd83031f、协议2a0457e5e01152e9ca5f8afdffd84716227046ca未变，本机code-core独立checkout不参与按锁导入。

uv按原锁重建非editable .venv（codex-direct/claude-direct）和native-venv（另加native）；Python3.13.15、官方Claude SDK0.2.115、Codex SDK0.163.0。记录在evidence/claude-opencode/*-install-source.json，三个Provider实际安装文件哈希均匹配候选；Native实际Core Git SHA按direct_url核验。恢复模块13项原测试继续显式加载候选文件，其余原Facade/消费及真实运行用安装包。数据走JIUWENSWARM_DATA_DIR，不覆盖HOME；真实配置仅私有临时复制，退出删除，不把密钥/配置入Git。

最终无Core按锁343 passed/3 deselected；3项是可选真实恢复测试，不作为通过数。Native组合253 passed（含三家adapter及原生rendered_result/参数重写消费）。原Web解析器10 passed，真实OpenCode历史再交给它校验通过。新增覆盖逾1MiB控制字符、Unicode、内容块、正文边界、Read未知、exit0/7/缺码、错误结果、子工具长/短/空、父子归属、仅metadata过大、总metadata预算/长完整路径、未知小字段、原历史分页、codec/ws_send及续聊。测试没有扩大白名单或跳过冲突。

## 真实OpenCode：原生截断与文件引用保持

verify_other_live.py opencode从原AgentRuntime/Facade进入官方1.18.18 HTTP/SSE，再经原codec/ws_send与实际本地WebSocket。使用已有glm-5.2-OpenAI、任务私有目录，自有CLI服务正常关闭；保持原TLS和权限映射，没有替换模型访问路径。

受控命令输出90028字符并exit7，原生先裁成51460字符，metadata含output/exit/truncated/outputPath，未触发本工程新增裁剪。显示/历史双字段一致，退出7/false、任务验收unknown保留，最大实时帧134586字节；原生文件仍在本任务私有目录，独立读取含完整90028字符及首尾标记。同会话后续命令exit0，返回CONTINUED_42，无chat.error/未加载Core。真实入口证明既有原生截断和引用不受破坏，不能据此说真实Provider已走过本工程60000上限；后者由原生产消费链的确定性大结果回归证明。

首次验收脚本错误要求截断预览仍包含头标记，故opencode-live-report.json的passed=false保留；该次实际执行/续聊均成功。opencode-live-verified.json使用已有真实历史、原生truncated事实和独立文件内容重新核验，不再拿头标记是否出现在预览当成功依据，没有重放任务或篡改原报告。模型曾额外读取任务自有的原生输出文件确认头标记，记录该差异，不假称只调用过一次工具。

实际运行随后只改OpenCode提示的SDK→Provider用词及Claude空行，未改变上述未触发裁剪的路径；最终按锁回归与安装来源对应当前候选。

## Claude真实验收阻塞及清理

同一原Runtime/官方SDK/实际WebSocket，复用原glm-5.2-anthropic；180秒未获得工具结果，原记录为TimeoutError/false，不能记作真实成功。同一配置的一次12秒、无重试Anthropic最小请求诊断得到HTTP429、rate_limit_error、服务码1113；只保存状态/类型/码，不输出密钥或响应正文。这说明当前模型服务拒绝请求；原运行每次重试的HTTP轨迹未捕获，不能据诊断断言完整原生重试时序，也不是此次显示映射代码回归证据。未换模型、未增加旁路、未关闭TLS保护。

Runtime.close返回，但日志提示Claude SDK shutdown unconfirmed且保留所有权；不能只凭close返回就声称原生停止得到确认。随后按子进程继承的精确任务数据目录检查/proc，未发现属于该测试的残留进程，结果留档；这是测试收尾观测，不提升产品取消/恢复保证。临时config已删除，未触碰用户进程。

自动审批起初误将待执行verify_other_live.py判为覆盖HOME而拒绝；只读核验脚本唯一环境赋值为JIUWENSWARM_DATA_DIR并给出SHA后，同一安全脚本获准执行。没有通过间接脚本绕过拒绝，也未覆盖通用HOME。最小诊断仍不替代真实Claude工具与续聊验收。

## 复验命令与交付边界

cwd本任务swarm，用独立JIUWENSWARM_DATA_DIR，外层timeout -k 5 -s INT 150：

```bash
.venv/bin/python -P -m pytest tests/unit_tests/agentserver/test_codex_direct_adapter.py tests/unit_tests/agentserver/test_claude_direct_adapter.py tests/unit_tests/agentserver/test_opencode_direct_adapter.py tests/unit_tests/agentserver/test_ws_send.py tests/unit_tests/process_cli/test_ui.py jiuwenswarm/server/runtime/agent_adapter/providers/test_session_recovery.py -k 'not live_native_context' --import-mode=importlib -o pythonpath= --no-cov -q --tb=short -rs
../native-venv/bin/python -P -m pytest tests/unit_tests/agentserver/test_codex_direct_adapter.py tests/unit_tests/agentserver/test_claude_direct_adapter.py tests/unit_tests/agentserver/test_opencode_direct_adapter.py tests/unit_tests/agentserver/test_stream_event_rail_rendered_result.py tests/unit_tests/agentserver/test_stream_event_rail_rewritten_args.py --import-mode=importlib -o pythonpath= --no-cov -q --tb=short -rs
.venv/bin/python -P ../verify_other_live.py opencode
.venv/bin/python -P ../verify_other_live.py claude
```

前端仍在frontend目录直接运行原node tests/toolEventNormalizer.test.mjs。原始失败、成功、来源和版本在管理任务evidence/claude-opencode。spec与中英文指南同步；管理设计/HTML/任务记录同修。

状态为代码和确定性验证完成、Claude真实验收待服务恢复后复验。没有提交/推送/PR/stable/合并/打包/替换发布包。Windows/macOS实机、冻结桌面完整聊天链、真实Claude大结果/子工具显示未验收；OpenCode仍task=deny，不开放子Agent。后续先恢复原Anthropic服务，再沿同一Runtime完成工具、历史及续聊，不用另一执行流程绕过。

最终收尾：原生内容不改写断言改用独立序列化快照后，9个受影响Claude大结果回归通过（immutable-input-final.txt）。管理文档check-docs与HTML新鲜度校验通过；产品索引已同步。final-cleanup.json确认两个临时配置均删除、无任务专属残留进程。没有运行格式化或静态检查。
