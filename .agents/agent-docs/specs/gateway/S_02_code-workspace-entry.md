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

1. `workspace.locations({})` 返回服务端识别的 `kind: local|cloud`、`switch_mode: entry_navigation` 与两个入口。类型来自既有 AgentOS/共享本地客户端，不由浏览器提交。未知客户端拒绝。可选配置 `CODE_PLATFORM_LOCAL_ENTRY_URL`、`CODE_PLATFORM_CLOUD_ENTRY_URL` 只接受 HTTPS 根 URL；Local 额外允许 loopback HTTP。禁止用户信息、查询参数和片段。导航仅追加并消费 `#code-workspace` 视图提示以保持 Code 模式，不参与执行路由。前端跳转不携带主体、凭据、项目或会话 ID，原认证继续生效。
2. `project.workspace.list|mkdir|open` 只接受无显式 session_id 参数的 Code 目录操作；WebChannel 自动合成的临时关联ID不作为业务会话绑定；请求允许 `path,name,offset,work_mode`，显式非 code 拒绝。经原 `path.select_directory` 协议的 `workspace_operation` 委托 AgentServer；旧无该参数的原生选择器不变。不得自定义 root、user、instance 或执行目标。
3. 根固定为 `get_agent_workspace_dir()/code`，path 为相对目录；根允许浏览但不能注册。拒绝点开头分段、空段、反斜线、NUL、超过2048字符的路径与符号链接。列目录每页100项、最多10000目录，排序后返回 `{path,work_mode,items:[{name,path}],next_offset}`。offset 必须为有效非负整数。
4. mkdir 的 name 是单段合法项目目录名，以目录描述符创建0755并同步父目录；已有名称返回 CONFLICT。返回 `{path,created:true}`，此时尚未注册项目。open 返回 `{project,path}`，复用原 ProjectStore 和 Git 初始化；已有同路径项目复用，隐藏/异模式拒绝，包含或处于另一个项目内拒绝 PROJECT_ROOT_REQUIRED。
5. 云环境 status/ensure 契约保持原样，无客户端配置选择器；READY 必须有环境ID。单账号单默认环境，ensure 幂等，未返回成功不能显示创建完成。目录失败或结果未知时刷新核对，不自动重放变更。
6. 前端 Work 原控件不变；Code 的连接/身份变化撤销旧响应，打开目录/创建操作期间阻止发送。Local/Cloud 导航仅在无未发送内容、附件、已选技能时启用，原草稿不跨域复制。本机桥接缺失时不回退到云服务器原生选择器。

与目标设计不同的同页路由及子目录会话契约差额见 F-20261112-1320-platform-code-workspace。本契约不包含项目文件同步或会话历史同步。
