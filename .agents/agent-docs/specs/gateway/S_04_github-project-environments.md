---
id: S_04_github-project-environments
title: GitHub 云端项目环境契约
type: S
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway/services, gateway/extensions/cloud_workspace, jiuwenswarm/server/control, jiuwenswarm/channels/web/frontend]
files: [gateway/services/project_environments.py, gateway/services/project_github.py, gateway/services/project_preparation.py, jiuwenswarm/server/control/project_import.py, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/CloudEnvironmentDialog.tsx]
---

# GitHub 云端项目环境

本地目录、Local/Cloud、云端操作三段式入口保留。创建云端环境对应 GitHub 项目工作区，不创建额外物理实例。账号默认运行实例仍由原 Router/AgentManager 唯一管理；原 session.create/chat.send 及旧会话绑定不改变。

`project.github.status|begin|poll|disconnect|accounts|repositories|branches|resolve` 使用原云 WebChannel。直接云页面不指定执行实例；本地页面用 `execution_target: cloud` 选择既有同源云桥，桥移除传输选择器并重写项目资源地址。云端仅接受当前账号及 `cloud` 目标，不接受客户端 user_id、instance_id 或任意上游 URL。

`JIUWENSWARM_PROJECT_GITHUB_CONFIG` 可选，仅指定私有 root/executable；默认 root 为 Gateway auth_dir/project-github-gh。官方 gh 不可用时 configured=false，不申请实例。配置变更需重启；旧 App 连接库禁止复用。每次登录独立 GH_CONFIG_DIR/HOME，不继承宿主凭据，未修改的官方 gh 负责设备授权；浏览器只获得短期 user_code。凭据文件仅在临时私有目录落地，加密持久化到 Gateway-only 卷后清理，执行实例无访问权。服务独占存储租约，重启丢弃 pending 并清理临时目录；断开连接的 generation 防止迟到授权复活。授权与结果投递继续实时检查云账号权限。使用连接时调用官方 gh 读取 token，并通过实时 GitHub /user 校验账号；网络/限流失败保留连接，撤权进入 reauthorize。断开本服务不等于撤销 GitHub CLI 的外部 OAuth grant。

`project.environment.prepare` 仅接受 execution_target、32位十六进制 operation_id、name、account_id、repository_id、branch。相同操作保持原意图、第一次解析的 commit 和原 bundle；改变意图拒绝。状态为 accepted/resolving/fetching/transferring/verifying/ready/failed/interrupted。`status` 只接受 target/operation，进程中断后查询返回 interrupted，显式重试恢复原操作。后台准备最多两个在途操作；不是 Runtime Turn 调度器。

GitHub 仓库/分支解析受当前 GitHub 用户授权限制；accounts 返回所连接用户，repositories 从 /user/repos 分页读取，准备和发布前实时读取仓库及分支。准备前和目标发布前重新解析校验；Git fetch 凭据仅存在 Gateway 子进程环境，不写入 argv、远程 URL 或项目配置。有界超时/字节数/文件数、禁用 hooks/配置继承、Git 对象及树检查、私有按账号仓库缓存沿用 codeswarm 语义。默认完整 Git 历史，LFS deferred；不加载依赖、不展开子模块、不执行仓库脚本。

原 E2A 新增 project.import 兼容枚举接缝，AgentServer Front Control 处理 capabilities/begin/chunk/verify/publish/status，不预热模型 Runtime。每个请求仍经过原 Router 服务断言认证。目标以可信 routed user + operation 分隔回执，目录由原 project_store.resolve_default_project_dir(code) 决定；不接收客户端根目录。预留目录 inode、分块偏移/重放内容、最终 SHA-256 和 Git 来源必须一致；已有路径/名称不覆盖。耗时检出 verify 完成后重新校验账号和 GitHub，再以单独 publish 请求原子登记原 ProjectStore.repository_source，断线恢复可收回同一项目结果；隐藏/移除项目或换根不复活。

`project.environment.list` 在新鲜账号鉴权后读取原 project.list，返回带 repository_source 的可见 Code 项目，不另存项目清单。已准备工作区允许用户后续修改，查询回执不重置文件。ready 检查明确 dependencies=unknown、execution_authorized=false。用户显式使用只选择原项目；发送时仍遵守原会话/模型权限入口。

UI 未配置/未授权/目标不支持均明确区分，不假装准备成功。关闭弹窗不取消已接受准备，保留 opaque operation_id 可恢复；账号变化清除本地意图并隔离迟到结果。源码、mock、未配置状态验证不得标记真实 GitHub 授权验收通过。

Git 下载总预算为 900 秒，重试共享剩余预算；不再按 90 秒截断有效传输。Git HTTPS 使用 HTTP/1.1 保留 TLS 验证，连续 60 秒低于 1 KiB/s 时由 Git 判为传输失败；下载进程中每秒重验云账号权限与连接 generation，发布前另行实时重验 GitHub 仓库权限。退出后只清理本次进程新建的临时 pack/lock，保留先前文件。

## GitCode 平台适配

GitHub `project.github.*` 与官方 gh 授权兼容保留。GitCode 使用 `project.gitcode.status/connect/disconnect/accounts/repositories/branches/resolve`；`connect` 仅接收 `execution_target` 与 `access_token`，通过固定 `api.gitcode.com/api/v5/user` 验证身份，再按可信云账号加密保存。访问令牌不得出现在返回值、URL、日志、前端持久化或项目文件。`repositories` 以 account_id 分页；`branches/resolve` 还要求 repository_id/full_name，后端重新查询并核对 ID，不信任克隆 URL。

`project.environment.prepare/status` 可选 provider，默认 github；gitcode 准备还包含 full_name，GitCode account_id 为不透明字符串，repository_id 为整数。准备记录与缓存随平台凭据根目录隔离，前端操作 ID 按目标/平台保存。原 AgentServer `project.import` 能力返回 repository_providers；未声明 gitcode 的旧实例不允许 GitCode 准备。来源带 provider=gitcode；旧来源省略 provider 时保持 github 语义，远端 URL 仅由固定主机表构造。

GitCode 连接通过官方个人令牌创建页加一次性密码输入控件完成，不宣称官方设备码授权或自动 OAuth。已连接/缓存状态不是访问授权，读取仓库、分支、准备与发布前继续进行云账号与远端权限校验。断开、账号变化或连接代次改变时拒绝迟到结果；上游临时失败保留现有连接，不自动清除有效令牌。

Electron 的 GitHub 设备授权和 GitCode 令牌页由受信主进程交给系统已安装的 Google Chrome。IPC 只接受平台枚举，由主进程确定官方 HTTPS 地址。启动失败在原授权区提示，链接和设备码或令牌表单可继续使用。网页入口保留当前浏览器标签页行为。

## 关闭、连接替换与发布

准备服务关闭后拒绝新操作，对在途阻塞工作发出中断并等待退出，再保存 interrupted 回执和释放凭据存储租约。取消 asyncio 任务不能代替下载线程及其 Git 子进程退出确认。慢速检出结束后，发布前重新验证远端仓库身份、云账号权限及本次连接 generation；断开或换连接后不得发布旧准备结果。

GitCode 更换令牌期间，同一作用域不接受第二个更换请求。新令牌验证失败时，仅在本次 generation 仍有效的条件下恢复原连接；期间发生断开时不恢复。打开更换令牌表单立即清空旧仓库选择，避免在连接变更中误用旧选择。

弹窗关闭或运行位置变化时，新视图重置请求 busy 标记，保留服务端已接受操作及原 operation_id；迟到响应不能覆盖恢复后的状态。已有环境选择中的登录续办只重开环境列表，不转为创建新环境。
