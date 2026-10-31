---
id: B_20261031_1418_session-recovery-lifecycle
title: 外部主Agent取消续聊与历史恢复活动状态收敛
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server, jiuwenswarm/channels/web]
files: [jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/agent_ws_server.py, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/services/runtimeResume.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, tests/unit_tests/agentserver/test_claude_direct_adapter.py, tests/unit_tests/agentserver/test_command_workflows_handler.py, jiuwenswarm/channels/web/frontend/tests/webClientRuntimeAck.test.mjs, jiuwenswarm/channels/web/frontend/tests/sessionInput.test.mjs]
designs: []
design_note: 用户要求修复现有流程遗留，不新增旁路；沿既有Runtime、SDK resume、Native可选边界和Web订阅修复。
---

# 现象与根因

1. Claude取消后Runtime正常取消并排空producer，但适配器将未收到ResultMessage等同Session必须销毁，删除已确认初始化的官方SDK会话。后续历史守卫因此拒绝续聊。
2. command.workflows是通用历史恢复调用，入口却无条件导入Native Team。external-only安装因此报缺少openjiuwen。
3. Web metadata先读busy，再等待runtime_resume，仍返回第一次的旧busy；查询期间接收实时终态也可能被延迟快照覆盖。历史加载还曾忽略实时processing事件。真实UI第一轮复现后台已idle而前台busy；仅换回最新恢复结果不足，需要处理实时事件与快照的先后关系。

# 最小修复

- 已初始化且用户取消的Claude Session保留SDK transcript/native_id，原SDK resume用于下一Turn。当前client、reader、待审批Future仍清理；关闭/驱逐仍删会话目录。未初始化、无终态错误不因此被保留。没有重放用户文本、新执行器或持久化会话映射；进程重启后的冷恢复仍未交付。
- 沿已有native_available探测，在无Native安装时返回同一workflow list/detail协议的空列表/未找到；装有Core时原live/checkpoint查询完全保留。不用ImportError吞掉真实Native故障。
- WebClient返回恢复后的metadata。仅在原metadata请求生命周期内观察相同session的processing_status；期间若活动状态更新，去除旧响应中的is_processing，保留其余metadata/权限，不覆盖实时状态。请求成功/失败均解除观察，不新增轮询或全局状态机。
- 历史加载时更新已有processing/thinking，消息重建仍归原history流程。

# 验证与边界

无Core Python16项、固定Core工作流13项、Codex/OpenCode108项通过。前端订阅/输入回归与构建记录以管理仓最终验证记录为准。真实Claude Runtime待审批取消后返回取消前随机标记、文件未写入、关闭后临时会话为0、Core未导入通过。首轮模型因测试文件名拒绝调用工具，未计成功；保留失败证据。UI最终验收见管理候选docs/verification/P1_SESSION_LIFECYCLE_FIX_20261031.md。

候选codex/p1-ui-lifecycle-fix，8910f05+继承P1 dirty；既有24个文件逐摘要保留。Core/协议/SDK锁未升级。未修改Provider源码、CLI/SDK包、TLS/保护；未提交发布。非editable按锁、冻结桌面与跨平台发布不在本次验收结论内。


## 2026-10-31 发布复核：已完成授权被重放

c197e41真实Work界面返回已有Claude会话并续聊时，旧的claude-approved.txt写入授权重新显示。新请求req_mvw79f7z_40的持久历史只有用户、chat.final与request_completed，没有新的工具/提问事件；因此不能把此现象归为Claude再次调用工具。失败截图和原候选保留，原先“验证通过”的范围不覆盖本次发现。

现有RuntimeResume的完成dispatch集合仅在首次创建游标时初始化。实时事件先创建游标、或原活动dispatch后来结束时，后续metadata未更新该集合；重连回放可把旧授权作为活动输入。修复只在原WebClient接收session.get_metadata响应时，同步采用权威快照的完成边界，并在原RuntimeResume更新历史dispatch，保留已观察游标、去重和Worker实例隔离。只过滤被标记replayed且属于已结束dispatch的事件，不丢弃实时事件，不用chat.final片段推断活动dispatch结束，不清空所有待答问题；后端Runtime/Provider未改。

两项新增生产WebClient回归覆盖实时事件先到、idle metadata、已允许/已取消控制、仍在等待的片段终态，以及同游标重连响应后立即到达的旧授权。新增首项在修复前失败、修复后通过；原17项与新增2项共19项通过。真实UI复验结果及候选来源见管理验证记录MAIN_UI_CLAUDE_RELEASE_20261031。


真实UI第一次复验仍失败，单纯更新completed dispatch集合不足，保留该次失败。随后原Web接口只读报文证明：快照pending_interactions为空，而replayed=true旧提问的dispatch_id已不在当前快照（Worker记录和有界事件日志生命周期不同）。补充最小检查：对快照cursor以前的重放chat.ask_user_question，只有权威dispatch.pending_interactions仍列出的原生控制ID可再次入队；实时/快照之后事件保留，不修改后端日志清理或推断Provider状态。19项回归包含被回收dispatch的旧授权、真正待答控制和快照后的新审批；证据control-replay-wire.json。


最终真实前端36313复验：相同Claude会话执行中刷新后继续返回京都四晚，无旧授权；新Write授权刷新后正常恢复并允许，独立文件为VERIFIED，完成后idle。取消目标与迟到写入文件仍不存在。最终原Vite构建54.54秒通过；后端与按锁环境仍为c197，本次追加只改前端。证据history-controls-real-report.json及stale-approval-after/active-approval-refresh-after截图。
