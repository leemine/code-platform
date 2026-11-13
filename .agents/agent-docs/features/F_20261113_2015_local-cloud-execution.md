---
id: F_20261113_2015_local-cloud-execution
title: 本地页面云会话执行与目录请求期限
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway/services, gateway/extensions/data_sync, jiuwenswarm/channels/web]
files: [gateway/services/cloud_execution_bridge.py, gateway/services/cloud_resource_address.py, gateway/extensions/data_sync/ui_extension.py, jiuwenswarm/channels/web/app_web.py, jiuwenswarm/channels/web/frontend/src/services/webClient.ts, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/useCloudCatalog.ts]
designs: []
design_note: 用户明确授权定位旧目录失败并沿用三段式UI接通本地页面云会话，验证后提交CI和合入；本记录保存实施事实，当前契约归S_02_code-workspace-entry。
---

# 范围与解耦

基线4a9ceecfae485c8af391b103b2baae2dd7efa088，候选codex/platform-cloud-execution-20261113。参考codeswarm 24f29148193b5b590fe9f4b3e21f779c87253e5e的cloud_entry账号/目标地址和原通道委托方式；本项目使用自己的WebChannel插件接口。当前Core/protocol锁定版本保持，不复制参考工程的项目存储或执行生命周期。

本地目录、Local/Cloud、云环境/目录保持三段式。选择位置不连接；具体操作按已登录账号连接固定云目标。目录open显式address_version=1返回带目标/主体作用域的项目地址，旧无版本请求保持兼容。新会话携带明确execution_target，缺少云项目也不能退回本地执行。历史会话沿绑定路由，跨端previous_session引用删除。

独立同源WebSocket只转换协议资源引用并委托原云WebChannel。消息、审批、停止、模型选择、历史和重连复用原客户端与云Runtime；输入不重发，不新增执行队列或历史库。历史协议记录的元数据需单独映射；记录内用户内容、工具参数/结果和Provider绑定仍不改写。云模型目录不覆盖Local目录，账号变化清理云端显示状态和重连游标。原目录池/元数据同步池不升级为执行通道。

# 目录失败诊断

旧浏览器两次“工作区暂不可用”没有可关联的请求阶段记录，不能认定为会话过期。基线真实云新登录、热连接和空闲65秒后的读取均成功；空闲组身份校验+读取+身份校验约19.339秒，说明重建链路存在波动，但未复现旧失败。

确认的缺陷是本地Web HTTP转发30秒，而目录后端150秒、前端155秒。候选仅将目录HTTP和云会话WS握手的代理等待提高到175秒，后端目录总处理限制150秒；普通HTTP仍30秒。真实回环慢响应回归验证普通接口超时、目录接口成功、写入只发送一次。增加阶段/响应码/耗时日志及Server-Timing，不记录凭据、路径或用户内容。此修复不等于证明旧两次失败的唯一根因。

后续真实验收捕获独立的登录503：空闲HTTP池复用已关闭连接，约0.8毫秒即RemoteDisconnected。发送前淘汰空闲超过4秒或已可读的连接，不在写请求失败后重放。真实回环HTTP/1.1服务主动FIN后，下一次登录在新TCP连接仅发送一次；既有TLS热连接复用与逐次权限校验测试继续通过。该证据不能反推旧两次目录失败的唯一根因。

最终包复验再次捕获云执行WS失败：目录成功后，云身份/连接准备约10.5秒，底层websockets服务端默认10秒Upgrade期限先关闭；外层代理175秒不足以解决。改为同源/容量检查后升级本地传输、在后台完成原权限/连接校验，完成才发送既有connection.ack；前端等待该回执才发业务请求。受控身份屏障用例验证握手不等授权、授权前零云请求/零数据、放行后唯一请求执行。旧HTTP/1.0错误是本地代理502包装后的表象，失败日志保留。

检视补充Local/Cloud全局运行状态合并、云配置通知只刷新云目录、离开Cloud Code恢复Local草稿模型选择；回到Code保留此前云选择。历史会话自身绑定不随全局选择修改。

# 验证进展

源码定向后端44通过（data_sync、慢HTTP、WS握手及云就绪门控），六组既有前端回归通过；最后的事件泛型修正后web-client-runtime-ack重验通过，跨工作模式与项目选择边界由workspace-store回归通过。最终Python候选按锁非editable安装、Core/protocol/SDK实际来源与源码核验通过，Native生产边界1156通过、3个Windows条件跳过，179.29秒。命令见任务工作区validate.py与package-candidate.py；结果分别在evidence/backend.log、validation.json、package-Verify-installed-sources.log和package-Test-production-boundaries.log。最终前端构建与非editable发行包源码核验通过；来源摘要保存在candidate-source-sha256.json，不转记旧候选或旧前端产物成功。

真实云使用既有隔离部署和已批准GLM测试模型，从本地安装包入口完成登录、目录list/mkdir/open、云模型读取、会话创建、真实流式执行。原Runtime任务终态succeeded，执行12.695秒；实际写入并读回bridge-proof.txt，SSH独立核验内容严格为CLOUD_BRIDGE_OK。空闲后重新登录同一账号读取12条原云历史，包含证明文本且会话引用保持限定地址；新一轮纯文本流中发送停止，8.415秒收到回执，11.895秒恢复到cancelled且is_processing=false。证据见cloud-stop-verified.json/log和cloud-stop-file-audit.json。

验收脚本曾错误等待结束事件、使用limit=100，以及只读取旧content字段而漏掉当前message字段，分别造成超时/断言失败。保留失败后按原前端消费者协议修正，恢复同一会话验证，不重发文件写入。真实审批交互和右侧完整点击仍未验证，不把TLS桥的受控审批用例当成真实用户审批成功。

多次本地增量打包暴露build/lib缓存遗留：最新dist255文件，安装包453文件；当前255文件内容均相同，多余为旧哈希资源。旧缓存移到任务证据目录外的本地归档后重新按锁安装；package-assets-final.json确认255/255文件逐字节一致，实际Python来源再次核验。产品源代码摘要与已通过的1156项生产边界候选一致，额外只读恢复检查独立记录，不转记为新的全量测试。


早期浏览器工具返回“Local browser use is disabled in Work settings”，当时自动点击验收受阻；用户启用后已进入右侧真实点击续验。当前不把API测试当成浏览器成功；未提交、未推送、未通过远端CI、未合入。管理仓记录按用户指示仅保留本地。文件双向同步和运行迁移不在本次交付范围。

# 浏览器权限恢复后的登录排查

用户启用浏览器权限后，右侧本地页面仍显示账号服务不可用。2026-11-13 21:52:50任务网关已停止，预览端口服务不在运行；浏览器继续执行身份状态GET并每2秒重试，不是重复提交密码。恢复同一任务安装包服务后，同一账号在本地原位一次登录成功，后端login记录6130.6毫秒，左下角显示账号头像。云端独立页能够显示登录表单，不能把本地服务停止归因于云账号密码错误。

修正账号故障恢复显示：后台探测保持错误视图，完成后2/4/8/16/30秒退避，手动/后台单请求互斥；身份校验与失效关闭不变。29项cloud-workspace行为回归通过，覆盖稳定提示、慢请求不重叠、退避、同身份恢复和变化身份清理。首次沙箱测试进程失败单独记录；放开本地子进程后的旧用例仍期待checking，更新为本次稳定unavailable契约后29项通过。

真实点击续验：三段式选择Cloud保持本机URL，原位登录头像、云环境选择、目录加载时输入、创建新文件夹均通过。一次目录open在身份前置校验处出现SSLEOFError（5004毫秒），刷新核对后open成功；身份未失效、不重发mkdir。目录list19834.9毫秒、mkdir14737.1毫秒、再次open20600.3毫秒；这些是本次网络条件的观测，不作为严格前后性能对照。

首次新云会话UI出现1008，但SSH与原历史证实任务已成功执行18.23秒，ui-proof.txt内容CLOUD_UI_OK精确匹配；未重发文件任务。纯文本复现确定触发请求为address_topic_starters.get：创建切换时云project prop先更新、active editor仍为本地new，占位ID触发地址保护。ChatPanel在不匹配的瞬态跳过该推荐读取；地址隔离、实时鉴权和关闭规则不放宽。补充脱敏method/stage日志，仅记录经过格式限制的方法名和异常类型。

同期捕获identity_models.list的TLS EOF，原实现把所有SSLError等同证书错误而禁止只读恢复。仅SSLEOFError/SSLZeroReturnError按原预算允许只读重连一次；证书/主机名/其他TLS协议错误仍直接失败，登录/ensure/发送不自动重放。8项专项传输/桥回归通过，随后全范围定向45通过、六组前端通过，发行包与完整UI复验中。

# 最终候选UI验收

修复包完成右侧真实新云会话创建、发送并直接展示CLOUD_UI_FINAL_OK（8.15秒），未再次出现1008；继续长文本流后点击停止，原Runtime终态包含cancelled且is_processing=false。刷新恢复原历史，项目侧栏显示云任务；创建云环境入口对已有环境执行幂等准备成功，Local→Cloud切回保留云目录，始终停留127.0.0.1:29011。原登录cookie跨任务服务重启保留，不再重复登录。新建环境验收针对既有账号已有环境的幂等准备，不声称新建多环境。

独立只读复核同一UI会话：元数据1.231秒，6条历史3.839秒，包含CLOUD_UI_FINAL_OK；ui-final-session.json。安装包Native1157通过、3个Windows条件跳过（182.66秒），255/255前端资源一致；定向45通过、六组前端及推荐18项通过。真实审批交互与External Provider仍未扩大；文件任务首轮已执行且已独立核验，不重发。

性能限制：一次页面刷新初始化日志出现19次耗时超过日志门槛的账号status调用，单次最大5.134秒；从连接启动到最后初始化校验约29秒。调用存在重叠，不能把累计27.453秒当作历史读取时间。独立热连接的历史读取3.839秒与页面冷启动不是同条件前后对照。后续应分阶段记录首条历史时间，减少重复初始化、优先恢复历史并复用连接；不通过缓存授权或关闭实时权限校验提速。


# 历史首屏优化续接（2026-11-13）

本次用户明确授权优化首屏、保留实时权限，并完成真实UI、CI及合入。原首屏被Local连接门控，并在云通道中排在模型、配置、附件、推荐等读取之后。改为layout阶段初始化runtime并发起metadata/history，云请求自行等待云连接；Local恢复仍等待原Local连接。相同status只合并未完成请求，完成/失败及账号变化均释放，不缓存权限结果。

新增connection.cloud_ready通知只供云端只读恢复使用：重连后读取当前metadata、尚未完成的history及catalog，不重发聊天输入。网络错误不再误标NOT_FOUND。实际验证发现原30秒历史timer包含云连接等待，增加可选requestStarted起点；云首屏从实际发送开始计30秒，连接仍由有界传输预算限制。后续分页不改，销毁后不可重启timer。

受控验证：账号并发/失效与云独立连接回归并入原前端套件；history-restore-pagination 9通过；云桥实时撤权7通过。原安装包Native1157通过、3Windows条件跳过；定向45通过及六组前端通过。首次受限沙箱定向夹具无法建立端口、已中断并保留原日志，获准本机端口执行后通过，不算产品失败白名单。

性能基线：同账号/同旧会话/同本地安装包入口、完整页面刷新，以历史正文p元素进入DOM为计时终点，两次成功20.341秒与28.647秒。此前getByText定位器未命中不能充当精确性能数据；另外出现ConnectionReset/Timeout样本，单独保留失败证据。网络波动明显，首轮候选连接等待22.726秒、历史前置校验7.407秒触发旧恢复预算，此样本用于修复验证，不能冒称性能改善。最终复测与交付结果随后追加。


# 本轮完整验收与性能结果

最终候选的右侧流程完成：退出→统一表单单次登录（账号HTTP4815.2ms）→选择已有环境→加载目录时输入→新建 cloud-final-20261113-2312→打开→创建环境入口幂等准备→选择批准测试模型→创建并读回 acceptance.txt→发送流式任务并停止→刷新恢复→Local/Cloud双向切换保留目录。始终停留本地29011页面；环境已有，不声称新分配第二个环境。服务器只读独立核验文件精确17字节 CLOUD_DELIVERY_OK；原Runtime回读含cancelled且is_processing=false，历史14条含证明内容。SSH首次banner失败、API首次1011均保留日志；只读重试成功，未重发文件任务。

同账号/同旧会话/完整刷新、历史正文DOM已渲染：基线20.341/28.647秒，最终26.537/13.643秒，平均24.494→20.090秒（约18.0%改善）；两次样本不足以承诺稳定百分比，连接波动仍是限制。云桥就绪到history转发：5.660/6.790→4.496/1.278秒，均值6.225→2.887秒。最终请求顺序metadata、history、models、config，实时身份与投递校验未减少。新文件会话刷新18.839秒，另记功能回归，不混入同会话性能对照。

最终前端生产构建通过，安装包255/255资源精确一致；六组前端回归通过、历史恢复9通过、实时撤权云桥7通过，Native1157通过/3Windows条件跳过（后端不再变动，后增撤权测试单列）。Core e089198835426cd7681761b0cc278670cd83031f、protocol 2a0457e5e01152e9ca5f8afdffd84716227046ca保持锁定，非editable真实导入来源核验通过。没有运行无关每日full-python；远端stable和合入后验证为后续交付关口。

检视范围：基线4a9ceec到本候选41文件，重点核对原WebChannel/Runtime委托、地址映射与用户正文不变、account generation、错误/恢复不重放输入、Local模型与Cloud目录隔离、计时器销毁/续页、同源Host/Cookie/TLS及逐请求权限。未引入执行器、依赖升级或外部Provider修改。新增行为有定向和真实UI证据，无已确认阻断问题。真实External Provider及审批交互未扩大，相关既有stable边界仍运行。提交/CI/合入状态以对应远端SHA记录为准。
