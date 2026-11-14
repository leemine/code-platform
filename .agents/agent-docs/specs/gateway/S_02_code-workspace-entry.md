---
id: S-02-code-workspace-entry
title: Code 工作区入口与目录操作
type: S
author: leemine
modules: [gateway, jiuwenswarm/server, jiuwenswarm/channels/web]
files: [gateway/routing/workspace_locations.py, jiuwenswarm/server/runtime/gateway_adapter/project_workspace.py]
author_email: leewanlong@gmail.com
---

# Code 工作区入口契约

1. `workspace.locations({})` 保留服务端识别的 `kind: local|cloud`、`switch_mode: entry_navigation` 和旧入口 URL 字段，兼容旧客户端。新版 Code 控件把所选位置与当前服务端类型分开：Local/Cloud 选择立即更新，不导航、不登录、不探测或创建云环境。当前主机目录来源未知时也可选择，但具体操作失败关闭。目录元数据返回不能覆盖用户刚选的位置。
2. `project.workspace.list|mkdir|open` 只接受无显式 session_id 参数的 Code 目录操作；WebChannel 自动合成的临时关联ID不作为业务会话绑定；请求允许 `path,name,offset,work_mode`，显式非 code 拒绝。经原 `path.select_directory` 协议的 `workspace_operation` 委托 AgentServer；旧无该参数的原生选择器不变。不得自定义 root、user、instance 或执行目标。
3. 根固定为 `get_agent_workspace_dir()/code`，path 为相对目录；根允许浏览但不能注册。拒绝点开头分段、空段、反斜线、NUL、超过2048字符的路径与符号链接。列目录每页100项、最多10000目录，排序后返回 `{path,work_mode,items:[{name,path}],next_offset}`。offset 必须为有效非负整数。
4. mkdir 的 name 是单段合法项目目录名，以目录描述符创建0755并同步父目录；已有名称返回 CONFLICT。返回 `{path,created:true}`，此时尚未注册项目。open 返回 `{project,path}`，复用原 ProjectStore 和 Git 初始化；已有同路径项目复用，隐藏/异模式拒绝，包含或处于另一个项目内拒绝 PROJECT_ROOT_REQUIRED。
5. 云环境 status/ensure 契约保持原样，无客户端配置选择器；READY 必须有环境ID。单账号单默认环境，ensure 幂等，未返回成功不能显示创建完成。目录失败或结果未知时刷新核对，不自动重放变更。
6. 前端 Work 原控件不变。Code 的本地页面通过既有同源账号桥访问云端；云目录结果独立保留，不写入本地 `workspaceStore.selectedProject`。选择 Cloud 不清草稿、附件或技能，输入仍可编辑；所选位置没有原执行路由时禁止发送，不能回退到当前本地执行。已有会话的位置仍锁定。本地页的云端会话按第15–19条通过独立云WebClient绑定，目录连接本身不承担执行。
7. 本地 POST `/api/v1/data-sync/workspace` 复用原 HttpOnly、SameSite=Strict 登录会话、Host/Origin 与 `X-Jiuwen-Sync` 校验。允许 `operation=environment|ensure|list|mkdir|open`，后者仅允许各自的 `path/name/offset`，服务端固定 `work_mode=code`。目标仅取操作员私有配置 `CODE_PLATFORM_LOCAL_SYNC_CONFIG`，浏览器不能提交地址、账号、环境、实例或根选择器。云宿主拒绝这个本地桥端点。操作前后验证身份；错误或超时不自动重放变更。
8. 环境读写委托原账号 HTTP API；目录调用复用原 WebChannel JSON RPC 和 AgentServer 目录适配器。WorkspaceRPC 仅开放三个目录方法，使用正常账号连接；原 DirectoryRPC 保持 `data_sync.*` 白名单和无执行生命周期的连接范围。不能把元数据同步连接升级成执行连接。本地桥不保存云文件副本或新建第二套项目存储。
9. 未登录的具体操作打开现有本地云账号弹窗。成功登录只恢复目录/环境表单，mkdir/open/ensure 变更不自动重放；取消、切换位置、切换 Work 或卸载撤销待恢复意图。窗口事件通知本页，BroadcastChannel 通知其他页面，同页发送方去重，兼容旧 `changed` 广播。账号变化清理云端选择和晚到响应。

10. 本地和云宿主复用 AccountControl、既有头像主题样式和菜单布局。未登录本地入口为圆形用户图标，点击原位登录；登录后显示用户名大写前两字，点击显示完整用户名和“退出登录”。身份变化关闭旧菜单，退出失败回到原账号弹窗显示错误。展示复用不合并两端认证生命周期，云宿主未登录仍使用原 LoginPage。

11. 本地与云端共用AccountLoginForm与既有账号权威；保留匿名Local入口。本地各云操作复用同一HttpOnly会话，已有新鲜认证身份时自动续接原表单，不再要求额外“继续”；不自动提交mkdir/open/ensure。登录页仍由各宿主原生命周期负责，不跨域复制浏览器Cookie。
12. 目录只读加载期间可以输入文件夹名称、取消弹窗；取消推进generation/intent并忽略晚到响应。完成当前目录校验前禁止创建；创建已提交时保留原结果不明处理和防重复提交。原位登录续接保留名称草稿。
13. CloudAccountClient复用原account_transport的有界HTTP池，逐请求发送凭据与读取权威响应；只有status/environment读取可在传输中断后重试一次，登录/退出/ensure不自动重放。发送前淘汰空闲超过4秒或已可读（EOF/TLS关闭通知）的连接，避免把新的不可重放请求交给已关闭连接；这不是失败后的重发。CA配置变化与五分钟信任上下文期限使传输失效。
14. WorkspaceConnections按凭据摘要、固定目标、CA及信任期限隔离，最多四个连接、空闲60秒回收，关闭/退出/失效时清理。DirectoryRPC由唯一接收者分派待处理回执并排空无关事件，保留data_sync方法范围；WorkspaceRPC仍只开放三个目录方法。操作前后身份校验、云端request/delivery guard不变，任何目录RPC失败不自动重放。连接复用不授予执行权限或建立第二套项目存储。

15. 本地页面通过独立同源 WebSocket `/api/v1/data-sync/ws` 连接原云 WebChannel。沿用 HttpOnly 云账号 cookie、固定 HTTPS/WSS 目标和正常证书校验；校验 Origin/Host、每请求新鲜身份及云端原 request/delivery guard。退出或账号变化关闭旧连接、清理云会话 UI 缓存。桥接层不创建执行器、队列、会话库或历史副本。
16. 新客户端打开目录时显式请求 `address_version: 1`；返回的 `cloudp_`/`clouds_` 地址绑定账号权威、主体和云目标。未携带版本的原目录 API 保持物理 ID 兼容。浏览器按地址选择原本地或独立云 WebClient，云端元数据中的会话/项目引用转换，用户内容、工具结果和 Provider binding 保持原样。地址不是授权凭证；混合账号/目标/本地物理 ID 拒绝。
17. Cloud 草稿使用云端模型/执行 Provider 目录，不能用 Local 默认模型或模型 ID 修复云会话。Local/Cloud 选择仍立即响应，选择本身不发起登录/连接；具体目录或会话操作才访问云端。已创建会话沿持久绑定执行。消息、审批、停止、历史读取和重连回执复用原 Runtime/协议；传输断开不重发用户输入或变更。
18. 目录请求总预算150秒，浏览器155秒，本地 Web 代理175秒；普通HTTP代理仍30秒。工作区响应记录阶段、状态码和耗时，不记录凭据/路径/用户输入；`Server-Timing` 暴露总处理耗时。超时或结果不明不重发mkdir/open/ensure。
19. 同源/容量检查后本地云执行WebSocket先完成传输升级，并行执行云身份检查与上游已鉴权连接，随后执行二次身份校验；升级不代表取得云权限。只有准备完成才发送既有`connection.ack`（transport=cloud-bridge），客户端在175秒内等待此回执，再启动业务请求期限。期间不转发排队帧、不返回云数据，认证失败关闭1008；不将云冷启动放在底层10秒Upgrade握手中。

这里的历史读取访问云端原会话，仍不是项目文件同步或会话历史复制。单账号单默认云环境契约保留；多命名环境、文件双向同步与无损运行迁移另行开发。

20. 账号服务失败时保持错误视图，恢复探测在上一请求结束后按2/4/8/16/30秒退避，不反复切换整页检查提示；手动与后台恢复共用单个在途请求。后台不提交登录凭据，不能用旧身份绕过权限校验；相同新鲜身份恢复原界面，不同身份仍清理原缓存与连接。

21. 只读身份/环境HTTP遇TLS EOF或正常关闭可在原预算内重连一次；证书、主机名及其他TLS协议错误不重试，变更请求不重放。新会话创建时云项目prop与活动编辑器尚未同步，不发携带本地占位ID的话题推荐请求；不放宽云资源地址检查。


## 云端历史首屏恢复

- 云端会话的 metadata/history 由云传输自行等待认证就绪，不依赖 Local 连接或本地配置加载。页面在辅助初始化前发起恢复；原历史分页和事件单消费者保持。
- 同文档中并发的账号 status 只共享未完成请求，完成/失败即移除；登录、退出和账号变化使其失效。不缓存身份或权限，服务端仍逐请求及投递校验。
- 首次云历史的连接等待由传输超时管理，原30秒历史响应预算在请求分配并发送时启动；后续分页沿用原每批超时。销毁后不能重新启动计时器。
- 连接恢复只重新读取当前会话 metadata/未完成历史和模型目录，不重放用户输入。网络/账号服务错误不能显示为会话已删除，只有明确 NOT_FOUND 才进入缺失会话视图。


## 云连接与实时校验性能

- 云WebClient直接连接同源云桥，等待后端新鲜鉴权后的connection.ack；不在连接前另串行查询HTTP status。1008拒绝后才新鲜查询账号状态用于原位登录提示；账号代次变化使迟到结果失效，不自动重发原请求。Local连接路径不改变。
- 本地身份读取与固定上游的独立鉴权握手可并行。两者完成后必须重新校验身份，全部成功前零业务转发、零云数据交付。任一失败取消同批未完成步骤并释放已打开上游；上游401/403归为1008拒绝。
- HTTP只复用传输，空闲超过30秒或已可读/失效的socket淘汰；配置/CA变化和既有300秒代次仍失效。每次身份请求均读取权威新结果，不保存身份或撤权缓存。只读传输重连上限与写请求不重放保持。
- 诊断记录HTTP排队、建连、响应和是否复用，云桥以随机短trace关联身份/握手/就绪/请求耗时；不记录token、账号、资源ID或正文。并行阶段耗时不能相加当成总耗时。
