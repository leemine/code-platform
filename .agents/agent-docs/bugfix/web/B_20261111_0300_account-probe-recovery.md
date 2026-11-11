---
id: B_20261111_0300_account-probe-recovery
title: 账号探测短暂故障容错与串行自动恢复
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/channels/web, deploy/web]
files: [jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudWorkspaceGate.tsx, jiuwenswarm/channels/web/frontend/src/services/organizationCredentialEvents.ts, jiuwenswarm/channels/web/frontend/tests/cloudWorkspace.test.mjs, jiuwenswarm/channels/web/frontend/src/services/runtimeResume.ts, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, deploy/web/proxy_switch.py]
designs: []
design_note: 补回 codeswarm 既有恢复行为，不新增账号或执行链。
---

# 根因与范围

平台登录提炼遗漏 codeswarm App 中已有的探测失败串行自动重试。一次传输失败即卸载工作界面并停在手动重试页，是已确认的恢复缺陷。此前非计划内公网探测失败的底层触发原因未复现，不能把此缺陷当成该网络故障的确定根因。

# 修复

同一 10 秒期限内对网络错误及 502/503/504 重试一次，成功保留工作界面；持续失败后每次完成再等待 2 秒自动探测。延迟响应受原 generation 保护。恢复仍以服务器新身份决定同账号原路由或换账号根路由。已确认云模式遇到 404 不回退本地；准备完成后的账号复核失败也进入账号自动恢复，环境创建失败仍保留显式重试。诊断不含凭据、身份、响应正文或原异常内容。服务端逐请求鉴权、SDK、Runtime、Router 和创建回收流程不变。

# 验证

原候选 3a68ffa 上修改。前端 24 项云入口测试、5 项账号 store 测试通过；覆盖瞬态故障保持原 DOM、长响应不重叠、持续故障自动重试、超时 abort、401/403 与非法身份不重试、已知云端点消失不降级及原退出/就绪约束。生产构建通过。真实隔离 UI 的最终版本、故障注入证据与 stable/按锁核验结果统一见管理仓 PLATFORM_CLOUD_UI_ACCEPTANCE_20261110；单测不替代端到端验收。

# 2026-11-11 系统复查后的收敛修复

上述首次修复仍在同身份恢复时调用 discard，导致清偏好、整页初始化和额外 ensure。现保留故障前入口阶段，并严格比较服务端新验证的 actor/authority/subject/session_revision；同身份只恢复原阶段，环境 READY 后复核失败也不重做 ensure。变更身份/撤销仍走原清理链，不放宽服务端认证。

## 历史重放根因证据

同一 ui-d 现场去敏捕获：初始空闲快照 cursor=2025，旧 dispatch 不在 dispatches 中；代理短断后旧 final 序号22/26、delta32–46和final50被旧 RuntimeResume 接受，重连快照在delta44后到达。部分旧final缺timestamp，delta仍带旧output_phase_id。Worker终态记录和journal分别有512/2048条保留上限；现场确认的是“快照缺席而journal仍有旧帧”，未读取远端内存证明具体淘汰计数。旧历史26行字节哈希不变，不能判作重复模型执行。

既有过滤只认快照仍保留的terminal dispatch；首次空闲页恢复游标仍是0，重连重放整段journal。现在快照覆盖边界内已缺席dispatch和已终态旧帧交回原持久历史，通过已有runtime.history_required通知对账。首次空闲且无待交互时采用快照cursor；运行中、待审批、已观察输出不跳过原恢复。既不重发用户输入，也不伪造结束时间。第一版仅过滤旧帧仍出现历史RPC超时，因此补了初始空闲游标处理；该中间失败证据保留。

## 部署回滚失败根因与决策

原临时脚本先停/删入口再读恢复材料。新增可替换deploy/web/proxy_switch.py先检查显式材料、镜像、证书、归属及语法，保留原容器ID，失败只清理本次替身并恢复原角色。远端首次两次故障演练又暴露Docker缺失对象错误文案大小写差异；人工按保留ID恢复后，补入真实 `error: no such object:` fixture，最终健康失败自动恢复原ID通过。不得把这些中间失败写成通过。无SDK/Runtime/Gateway业务新依赖。

## 拒绝的方案与限制

不缓存身份越过认证，不重建环境，不删除历史，不把所有重放一律丢弃，不扩张Worker journal或另建队列。部署不删数据卷，不做全引擎清理，不承诺零停机/自动续证/崩溃事务；同时只能一个操作方管理。持续账号故障时未发送草稿仍可能丢失。导出能力装配缺口、Codex用户命名空间限制保持单列，不误报已闭合。

## 验证

新增真实useWebSocket/WebClient/chatStore组合回归，在旧RuntimeResume上可确定性复现重复流式回复，当前实现通过。Gate27、WebClient/RuntimeResume25、真实Hook组合13、部署失败14项通过；另保留账号store、流式store及时间线既有套件回归与Vite构建。stable已纳入组合用例；本轮没有推送或运行远端stable，不把本地结果记为CI通过。113隔离ui-d实测、完整命令/版本/截图/中间失败统一见管理记录PLATFORM_SYSTEM_RECOVERY_FIX_20261111。

# 合入前能力边界收敛（2026-11-11）

复审确认云实例模式已有服务端agentserver_file_rpc_required拒绝；App仍自动恢复导出任务，造成无效请求和可点击但失败的入口。Gate现在传递可选禁用原因给原App与ChatPanel；原查询函数以显式能力开关返回null且不读写任务记录，旧调用默认启用，本地导出不变。按钮、辅助技术及中英文原因共用原控件，不新增导出服务，不绕过文件权限。新回归证明有/无待办任务均不请求、不清理；既有分享上传/协议/渲染测试仍运行，stable纳入分享套件。

本轮复审范围包括上述差额及前轮Gate/RuntimeResume/WebClient/部署补偿/测试/装配；原38文件PR既有差额继续以PLATFORM_SYSTEM_REVIEW_20261111为依据，锁未变。真实Native/Codex待审批重连、精确提交stable及复查结论由管理记录PLATFORM_MERGE_READINESS_20261111维护，未完成项不能以本地测试或旧SHA通过替代。
