# 云工作区后端接入

本增量提供独立账号权威、环境绑定和原 Router 接线。正常 Gateway 仍是唯一公网入口；没有独立 cloud_workspace 启动器。完整账号 UI、跨宿主 Local/Cloud 选择和同步产品尚未交付。

## 装配

1. 账号角色运行 `python -m gateway.auth.account_http --account-auth-file /private/accounts.json`。私有 JSON 包含 `database`、`authority`，可选 `session_ttl`；账号库使用原 scrypt/会话摘要格式。非回环地址必须提供 `--cert` 和 `--key`。现有账号服务需支持幂等注册 `operation_id` 才能闭合注册恢复，不复制账号库到 Gateway。
2. Gateway 沿用正常启动命令和 `agentos_router`，实例键固定 `user_id + agent_type`。设置 `CODE_PLATFORM_CLOUD_CONFIG` 指向下述配置，并确保既有扩展筛选允许 `Cloud Workspace`。业务服务通过原注册表在 Router.connect 前装配；无权威配置、角色或实例客户端不匹配会拒绝启动。未设置此变量时原本地路径不装配云业务。
3. 配置字段：`authority`、HTTPS `public_origin`、绝对 `state_root`、独立绝对 `workspace_root`、固定 `image`（sha256:64位十六进制）、`frontend_endpoint`、`function_version_urn`、`account_backend_config`。后者是0600私有文件，内容如 `{"url":"https://account.internal","ca":"/private/ca.pem"}`。元戎地址、URN和namespace必须与原 Router 相同。`registration_enabled` 默认false；`runtime_user`须匹配持久目录实际UID:GID。配置与真实镜像、共享挂载的可达性需在隔离部署中另验。
4. 环境角色只写独立SQLite绑定库；首版用文件锁限制为单Gateway写入者。目录0700，文件0600。执行容器只挂本账号 `/data` 和本代只读 `/run/jiuwenswarm`，注入独立数据/配置路径、`CODE_PLATFORM_ROLE=account-instance` 及实例凭据路径。共享控制库、账号库、其它账号卷不进入容器。权限由既有Runtime/Provider继续执行。

## 行为与恢复

原账号HTTP路径 `/api/v1/auth/organization/{register,login,logout,status}` 和Cookie保持；新增环境查询/ensure使用同前缀。注册持久化意图与固定镜像，返回NEW；显式 `environment/ensure` 或原连接预热调用唯一Router创建、连接。插件仅贡献 `cloud.environment.ensure/status`，不接管 `session.execution.options`。

创建超时或取消后的未知结果保留回执，以有界清单和实例详情精确对账；零匹配、多匹配均不再POST。启动清理保护本控制面已有账号实例。DELETE需原实例查询明确404；启用physical_verification的绑定还须物理完成确认才闭合，未确认时维持DELETING；下次ensure可重试该已知实例删除。重建增加epoch、保持原镜像和数据。普通网络断开仅关闭云连接，不自动删除绑定实例。

旧账号未导入绑定时可登录，环境返回不可用，不套新默认镜像。运维可在隔离迁移中调用 `EnvironmentStore.adopt_existing` 显式导入原实例、镜像、目录和凭据引用；只接受归属、代次、工作区和撤权配置兼容的实例，不自动改旧密钥或迁移历史库。源codeswarm六字段旧凭据及旧控制库需要另行审核迁移，不能把函数单测当成现网兼容认证。

账号校验沿原Authenticator。进程内请求作用域经原消息队列传递；不把Cookie写入协议。实例握手与请求断言有目标、代次、用途、短有效期和防重放。维护仅开放已有配置读取/模型列表和列明cron用途，不能把普通未登录请求当作维护。平台logout先撤销权威会话，再写当前代次撤权屏障；请求和WS/文件输出均复核身份。权威侧绕过Gateway直接撤销时，已经签出的在途断言最多保留15秒有效期；其后的请求及Gateway输出仍重新查询权威。撤销不另造Runtime取消状态机。

## 验证边界

2026-11-10，三角色候选已按原Core/协议锁构建并核验实际来源；用户指定的113.207.105.228已完成独立账号TLS、原Router自动创建及真实AGENT_READY、原Gateway WS请求/重连、真实回执丢失对账、删除404与新代重建、注销撤权验证。只验证后台角色与原实例链，未部署现网，未完成完整UI、真实Provider/模型业务、跨节点共享卷或旧凭据迁移验收。

**B01云文件接口已修复；B02在专用Docker日志适配部署中已通过定向隔离复验，候选仍未达到生产发布条件。** 云账号文件请求沿原Router/E2A进入Runtime文件适配器，在实际访问时以逐级目录FD/no-follow约束工作区，不回退SDK文件代理。最终本地24项专项及服务器43项文件回归通过。后续双账号合成日志验证确认：当前Docker基础设施自动挂入整池日志根，实例可读取对方合成日志。日志是供运维集中采集，不是账号间共享需求；需基础设施提供私有日志挂载或独立隔离资源边界，不能以改文件API、只读挂载或chmod000替代。不修改外部SDK和旧资源池。

账号适配器通过原AuthResult显式贡献可信routing_user_id，FastAPI/WS入口保留完整扩展与请求/回包guards；原IAM用户名映射不变。原文件HTTP契约仍要求user_id，必须与认证账号一致。三角色构建、独立Python3.11元戎启动层及运行限制见[角色构建](../../deploy/cloud-workspace/README.md)。

历史主链证据见管理仓PLATFORM_CLOUD_ROLE_E2E_20261109；B01修复见PLATFORM_CLOUD_FILE_BOUNDARY_20261110，修复前日志验证及329项回归见PLATFORM_CLOUD_LOG_ISOLATION_20261110。测试新增实例及容器均已回收，私有合成数据保留；原180个容器元数据与5个元戎实例清单一致。后台主链通过不代表F1/F2完整隔离验收通过。

## 云文件访问边界

账号绑定模式的原 `/file-api` 经原 Router/E2A 转交 Runtime 文件适配器，工作区根由部署注入，所有路径分量禁止跟随符号链接；不支持时返回错误，不回退元戎文件接口。软链接（含根内链接）不作为可访问文件；普通读写、分块上传、列表和建目录保持原入口。Gateway 与 Agent 镜像须配套，已有固定绑定不自动升级。此项不代表附件/工具的全部文件访问或共享基础设施日志已完成隔离验收。

## 可选执行池绑定

运维可设置resource_pool_id，将池标识及原frontend_endpoint/namespace/function_version_urn固化至已有环境profile。读取、注册恢复或导入遇到不一致即拒绝；旧无池绑定不会自动归入新池，移除配置也不能绕过检查。此项仅防止重定向，当前单Gateway仍使用一个原Router端点，不创建或选择元戎资源池，不代表日志隔离通过。启用需独立状态或另行审核迁移；不得原地改旧部署。当前相关389项回归通过，真实多池调度未实现，后续Gateway镜像已按锁复验，见管理记录PLATFORM_CLOUD_POOL_BINDING_20261110。

日志适配器已提炼到deploy/cloud-workspace/docker_log_boundary.py；只影响任务专用部署，旧底座不自动切换。前一硬编码规则候选25项专项及双账号实际挂载、合成日志隔离、代理重启和原链回收重建已验；代理服务守护/故障拒绝、连接上限、日志采集配额等生产缺口见角色构建说明及管理记录PLATFORM_CLOUD_DOCKER_LOG_BOUNDARY_20261110。

本版将适配器限定为临时可替换的部署接入，目录规则须显式传入--workspace-name-pattern；平台业务不依赖代理类型/端点，数据库和日志映射不因兼容规则变化而迁移。43项本地回归通过；同一新版脚本已在113.207.105.228专属底座通过显式配置、双账号日志隔离、人工代理重启和原链回收重建复验，见管理记录PLATFORM_CLOUD_LOG_ADAPTER_SERVER_20261110。替换机制必须先通过实际隔离验收，才能切换部署并退役代理，不能直接退回共享日志根。详见[配置与退出契约](../../deploy/cloud-workspace/LOG_BOUNDARY_CONTRACT.md)。

上一轮运行保障记录（旧候选）：临时适配器新增连接/IO约束、SIGTERM清理、显式安全socket恢复和systemd模板，58项专项通过。服务器故障注入中，停机和上游503安全失败，代理在SIGKILL后自动恢复；但创建成功响应丢失时出现元戎API404与Docker容器残留不一致，后续重试产生重复物理容器。因此故障验收未全通过，仍禁止现网启用；适配器不重放请求或另建回收器。详见PLATFORM_CLOUD_LOG_ADAPTER_RELIABILITY_20261110。

### 创建响应丢失与物理对账

在新专属底座显式启用受限物理确认接口后，原Router删除同时确认元戎记录与物理容器，失败保持DELETING并暂缓重建。部署适配器保存最小派发回执，使用工作区唯一名字防重；仅补偿删除归属明确、从未启动的残留，不强删运行实例或数据卷。Gateway不挂载Docker socket，不修改SDK。配置、权限、未知结果限制和退出步骤见[部署契约](../../deploy/cloud-workspace/LOG_BOUNDARY_CONTRACT.md)。旧部署/绑定不自动迁移。

当前候选已通过物理对账修复的隔离验收；上述故障为旧候选历史，不是本轮未闭合阻断。配置和逐状态恢复步骤统一见[候选交付说明](../../deploy/cloud-workspace/CANDIDATE_HANDOFF.md)。生产化事项另行安排，未部署现网。

内部补充消息及演进审批重新入队时保留原账号作用域；发送前仍检查会话撤销，不把用户请求降级为维护请求。

## 云端登录与环境入口（候选）

新版 Web 入口沿用 codeswarm 的用户名密码登录、身份状态与退出行为，使用独立账号权威；Account Kit 继续处理原模型授权。部署应让静态页面、账号 HTTP 和 WS 处于与 `public_origin` 一致的 HTTPS origin，默认账号路由为 `/api/v1/auth/organization`。注册入口仅在 `registration_enabled=true` 时显示。

登录后首次点击“进入云环境”，已有绑定经原实例链核验就绪再进入主界面。账号或环境服务异常显示明确错误和重试；不会无限显示“加载配置中”。退出先关闭连接，服务器撤销成功后清理账号缓存；失败保留重试。此版本真实 UI/Provider 隔离验收进行中，不能沿用旧版本的成功结论。

登录标记使用圆形头像显示用户名的前两个字符（拉丁字母大写），悬停或辅助技术可读取完整用户名；侧栏仅保留头像按钮，点击后展开账号菜单与退出项，退出仍走原撤销接口。
Codex 会话切换权限在下一轮前生效：平台重连自有客户端并恢复同一个原生线程，确认权限后才执行。恢复失败会拒绝执行；已有历史与 MCP 选择保留，不修改官方 SDK。
