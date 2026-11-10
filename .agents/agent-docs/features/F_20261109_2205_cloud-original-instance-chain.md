---
author: leemine
author_email: leewanlong@gmail.com
id: F_20261109_2205_cloud-original-instance-chain
title: 云账号提炼与原实例链收敛
type: F
modules: [gateway, server/front, deploy/cloud-workspace, channels/web]
files: [jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudWorkspaceGate.tsx, jiuwenswarm/channels/web/frontend/src/features/auth/LoginPage.tsx, jiuwenswarm/channels/web/frontend/src/services/organizationCredentialEvents.ts, jiuwenswarm/channels/web/frontend/tests/cloudWorkspace.test.mjs, deploy/cloud-workspace/CANDIDATE_HANDOFF.md, deploy/cloud-workspace/physical_resources.py, gateway/services/resource_reconciler.py, tests/unit_tests/cloud_workspace/test_physical_resources.py, deploy/cloud-workspace/LOG_BOUNDARY_CONTRACT.md, deploy/cloud-workspace/docker_log_boundary.py, tests/unit_tests/cloud_workspace/test_docker_log_boundary.py, gateway/extensions/cloud_workspace/config.py, tests/unit_tests/cloud_workspace/test_cloud_workspace.py, gateway/channel_manager/web/web_channel_app.py, gateway/channel_manager/web/web_connect.py, gateway/extensions/application_host.py, deploy/cloud-workspace/Dockerfile, deploy/cloud-workspace/Dockerfile.yuanrong, gateway/services/cloud_environments.py, gateway/services/cloud_instance_policy.py, gateway/services/cloud_workspace_assembly.py, gateway/auth/account_http.py, gateway/auth/account_authenticator.py, gateway/auth/request_scope.py, gateway/extensions/agentos/agentos_router/router_client.py, tests/unit_tests/cloud_workspace/test_integration_boundaries.py, tests/unit_tests/server/test_gateway_adapter.py]
designs: []
design_note: 依据管理仓 PLATFORM_CANDIDATE_DISPOSITION_20261109（M01-M12/C01-C22）及用户本会话授权；无独立D编号。
---

# 云账号提炼与原实例链收敛

2026-11-09，在原独立候选工作区恢复产品修改。基线34904d097；初始22文件与处置表逐项hash一致，完整原件/暂存与未暂存补丁已备份。codeswarm只读来源24f29148；Core锁e0891988、协议2a0457e5未变，实际导入为按锁安装site-packages，无editable替换。

## 实现与决策

保留候选账号存储/传输、通用HTTP贡献和实例验签方向；增加独立账号HTTP角色、原Authenticator适配、独立环境库和策略注入。退出cloud_workspace/yuanrong.py及__main__.py生产源码，原件仍在管理任务before快照。插件仅入口，无元戎客户端、物理任务队列、独立WS和本地账号库回退。

原Router新增启动策略/回执/恢复/就绪认证窄接缝，仍用原AgentManager single-flight、连接池、持有和回收。修正原超时再次POST及预热丢弃FAILED两条重复创建路径；未知结果没有唯一回执不重发。删除后必须单实例GET确认404，且内存删除按instance_id比较，避免迟到清理删除新代次。原连接网络失败不会销毁云绑定实例。

实际发现原消息队列不携带认证任务上下文，因此新增通用进程内scope包装，未登录消息仍是原Message；不向协议metadata加入Cookie。可选guard在原Web帧入口、WS writer及文件HTTP出口复核。真实WS测试发现PermissionError继承OSError，会被旧发送异常分支误判网络故障；验权移到网络try之外。相对initial_dir解析存在根包含缺口，已沿原WorkspaceFileAdapter修正，不另造文件实现。

## 范围和差异

注册先返回持久NEW，物理创建由显式ensure或原连接预热触发，避免插件另持后台任务。单写者是当前部署限制；兼容旧绑定需显式导入，未自动重写既有六字段凭据/历史环境数据库。云角色目录/UID由配置与挂载约束，真实元戎仍待验。

本轮完成后台收敛；未新增原账号前端UI或跨宿主Local/Cloud选择接线，未完成角色镜像构建/真实Provider/现网部署。已有Local选择方法未被插件占用。完整目录、同步、执行交接继续后置，不能把本轮后端测试写作特性1～2整体完成。

## 验证与证据

管理任务implementation-20261109保存startup.json、修改前快照、implementation-snapshot.json及全部测试日志。初轮受限环境出现asyncio线程唤醒阻塞；10秒faulthandler记录和超时原件保留，使用同一解释器/锁定来源、临时目录在正常权限下完成测试。

affected-tests-5.log：425 passed（30.38秒），无失败/跳过。覆盖原Router/元戎/清理/插件、HTTP/WS/文件认证、模型配置热加载、权限、下载、原消息队列/取消/cron，以及真实本机账号HTTP和原WS客户端/Front协议。boundary-tests-6.log补测15通过；发现原公共配置模块默认后台只读拉取后，使用原JIUWENSWARM_CONFIG_URL=off关闭并重验。最终final-tests-8.log：430 passed（30.80秒），0失败/跳过，exit 0；另验证权威故障不误报退出、幂等logout、环境不可用映射和文件出口状态。最终摘要以管理验证记录为准。元戎资源为模拟端口，不宣称真实容器/Provider端到端。

四项既有测试由重试POST/清除FAILED旧预期改为保留未知回执；失败日志保留，不扩大白名单。原功能回归结果只对应本候选hash和固定依赖。

## 检视及交付

按jw-review核对本次差异、账户权威、单实例所有权、协议/Runtime复用、认证在入口/队列/出口的实际路径和未知结果。已修复上述预热/网络异常及迟到删除问题。外部验收缺口如上；代码未提交、未推送、未部署。当前为可继续隔离联调的本地候选。


## 角色镜像与隔离联调续作（2026-11-09）

开工40个源码/测试文件摘要一致。新增 deploy/cloud-workspace 三角色 Docker target、上下文白名单和依赖/实际导入核验；从干净源码快照打包，拦截 setuptools 旧 build 将两个已退出入口带回 wheel 的问题。三角色 r2 使用同一新 wheel、原 uv.lock 和固定 CPython 3.13.15 基础镜像；每角色实际核验255项依赖及1587个源码/配置文件，Core e0891988、协议2a0457e5不变。

真实容器注销测试复现 Front 子任务抛 PermissionError 后连接静默超时。仅在 Front 解析边界将认证拒绝明确关闭为1008，实例验签接缝把破损凭据/断言格式统一为拒绝；保留原 Runtime、协议、调度及其他异常行为。补4种真实回环拒绝测试；云账号专项41通过（25.43秒），原Front/启动45通过（8.11秒）。最终容器注销在途断言1008复验通过。

原Gateway→独立TLS账号权威、原WS客户端→真实Front/Runtime、账号隔离、模型/配置/项目列表、重连、注销、四个合成账号跨重启会话/绑定及卷标记已验。手动测试Agent使用原环境服务实际生成的独立卷/凭据和对应候选镜像，未伪造元戎创建回执；环境状态仍UNKNOWN，不冒称READY或自动创建成功。

完整元戎端到端仍阻塞：本机无既有专用资源池；共享Docker socket挂载被自动审批拒绝；无socket的官方0.10.0测试控制面在封闭网络中因get_ip默认路由检测失败退出。未改外部源码或扩大网络/宿主权限绕过。后续需专用测试节点/引擎，核验具体runtime/SDK/镜像匹配及真实创建、对账、回收、跨节点卷。完整UI、真实Provider和生产交付仍未验。本轮未提交、推送、部署现网；证据位于 role-e2e-20261109，管理验证记录 PLATFORM_CLOUD_ROLE_E2E_20261109。

## 指定服务器续验与装配修正

用户指定113.207.105.228后，使用独立账号权威、目录与namespace接其既有元戎API；没有给候选容器挂Docker socket。三角色实际导入再次核验，远端Docker29.1.3规范化旧镜像配置导致ID变化，文件层/应用配置一致，分别留档实际ID。

真实创建暴露UID:GID被元戎用于/home/<user>而产生非法挂载：CloudConfig改为POSIX登录名并校验当前uid/gid，镜像采用既有agentos登录名（1000:1000）保留原文件API根。元戎GET不返回name，改为严格核对私有工作区、代次只读认证挂载、固定镜像和运行用户；有name仍校验。FATAL识别为明确失败。相关87项通过。

实际启动进一步暴露/data挂载遮蔽镜像HOME目录，SDK原生模块导入139。标准faulthandler定位后，无网络tmpfs对照明确证实缺少/data/home时139、创建后通过。EnvironmentStore.prepare补私有home并保留原内容，拒绝symlink和宽权限；未修改SDK。并发失败回收还暴露inflight.cancel把HTTP等待者取消，原Router仅单实例关闭改为RuntimeError唤醒，保留整进程关闭取消语义。最终216项受影响账号/Router/元戎测试通过（31.55秒，0失败/跳过）。

最后两项仅影响Gateway，r5使用新wheel/manifest；账号/Agent保留r4已核验角色镜像，Core/协议及实例固定快照不变。完整服务器就绪、恢复、回收与旧服务保护核对结果以管理验证记录PLATFORM_CLOUD_ROLE_E2E_20261109最终结论为准；前述本机缺资源阻塞已被用户指定服务器替代。

### 2026-11-10 服务器原链续验

元戎真实启动暴露镜像漏装独立executor，补入已有官方源码固定提交、固定wheel摘要的原包；应用Core/协议锁未变。代理使用任务namespace作tenant_id时403；实际default租户已收到真实AGENT_READY，修正候选部署配置，任务隔离依赖独立权威、私有工作区与实例epoch凭据，namespace不作为安全边界。

原WebSocket入口还暴露FastAPI适配层丢失AuthResult扩展。仅透传既有认证结果/guards，并由账号模块显式贡献routing_user_id；旧IAM映射保持。握手错误由环境模块映射503，保留已创建回执；通用HTTP贡献兼容未实现http_routes的旧插件。受影响首次205项中204通过、1项旧插件装配失败；修复后对应34项全部通过（host-compatibility-regression.log），未扩大历史失败白名单。本地首轮测试因缺少日志隔离路径被沙箱拒绝、第二轮网络受限超时，后在隔离目录与允许回环环境重跑，不记为产品通过。服务器最终原链验证以管理仓PLATFORM_CLOUD_ROLE_E2E_20261109记录为准。

最终服务器原账号/实例主链、真实WS8项、回收重建7项、撤权5项和真实丢回执恢复通过。目录原文件API正确契约下8项通过、2项符号链接越界失败：测试工作区链接可读取本实例认证文件，未输出内容，列P1发布阻断。不能把既有Runtime路径包含修复转记另一条SDK文件代理安全。后续需在实际文件服务执行边界封闭权限，不能以Gateway预检查消除竞态；本轮未改外部SDK或擅自关闭旧接口。元戎共享日志挂载隔离待验。测试新增容器/实例已全部按归属回收，原180容器元数据和5个元戎实例清单一致；数据未读取/哈希证明为静止，未操作旧账号数据。候选未提交/推送/部署，F1/F2仍待目录修复及未覆盖验收。

## 2026-11-10 B01修复

沿原独立候选修复云账号绑定文件API：原Router/E2A进入WorkspaceFileAdapter，执行端逐级目录FD/no-follow；原元戎SDK不改。兼容注册四个内部文件方法，不新增信封、服务或Runtime生命周期。codeswarm旧元戎代理有同类不足，其受限工作区下载实现提供可复用的FD操作方式；codeswarm源码未修改。具体故障、兼容约束和回归见 `B_20261110_0135_cloud-file-boundary`，不将本轮结论扩展为目录/同步全功能或旧模式全量隔离通过。


### 2026-11-10 B02与既存测试续行

本轮产品源码1589文件与B01最终wheel一致，生产代码未新增改动。仅test_gateway_adapter.py两个session.delete测试桩补enable_writeback关键字、两个配置测试用夹具注册真实A2UI并恢复原注册表。最终相关329项全部通过（38.98秒），保留此前4项失败及r7复现历史；未关闭A2UI或跳过用例。

指定服务器新M/N账号及独立目录、端口复用原实例链，注册16项、WS8项通过。两个实例均能读取对方合成日志，B02确认为共享日志挂载读隔离失败；没有读取旧日志。当前元戎Docker执行器额外挂入全池日志根，codeswarm的Supervisor私有日志配置不能直接复用，未改SDK/旧池。后续基础设施私有日志挂载或独立隔离资源边界未验证，继续阻断发布；不把同实例B01与本轮B02混称同一漏洞。完整命令、来源、测试脚本、保护与回收以管理记录PLATFORM_CLOUD_LOG_ISOLATION_20261110为准。

上游来源补核：元戎functionsystem固定提交6199dc6b的docker_executor.cpp直接下载SHA256 cb5ee566…与服务器解包及构建源码一致，942–944行已有整日志目录挂载。此机制来自沿用历史版本，不是本轮平台新增；不外推最新版。

## 2026-11-10 预建执行池绑定保护

用户同意共享控制面与按隔离边界分池后，先核验固定Docker接口：未暴露逐实例日志覆盖或选池字段，未获得专用可隔离资源。仅在配置与环境profile加入可选placement绑定，注册/恢复/导入/读取拒绝池参数变化，原Router启动前检查；未新增Router/Runtime调度链。该实现只防重定向，一Gateway一端点限制仍在，不能冒称多池路由或日志修复。

17项新增、相关389项全部通过（47.19秒）；干净wheel1589项源码核对通过。新修订镜像安装来源、真实资源隔离E2E仍未运行，B02继续阻断。原SDK、锁与旧部署不改；资源能力、命令和证据见管理记录PLATFORM_CLOUD_POOL_BINDING_20261110。

### codeswarm Docker日志方案补核

此前仅对照Supervisor private_log_mount，遗漏了deploy/yuanrong/docker_log_boundary.py。用户指出后，只读复核24f29148及历史真实双账号记录，重跑21项专项通过；服务器固定DockerExecutor支持unix:// DOCKER_HOST。优先提炼部署适配器，按平台env_受管工作区适配，不新增Gateway/Router/Runtime日志业务逻辑，无须K8s或pool_id前置。本次仅分析与资料修订，未迁入产品或启动代理；B02仍待新候选实测。完整记录PLATFORM_CLOUD_DOCKER_LOG_BOUNDARY_REVIEW_20261110。

## 2026-11-10 Docker日志适配实施及检视

用户继续授权后，从codeswarm24f29148提炼部署适配器，只将工作区规则u_改为env_，迁入21项原测并补4项目录拒绝；25项通过。原1589产品源码、SDK及锁不变。任务新底座使用私有Unix Docker端点，首轮实际日志路径与CLI前缀不同，创建前按实际deploy_path/logs纠正；旧底座不改。

新Gateway镜像f21702d4使用此前pool保护wheel并核验255依赖/1589源码；Agent原镜像重验8525 SDK文件。真实新账号16项、WS8项、原Router生命周期7项通过；双账号首轮及代理重启/实例重建后各自日志可写、对方及平台合成日志不可读。仅为定向B02修复验证，非生产发布。用户要求审视后收敛本轮，不扩展产品功能；服务监督/socket恢复、连接上限/超时、停机故障拒绝、日志采集配额和完整协议兼容待补。全部结果、清理及代价见管理记录PLATFORM_CLOUD_DOCKER_LOG_BOUNDARY_20261110。

## 2026-11-10 临时部署适配器解耦

用户确认临时可替换定位后，在同一独立候选继续收敛。开工1589应用文件及部署适配器/测试与前轮一致；部署模块只增加必填workspace-name-pattern及启动校验，以fullmatch检查目录名，保留独立文件系统边界。无隐藏env_/u_默认，平台命名仍由原环境服务生成，装配显式提供规则。日志键仍是工作区绝对路径摘要，兼容规则调整不迁移旧日志，不引入账号查询、状态库、Gateway开关或代理框架。

新增LOG_BOUNDARY_CONTRACT.md集中定义参数、旧实验命令必须补参、替代机制统一结果验收、按原生命周期切换、对账/回退和最后退役顺序。先选择显式配置而非通用插件/目录映射服务，以保持组件可删除且业务不依赖实现。旧日志按保留策略处理，不随退出删除；上游原生替代方式仍待真实能力核验，不伪造native模式。

43项专项全部通过（7.01秒）：原保护回归、两种部署目录规则的真实CLI/Unix转发、缺失/非法配置启动前拒绝、自定义规则不放松目录边界、兼容规则保留日志目录及内容。本轮仅本地临时文件系统/假Docker端点，没有服务器操作；旧25项和服务器成功证据归属旧脚本，不转记为新CLI部署成功。SDK/锁/Gateway/Router/Runtime未改，未构建应用镜像或部署。必要可靠性缺口继续保留，不将临时组件扩成通用网关。详见管理记录PLATFORM_CLOUD_LOG_ADAPTER_DECOUPLING_20261110。


## 参数化适配器服务器复验（2026-11-10）

本轮沿用原工作区、参数化脚本3be037d7与固定角色镜像，仅新建专属113服务器底座。缺失/非法命名规则均在socket创建前退出2；显式env_规则、实际9个元戎进程DOCKER_HOST及runtime_launcher参数一致。16项账号、初始8项和重建后重复8项WS、7项原Router生命周期通过；初始/人工代理重启/实例重建后三轮双账号实际挂载及自身SDK日志、对方/平台合成日志拒绝通过。同工作区私有日志源、历史SDK日志及工作区数据保留。

配置证明脚本首次错误期待socket0600，修正为契约规定的私有父目录和实际0700模式核验后通过；清理及最终基线各一次SSH握手EOF，未执行远端命令，分别重试成功。产品代码、SDK、协议及锁无本轮改动；不将既存43项本地测试算作本轮新增测试，不将人工重启算作自动恢复或停机故障注入。完整收尾、旧环境对照与证据统一见管理记录PLATFORM_CLOUD_LOG_ADAPTER_SERVER_20261110。


## 临时日志适配器运行保障与故障发现（2026-11-10）

用户授权第1、2项：仅部署适配器补连接名额、请求/上游/流空闲超时、信号退出清理、受flock保护的显式残留socket恢复，并提供原生systemd模板。保留临时可替换定位和原日志映射，不重放Docker请求，不加业务状态库/监督服务。新增15项加原43项共58项专项通过；源文件9421fe5a及固定应用镜像在113专属新底座验证。应用1589文件、协议/Core锁和SDK未改。

停机及模拟上游503安全失败；原链异步清理可确认GET404后转DELETED，测试需按状态和物理证据核验，不能强求永远ALLOCATED。创建已提交但201丢失时杀死代理，systemd自动恢复成功，但元戎API404后仍遗留一个从未启动容器，原链重试产生第二物理容器；最终保留重复容器断言失败作为真实阻断。未修改SDK、未添加代理分配/回收链；只按已证实归属人工移除任务残留并保留数据，不能把此清理算产品修复。删除超时独立验收、全部失败与最终旧环境对照统一见PLATFORM_CLOUD_LOG_ADAPTER_RELIABILITY_20261110。当前不能标为故障验收全通过或可上线。

## 2026-11-10 物理残留修复

上一轮真实故障证明元戎GET404不能代表Docker容器已删除。按用户授权继续原工作区：宿主Router只在两个既有删除入口各增加3行可选异步确认，协议声明同步；环境策略校验持久epoch/instance/state后调用部署受限Unix接口，失败仍DELETING。创建仍仅原Router委托元戎，未改SDK、Runtime、账号权威或另建调度。

部署侧新增最小派发回执与工作区唯一Docker名称；创建转发一次，201先落回执再回复，旧代/未决代拒绝重复派发。确认沿原删除同步调用，严格匹配镜像/用户/工作区/只读凭据/标签，仅补偿从未启动残留，不删除卷；Gateway仅挂载只读受限socket目录。选择独立部署模块而非Gateway直连Docker，使临时实现可被原生物理完成机制替换。原日志命名准入参数保持，业务不引入Docker字段。

本地原Router及云环境相关261项通过；部署模块最终71项通过（与前组有重叠，不相加）。第一次新增测试出现2项失败，为断连接异常和业务异常包装的测试期望不正确，修正并复验；沙箱内asyncio/IPC挂起与初次uv缓存只读失败单独记录，不算产品失败。独立服务器结果统一写管理记录PLATFORM_CLOUD_PHYSICAL_RECONCILIATION_20261110；未部署现网。

有效契约见S_01及LOG_BOUNDARY_CONTRACT。未知SENT且从未观察物理资源/201时仍保守阻塞；历代回执需保留，暂无自动压缩；旧部署不自动切换，不把新底座成功外推成全部原环境已修复。

最终113复验：原链故障脚本23项通过，真实201丢失/SIGKILL后补偿清除未启动孤儿，204丢失后重建无重复；迟到旧代502且未上游派发。前后两轮双账号日志及各8项WS通过；10回执全DELETED、任务资源清理、数据保留，旧180容器状态/5元戎清单未变。无现网部署；完整证据见上述管理记录。

## 2026-11-10 候选交付收尾

按用户确认停止新增功能，仅核对差额并整理配置与恢复说明。1970个wheel对应文件、上一轮9个实现文件、uv.lock及26份证据摘要一致；开工完整候选72文件（含源码、部署、测试、文档索引）留档，原重复客户端源码与wheel均缺席。Router最新6行确认接缝不冒充整轮集成总改动量。

操作说明集中于deploy/cloud-workspace/CANDIDATE_HANDOFF.md；明确DELETING/UNKNOWN/SENT等恢复入口、可证明完成条件、不能强制解除的状态、备份及回退边界。纠正文档中旧“API404即完成”及旧阻断的时态，不修改产品执行代码。验收及唯一任务状态见管理记录PLATFORM_CLOUD_CANDIDATE_HANDOFF_20261110与任务台账。

本次后台集成修复及候选交付范围完成，原独立dirty保留待后续提交/合入决定；不部署现网。日志运维、完整UI/真实Provider、跨节点/旧数据迁移为后续独立范围，不再追加为当前完成门禁。本轮不连接服务器或操作任何账号/实例/数据，不把以前的隔离验收表述为本轮重新执行。

## 2026-11-10 本地候选提交

用户在候选收尾完成后授权继续提交。该版本按原任务分支独立提交产品代码、部署适配器、测试和说明；管理仓另行提交方案与证据并记录两仓提交关联。源码/锁与冻结候选一致，不新增功能，不推送/合入/部署。提交号、检查及后续评审状态见管理记录PLATFORM_CLOUD_CANDIDATE_COMMITS_20261110；此前“未提交”为对应轮次历史状态。


## 2026-11-10 候选评审与 PR 修复

在70958004相对34904d09的73文件候选差额中，确认P1：MessageHandler四个内部审批/补充消息生产者直接写队列，绕过capture；consume恢复时清除账号作用域，普通chat.send被维护用途白名单拒绝。6项定向用例先复现身份断言失败；仅改四个调用点复用原publish_user_messages_nowait，无新队列、凭据持久化或身份权威。新增3入口正常/撤销6例及真实forward_loop补充消息1例。首轮夹具漏填Message的timestamp/ok产生6项测试失败（夹具缺字段），修正后才记产品复现；受限沙箱首次导入无输出挂起，超时回收，不计通过。

本地399项受影响回归通过（69.70秒）：cloud_workspace、文件边界、原Router、元戎客户端、原演进审批和Web双协议。使用原隔离native-venv与独立JIUWENSWARM_HOME，本地来源不替代干净按锁CI。CI原stable遗漏本次云集成测试与协议VCS实际来源，native矩阵补上述范围，两个矩阵补协议URL/SHA/subdirectory及导入路径核验；Core/协议/SDK锁均未改变。CI最终SHA、运行与状态在管理记录PLATFORM_CLOUD_REVIEW_PR_20261110留档，不预记远端通过。

部署适配器、物理回执、文件边界与实例策略源码未改；既有113隔离证据继续仅证明对应旧角色镜像及其未变路径，本轮无服务器操作、新镜像或现网启用。新版Gateway身份重新入队通过本地装配验证，尚未以新镜像执行服务器真实Provider业务。用户授权推送和创建PR，未授权合入或部署。

## 2026-11-10 续修：账号 UI 与云环境入口

依据 codeswarm `24f29148193b5b590fe9f4b3e21f779c87253e5e` 的 LoginPage、OrganizationStatus、凭据变更事件和 LogoutButton 提炼 builtin 用户名密码路径。保留原 Account Kit 模型授权；不移入组织治理限制或第二套实例链。入口先确认身份，首次绑定须点击进入；ALLOCATED 仅作持久回执，必须经原 environment.ensure 返回 READY 后才挂载原 App/WS。

宿主差额为 main 入口包装、App/SessionSidebar 通用 footer 槽、连接提示 20 秒错误/重试及卸载清理。账号 HTTP 插件状态增加当前凭据摘要前 24 位 session_revision，便于沿用 codeswarm 身份续期隔离；不增加账号存储、Authenticator、Runtime 或 SDK 状态机。

身份检查 10 秒超时；5xx/非法状态关闭门控，只有初次明确 disabled/404 沿用本地入口。凭据变化、失效、退出先断开旧连接，确认后清缓存并整页导航；状态只由服务器核验，广播只作失效通知。就绪请求 150 秒超时仅表示响应未知，不取消或另建创建请求；重试仍走原绑定对账。

本地：入口行为测试 13 项（含迟到 ensure、退出失败、权威故障、注册与错密），原 Account Kit/WS 回归 24 项，账号 HTTP/实例链定向 44 项；生产构建通过。113 新隔离环境真实 UI/Native/Codex 验收进行中，尚不标记端到端交付完成；未合入或部署现网。
