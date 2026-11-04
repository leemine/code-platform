---
id: F_20261104_1230_codex-native-usage-observation
title: Provider 原生用量只读观测（Codex、Claude、OpenCode）
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend]
files: [jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex_usage.py, jiuwenswarm/server/runtime/session/session_history.py, jiuwenswarm/channels/web/frontend/src/types/sessionTokenUsage.ts, jiuwenswarm/channels/web/frontend/src/types/message.ts, jiuwenswarm/channels/web/frontend/src/features/historyRestore.ts, jiuwenswarm/channels/web/frontend/src/hooks/useWebSocket.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ContextUsageIndicator.css, jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json, jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude_usage.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_usage.py]
designs: []
design_note: 用户确认管理仓 OBS-01 只读方案后授权先做 Codex 原生事件试点；无独立 D 文档，不扩展到压缩或发布；同日用户授权将只读方案续接 Claude/OpenCode。
---

# Provider 原生用量只读观测（Codex、Claude、OpenCode）

## 来源与决策归属

候选为管理工作区 `artifacts/codex-usage-observation-20261104/swarm`，分支 `codex/codex-usage-observation-20261104`；已 fetch 的 origin/main 与 HEAD 均为 `0fc0e316a33ffbdd44b2ae2ba72969ae23d0f410`，另含保存并核对的 P1/三家输出保护未提交增量。原候选不动，本轮增量与继承差异分开核算。按锁外部版和 Native 组合均为非 editable 安装；Core 固定 e089198、协议2a0457，Codex SDK0.163.0不升级，实际 CLI0.166.0由本轮原生日志元数据确认。

延续 S_02_external-adapter-boundary 与 F_20261104_1030_provider-input-ownership 的原 Runtime 所有权。本轮只增加原生计数到现有统计事件的映射；不改变执行、取消、权限、恢复、队列或生产者终态。Claude/OpenCode 实现未增加观测能力；P1 的 Claude 待验仍独立存在。

## 实施与接口

- CodexAdapter 的原 `next_turn_notification` 唯一消费者处理 `thread/tokenUsage/updated`；验证当前 threadId/turnId，使用 `exclude_unset=True` 保留 SDK 可选字段是否原生提供。没有额外订阅者、轮询或读取原生轨迹作为生产输入。
- Provider 内 `CodexUsage` 仅缓存数值、增量基线和观测修订号，不持有执行状态机、队列或控制权。原 `total` 作为覆盖式累计快照，不逐通知相加，不进入 Native 的逐调用 Ledger，不新建持久账本。耐久事实沿原历史保存。
- 窗口字段后续缺失时发送清除快照，不保留旧容量。本轮增量只在新线程已知空基线、或上轮正常结束且已观察到用量时计算；恢复、取消、失败、计数倒退时不猜差额。观察到计数倒退后清空可见累计值并保留 provider.codex 原始数值/continuity=unknown 诊断；不能把旧值伪装为当前统计。修订号为本机观测微秒时间并在当前消费者内递增，不当成模型调用次数。
- `chat.usage_summary.session_usage` 继续使用原 schema_version=1、session_id、revision、main/others；模型调用数未知时为null，主线程以外类别也为null，不假装子Agent已统计。主线程类别增加可选 total_tokens/cached_input_tokens/cache_write_input_tokens/reasoning_output_tokens。没有新事件协议或第二账本。旧 Native 整数调用数保持；旧严格客户端可能不呈现新增外部快照，不伪造零满足旧类型。
- `usage` 是可选的本轮输入/输出/总量；没有确定基线时只保留 session_usage。原历史空壳过滤保留这类累计快照，前端实时/恢复统一保留缺失，不补0。
- `context.usage` 只投影原生 modelContextWindow 为窗口容量，input_tokens/occupancy_rate/cache rate 为null、parts为空；不拿 last 或累计消耗充当当前占用。Facade 主动上下文查询仍未开放，手动压缩仍不支持。
- 沿用原底部统计按钮与详情；按指标隐藏缺失，整组缺失时隐藏入口。真实报告0保留。容量可以单独显示；无占用、分类、命中率时没有占位。额外计数仅增加原详情里的行，不加页面或另一套控件。中英文同步，主题变量/Chrome107要求保留。

## 验证与证据

证据在管理工作区 `artifacts/codex-usage-observation-20261104/evidence/`，不放入源码Git。两套最终安装源文件哈希一致，external-source.json 未安装 Core，native-source.json 实际 Core 固定；锁和声明未改。前端复用依赖目录与候选package-lock.json逐字一致，构建缓存属于本任务。

| 验证 | 命令/结果 | 证据 |
|---|---|---|
| 无 Core 按锁生产入口/历史/能力 | `python -P -m pytest --import-mode=importlib -o pythonpath= --no-cov` 定向5文件，132 passed（Codex整套78） | external-final-locked-tests.txt |
| Native 同锁原用量、上下文、共享历史 | 同命令在 native-venv 定向5文件，62 passed | native-final-locked-tests.txt |
| Codex 整套源码生产 Facade/Runtime 回归 | 补充前77 passed，新增窗口缺失反例1通过；最终按锁集含整套78 | codex-direct-final.txt、codex-window-clear.txt、external-final-locked-tests.txt |
| 前端既有控件与历史 | 原 test:context-usage 两文件、test:subagent-history 一文件通过；含中英文、缺失、0、累计和刷新恢复夹具 | frontend-context.txt、frontend-history.txt |
| 构建 | 原 npm run build 通过，保留既有大chunk提示 | frontend-build.txt |
| 真实 Web→Gateway→Front/Worker→SDK/CLI | 两轮正常、工具执行中取消、原会话继续；全部沿原渠道 | channel-report.json |
| 独立原生对账 | 原 CLI 会话日志六字段逐值相等，窗口258400一致；原生 turn_aborted 后原线程新turn完成 | native-reconciliation.json |
| 真实历史 RPC | 按原流式/项目/page_idx参数，27帧含5快照，最新值与原生一致 | history-rpc-report.json |
| 真实浏览器 | 原按钮展开；整页刷新详情逐字一致，无缺失占位/占用百分比；截图已存 | ui-report.json、ui-usage.png |

最终候选真实输入67091、输出133、总67224、缓存输入53346、缓存写入13730、推理输出0；原生窗口258400。取消后续聊只有原生累计快照，本轮 usage 缺失，符合不猜基线的约束。子Agent累计、占用率、会话命中率、压缩事件没有新增成功结论。浏览器只验证统计与该会话历史，不代表整个无Core产品或已安装桌面版通过。

原失败保留：受限执行环境的异步Facade测试停在等待，超时终止；正常进程环境下复验。新测试曾误用原Facade终态/codec参数、复用了控制request_id关键字、误认历史页顺序，已对照既有契约修正，不改产品绕过。计数倒退反例发现缺少前一快照比较，已修正并通过。首次真实脚本早连Gateway；另一次等待取消后不存在的聊天终态；历史脚本缺原页码/流式参数；UI保留时限届满曾被脚本误记为功能失败，已分开记录并在最终候选收尾前停止。均修正验收脚本后按原生产入口重验，失败日志不删除，不能记为对应产品失败或成功。

## 检视与交付边界

本轮差异自检覆盖 Provider→原事件/codec→Facade历史→Web实时/恢复→原控件；计数重放、未知调用数、失去基线、外部/旧Native兼容分别有定向证据。本轮独立增量11个产品文件+262/-84、3个测试文件，不混入继承P1/输出保护。没有独立审查人签字或CI stable结论。未提交、推送、创建PR、合并、发布或更新已安装桌面版；继承P1/输出保护也仍未提交。本机Linux源码/正常安装渠道通过，不宣称Windows/macOS安装包验收。

验收收尾已通过原API关闭Worker、确认IPC关闭，Front/Gateway退出0、私有配置副本移除；预先记录的Worker3370339、Codex3370388及工具宿主3370591均确认退出（owned-processes-before/after.json）。无Core关机日志中原有KV清理导入Core警告仍保留，非本轮新改动，不据此宣称整个无Core产品所有功能已验证；本轮自有进程退出有独立证据。

## 累计标签与统计范围澄清

按用户要求，只有一行有效累计时隐藏 Main Agent/主智能体分类，已有两行 Native 分类保留。该显示调整不改变计数口径：当前只映射绑定原生 thread 的 total，不接收或汇总子线程用量；官方通知按 active thread 报告，尚未证明父线程 total 包含全部子智能体。不能将当前数值宣传为所有智能体总量，也不能直接相加父子累计。后续需同一次真实子Agent任务对账后再确定覆盖范围。中英文原 context-usage DOM 回归验证单行标签隐藏和双行分类保留；未重跑模型访问、未更新安装包。

## Claude / OpenCode 续接与 Tokens 文案

用户追加授权将单行 Main Agent 改为 Tokens，并将只读观测延续到 Claude/OpenCode。本节替代上节“单行隐藏”的当前显示结论；原 Codex 验收事实、限制与未发布状态保留。只修改当前独立候选，先保存本轮前补丁、dirty 文件和摘要到 evidence/other-providers-start；已刷新 origin/main，HEAD 仍为 0fc0e316a33ffbdd44b2ae2ba72969ae23d0f410。Core、协议和 SDK 锁均未升级，原候选与主目录不切换。

### 实际实现与口径

- 三家单行数值统一显示 Tokens；Native 原有多行分类保留。Claude/OpenCode 在原快照上使用可选 scope=native，由同一详情显示“原生用量”，不宣称是整个产品会话、账户或团队树的统一累计；旧 Native 不带 scope 时沿原累计标题。
- Claude 的唯一原 SDK 消费者，在原输入回显被接收、ResultMessage 会话身份匹配后，投影 model_usage；跨模型同字段求和，任一模型未返回该字段就隐藏对应总计。该原生汇总包括子Agent，不能再叠加 AssistantMessage 或 ResultMessage.usage。inputTokens 为非缓存输入，缓存读写分别展示；没有原生总Tokens/推理字段就不合成这些指标，不猜模型调用数。重复快照替换、不相加；失败结果仍可提供已发生用量，error_during_execution 的全零可疑快照隐藏并保留诊断，而正常明确返回的0保留。
- Claude 的原生累计范围由 CLI 定义。本机 SDK 0.2.115 配置的 CLI 为 2.1.274（SDK 自带 CLI 2.1.206）；官方文档说明 v2.1.277 之前 SDK resume 会重置调用累计，因此本次不把返回快照当作跨进程产品会话总量。无需新增版本拒绝规则或外部持久账本；只显示原生已报告值，主动上下文查询仍未开放。
- OpenCode 只采当前原生 session 的已完成 assistant message，以 message ID 覆盖去重，不叠加同源 step-finish。单个消息缺字段或补0来源不可辨时，隐藏该字段累计，不能把已知部分的和当完整总量；保留官方原生 total（有返回时）。input 为非缓存输入、output 不含独立 reasoning，缓存与推理保留原生分类，不与其他 Provider 强行统一或反推总量。
- OpenCode 正常新会话从空原生会话开始；恢复绑定仍走原校验/服务，首次只读 GET /session/{native_id}/message 重建计数基线，不重发历史任务。读取上限5秒，观测失败隐藏无可靠基线的统计，聊天原入口继续；不进入原 Turn 总时限，不建设第二队列/状态机/持久账本。保留 task=deny。
- 原生标识放 provider.<name>.native_session_id，产品 session_id 不变。继续使用原 usage_summary / history / UI，流量只含数值和来源，不携带模型密钥、工具大正文或完整原生历史。没有额外压缩、轮询、执行调度、审批或前端控件；Core 不改。

### 本轮验证与限制

证据仍在 artifacts/codex-usage-observation-20261104；实现细节以最终源码和 other-reviewed-*-source.json 的非editable实际导入/文件哈希为准。前端原 test:context-usage（中英文 Tokens/0/缺失/Native多行）、test:subagent-history（含真实流式信封和来源身份）及 npm run build 通过，构建保留既有 chunk 提示。Native 同锁原账本/上下文/共享历史62通过。三家 Provider 原 Facade/Runtime/能力与历史的最终定向结果见 other-delivery-locked-tests.txt，不以此前版本的通过替代。

OpenCode 1.18.18 在原 Web→Gateway→Front/常驻Worker→官方CLI/API 两轮成功；原生数据库的所有可显示字段逐值对账，缺失/补0字段一致隐藏。原 history.get 保留计数；真实浏览器显示 Tokens，整页刷新前后逐字一致，未出现未知/未报告占位（other-tokens-ui.png、other-ui-report.json）。原Worker正常关闭后在同数据环境重启，恢复相同原生session并续聊，统计基线和原生数据库再次相符，历史再次匹配（real-opencode/evidence/resume-report.json、other-opencode-full-reconciliation.json）。真实验收后OpenCode仅补类型注解及标准库Any导入，统计/执行主体未改；最终按锁安装与回归再次核验。

Claude 真实原渠道180秒未返回有效结果；原生 CLI 自身轨迹明确记录10次 HTTP429重试（claude-native-api-diagnostic.json），属于当前原模型服务阻塞，不修改外部源码或换路绕过。Claude 的映射/错误/快照/原历史确定性回归通过，但最终真实模型、真实子Agent用量对账和浏览器验收仍待服务恢复，不能记为已完成或已发布；未用别的渠道成功替代。当前也未新增任一家的精确占用率/命中率或压缩功能。

### 实测暴露的问题及修正

首轮来源元数据用了 session_id 承载原生身份，真实流式历史的防串会话递归校验因此拒收统计，虽然后端记录和文件预览都能读到。只在两个 Provider 映射改为 native_session_id，保留宿主原校验；新增流式信封回归，最终真实OpenCode刷新通过。旧帧/失败UI等待保留，不能把首轮后端成功称为UI通过。

最终定向回归另暴露原 Codex 取消参数化用例只按 stage 复用 session ID，切换 tmp_path 后元数据缓存仍带上个参数的不可变目录，触发恢复绑定拒绝；将测试身份包含 failure 参数，保留同一用例内多轮/取消/续聊身份不变，不改生产保护、不跳过用例。首次 Native 命令误写测试目录也保留为命令错误，随后按真实路径62通过。其他失败文件不删除，不扩大白名单。

尚未提交、推送、PR、stable、合并或打包，已安装桌面版不变。独立CLI、P2、独立插件分发、异常强杀接管仍不在此次范围。


本轮最终交付核对：other-delivery-locked-tests.txt 为320 passed（含取消参数化测试身份隔离修正），other-reviewed-native-tests.txt 为62 passed；other-reviewed-external/native-source.json均记录最终7个Python产品文件与非editable安装逐字一致，Core/协议固定来源和锁哈希未变。产品独立增量8文件+161/-2；新增/修改测试5文件，未计继承P1/输出保护及前轮Codex增量。前端构建后未再改产品前端，只有补充原生身份的流式历史测试；该测试集已重新通过。OpenCode最终原生计数来源与真实报告记录保留，不把Claude后续仅本地映射的改动误称为真实通过。

本任务4次Worker关闭均确认PID已退出、IPC已关闭、Front/Gateway退出0；两次临时前端原SIGINT未退出，经核对既有PID/完整命令后正常SIGTERM退出，未回收其它进程。私有主配置与两个OpenCode服务模型配置副本均清理（other-resource-cleanup.json）；原生数值/历史证据保留。已确认窗口未返回时不补值、Claude未提供总Tokens时不合成、OpenCode来源不明0不当成真实0。不宣称跨Windows/macOS或已安装桌面版完成。

最终补齐新模块类型注解后，以同锁非editable来源再次核对7文件一致；最新完整定向记录为 other-final-annotated-locked-tests.txt，Native记录为 other-final-annotated-native-tests.txt。OpenCode真实链路证据适用范围见 other-real-evidence-applicability.json：后续仅类型注解/标准库导入，不声称较早原始文件哈希与最终文件逐字相同；没有执行逻辑变化。
