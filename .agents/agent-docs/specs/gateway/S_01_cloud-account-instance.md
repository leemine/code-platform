---
author: leemine
author_email: leewanlong@gmail.com
id: S_01_cloud-account-instance
title: 云账号与原实例链契约
type: S
modules: [gateway, server/front]
files: [gateway/services/cloud_environments.py, gateway/services/cloud_instance_policy.py, gateway/auth/account_authenticator.py, gateway/extensions/agentos/agentos_router/router_client.py, gateway/common/security/service_auth.py]
---

# 云账号与原实例链契约

独立账号服务是账号库唯一写者；环境库只保存账号引用、固定镜像、注册意图、实例操作回执和代次。注册operation_id在账号权威与环境意图间闭合，密码不进入环境库。首版单控制面写者，不声称分布式租约。

插件提供原HTTP路径及cloud.environment两项RPC；原装配层注入服务，不覆盖session.execution.options，不另建创建/轮询/执行连接。原Router/AgentManager唯一持有物理生命周期；通用生命周期策略只注入启动快照、回执和认证。Core、协议、Runtime状态机不复制。

NEW→CREATING→ALLOCATED；未知结果→UNKNOWN，清单零匹配不授权再次创建。READY来自物理running及AgentServer应用ACK，不是持久化权威状态。DELETING只在原实例明确不存在后转DELETED，再增代次/operation_id；固定镜像和工作区保留。删除核验绑定归属/代次，内存清理按预期instance_id比较；迟到回执不能删除新实例。启动清理跳过本控制面旧账号实例；普通网络故障不触发云实例重建。

登录会话与模型OAuth分离。原Authenticator返回的可信主体和可选请求/投递guard经过原WS、队列、HTTP文件出口。身份上下文仅在进程内，Cookie不进入E2A或日志。每代实例断言绑定身份、目标、有效期、用途、防重放及撤权摘要；缺失云角色凭据/工作区绑定时拒绝。维护仅允许明确白名单，已失效用户作用域不能降级成维护。注销权威后写当前代次屏障；直接权威撤销的在途断言上界15秒，Gateway请求/输出重新查权威。已在Runtime执行的任务遵循原取消/结束机制。

每账号独立/data及config目录；凭据只读，UID/GID与0700/0600持久目录匹配，不挂控制/账号库。相对目录越界和符号链接逃逸均按解析后的根包含关系拒绝。原模型/工具权限接口继续路由原执行侧，不引入第二权限引擎。

旧账号缺绑定不新建默认实例。显式导入只接受兼容凭据/归属/代次与指定旧镜像、目录；不自动迁移旧库/六字段凭据。完整UI/跨宿主目标选择/同步与真实部署验收不包含在本契约的已验证范围。使用方法见docs/zh/cloud-workspace.md与docs/en/cloud-workspace.md。

实例请求的认证拒绝在Front传输边界明确关闭WS（1008），不得让后台解析任务异常变成客户端静默等待；格式损坏/撤权文件不可读均按拒绝处理。Runtime/协议不新增状态。三角色候选共享按锁依赖层，具体元戎runtime/SDK兼容性必须独立实测。

部署身份契约：元戎rootfs.user使用POSIX登录名，不接受Docker式UID:GID文本。Gateway在准备默认快照前解析账号并确认uid/gid与私有卷创建者一致；角色镜像提供相同登录名及数值UID/GID（候选agentos=1000:1000）。固定镜像核验必须覆盖该映射；已有绑定的镜像/身份快照不被新默认配置覆盖。

对账兼容：元戎GET不返回name时不以名称缺失否定真实回执，但必须同时精确匹配私有工作区、代次认证目录的只读挂载、固定镜像及运行用户；返回name时仍校验一致。多候选或缺失任一必要字段保持UNKNOWN，不能重发POST。元戎FATAL按明确失败处理。

容器卷准备必须包含私有agent/config/home。数据卷会遮蔽镜像预建目录，HOME=/data/home必须在基础设施启动器导入前存在；已有HOME数据保留，符号链接和宽权限拒绝。单实例关闭应以传输错误唤醒连接等待者，不把资源回收误当作取消业务HTTP任务；进程关闭仍保留原取消语义。

- Web/FastAPI 适配层必须保留完整 AuthResult 扩展，通过原 `apply_auth_result_to_ws` 传递请求及回包校验回调。账号模块显式贡献 `routing_user_id`，Web路由优先使用该可信身份；未贡献时沿用旧 IAM 用户名映射，不把所有 IAM UUID 改作工作区标识。
- 实例 WebSocket 握手拒绝应映射为环境不可用（HTTP503），保留ALLOCATED回执，重试不得重复创建。
- HTTP插件贡献为可选能力；既有仅贡献WebSocket的插件没有 `http_routes` 方法时仍可装配。元戎代理租户必须匹配部署实际租户，不把任务标签当成租户权限边界。

云文件边界：启用账号实例策略时，原 `/file-api` 读、写、列表、mkdir 经既有 Router/E2A 与实例认证进入 `WorkspaceFileAdapter`，不调用元戎 SDK 文件端点，也不在失败时回退。未启用账号实例策略的旧客户端保持原契约；这不代表旧元戎文件路径已得到同等加固。

执行根由启动策略注入 `JIUWENSWARM_CONTAINER_FILE_ROOT=/home/agentos`，不得由请求覆盖；缺失配置/平台不支持安全描述符时拒绝访问。逐级目录 FD + `O_NOFOLLOW` 打开根、父目录和目标，读写只接受普通且单链接文件；目录列表不跟随/返回链接。禁止 `..`、NUL 与根外路径。打开后的父目录被改名并替换为链接时继续持有原目录 FD，不重新按字符串打开。此约束针对文件接口，不等价于同 UID 任意代码执行隔离或容器逃逸防御。

`file.workspace.read/write/list/mkdir` 为现有 ReqMethod/codec 的增量方法；当前锁未提供该成员，沿现有 `common/schema/message.py` 最小兼容注册方式补齐，不复制枚举、信封或状态机，不修改依赖安装文件。每块最大512KiB，列表最多10000项/递归64层；上传保留原路径与返回格式，使用原 E2A 分块，不新增文件服务、存储或队列。Gateway/Agent须匹配该能力；旧固定镜像不自动升级，不支持时安全失败。

范围：本次闭合云账号绑定的 `/file-api` 越界；附件、URL导入、工具文件操作、签名资产下载各有独立契约，不能将本次结果外推为所有文件入口或跨账号共享日志隔离验收。实际候选及验证结论见故障记录 B_20261110_0135_cloud-file-boundary。

基础设施验收边界：平台请求的私有工作区/凭据挂载不是实际容器全部挂载的证明。云端账号实例不得看到其他账号或平台日志；集中采集归宿主运维，必须独立核验实际追加挂载及进程权限。未接入私有日志部署边界的Docker底座不满足该要求；不向Gateway加入另一日志服务，不把Supervisor专属私有日志设置用于Docker。

## 预建执行池绑定契约

运维可设置resource_pool_id，将池标识及原frontend_endpoint/namespace/function_version_urn固化至已有环境profile。读取、注册恢复或导入遇到不一致即拒绝；旧无池绑定不会自动归入新池，移除配置也不能绕过检查。此项仅防止重定向，当前单Gateway仍使用一个原Router端点，不创建或选择元戎资源池，不代表日志隔离通过。启用需独立状态或另行审核迁移；不得原地改旧部署。此契约不声明已实现真实多池调度。

## 可替换的日志部署边界

平台的稳定契约是账号环境日志隔离结果；Gateway/Router/Runtime及账号/环境库不依赖日志代理类型、端点或目录映射。部署可暂用deploy/cloud-workspace/docker_log_boundary.py，以受管/data工作区为键替换已配置共享日志bind源并保持目标路径；原Router/元戎保有创建/回收权威。

命名规则由可信部署侧必填workspace-name-pattern提供，仅匹配目录名，无隐式env_/u_默认。平台实例生成环境ID的既有规则不变，由装配传入相应正则。直接父根、规范路径、无链接、属主0700、明确镜像/非root用户及唯一/data约束独立于名称规则。配置错误或缺失安全失败；兼容规则调整不改变同工作区日志映射，不增加数据库记录或自动迁移。

当前代理仅向可信宿主控制进程开放Unix端点，不是通用Docker授权或所有挂载过滤。采集/配额/保留归运维；日志随持久工作区保留，不按epoch清空。替代机制必须先验证同一组实际挂载/读写隔离/生命周期/故障拒绝结果，再切换部署接线；已有容器不因配置自动改变挂载。停发/对账后才退出代理，历史日志保留，失败不得回退未隔离共享根。旧账号、固定镜像、凭据及数据不因替换日志实现自动改变。

完整部署参数和可执行装配示例由deploy/cloud-workspace/LOG_BOUNDARY_CONTRACT.md维护；本契约不声明上游原生替代机制或生产可靠性配套已实现。

部署侧运行保障不改变本契约的状态权威：日志适配器只限制连接/IO资源、清理自己的socket并交由原生服务管理器恢复进程，不重试Docker创建/删除。代理断开时，原实例链可在结果未知时保留原回执，或在删除完成条件满足后记DELETED；启用physical_verification的绑定必须同时取得原API404和物理完成确认，只有DELETED允许后续显式ensure推进epoch。观察回执时须考虑原链异步清理，不把“当次未就绪”等同于永久保留ALLOCATED，也不凭代理恢复判定实例已恢复。

历史缺口：仅凭元戎API404不足以证明物理缺席，曾出现created残留及下一代重复创建；旧候选证据见PLATFORM_CLOUD_LOG_ADAPTER_RELIABILITY_20261110。当前显式启用绑定按下节要求补物理完成确认，隔离修复结果见PLATFORM_CLOUD_PHYSICAL_RECONCILIATION_20261110。

## 物理删除完成确认

显式配置 `resource_reconciler_socket` 的新绑定固定 `physical_verification=true`；禁止运行时静默关闭或给旧绑定自动补入。原Router两个删除入口均在元戎确认不存在后调用可选 `confirm_deleted`，成功才注销/移除内存实例并落DELETED。策略使用持久绑定校验instance_id/epoch/DELETING，向受限部署接口提交工作区、凭据目录、固定镜像、执行用户和实例ID；未确认时保持DELETING，ensure继续原回收步骤，不新建。SDK/Runtime/账号权威不变；无该能力的历史部署沿用旧行为，不能宣称已获得物理保护。

部署实现与退出契约集中于 `deploy/cloud-workspace/LOG_BOUNDARY_CONTRACT.md`。Gateway不访问Docker API。临时部署模块通过工作区唯一Docker名称、代次scope与持久派发回执防止重复派发；仅对完整归属匹配且从未启动的残留执行原删除流程的同步补偿。未知派发结果、运行过的残留或检查失败均拒绝完成确认；没有后台扫描/新创建器。

所有用户消息入队（包括补充输入、演进审批回答和自动审批派生消息）必须复用现有 publish_user_messages / publish_user_messages_nowait 身份捕获入口；出队恢复原作用域，发送时仍查账号权威。无作用域的后台事件不借用其他请求身份，令牌不写入消息或持久化。

## 云端 Web 账号入口

云插件沿用 `/api/v1/auth/organization` 默认路径。状态的 `session_revision` 为当前会话 token 的 SHA-256 前 24 位，仅是 UI 变更投影，不授予权限。状态与其他账号响应均 no-store，cookie 保持 Secure/HttpOnly/SameSite=Strict。Web 静态服务、HTTP 及 WS 对外使用同一 HTTPS origin，与 public_origin 一致。

Web 独立入口提炼 codeswarm 登录/注册、凭据失效清理和退出行为；原 Account Kit 模型登录保持独立。身份确认和环境 READY 之前不挂载原 App/WS。首次云环境由用户进入，已有 ALLOCATED 经原 ensure 确认应用就绪后恢复；不另建创建/回收、Provider 或会话状态机。

已确认云账号后，权威不可用不得退回匿名/本地模式；挂起旧界面并关闭连接，重试重新核验。身份或会话版本变化通过整页导航丢弃原内存状态，仅同一已核验主体可保留会话 URL。退出未确认成功明确报错，不显示退出成功。

## Web 恢复与部署失败契约（2026-11-11 修订）

同身份仅指服务端新探测返回的 actor、authority、subject、session_revision 全部一致且认证有效；故障前 ready 状态恢复时不清偏好、不整页导航、不重复 ensure。环境已 READY 而身份复核失败，恢复仍复用这一就绪结果，执行请求继续由原服务端鉴权。主体/会话版本变化、撤销仍清理隔离缓存并走原入口；不能用旧身份缓存放行。持续故障仍卸载 App，未发送草稿保存不在本次保证范围。

Web RuntimeResume 将有 worker_instance/cursor/dispatches 的权威快照作为重放覆盖边界：已终态或快照范围内已缺席 dispatch 的旧重放不重新开启 UI 输出；必要时发出既有 runtime.history_required，由原历史加载与元数据链对账。首次空闲且无待交互快照可推进恢复游标，避免从零回放整个旧日志；运行中、待审批和已经观察到的输出保留原游标语义。工作进程变化重置边界；缺元数据的旧协议保持兼容，不伪造时间/终态，不重发 chat.send。

Web/TLS 失败恢复只属于可替换部署层 deploy/web/proxy_switch.py。停服前检查材料/哈希/镜像/归属/证书/语法；旧容器保留 ID，失败仅移除本次替身并恢复原角色；补偿失败明确报需人工恢复，不把其记作成功。账号/环境/Runtime 不依赖该脚本。单操作方、有界停机与保留容器代价见 deploy/web/README.md。

云实例角色尚未装配分享导出的Agent文件链。Gate通过可选shareExportDisabledReason装配原App/ChatPanel；控件禁用并显示原因，启动恢复不发送/share-api查询，不删除已有导出任务记录。本地角色未传入该限制，保持原行为。此项是UI能力声明，不替代服务端既有拒绝；完整云导出实现与旧runner链接访问仍不在已支持范围。
