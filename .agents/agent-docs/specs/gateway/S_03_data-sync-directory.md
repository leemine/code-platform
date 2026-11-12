---
id: S_03_data-sync-directory
title: 显式项目目录同步契约
type: S
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway/extensions/data_sync, gateway/services/data_sync, jiuwenswarm/data_sync, jiuwenswarm/server/control, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace]
files: [gateway/extensions/data_sync/extension.py, gateway/services/data_sync/store.py, jiuwenswarm/data_sync/contract.py, jiuwenswarm/data_sync/connector.py, jiuwenswarm/data_sync/transport.py, jiuwenswarm/server/runtime/session/project_store.py, gateway/services/data_sync/cloud_source.py, jiuwenswarm/data_sync/cloud_export.py, gateway/services/cloud_environments.py, gateway/extensions/agentos/agentos_router/router_client.py, jiuwenswarm/server/control/repositories/project_repository.py, gateway/extensions/data_sync/ui_extension.py, gateway/services/data_sync/ui.py, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/LocalCloudAccount.tsx, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/localCloudAccountClient.ts]
---

# 显式项目目录同步契约

## 范围与权威

本契约描述 P1S-02 首轮候选的可选目录 RPC、显式发布连接器和独立只读索引。只有原项目 ID、名称和 work_mode 参与同步。原 ProjectStore、账号权威、云环境服务、Router 和 Runtime 各自保有写入及生命周期权威；同步不能创建执行实例、会话、目录或注册可执行项目。不开启 `CODE_PLATFORM_DATA_SYNC_ROOT` 时不注册任何同步方法。

服务端要求原 `CODE_PLATFORM_CLOUD_CONFIG` 账号装配。RPC 复用原 WebChannel req/res 信封，所有 `data_sync.*` 方法为 Gateway 本地方法；可信账号只来自 AccountPrincipal，并在排队后、返回前重验。客户端不得提交 authority、user_id、session_id、root 或 instance_id。数据传输不经过 chat.send，不新增 Provider 事件消费者。目录事务和共享契约不导入 Core、Provider、codeswarm 或执行服务；云角色适配器复用原实例认证和 Router 公共接口。

## 来源与完整库存

来源注册协商版本1和三个必需能力：project-inventory-v1、frozen-directory-v1、durable-receipt-v1；云端导出另需可选能力 cloud-role-export-v1，旧Gateway缺此能力明确拒绝，原本地v1客户端仍兼容。本地来源绑定账号内稳定安装ID，证明为操作员生成的32字节随机值的十六进制表示；服务端只保存SHA256。线上字段source_token复用宿主敏感日志过滤，证明只是有效账号内的发布凭证，不是独立登录、设备证明或可执行权限。

云来源由Gateway托管，稳定绑定原逻辑环境ID；客户端不可注册cloud来源或用证明直接发布云库存。`data_sync.cloud.publish`只接受operation_id和显式project_ids，账号来自原AccountPrincipal，环境来自原EnvironmentStore。Gateway通过原Router的send_existing_request读取已就绪、物理ID精确匹配的实例；使用原E2A project.list、签名握手/请求与Front控制面ProjectRepository（旧ProjectAdapter兼容分支保留），不新增传输或协议枚举。云端须为原account-instance角色，核验原凭据中的账号、逻辑环境、epoch及实际数据根摘要，再严格导出原ProjectStore。无READY实例、旧AgentServer不支持、绑定变化或完整性不足均失败；不调用ensure/create/reclaim。

导出前后及交付前查账号，提交时用原环境库guard_binding短事务锁定归属、代次、操作ID、物理ID、工作区与状态；锁内无网络等待。目录库存、来源generation、账号游标epoch及操作回执在目录库同一事务提交。原环境在相同工作区重建后，来源ID保持、generation递增，旧游标失效；工作区变更、epoch倒退或来源撤销明确拒绝，不自动认领旧候选自声明的cloud来源（SOURCE_REPAIR_REQUIRED）。这只保证受管绑定连续性，不证明卷中内容未被外部修改。

重复云操作按operation_id和排序后的选择集合返回原回执，不重新读取源；环境绑定仍需可读且ALLOCATED，来源未撤销。已提交操作即使当前传输离线仍可恢复，回执代表原提交而非当前实时库存。未提交操作遇离线不生成墓碑，不更改旧副本。
注册相同绑定/证明返回原来源；不同证明冲突。撤销增来源 generation 及账号 epoch，使旧证明不可用、旧快照/变更游标失效。撤销不自动恢复或删除源文件。来源、对象和账号分别维护 generation、revision、watermark，不复用会话游标。

连接器仅导出显式选中项目，一次读取原项目注册文件的完整内存快照。严格导出拒绝缺失、损坏、非普通文件、符号链接、重复 ID 和非法可见性；不使用 UI 容错空列表，不写原项目注册文件或迁移数据。兼容已有缺省 work_mode 的旧记录，保留未选中Design项目共存；首轮选择Design项目会明确拒绝同步。已选项目确实消失或隐藏才从投影撤回；显式空选择可撤回该来源全部元数据。空项目保留。安全导出当前需要 POSIX no-follow 文件打开，Windows 不静默降级。

完整库存上限 10000 项、4 MiB，逐条只含 native_id/name/work_mode；绝对路径、文件、历史正文不接受。服务端核验 complete、total、规范化摘要，按 base_revision 乐观并发校验，在同一 SQLite 事务内写对象、变更、墓碑和回执。失败不推导删除。跨源同原生 ID 以账号/来源维度区分，不按名称合并。

## RPC 与持久性

| 方法 | 语义 |
| --- | --- |
| data_sync.negotiate | 版本/能力及大小约束；不支持明确失败 |
| data_sync.source.register / source.revoke | 本地来源注册／账号所有者撤销；拒绝客户端自声明cloud来源 |
| data_sync.cloud.publish | Gateway从原云角色拉取显式所选库存；operation_id、project_ids，服务端托管来源与代次 |
| data_sync.inventory.publish | 完整所选库存，operation_id、base_revision、items、total、inventory_digest、complete |
| data_sync.snapshot | 冻结已接受对象、coverage 与账号水位；100项分页 |
| data_sync.changes | 从完成游标读取有序变更，含墓碑；每页100项 |
| data_sync.ack | 接收方耐久发布后提交完成凭证和 operation_id |
| data_sync.receipt | 查询 committed/unknown；unknown 不等于未提交，重试原操作 |
| data_sync.catalog | 账号只读目录分页；版本锁定，不注册来源或生成ACK |

除协商、注册、账号所有者撤销、cloud.publish和catalog外，调用必须带 source_id/source_token/generation。服务端最多4个并发执行槽，数据库事务超时15秒。单账号最多32来源、10000活对象，变更及回执有100000条配额；超额拒绝，不丢弃旧证据。

快照冻结整个接受列表，分页期间新写入只进入变更流。HMAC 游标签名绑定账号、接收来源、类型、epoch、水位与签发时间；快照最长1小时，每接收来源最多5个活动快照。只有最后一页提供完成凭证，未读完不可 ACK；普通游标最长30天。30天是游标有效期，当前没有自动 GC，不承诺30天后物理删除。

同步库和本地索引使用私有 POSIX 目录及 SQLite FULL 提交，数据库连接逐事务关闭。operation_id 的规范化 payload 摘要与结果同事务保存；同 ID 同内容返回原回执，异内容拒绝。连接器先持久保存发布意图，丢响应先查回执，完成旧意图后再处理新选择。接收页先持久暂存，完整总数和摘要通过后才原子替换可读视图、保存水位和待 ACK。ACK 丢失保留相同操作重试。

本地副本位于原数据根的 data-sync 私有子目录，按端点/来源/代次隔离；不写原 ProjectStore、活动 cwd 或历史。拉取失败标 stale，过期/撤销游标清理检查点但保留旧副本；需要再次显式拉取恢复。current 仅表示 checked_at 时该次接受边界已追上，不代表所有账号来源齐全或源仍在线。account_complete 始终 false。单次拉取有分页预算，预算耗尽保留检查点并明确报错。

## 入口与限制

`python -m jiuwenswarm.data_sync` 为操作员一次性入口，必选 --project（可重复）、--withdraw-all 或 --receive-only，不自动扫描全部项目、不安装后台服务。账号令牌及来源证明通过环境变量注入，不写入索引。远端只允许校验 TLS 的 wss；ws 仅数字回环地址；URL 不接受凭据或查询选择器；拒绝握手重定向，不向其他端点转发账号令牌。请求有超时，失败不自动重放写入。

CLI的--kind cloud表示请求Gateway发布原云角色项目，--installation-id和来源证明仍只注册本地接收方；--project此时必须为云端原项目ID。云角色随原AgentServer装配，按需发布，无后台自动轮询。短期设备委托、跨平台安全凭据存储、来源重新配对、历史/文件对象和GC尚未实现。候选验证与远端CI状态由实施记录维护。操作步骤见 docs/zh/data-sync.md 和 docs/en/data-sync.md；实施证据见 F_20261112_1545_platform-directory-sync.md。


## 产品界面与本地账号适配

根据用户2026-11-12确认的范围调整，产品不提供项目清单同步、手动发布、撤回或来源列表入口。三段式Code控件继续只负责本地目录、Local/Cloud切换，以及云端目录选择/新建文件夹/创建环境。本地左下角LocalCloudAccount只提供云账号登录、状态和退出；云端登录仍由原CloudWorkspaceGate负责。底层目录协议作为可选基础保留，不称为文件或会话同步完成。

本地账号控件只调用同源HTTP前缀 `/api/v1/data-sync` 的GET status和POST login/logout；名称保持既有后端接缝兼容，不注册来源、不读取或发布清单。云端原账号权威负责认证，本地以固定HTTPS桥接，用独立HttpOnly、SameSite=Strict Cookie承载会话，密码不持久化。未配置可选本地接入时不展示控件；服务不可用时可重试。配置与操作步骤见中英文data-sync文档。

保留的HTTP适配还支持view/choices/publish/refresh/revoke，用于协议集成与验收，不再由产品界面调用。每次检查Host；存在Origin时必须完全匹配配置，POST还须X-Jiuwen-Sync:1和参数字段白名单，拒绝账号/根/实例选择器。云端原AccountPrincipal负责请求与交付前复核。HTTP与RPC共享4槽。目录view使用账号隔离、版本一致性校验的只读catalog分页，不注册接收来源或生成ACK；云choices沿原READY环境及existing-only Router导出；refresh不读云角色。local副本、意图及ACK仍由原连接器持久化。

同步连接以 `X-Jiuwen-Connection-Scope: data-sync` 请求收窄范围。原账号鉴权返回仅data_sync方法前缀的连接能力；原WebChannel在分发前拒绝其他RPC，连接与断连均不进入执行实例计数、预热或延迟回收。普通连接保持原生命周期。握手缓存纳入作用域，不能复用其他范围的鉴权结果。此接缝仅减少权限，不跳过逐请求/交付账号校验。无启动承诺要求配套新版Gateway，不能把旧Gateway接受握手当作支持证明。

增量changes响应附带当前来源coverage，与对象页在同一事务读取；新版接收方将来源类型、代次、修订与对象变更原子持久化。旧接收方可忽略新增字段；新接收方兼容旧端未提供coverage时保留既有摘要。coverage描述已接受来源，不代表来源在线或账号完整。
