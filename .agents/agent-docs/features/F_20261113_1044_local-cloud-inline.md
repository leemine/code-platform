---
id: F_20261113_1044_local-cloud-inline
title: Local/Cloud 即时选择与本地同页云目录访问
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway/services, gateway/extensions/data_sync, jiuwenswarm/data_sync, jiuwenswarm/channels/web/frontend]
files: [gateway/auth/account_transport.py, jiuwenswarm/channels/web/frontend/src/features/auth/AccountLoginForm.tsx, jiuwenswarm/channels/web/frontend/src/features/auth/LoginPage.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/AccountControl.tsx, gateway/services/cloud_workspace_client.py, gateway/services/data_sync/ui.py, gateway/extensions/data_sync/ui_extension.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/CodeWorkspaceControls.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts]
designs: [code-projects:D-20261112-1120-platform-workspace-sync]
---

# 本地同页云目录访问候选

用户在2026-11-13明确“立即选择、具体操作再登录/连接”，随后补充“保持本地页面访问云端，不跳转云端网页”。据此替代 F-20261112-1320-platform-code-workspace 的入口导航过渡行为；原认证、目录边界、单默认环境和 Runtime 所有权不变。当前契约见 S_02_code-workspace-entry。独立候选 codex/platform-lazy-entry-20261113，基线 f354f772；P1S-03已有未提交候选保持不动。codeswarm参考源码24f29148，其同页选择与执行绑定分离作为体验依据，不直接复制另一工程的 federation/会话存储。

## 实施和边界

选择只更新视图，移除控件挂载时云环境探测；原位登录后只恢复操作表单。同源账号桥只允许环境读写和三种原目录RPC，固定服务端云地址；身份前后检查，云文件和项目持久化仍属于云端原实例。保持元数据同步RPC的能力边界，不添加会话队列或Provider协议。

本地页云端会话执行绑定尚未实现，Cloud选择期间发送受保护；云项目选择不污染本地项目。当前不能宣称同页完整云会话、双向文件同步、历史接续或多命名环境完成。相对于最初整页导航阶段，当前不会因草稿阻止位置选择或登录，但仍不具备跨端执行接续。

## 验证和实际问题

证据根：管理工作区同级 `../evidence`，完整绝对目录为 `/home/leewanlong/work_leewanlong/code-projects/artifacts/platform-lazy-entry-20261113/evidence`。Native 源码受影响36通过，External源码31通过；使用P1S-03合入后固定依赖的独立解释器，PYTHONPATH指向本候选、家目录/数据/随机回环端口隔离。新增真实TLS链路经过原AccountStore、WebChannel、原目录适配器和ProjectStore；物理云另验，不能把夹具当云验收。

原stable Web脚本的374项测试通过，生产构建通过。首次wheel检查发现本任务build/lib保留前一次生成资源，清理该临时打包缓存后255资源精确一致；2245个安装文件与wheel相同。真实本地安装页访问既有113隔离云完成目录创建/打开，独立SSH只读核对 `agent/workspace/code/lazy-entry-20261113`、项目记录和Git目录，确认本地未创建同名目录。

真实登录恢复发现窗口事件与同页BroadcastChannel重复通知取消新弹窗。修复发送方去重，保留跨页和旧字符串广播；新增回归。最终修复24项交互测试通过，最终重打包和浏览器重验另见管理实施记录。首轮测试夹具未设置WebChannel消息回调及错误使用字符串数据根，分别导致超时/类型错误；纠正夹具后重跑，原失败日志保留，没有白名单或跳过。

## 状态

本轮交付范围为同页云目录管理、共用账号控件与连接复用。提交、合入与远端CI状态以Git记录及管理仓任务台账为准，下文按阶段保留当时验证事实。同页云端执行路由仍待开发，P1S-03/04的文件/历史同步不在此处冒记完成。


2026-11-13界面收敛：用户明确删除“已选择云端目录；本地页面的云端会话执行尚未接入，发送暂不可用”提示。候选已删除该UI节点及中英文资源，保留实际执行未就绪时的发送保护，不以删除文案宣称执行能力完成。24项相关交互回归通过，正在更新最终验收包。


最终验收包：`f63b77bdcf81acd6943e8329e4ffb2346995f76bc1f78467ac8805f74e0a0b72`，证据`wheel-no-message-installed.json`。移除指定提示后的24项交互回归、生产构建、255资源与wheel一致性通过，安装文件2245逐一核对。实际右侧本地页原位登录后恢复云目录弹窗已通过；默认环境选择及创建入口幂等准备通过，Local→Cloud→Local草稿保留且URL不变。未新增云命名环境，不把既有绑定准备称作新环境物理创建。产品与管理候选保持未提交，主线、Core、Swarm均未更改。


2026-11-13账号展示统一：本地和云端改用同一个AccountControl，复用既有32px圆形主题样式、完整用户名菜单和“退出登录”文案。本地未登录显示用户图标，点击原登录弹窗；登录后显示大写前两字（CH）。身份变化关闭菜单，菜单退出失败显示原错误弹窗；背景身份检查不禁用头像入口。CloudWorkspaceGate保留原认证/环境生命周期及testid。定向命令`node --test tests/localCloudAccount.test.mjs tests/cloudWorkspace.test.mjs tests/codeWorkspaceControls.test.mjs`共53通过，证据avatar-tests-final.log；最终打包和真实UI记录另附。


2026-11-13账号展示最终验收：基线f354f772的未提交候选，53项定向UI测试通过（avatar-tests-final.log），生产构建通过（avatar-build.log，既有大chunk警告保留）。按stable轮子资源步骤核对255项，安装文件2245逐项相同；最终wheel SHA256 `4fd45ce4020496f0253142eec653fd791b4933ba91d0f40f90c3704443b08ee6`（avatar-wheel-installed.json）。右侧本地28986在最终包实测未登录圆形用户图标→原位登录既有113隔离云→CH头像与完整用户名/退出登录菜单；URL保持本地。退出请求成功已在前一仅菜单文案不同的5fd02518包实测，最终包同路径由回归覆盖。证据avatar-signed-out.png、avatar-signed-in.png。云端Gate共享控件回归通过，云服务器未重新部署；不把本地验收记作远端CI。产品/管理仍未提交、未合入，主线及其他候选未改动。


2026-11-13用户批准连接复用和统一登录流程：参考codeswarm account_transport/CloudEntry的传输复用语义，在本仓既有AccountHTTPPool中扩展有界GET/POST响应头接口，保留authority_post兼容；没有另建账号权威。本地CloudAccountClient使用该池，CA/五分钟上下文刷新、读取可重试、变更不重放。WorkspaceConnections仅管理本地目录桥传输，四连接、凭据/目标/CA隔离、60秒空闲回收，注销和失效销毁，目录请求前后仍做真实身份验证。DirectoryRPC保留协议和方法边界，改为唯一接收者，避免持久连接空闲事件堵塞；未知变更结果关闭连接并交还错误，不重发。

共用AccountLoginForm保留原cloud注册入口和所有原控件testid；本地首次云操作仍原位登录，已有身份自动续接、不重复确认，不强制匿名本地用户登录。目录加载可编辑名称/取消，取消丢弃晚到回复，原位登录保留草稿；提交变更仍等待权威响应。Native与External受影响同步/账号回归各36通过，前端55通过。真实包首次目录4.8041秒、复用目录1.9285～2.0321秒、创建1.9722～2.6754秒，包含原前后身份校验。对比前一包list9.4077～9.9908秒、mkdir单样本12.3984秒。原始证据pool-after-timing.log/json、pool-python-tests.log、pool-python-external.log；右侧流程与最终包结果另附。仍未提交/合入，远端CI未运行。


2026-11-13连接复用最终验收：安装wheel SHA256 `2a3ee3afa77a0eb8f5fa6fbea76ce1968650dd946da3bee9db6508c90e1f72f7`，255前端资源、2245安装文件精确核对（pool-final-wheel-installed.json）；代码来源为本候选f354f772+dirty，pool-candidate-sources.json保存源码摘要，不是新提交SHA。Native/External原受影响回归各36通过；检视补充150秒连接排队总期限后Native桥12通过；共用表单保留注册入口顺序后前端55通过、生产构建通过。未运行远端CI，没有提交/合入。

同一113隔离云、已就绪实例、同一本地HTTP入口最终计时：首个list4.9597秒（登录已预热HTTP，WSS尚未建立），复用list2.0738/1.9356/1.8651秒，mkdir2.0112/2.0129/2.1330秒。原包list9.6072/9.4077/9.9908秒，mkdir一次12.3984秒。按中位数分别改善79.9%、83.8%；创建前值只有一个样本，网络条件会波动，不当作SLA。计时包含本地桥前后实时身份检查，最终复测未取消权限校验。证据pool-final-timing.log/json、pool-comparison.json；脚本platform-final-timing.py，不含凭据值。

右侧最终包真实验收：退出后Local/Cloud仍立即切换，首次新建文件夹唤起与云页共用的登录表单；登录后自动恢复目录表单，无“继续”确认，无变更自动重放。刷新目录时实测名称输入与取消可用、创建禁用，取消关闭；晚到回复不重开由定向测试精确控制。重新创建并打开pooled-ui-20261113成功，全程URL保持127.0.0.1:28986/chat/new，原本地项目仍为空。独立SSH只读核验云ProjectStore proj_177ddde4、实际云目录与.git，证据pool-remote-audit.json。右侧保留已选云项目；pool-ui-observations.json、pool-ui-opened.png留证。页面话题推荐区另有“请求失败”提示，未作为云目录错误处理，当前未配置模型的隔离预览不据此宣称对话执行验收。

本轮只统一账号交互与本地云操作会话复用，不实现跨origin浏览器SSO，也不新增本地页云端会话执行路由。创建测试样本均使用任务命名空间，用户原文件未覆盖。单账号默认云环境沿用，不宣称新命名环境或项目文件同步完成。


2026-11-13交付收尾：用户明确授权提交、远端CI、合入主线和合入后验证。按jw-review核对全批差异与原账号/目录/同步消费者，源码与最终实测安装包保持一致；未发现阻断本批范围交付的问题。后续以PR检查和合入SHA复验结果记录交付状态，不把本地实测当作远端CI。
