---
id: B_20261102_1436_claude-background-lifecycle
title: Claude 后台探索的原生完成边界
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/runtime/agent_adapter/providers]
files: [jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, tests/unit_tests/agentserver/test_claude_direct_adapter.py]
designs: []
design_note: 用户明确确认的最小缺陷修复，沿现有 S_02_external-adapter-boundary 契约，无新增执行架构。
---

# Claude 后台探索提前关闭修复

## 现象与根因

已安装 beta3 / main 13d17136610c80d342bd621371ede3e43e7e1d84 的 sql2java 真实会话先启动四个 Explore 后台子任务，主 Agent 先返回“本轮结束，等待通知”。适配器使用官方 receive_response，只读到首个 ResultMessage，随即断开客户端，结束原生 CLI；四份子记录无最终回答。这是主回答与后台任务生命周期的接入缺口，不是本轮 TLS 或整轮超时。

当前 SDK0.2.115/显式官方 CLI2.1.274 原生最小探针确认：全部任务结束后仍可能先返回“还在等第二个”，再返回完整汇总，最后发出 session_state_changed(idle)。因此不能以任务归零加任意一个结果推定全部汇总已返回，也不从模型文字、文件数或静默时间推定结束。probe 原始事件见候选外 ../evidence/native-probe.jsonl。

## 修复决策与边界

唯一生产变更为 ClaudeAdapter：沿官方公开配置启用 CLAUDE_CODE_EMIT_SESSION_STATE_EVENTS，唯一读者改用 receive_messages。消费 task_started/progress/updated/notification 及 background_tasks_changed；快照是活跃集合，不补造成功，终态同时接受 completed/failed/stopped/killed。Provider 内部任务仅作事实投影，不增调度/轮次队列，不改 Native/Core、外部源码、SDK/CLI 或锁文件。

原生结果保留至 idle 且无自有活跃任务才完成原 Runtime producer；中间 Result 不触发 Swarm 收尾，最终只提交最新原生结果。子任务状态保存在 final.provider.claude.tasks，并沿原历史保留，task_acceptance 仍 unknown。只消费当前 native session、排除 owned_by_subagent 的嵌套工具；观察事件不审批。

取消通过原 Runtime 控制、官方 interrupt 和 stop_task，范围仅为当前 producer 原生事件确认的任务 ID；ACK 不代表终态，正常读取继续直到原生收敛，Runtime 仍拥有生产者取消/排空，SDK连接和关闭保留同一任务所有权。CLI不暴露idle时，普通无后台任务保持原Result完成兼容；已出现后台任务时明确返回 claude_lifecycle_unsupported，不猜测成功或增加自定义看门狗。EOF缺结果/idle仍走不完整错误。

## 回归证据（2026-11-02）

候选 codex/claude-background-lifecycle-20261102，基线13d1713，源码与证据在 artifacts/claude-background-lifecycle-20261102。SDK0.2.115、CLI2.1.274；external 无 Core，Native extra 的固定 Core e0891988 未改。独立用户目录与进程，不替换桌面安装版或其他 checkout。

- 原基线执行新增测试：3失败，捕获首Result提前收尾及空快照被误当完成；原始日志 tests-original-baseline.txt 保留。
- Claude生产Facade/控制/历史定向31通过，涵盖四探索、多个/空Result、updated单独终态、失败/停止、未知边界、EOF、嵌套/外会话隔离、取消后原native续聊。
- 干净非editable按锁external stable范围249通过（locked-external-tests.txt），实际导入来源与SDK/锁摘要见locked-source.json；无Core加载。
- 原 AgentRuntime.stream / web 渠道，目录 /home/leewanlong/work_leewanlong/projects/sql2java-workflow，输入原文“请分析整体架构和功能”：458.433秒完成，4个Explore均原生completed，最终6739字报告及4份状态在历史原样保留；项目HEAD/status/diff摘要前后一致，Runtime关闭，私有模型配置已移除。sql2java-report.json、sql2java-native-events.jsonl、sql2java-final.txt。
- 首轮记录时原Code界面与取消真实复验未闭合；后续结果见下方最终候选验证，不把首轮结果外推至最终代码。

第一次pytest未设置隔离环境而在导入日志时遇到只读用户目录；未完成用例。随后沙箱内线程唤醒停滞，记录保留，停止本任务测试进程后在正常环境使用隔离目录重跑通过。不是删除测试或扩大白名单。

## 遗留与交付

未提交、推送、PR、合入或打包；用户已安装beta3仍为旧实现。原窗口恢复/外部客户端进程异常接管不在本次修复范围，独立插件拆包未启动。Windows/macOS真实原生CLI与桌面包未验证；不从Linux源码验收外推。

## 真实复验发现的相关接缝（追加，保留上轮事实）

第一候选 UI 原输入成功结束，3个原生探索均返回、最终4961字报告；但未映射chat.subtask_update，用户截图中原任务面板没有子智能体。第二候选仅在ClaudeAdapter补既有事件投影，不改前端控件，原始启动标题与最后工具进度分开。

后台工具执行中取消的真实验收先发现原会话native ID虽保持，但下一轮返回空结果、未回答记忆token。官方SDK公开回显诊断确认：CLI重连先输出旧任务stopped通知、num_turns=0的空Result、idle，然后才处理新输入。现SDK未透传最新Result.origin，不能猜测空结果归属；改用官方AsyncIterable输入UUID与replay-user-messages，等待精确UserMessage.uuid回显后才接收新请求的成功结果边界。

继续复验观察到Runtime在取消控制返回后取消producer，可能撞上SDK owner正在关闭AnyIO上下文，触发shutdown unconfirmed。保留fence和失败记录，取消控制补等待同owner实际关闭再返回，仍由原Runtime管理producer，不转到另一任务关闭SDK，不修改外部依赖或关闭保护。最终复验进行中，前两次取消失败不能记通过。

用户查看57335时，验收角色停止导致AgentServer unavailable；AgentServer恢复后发现旧Gateway仍占锁，核对自有PID/启动时间后回收并重启原端口，已恢复模型列表/编辑入口，保留原配置和常驻Worker。为避免干扰用户，此后所有产品修改迁到swarm-final分支codex/claude-background-ui-20261102，运行用户界面的swarm保持第一候选，不热换已加载目录/环境。上一轮证据保留，最终当前候选必须重新验收。

## 最终候选核验（当前进度）

最终候选swarm-final / codex/claude-background-ui-20261102，基线仍13d1713；生产仅claude.py +145/-11，测试+239/-2，未修改SDK、Core、锁文件、公共Runtime或前端。final3-venv为按锁非editable安装，源码与实际安装claude.py的SHA256同为9c5ba0954e5538f4b7a88edc77843fdfbadadc410f1885ad4f5dc504fe3b155c，SDK0.2.115，显式CLI2.1.274，未安装Core。锁文件摘要和导入来源见final3-candidate.json、final3-locked-source.json。

- final3-external-tests.txt：现有external stable受影响范围251通过，退出0；包括33项Claude生产Facade/历史/权限/取消回归。不是本轮GitHub Actions或全量Python通过。
- 原前端subagent-store / subagent-history / subagent-status各1个测试文件通过，退出0。运行于固定发布源码目录的原前端，4份相关源码摘要与候选相同，未修改前端。frontend-existing-contracts.json。
- cancel-final3-report.json：真实后台Bash执行中取消，Runtime等待控制完成；同native ID续聊、随机token保留、35秒无迟到写入及Runtime关闭全部通过，122.969秒，退出0，无关闭fence。孤立验收配置已移除。
- final2安装复核发现uv复用旧版本缓存wheel，安装位置虽正确但文件缺最终关闭等待。其失败/日志保留，不当成最终源码结论。final3显式--reinstall-package workswarm并核对文件摘要后才开始正式验证。
- 新隔离UI50821，AgentServer/常驻Worker/Gateway/原前端：Code下从已有项目列表选sql2java-workflow、选择Claude Code、输入精确原文。已实际出现3张运行中子智能体卡片，ui-final3-subagents-running.png；终态/最终报告/刷新恢复尚待当前请求结束。原任务页是规划看板，子Agent列在现有子智能体页，不伪造Team任务。

当前投影只承诺原生子Agent身份、标题与生命周期。子Agent详细工具流/对话结果卡片尚未投影，原面板可能显示“暂无活动”；这不等同原生Agent未运行。原生汇总仍由主Agent结果返回，不补造详情或开放子Agent输入。

等待授权取消真实回归 approval-final3-report.json 也已通过，128.621秒、退出0：收到原审批事件后取消，待授权脚本未启动，无迟到写入，同native ID续聊与随机token保留，关闭完成且私有配置移除。中断终态的chat.error/claude_cancelled属于预期取消，不记为任务失败；续聊不含chat.error。

最终Code UI第一次完整请求web_1a19b0a46a2_1999b7fd0442于417.198秒遇到官方CLI is_error=true / api_error_status=429，原生记录error=rate_limit；两探索completed，第三个只有running末态，没有最终汇总，原request_completed.status=error。保留ui-final3-attempt1-report.json及截图，不将子Agent局部完成/界面可见记为完整成功；这不是TLS、AgentServer连接或首Result提前终止。没有更改SDK重试策略、规避服务限流或变更模型配置；无其他本任务模型验收并发后，同目录/原文UI顺序复验正在进行。原429失败不被重验覆盖。

## 最终交付状态：代码及局部验证完成，完整真实UI验收环境阻塞

第二次顺序UI请求web_1a19b125bbf_88286c52cc7d在5.180秒再次收到HTTP429。只读核对原生CLI错误正文，具体为1308“已达到5小时的使用上限”，服务返回重置时间2026-11-02 15:17:06（原样时间，不是推测）。第二次尚未派出子Agent，不能归因于本工程子Agent并发/提前断流；不把429解释为TLS或模型配置协议失败。ui-final3-attempt2-report.json保留脱敏事实，停止重复消耗请求，不改变模型凭据、配置或外部重试策略。

因此，本轮251项按锁确定性测试、原前端3文件测试、2项真实取消续聊、子Agent运行/部分终态可见均有证据；最终候选“指定原文→全部探索→完整报告→刷新恢复”尚未通过，需模型额度恢复后续验，不冒记完成/可发布。首次候选4探索/6739字符成功仍仅属于首候选。当前交付未提交/推送/PR/合入/打包。

57335是用户正在使用的首候选，保留原服务/配置；50821是最终候选独立验收实例，失败历史保留，不自动改动已安装beta3。未使用的41413中间实例仅按专属环境/数据目录核对4个自有PID后回收，私有配置移除。实际查询原生服务额度没有改动sql2java，最后核对HEAD/status/diff摘要与最初基线相同。
