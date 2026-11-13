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
6. 前端 Work 原控件不变。Code 的本地页面通过既有同源账号桥访问云端；云目录结果独立保留，不写入本地 `workspaceStore.selectedProject`。选择 Cloud 不清草稿、附件或技能，输入仍可编辑；所选位置没有原执行路由时禁止发送，不能回退到当前本地执行。已有会话的位置仍锁定。本切片只接通云目录/环境管理，本地页的云端会话执行绑定尚未实现。
7. 本地 POST `/api/v1/data-sync/workspace` 复用原 HttpOnly、SameSite=Strict 登录会话、Host/Origin 与 `X-Jiuwen-Sync` 校验。允许 `operation=environment|ensure|list|mkdir|open`，后者仅允许各自的 `path/name/offset`，服务端固定 `work_mode=code`。目标仅取操作员私有配置 `CODE_PLATFORM_LOCAL_SYNC_CONFIG`，浏览器不能提交地址、账号、环境、实例或根选择器。云宿主拒绝这个本地桥端点。操作前后验证身份；错误或超时不自动重放变更。
8. 环境读写委托原账号 HTTP API；目录调用复用原 WebChannel JSON RPC 和 AgentServer 目录适配器。WorkspaceRPC 仅开放三个目录方法，使用正常账号连接；原 DirectoryRPC 保持 `data_sync.*` 白名单和无执行生命周期的连接范围。不能把元数据同步连接升级成执行连接。本地桥不保存云文件副本或新建第二套项目存储。
9. 未登录的具体操作打开现有本地云账号弹窗。成功登录只恢复目录/环境表单，mkdir/open/ensure 变更不自动重放；取消、切换位置、切换 Work 或卸载撤销待恢复意图。窗口事件通知本页，BroadcastChannel 通知其他页面，同页发送方去重，兼容旧 `changed` 广播。账号变化清理云端选择和晚到响应。

10. 本地和云宿主复用 AccountControl、既有头像主题样式和菜单布局。未登录本地入口为圆形用户图标，点击原位登录；登录后显示用户名大写前两字，点击显示完整用户名和“退出登录”。身份变化关闭旧菜单，退出失败回到原账号弹窗显示错误。展示复用不合并两端认证生命周期，云宿主未登录仍使用原 LoginPage。

11. 本地与云端共用AccountLoginForm与既有账号权威；保留匿名Local入口。本地各云操作复用同一HttpOnly会话，已有新鲜认证身份时自动续接原表单，不再要求额外“继续”；不自动提交mkdir/open/ensure。登录页仍由各宿主原生命周期负责，不跨域复制浏览器Cookie。
12. 目录只读加载期间可以输入文件夹名称、取消弹窗；取消推进generation/intent并忽略晚到响应。完成当前目录校验前禁止创建；创建已提交时保留原结果不明处理和防重复提交。原位登录续接保留名称草稿。
13. CloudAccountClient复用原account_transport的有界HTTP池，逐请求发送凭据与读取权威响应；只有status/environment读取可在传输中断后重试一次，登录/退出/ensure不自动重放。CA配置变化与五分钟信任上下文期限使传输失效。
14. WorkspaceConnections按凭据摘要、固定目标、CA及信任期限隔离，最多四个连接、空闲60秒回收，关闭/退出/失效时清理。DirectoryRPC由唯一接收者分派待处理回执并排空无关事件，保留data_sync方法范围；WorkspaceRPC仍只开放三个目录方法。操作前后身份校验、云端request/delivery guard不变，任何目录RPC失败不自动重放。连接复用不授予执行权限或建立第二套项目存储。

这不是项目文件同步或会话历史同步。单账号单默认云环境契约保留，不宣称多命名环境、云会话执行接续或双向无损运行完成。
