---
id: F-20261112-1545-platform-directory-sync
title: P1S-02 显式项目目录同步首轮候选
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway/extensions/data_sync, gateway/services/data_sync, jiuwenswarm/data_sync, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend/src/components/ChatPanel, gateway/channel_manager/web]
files: [gateway/extensions/data_sync/extension.py, gateway/services/data_sync/store.py, jiuwenswarm/data_sync/connector.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/data_sync/__main__.py, jiuwenswarm/server/runtime/session/project_store.py, tests/unit_tests/data_sync, tests/unit_tests/cloud_workspace/test_data_sync_cloud_role.py, gateway/services/data_sync/cloud_source.py, jiuwenswarm/data_sync/cloud_export.py, gateway/services/cloud_environments.py, gateway/extensions/agentos/agentos_router/router_client.py, gateway/common/security/service_auth.py, jiuwenswarm/server/runtime/gateway_adapter/project_adapter.py, .github/workflows/stable.yml, gateway/services/data_sync/ui.py, gateway/extensions/data_sync/ui_extension.py, gateway/auth/account_authenticator.py, gateway/extensions/auth/common.py, gateway/channel_manager/web/web_connect.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudWorkspaceGate.tsx, jiuwenswarm/channels/web/frontend/tests/directorySyncDialog.test.mjs, jiuwenswarm/server/control/repositories/project_repository.py]
designs: [code-projects:D-20261112-1120-platform-workspace-sync]
---

# P1S-02 首轮实施

用户授权先闭合 P1S-01 交付、通过后提交，再推进 P1S-02 契约和开发。独立分支 codex/platform-p1s02-sync-20261112 基于已提交 P1S-01 92b6897，后者正式 stable 43173950695 全部通过；本候选尚未提交/合入。首轮时原主线5048bd0、Core和codeswarm未改；后续主线合入见下方续记。契约见 S_03_data-sync-directory，管理设计第5.2节；完整P1并未视为已交付。

## 实施与参考

参考 codeswarm 的 sync_store 冻结快照、增量墓碑、操作回执和ACK丢失恢复原则，重新适配平台原 AccountPrincipal 和插件宿主。没有复制 federation node 表、HandoffStore、执行队列或 Store 多继承。共享数据值放 jiuwenswarm/data_sync/contract.py，共享契约和本地生产/消费逻辑不反向依赖Gateway；云角色适配复用原Gateway认证公共接口；薄入口只验证身份、参数并委托独立目录事务。

原 ProjectStore 在读取失败时容错返回空列表，不能用它生成删除清单。新增严格只读库存入口，缺失、损坏、链接或非法可见性均失败，UI旧容错入口不变。连接器显式选择项目，原子发布完整库存；只读副本从完整快照转增量，ACK必在持久视图和检查点之后。恢复旧发布意图后继续处理新选择；重复相同选择仍验证账号/来源，不以本地缓存绕过撤销。

新增操作员单次CLI与原WebChannel传输，无后台循环或UI控件。云注册只读取原逻辑环境、不ensure；首轮不声称发布来源已绑定到真实运行实例，自动云角色与角色证明留在P1S-02剩余工作。所有接口默认关闭。

## 验证

候选源码直接由本工作区导入，依赖复用P1S-01两份干净按锁安装环境：Python3.13.15；Native Core e089198835426cd7681761b0cc278670cd83031f，protocol 2a0457e5e01152e9ca5f8afdffd84716227046ca；External没有Core。不是候选wheel正式安装验证，也不是远端stable。

定向命令：`python -m pytest tests/unit_tests/data_sync tests/unit_tests/test_project_store.py -q --no-cov --tb=short`；Native另加 tests/unit_tests/server/test_project_workspace.py 和 tests/unit_tests/gateway/test_workspace_locations.py。最终 Native60通过、External55通过，零失败/跳过。新增16项涵盖冻结分页与并发更新、事务失败不撤回、跨账号/证明/代次、撤销与过期、发布/ACK丢响应和SQLite重启、未完整副本拒发布、并发来源写者冲突及真实回环WebSocket。

真实回环使用原WebChannel/FastAPI/uvicorn、原AccountStore/Authenticator、真实ProjectStore、多个来源、真实CLI子进程和独立SQLite副本：发布→另一来源拉取→撤回→来源撤销拒写→账号退出断连；独立检查原项目文件字节不变且未创建活动目录。仅本机随机回环端口，finally关闭服务/连接。Native与External均执行。没有调用模型或外部Provider，也未把该回环当成完整云部署。

开发失败保留：初次插件缺抽象initialize/shutdown导致1失败；修复后10通过。沙箱线程唤醒停滞，超时日志留存，改为受控沙箱外隔离测试通过。真实WS首次用UNAUTHORIZED响应断言，原宿主实际以1008关闭连接，按真实原契约调整断言后通过。没有修改原认证来迎合测试。CLI首次help因提前导入原utils尝试初始化用户日志被只读沙箱拒绝，改为解析参数及验证输入后延迟导入，并在隔离数据根重验帮助和真实子进程。最终检视补充未选Design项目共存、source_token复用原日志脱敏，以及本工程传输适配器拒绝依赖默认重定向，真实双端口证明未向重定向目标转发账号令牌；均已重验，未修改依赖源码。

证据在管理工作区相邻 artifacts/platform-p1s02-20261112/evidence：opening.json、affected-native.log、affected-external.log、directory-tests.log、plugin-diagnose.log、runtime-native.json、runtime-external.json、candidate-review.json。stable已纳入新增目录测试和原ProjectStore回归，但本候选远端CI尚未执行。

## 剩余交付

P1S-02仍开发中：原云角色装配与来源生命周期已在下方续记完成候选实现；剩余原UI只读投影消费、按锁候选wheel安装及正式CI、113.207.105.228真实云链路与断网恢复。尚未实现定时自动同步、账号全量完成、设备委托/安全凭据库、GC。文件和主子会话历史分别属于P1S-03/04；不提前标记成功。


## 云端来源装配续记（用户推进第1～2项）

P1S-01已由PR #23普通合入main 8d272b43ebd46c74d222e3f3a1e28daf97910f59，PR stable 43182567535及实际main stable 43183313172均成功。main树与92b6897相同，本工作区仍在92b6897上保存未提交候选，没有在dirty工作区切换或rebase。

云端发布沿Gateway原服务装配→原Router既有实例只读请求→原签名WebSocket/E2A→原ProjectAdapter→严格ProjectStore导出。选按需拉取以复用原账号/实例凭据，避免另建云端发布秘密、进程或调度器。云端来源只能由控制面依据真实角色回包创建；通用客户端cloud注册与直接库存发布拒绝。原默认Router请求路径不变，新existing-only路径不触发ensure、冷启动或网络失败回收。业务默认关闭，仍需显式选择项目。

原EnvironmentStore新增短guard_binding，导出期间允许原生命周期继续，提交前重新锁定并核验；目录事务原子提交库存、generation、epoch与回执。相同逻辑环境和工作区重建沿用来源ID、递增代次；换根、旧epoch、撤销及早期未证明的cloud来源拒绝。原账号退出和原签名校验继续有效。cloud-role-export-v1是可选能力；旧Gateway不接受云发布，旧本地v1仍兼容。独立CLI使用本地接收方证明，--kind cloud只传云项目ID，不能携带目标路径或身份选择器。

本轮证据根为artifacts/platform-p1s02-20261112/role-assembly-20261112/evidence。原云账号、Router、文件边界、ProjectStore和目录同步的Native受影响回归477通过（affected-native.log）；之后补可选能力/CLI及五项事务与恢复测试，最终Native目录+云角色35通过，External目录+云角色+ProjectStore74通过（final-sync-native.log / final-sync-external.log），0失败/跳过。最终两条命令分别为 `python -m pytest tests/unit_tests/data_sync tests/unit_tests/cloud_workspace/test_data_sync_cloud_role.py -q --no-cov --tb=short` 和追加 `tests/unit_tests/test_project_store.py`；独立数据根、随机回环端口、超时和finally清理。477项记录属于前一候选快照，不转记为最后一次全套重跑。

新增19项测试覆盖原签名导出/回执/撤回、原环境重建与撤销、坏库存/离线/注销、在途环境变更、账号/epoch/数据根/旧端校验、并发环境guard、无回收网络失败、SQLite重启与事务回滚、丢响应同操作恢复。真实CLI子进程经过原Gateway WebChannel/Authenticator和Router，连接真实签名回环WebSocket并调用原ProjectAdapter；源注册文件不变。物理基础设施使用受控替身，因此本机回环不计作真实容器/113云端验收。

首轮云角色用例3失败/2通过：测试utils数据根缓存仍指向旧夹具，导致实际读取根与凭据不一致；修正夹具隔离并在生产导出增加实际根摘要核验后5通过，最终35/74均通过。原失败保留cloud-role-first.log。依赖、Core、外部Provider源码及模型执行均未变；本轮未调用模型。候选wheel、正式CI、原UI和真实云断网/重启仍待交付验证。


## 原UI与本地登录交付续记（进行中）

用户授权本地界面登录与发布，并要求右侧展示操作。已沿原三段式控件增加统一同步Dialog、只读来源列表、显式勾选发布、撤回/撤销与账号退出；本地左下角登录通过固定HTTPS桥接原账号服务，不另建账号权威。状态“云端未连接”来自入口URL缺失，与登录状态分离。预览启用原扩展白名单并配置可信CA后，真实本地安装包已完成登录→原入口新建Code项目→选择发布→原云服务接受→退出后清空展示。

ui-delivery隔离按锁非editable安装：Native 1138通过/3个Windows条件跳过，External547通过；前端CI各步及打包通过，wheel含255静态文件。以上属于发现连接预热问题前的候选，不转记为修复后的CI。首次web测试因旧请求数量断言失败，更新为新增可选状态查询后通过；首次镜像核验缺少lock摘要，修正任务构建清单后通过，未变更依赖。

真实113验收揭示仅目录发布也触发原WebChannel连接预热，独立环境绑定检查失败，不能记为完整通过。修复通过原鉴权结果收窄同步连接RPC范围，并在原WebChannel跳过其执行连接生命周期，同时拒绝chat/项目变更/ensure。补真实TLS连接正反对照及握手缓存隔离，含原双协议回归22通过；修复后的统一构建、CI与云端重验仍待完成。

浏览器云入口使用自签名测试证书，工具规则要求用户亲自确认浏览器提示；已发出交接，不能用HTTP成功替代云端UI验收。右侧原预览未被停止；自动审批拒绝替换可能共享的AgentServer后，改用独立28975–28978端口和local-packaged数据目录进行wheel验收。尚未提交产品代码，需完整验证后才提交。


后续复验：本机uv构建缓存复用了旧工程安装，新增连接测试在非editable环境出现3失败；显式重装本工程并逐文件核验1592个已打包Python文件后，最终Native1140通过/3个Windows条件跳过、External549通过。CI保留新来源校验；不升级任何依赖。首次来源校验误纳入未打包的cua_engine/setup.py，按真实distribution文件集合修正，原失败保留。前端无后续代码变化，原UI CI及255静态资源结果仍适用。

修复wheel为3e9dba8a7558d40d604c1708a200e989a84e41a886b3d5ed4fe2f727fed328fb。云Gateway/Account/Web安装逐文件核对1592 Python/255静态文件通过。新任务control-scope绑定保留旧库与原文件，原账号登录+本地连接器+真实WSS发布/刷新通过，源ProjectStore不变；独立数据库确认环境仍NEW且instance_id为空。旧误预热实例已沿原Router删除且原基础设施GET404。新AgentServer镜像构建通过，尚未在完整云UI流程启动。

登录故障定位：系统证书信任返回CERT_AUTHORITY_INVALID、verify_code18；指定测试证书严格校验后原账号登录/status成功（合计6.872秒）。证书有效期为2026-11-12至14日、SAN含隔离IP，但为自签名，浏览器未信任。不是账号校验故障，不绕过浏览器提示。用户要求定位后已说明；云UI交接仍待完成。产品未提交；剩余完整云UI、真实离线/同工作区重启、最终检视及正式远端CI。


## 证书与生产入口修复续记

浏览器信任阻塞已解除：复用隔离服务器已有的公开可信IP证书，仅复制到本任务Nginx证书目录并reload，不导入系统CA、不关闭TLS校验、不绕过浏览器提示；原443服务及账号服务证书未改。标准信任库HTTPS验证200，原账号登录/status成功；右侧已实际登录并进入Code三段式控件，创建并打开云文件夹。证书有效至2026-11-15 19:20:18 UTC，属于短期验收部署，不声明已配置本任务自动续期。私钥留在服务器，不进入源码或本地证据。

真实云发布随后返回SOURCE_EXPORT_UNSUPPORTED：原PROJECT_LIST被Front控制面拦截，初版只在旧ProjectAdapter实现sync_export。修复在原ProjectRepository中按需线程调用同一严格导出器，普通项目查询保持原行为；签名角色测试改走MethodRouter.dispatch并明确禁止进入执行admission。定向59通过；该候选native1140通过/3跳过、external549通过。

检视发现本地完成初始快照后新增云来源时，增量只更新对象未更新coverage，可能把云项目显示为本地。changes增加来源摘要，新接收方在同一事务持久化；新增回归覆盖空快照→云来源发布→增量识别cloud→无对象变化时来源revision更新，数据同步定向29通过。最终统一候选wheel SHA256为2e577968e5eed50036f60efa550ac7e67358820c1b3497873d5ee92e59aae8a4，CI与真实云验收继续，不沿用上一候选成功结论。


最终候选本机stable：native1141通过/3个Windows条件跳过，external550通过；安装来源1592 Python文件逐一匹配，Core/protocol锁定来源不变；最终wheel本地安装含255静态文件。云Gateway/Account/Web同样1592/255核验通过。无实例验收首次被仍打开的普通云页自动重连干扰：环境ALLOCATED，保留失败；关闭云页、通过原Router回收并GET404后，仅本地刷新连接保持DELETED，未重建实例。Gateway停止期间本地UI保留旧目录并标刷新未完成；恢复后刷新成功，截图已归档。

本地候选切换曾仅重启Front，原常驻Worker保留旧安装版本，原运行时正确拒绝不同部署。核对任务cwd/解释器/PID后通过原supervisor.shutdown --shutdown-worker收到shutdown.done ok，再启动最终版本，AgentReady及原目录选择恢复。属于验收升级操作修正，未改运行时生命周期或绕过版本检查。


## 用户确认的产品收敛（2026-11-12）

用户指出仅查看对方项目清单、不能继续工作的独立功能价值有限，明确选择“移除清单同步入口，保留底层契约和本地云账号登录”。本确认替代此前用户可见同步Dialog方案：撤去三段控件中的同步菜单、清单/选择/发布/撤回/撤销界面及浏览器发布意图；三段控件恢复P1S-01原行为。本地左下角替换为独立LocalCloudAccount，只调用status/login/logout；没有项目清单读写。底层可选协议、操作员CLI、只读索引及严格边界保留，不把项目名称互见当成文件或会话同步完成。

新的账号控件4项行为测试通过；完整前端回归首次因旧footer testid断言失败，更新为新账号控件后重跑通过；生产构建与新wheel验证继续。底层Python代码与2e577968候选完全相同，1141/550测试结论按代码范围保留，新的远端CI仍在提交后按新提交运行。

真实云恢复：同逻辑环境env_2c834ec1e4af833a24b3a3915e3caa89由epoch2重建到epoch3，原proj_5beeef5f及工作区保留；cloud来源src_052efee96fb8a750abfe44fa71baa754保持，generation从1到2。真实受保护WSS提交后模拟丢响应，再重新打开持久副本、重试相同operation_id，返回相同revision5回执，无重复发布。专用测试接收来源随后通过原接口撤销；不改主本地/云来源。上述为底层契约验证，不恢复已移除的产品入口。


新版账号UI完整前端CI和生产构建通过，最终wheel SHA256为1c088da4c4817dae4fa092a4e20170e9c5cfd0f4c0df782bc3aaaa9880b074a0，255静态文件逐一匹配。所有1592 Python文件与2e577968候选完全相同。新本地Web在独立account-web-runtime/venv按锁非editable安装，核对包后只替换本任务Web进程，Gateway/Front/Worker保持。真实浏览器已完成退出→重新输入已有测试账号→已登录，左下角显示chain-1112，账号Dialog不含任何清单/发布动作；本地目录选择和Local/Cloud两项菜单通过。等待登录断言首次超时，但随后独立UI读取显示登录成功，未重复提交登录。


最终新版UI验收通过：Local→Cloud→Local导航；本地目录选择；原云目录打开；新建p1s02-account-ui并打开；创建／准备已有环境。独立检查proj_a626b52f及.git存在，原proj_5beeef5f不变，epoch3/instance67b16103保持且只有一个物理实例。云菜单仅剩原三项操作，清单同步入口已删除。截图account-login-final/local-three-controls-final/cloud-three-controls-final及account-ui-final.json、remote-audit-account-ui-final.json归档ui-delivery/evidence。

统一新版镜像：Gateway/Web79ee291c、AgentServer44673e4e、Account164788f3均从同一1c088da4 wheel构建并核对锁定依赖。实际验收仅Web切换79ee291c；既有Gateway bb75e8f2、Account88300434、AgentServer dcf3f7cc保持原不可变绑定，四角色Python1592文件均与新版候选一致，实际Web255文件与新版构建一致。任务专属本地28975–28978与云28950–28954保留供右侧查看，原有基线资源未回收。

检视已闭合生产Front导出遗漏、增量来源coverage遗漏及同步连接预热三个问题；新账号UI核对同源HttpOnly会话、登录退出、凭据不落浏览器存储、跨页刷新与迟到响应保护、可选能力缺失隐藏和服务失败重试。没有发现尚未处理的本次阻断项；范围不含全仓、真实模型运行或文件/会话内容同步。候选完成本机stable、生产构建及真实云流程，准备按用户授权提交；正式远端stable将绑定实际提交SHA单独留档。
