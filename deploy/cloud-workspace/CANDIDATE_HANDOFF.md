# 候选交付：配置与恢复说明

本交付冻结已通过隔离验收的后台集成候选。本说明只整理现有行为，不提供新管理服务、强制解锁工具或现网安装脚本。源码基线34904d097加原独立候选未提交差额；本地候选提交不代表合入或部署现网；提交状态以管理记录 `PLATFORM_CLOUD_CANDIDATE_COMMITS_20261110` 为准。最新实际镜像/摘要、差额及验收范围见管理记录 `PLATFORM_CLOUD_CANDIDATE_HANDOFF_20261110`；历史各轮结果不自动转记给新版本。

## 配置接线

| 配置/角色 | 交付时必须对应的现有契约 |
|---|---|
| 独立账号服务 | 唯一持有账号库；`--account-auth-file`为私有0600文件。保持原authority、账号ID、会话撤销语义；Gateway只持有服务地址/CA。 |
| Gateway云配置 | `CODE_PLATFORM_CLOUD_CONFIG`指向可信配置文件；已有扩展白名单包含Cloud Workspace。`authority/public_origin/account_backend_config`与账号服务和HTTPS入口一致。 |
| 原Router | `frontend_endpoint/namespace/function_version_urn`与云配置完全相同；不能把其他池的健康状态或资源余量当作当前池。 |
| 持久目录 | `state_root`和`workspace_root`分离；工作区及凭据目录0700、属主与运行UID/GID一致。固定镜像及`runtime_user`使用实际登录名，本次镜像为agentos=1000:1000。 |
| 日志适配器 | 完整Docker代理只供元戎可信进程，位于操作员0700目录；`DOCKER_HOST=unix://...`与runtime_launcher的docker_host同址。工作区名称规则、实际共享日志根、私有日志根与允许镜像均显式设置。 |
| 物理确认 | Gateway `resource_reconciler_socket`指向独立确认socket。只读挂载其父目录；父目录操作员所有/Gateway组0710，socket同组0660。禁止把完整Docker代理或派发回执挂入Gateway/Agent。 |
| 配置稳定性 | 新绑定固定physical_verification能力；不可删除配置来绕过DELETING。既有未启用绑定不自动迁移；pool_id若已固定也不能更换。 |

物理确认附加参数对应现有[systemd附加模板](systemd/physical-confirmation.conf.example)，不是默认启用命令：

```ini
# 在对应专属环境原EnvironmentFile中一并设置；下面仅为路径示例。
PHYSICAL_JOURNAL_ROOT=/srv/code-platform/physical-journal
IDENTITY_ROOT=/srv/code-platform/control/instance-auth
IDENTITY_TARGET=/run/jiuwenswarm
RECONCILE_LISTEN=/srv/code-platform/confirmation/completion.sock
RECONCILE_FRONTEND=http://127.0.0.1:REPLACE_WITH_DEDICATED_FRONTEND_PORT
RECONCILE_GID=1000
```

六个参数须同时提供；`IDENTITY_ROOT`必须等于对应Gateway的`state_root/instance-auth`，确认Frontend仍是同一原实例链。回执根是持久目录、操作员所有0700，不放入临时RuntimeDirectory，不随代理重启清空。确认目录只读bind应挂整个目录而非单一socket文件，才能接收重启后的新socket inode。示例端口必须替换，不能复制测试端口到现网。

完整参数约束、超时、socket恢复与替换语义以[配置契约](LOG_BOUNDARY_CONTRACT.md)为准；启动顺序为预建专属目录→启动/核验适配器→原元戎使用该端点→账号服务和Gateway。模板只供后续部署评审，本次不执行安装、enable或重启。

## 先识别状态，再恢复

先记录精确账号/环境、epoch、operation_id、元戎instance_id、镜像摘要及部署回执scope/容器ID。普通HTTP环境响应不返回所有内部字段；如需核对epoch和回执，由有权操作员只读查看该环境记录，不向客户端增加管理字段。

账号环境状态与物理派发回执是两种不同记录：前者是平台绑定权威；后者只证明一次部署派发及物理完成。READY是应用就绪结果，不是独立的容器数量证明。

| 观察到的状态/故障 | 现有恢复动作 | 完成条件/停止边界 |
|---|---|---|
| 代理停机、socket失效、上游不可用 | 核对本专属服务/参数/挂载，恢复同一固定版本适配器及同一持久回执目录。仅使用已有服务管理器；安全socket恢复需显式开启，普通文件/链接/活监听仍拒绝。 | 不改回裸Docker。服务恢复后，已授权账号重新调用原environment ensure；不是重发Docker POST。 |
| 环境DELETING | 原ensure先重试该已知实例的原删除流程，再做物理完成确认；也可由原内部Router删除入口完成，未新增公开管理删除API。 | 原元戎404加物理确认均成功才DELETED；随后明确ensure才推进epoch。确认503期间保持原epoch/operation。 |
| 创建201丢失、残留容器从未启动 | 恢复代理后沿上述原链确认；部署模块校验镜像、用户、scope及工作区/只读凭据挂载，自动同步补偿该created残留。 | 不手动rm代替验收，不force、不删卷。物理404及持久DELETED后才能重建。 |
| 环境CREATING/UNKNOWN，未拿到实例ID | 原ensure通过原元戎清单/详情精确对账，唯一匹配才接回。 | 零匹配/多匹配不再次POST；保留状态和证据。 |
| 派发SENT，observed=false，当前物理404 | 保持待对账；核对是否存在延迟派发、实际上游及对应scope，保全回执。 | 当前没有经过验证的通用强制解锁步骤；不能改写为NOT_SENT/DELETED、删除回执或凭一次404放行。需要个案恢复时另行审阅准确资源与证据，不扩充本交付功能。 |
| 容器运行过、归属不同或原实例仍在 | 交回原实例生命周期核对；诊断只针对记录中的精确ID。 | 确认接口拒绝自动补偿，不强删、不扫描清理同池其他实例。 |
| 回执损坏/缺失、目录/权限或绑定配置不一致 | 停止受影响环境的新创建，保留现场，核对一致备份及原装配。 | 不空目录重新初始化、不直接改库/epoch来消除错误；未证实恢复前保持不可用。 |
| 迟到旧代请求 | 保留既有DELETED回执，由适配器拒绝；不把它当成新建需求。 | 当前代容器/数据不变，上游create计数不增加。 |

原业务恢复入口：已认证账号的 `POST <api_prefix>/environment/ensure`，空JSON对象；仍遵循原Cookie/Origin或可信客户端请求头约束。不允许在请求中指定user_id、镜像、socket、工作区或epoch。此入口可能在回收确认完成后创建新一代，诊断阶段先使用原GET环境状态；恢复前确认该账号确实需要重建。

## 保留、备份与回退

- 保留账号权威数据库、环境数据库、工作区、代次凭据及部署派发回执的关联。SQLite可能启用WAL，不能将在线主db文件的简单复制称为一致备份；使用既有一致备份机制或停止任务所属写入者后取一致副本，凭据/数据库不进入Git。
- 本轮未验证整套灾难恢复或跨版本数据库回滚。不要把旧环境库/回执单独覆盖到仍运行的实例，也不要删除已撤销会话信息、旧代回执来追求可用。实际恢复应先核对物理资源和在途操作，不能凭备份日期猜测状态。
- 版本回退仅可指向已验证且仍履行物理确认、日志隔离契约的版本。之前只有日志隔离、缺少物理确认的候选不能直接作为当前环境的安全回退版本。没有合格版本时停止受影响新创建并保留数据，不以降级绕过保护。
- 清理仅限明确归属本任务的实例/服务；按原Router回收完成并核对物理结果后，才停止任务控制面/底座。工作区、回执、历史日志及证据按既有保留决策处理，本说明不授权删除。

## 交付边界

本次隔离集成修复已验收，不再扩展功能。日志采集/配额/长期轮转、完整UI和真实Provider业务、跨节点及旧数据迁移属于后续另行安排，未执行不写成通过，也不继续挂作本次修复任务的阻断。现网启用、提交/合入均不包含在本次收尾动作中。
