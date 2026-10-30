---
id: S_02_external-adapter-boundary
title: 外部 AgentAdapter 单 Agent 边界规约
type: S
author: leemine
author_email: leewanlong@gmail.com
modules: [agent_adapter, runtime]
files: [jiuwenswarm/runtime/session/coordinator.py, jiuwenswarm/runtime/plan.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/control/config_service.py, jiuwenswarm/common/model_routing_registry.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/runtime/service.py]
---

# 外部 AgentAdapter 单 Agent 边界规约

## 范围与依赖

本规约描述隔离候选中已实现的 Runtime-direct 单 Agent 接缝；尚未发布。公共对象复用 common.schema 的 AgentRequest/AgentResponse/AgentResponseChunk，底层继续使用已有独立协议包；不新建协议、Turn 队列或调度器。Native 保留 Core 实现。OpenCode 插件直连官方 HTTP/SSE，外部单 Agent 执行无需导入 Core；主包安装仍声明 Core，不能据此宣称正常安装已经可选 Core。

UI在新会话选择Provider，已有会话绑定不可变。execution_provider存于原metadata；刷新、后续请求和取消读取绑定，已有Native历史不改绑。JIUWENSWARM_AGENT_SDK只保留兼容默认，未配置仍为harness。Manager/Facade对每个执行实例固定选择，缓存区分Provider与连接配置；已有活跃会话保留其所有者。外部默认Runtime首次显式选择Native时复用原共享初始化。运行中会话不支持热切换。

entry point group为jiuwenswarm.agent_adapters，工厂签名create(*, mode)；未知、重复或无效工厂拒绝，不静默改引擎。OpenCode目前通过实验安装元数据注册，独立插件未发布。聊天仅增加Provider下拉，复用原模型菜单和model_selection。连接由插件正常配置，模型从Swarm目录生成官方服务启动快照；不新增设置表单，不在聊天中PATCH服务配置。请求不传密钥，配置摘要不匹配时失败。ModelSelectionResolver默认Native构造不变，OpenCode配置转换使用无Core副作用的构造函数。其session.create不使用Native预热。连接配置只为新执行实例取快照；当前未持久化配置版本，未执行空会话首次执行使用当时配置，冷恢复仍不支持。

Native输入、控制恢复及原Facade答案转换兼容导出保留。

## 责任与接口

| 接口/事实 | 责任与失败边界 |
| --- | --- |
| create_instance | 插件校验显式 URL、workspace；模型为原Swarm选择，旧显式model仍兼容，健康检查失败关闭客户端；URL 模式只借用服务；配置 opencode.cli_path 时创建会话自有官方 CLI 服务，复用 Swarm 模型目录 |
| prepare_session / has_session_runtime | 创建、查询本适配器拥有的原生 session；固定 workspace；已有助手历史但原生 session 已释放时拒绝冷恢复，不隐式新建空上下文 |
| build_query（必需） | 返回(query, effective UserTurn)；外部实现解释原有UserTurn，Native拥有原InteractiveInput转换；缺失方法拒绝，不回退Native。OpenCode 支持文本、可移植模板 persona、Skill 与 MCP；Native tools/rails/subagents、Team/计划执行明确拒绝；允许原Swarm单模型选择，未映射协议/参数和模型组拒绝 |
| process_message_stream_impl | 原 Runtime/Facade 拥有请求队列、producer 和唯一消费者；适配器先订阅再 prompt_async，仅映射匹配 session 的原生事件；助手正文不混入用户提示 |
| deliver_control_input_impl（必需） | 在原 producer 活动期间答复指定原生权限/问题 ID，不发第二 prompt、不增加消费者；使用既有 Web selected_options/custom_input 输入；重复、过期、跨 session 答复拒绝 |
| process_interrupt | OpenCode 仅 cancel，经官方 abort；不声称支持暂停、补充输入或原生恢复 |
| cleanup_session_adapter / cleanup | 宿主先取消并等待 producer；插件删除自己创建的原生 session 并关闭客户端，不 dispose 借用的 server。借用模式 abort/delete 失败保留所有者；自有服务清理失败亦须释放自有进程/目录；Swarm 历史保留 |

## 终态与历史

完成须有官方完整助手消息和 session.idle；EOF、超时或仅 idle 不能判成功。MessageAbortedError 映射已有 runtime_completion=cancelled，Facade 按此写取消历史。官方错误正文不直接外发，诊断只保留允许的错误类型名称。拒绝审批经官方 permission reply=reject，原生权限保护不关闭。

工具 invocation_status=completed 只表示调用结束。bash 的退出码来自 state.metadata.exit，只有实际 int 才接受，bool 不当成退出码。exit=0 对应 command_success=true，非零为 false，缺失为 null；task_acceptance 始终 unknown，不能据调用结束或模型文字判任务验收通过。字段经已有历史落盘/恢复通道透传，Web 对未知结果展示中性“调用已结束，命令结果未知”。请求级 success 表示本次调用完成，工具失败不自动等同请求异常；审批答复 ACK 也不是原始任务通过。

## 能力边界与兼容

仅外部会话且外部默认的Runtime不启动Native Runner/checkpointer/原生扩展宿主；混合模式Native资源沿原共享机制初始化；已有 ExtensionRegistry 的请求 Hook 仍执行并尊重拒绝。没有原生扩展宿主时此模式只提供 OpenCode 自有权限，不宣称等价于完整 Swarm Native 治理。Native 建议模型 fork、云记忆/自动记忆、技能演进等依赖原生能力的组合不在本试点支持范围；验收配置未启用这些可选能力。

旧 interrupt 模块、RootPermissionQueueError、PromptSuggestionForkRail 与 KVCacheAffinityConfig 保留兼容导出；纯协议谓词和原生实现加载分开。Gateway push 由已有服务器显式绑定 sender；Runtime-direct 无服务器时返回未发送，不隐式创建服务器。

完整 AgentServer/Gateway/WebSocket 启动、第二 Provider、运行中切换、Team、双实例交错、跨进程恢复、MCP/产品工具注入及无 Core 正常安装未验收。官方 question 事件虽有映射，真实问题交互未验收；真实验证范围为文本、命令、权限批准/拒绝、取消和清理。

## 关联与验证

实现决策见 feature F_20261029_2258_agent-adapter-boundary-validation。行为测试位于 tests/unit_tests/agentserver/test_opencode_direct_adapter.py；管理仓验证记录 AGENT_ADAPTER_NO_CORE_IMPLEMENTATION_20261029.md 保存真实入口、环境、失败过程和最终证据。模拟官方 HTTP 回归不作为真实 Provider 成功证据。


## 当前验证边界（2026-10-30）

完整Web Gateway/Front/Worker渠道已通过Native/OpenCode、两模型选择、审批、取消和历史恢复验证。单Agent规范模式通过上游deprecate_mode归一化，不另造模式表。无Core环境真实两模型执行通过且未导入Core。当前支持OpenAI兼容单模型启动快照；配置变化需服务拥有者刷新。仅热恢复经过验证，冷恢复、第二外部Provider、独立包/可选Core安装未交付。浏览器旧组件预览不作为渠道证据。


## N01～N04 装备接入边界（2026-10-30）

Third-party agents 设置只表示原路径的启停、安装和 CLI 配置，不改写会话 Provider。OpenCode 试点仍通过插件配置显式接入，不把此设置页的旧 Core-backed CLI 启停解释为直连服务绑定。模板 runtime.provider_name 与当前 OpenCode 必须一致；同 Provider 的非空专有 config、非可移植字段也明确拒绝，不能静默降级。配置错误在 prompt_async 前失败，默认 Native 行为保留。

沿用 Facade 的 reconcile_session_mcp、原资产服务及 session_metadata 保存装备。template/plugin_names/mcp 省略沿用、空值清除、非空替换；只有成功挂载并查询原生发现/连接状态后才保存。selectedSkills 与 UserTurn 的 skills_to_use 仅为本轮意图，不写会话白名单；已安装/启用的通用 Skill 及合法模板/插件资源仍可用，禁用项不可绕过。

模板 persona 的 Markdown 经官方 prompt_async.system 独立传递；用户输入保留 parts/text。Skill 复制完整正文、脚本与资源，保留 Swarm 元数据决定的名称/描述；对 Swarm 宽松头部只规范生成副本中的 YAML 发现头，不改原文件。包内 enabled_skills 空值表示不过滤，按声明名称过滤。同名冲突、越界/符号链接、未安装、不支持配置明确失败。归档、Git 和 Python 缓存不复制，总资源上限50MiB。

官方1.18.18 的 Skill/MCP 配置按目录/实例生效，不能给共享借用服务打会话级补丁。opencode.cli_path 模式为每个会话管理独立配置、数据及缓存，实际 project cwd 不变；装备变更只在空闲时重启自有服务，复用其数据库与 native session ID。配置600、目录700，凭据只经原 CredentialStore/占位符解析进入私有配置；不写聊天请求/日志。模型来自原 ModelCatalog，没有第二模型服务。URL模式仍可文本/模板；挂载 Skill/MCP 明确要求自有 CLI，绝不改共享 /config 或 dispose 借用服务。

MCP 支持原已连接 connector 的 stdio、http/sse/streamable-http 配置与已有凭据 headers/env；不支持逐 connector cwd 覆盖，未解析凭据/未连接/官方连接失败明确拒绝。远程 OAuth 浏览器授权和刷新未验证，不能宣称完整 OAuth 等价。插件仅转换声明的 Skill/MCP，不运行其 Python/Hook/Native Rails。仍保留官方运行时审批，接入安装检查不替代审批。

Runtime 和 Facade 继续拥有会话、Turn、生产者与历史。外部 adapter 声明 supports_native_plan_state=False，Facade 透传，普通 Code/Work 不再创建 Core Plan state；显式 Plan 拒绝，Native 默认True不变。唯一 SSE 读者对每个审批施加背压，原控制回执完成后才呈现下一项，避免并行工具审批覆盖宿主单交互门。超时使用非空错误消息，先 abort；迟到回复不可恢复已结束轮次。

关闭只处理自有 session、CLI 及其 MCP 子进程和私有目录。冷恢复/服务跨进程重建仍是 N06，不因保留同生命周期数据库就声明已完成。Code 文件快照/逐轮Diff/撤销、Team、Plan、Goal、完整 Native 治理不在本范围；未改主包 Core 依赖或外部源码。


2026-10-30最终收尾补充：真实审批超时暴露原协调器保留等待门，现消费已有runtime_completion并在流释放后按成功/失败/取消收尾，保留无终态的等待语义，不建新调度器。复用原chat.interrupt_result关闭权限卡，随后错误终态保持provider_timeout；最终Web同会话继续返回RECOVERED。受影响141、无Core34通过；带鉴权MCP拒绝、取消历史与继续闭合。模板清除只停止下发system并清空装备，不删除历史；实测仍可沿用旧标记，不声称模型遗忘。完整限制和证据以N01～N04实施验收记录为准，未发布。

## 会话项目目录

自有 CLI 首次按 Swarm project_dir 绑定，省略则用 opencode.directory；已有会话省略则沿用绑定，显式变更拒绝。目录必须绝对且存在，规范化后比较。借用 URL 保留固定配置边界。装备解析、HTTP/SSE、CLI cwd 和关闭请求使用同一会话目录；默认目录不覆盖用户 UI 项目选择。修复证据：B_20261030_1455_opencode-session-workspace-binding。

## 全局权限档位与 Provider 生效状态

继续使用原全局 permissions 配置与 reload_agent_config(config_base, env_overrides, target_session_id, reload_scopes)。会话 desired/effective 只是投影，不形成第二个权限配置源。插件可选实现 PermissionAwareAdapter.runtime_permission_status，提供 supported_profiles、update_timing、desired_profile、effective_profile（未确认 null）和 not_started/pending/applied/failed/unsupported；工厂可声明 permission_profiles 供原配置目录与选择器读取。未实现可选接口的 Native 保持原生命周期/界面，不强制迁移。

OpenCode 自有 CLI 支持 default/full_access，Automatic 不降级、不放行，明确不支持。局部初始化配置缺少 permissions 时读取原全局配置；显式完整配置优先。Default 映射原生 ask，Full Access 映射 allow；question 保留用户提问，task 因未支持子 Agent 而 deny，skill 仍仅允许已安装/启用集合。此档位映射不宣称等价于完整 Native 文件治理/自动审批。

原有全局保存广播各渠道；执行中/等待审批只更新 desired，已有审批仍需原控制回复或取消，不能因选择 Full Access 自动回答。空闲时应用，并在下一 prompt 前设生效检查；初始化、装备刷新、权限刷新和关闭协调自有配置锁，不新建 Turn 队列。更新通过官方私有服务配置与会话 PATCH/GET，1.18.18 追加规则按原列表+新规则核对；相同尾规则不重复追加，超过4096条拒绝继续。自有服务配置变化重启保留数据库/原 session ID，以清除原生记忆授权；不碰借用服务器全局配置。读回失败 effective=null、failed，后续执行必须重新核验成功。

Skill/MCP 更新沿用 desired 档位并重新验证，不能退回固定 ask。借用 URL 不承诺权限切换（supported_profiles=[]，effective 未知）；Full Access/Automatic 拒绝，不把共享服务改成 allow。通过原 Worker runtime snapshot 随 session.get_metadata 返回当前状态，不落入历史元数据作为可恢复事实。UI 复用原权限下拉及档位名称，按插件能力展示选项，不显示Applied/Pending等状态标签或生效状态悬浮文案；新会话/离线/旧数据未知不冒充已生效，执行中或待生效才继续查询，稳定空闲态停止轮询。

验证与边界见 B_20261030_1607_opencode-permission-profiles。第二 Provider 尚未接入验证；后续需实现上述小接口及原生映射/读回，不在宿主增加 Provider if/else 或专有审批模式。

## 原生连接错误投影

session.error及assistant message.updated.error复用chat.error与原历史/渠道。原生泛化短语unknown certificate verification error映射provider_tls_connection_failed，说明握手或证书验证阶段失败，不能据此判定证书不可信；明确证书错误短语仍映射provider_tls_verification_failed。仅输出固定安全说明，保留原生错误类型；未知原文不直接透传。不得从UnknownError推断具体证书过期/网络故障，不自动重试或关闭验证。取消与失败终态保持分离。验证及未闭合故障见B_20261030_1646_opencode-tls-error-diagnostics。

## 执行引擎公开目录与控件

config.get 的 execution_provider_catalog 复用 AgentAdapter entry point，公开 id/label/available/modes/reason，不包含凭据或异常原文。工厂声明 display_name 与 supported_modes 才作为用户入口；缺失元数据的内部探针不展示，重复注册或导入失败明确不可用。目录可用仅代表插件装载与模式声明，不能替代运行时模型、权限、工作区与协议检查。旧 availability/permission_profiles 读者保持兼容。

复用主工程 ExecutionPicker 呈现，输入工具栏权限后、模型前，仅一个执行引擎菜单。新会话可选、既有绑定只读；选项消失或加载失败不静默切换。模型服务继续走原模型选择。sessionStore 通用 setter 接受非空插件ID以服务创建/恢复，选择校验归UI及原后端，不把恢复入口限制为草稿。


## 可选 Native 安装和桌面构建边界（2026-10-30）

本轮保持同一 Swarm UI、Runtime、Gateway、历史与审批通道。基础 Python 安装不再强制安装 Core；`uv sync` 默认仍包含固定版本 Native，`pip install '.[native]'` 显式安装完整组合。外部组合使用 `uv sync --locked --no-default-groups --extra dev --no-editable`，Core 固定 SHA 未升级。内置 OpenCode 通过正式 entry point 发现，不需要验证用的 probe 包或 PYTHONPATH。

Linux 测试包：`bash scripts/build-electron-linux.sh external`。打包前先构建现有前端，再用 PyInstaller 冻结后端并组装官方 Electron；产物为 `dist/workswarm-external-linux-amd64.tar.gz` 与 `.deb`，附 SHA256。Linux HTTP 页面使用绝对资源根路径，支持聊天地址刷新。源码工作区与配置、模型密钥、OpenCode CLI 均不装入包；使用者需正常安装 OpenCode，并通过 PATH 自动发现或显式 CLI 配置接入，在原 Swarm 模型设置配置兼容模型。

Windows 入口：`scripts/build-electron-exe.ps1 -BuildProfile external -NoSign -SkipInstaller`；macOS 入口：`JIUWENSWARM_BUILD_PROFILE=external bash scripts/build-electron-exe.sh --test`。默认 Native 入口保留；这两个外部组合尚未在对应系统实际构建或验收，不能作为可下载安装包声明。签名、公证和正式发布另行完成。

外部组合目前面向 OpenCode 单 Agent/Code；Native Team、记忆/推荐/设计器及 OpenAI 账号 OAuth 等 Core 专属路径不可据此宣称可用。原生路径不可用时明确拒绝，不把历史会话自动改绑 OpenCode。设置页复用原模型目录，连接测试当前仅支持 OpenAI 兼容端点且保持 TLS 校验。插件基础 Hook 在现有 Registry 内执行；高级 Core 回调选项明确不支持，不静默丢弃。独立 Provider 分包、第二 Provider、全量功能对等和冷恢复仍未交付。


## CLI 自动发现与 HTTP/SSE 边界（2026-10-30 候选）

选择顺序：显式 `opencode.cli_path` → 显式 `opencode.url` → PATH → 当前用户的安装候选目录。显式 CLI 无效时拒绝，不回退到另一程序或 URL；显式 URL 不启动本机服务。自动查找不会执行 shell profile、安装/升级 CLI 或采用项目中的相对 PATH 条目。未发现 CLI 时提示安装或配置，而不再误报 URL 格式错误。

OpenCode 候选包含当前用户 `~/.opencode/bin`、`~/.local/bin`；macOS 补充 `/opt/homebrew/bin` 与 `/usr/local/bin`，Windows 补充用户 Scoop shims 和 LOCALAPPDATA 下 WinGet Links。Windows 仅直接启动原生可执行文件，遇到 cmd/bat 包装器明确要求配置原生程序路径；不自动执行 shell 包装。Windows/macOS 只有路径规则测试，目标系统实机验收尚未完成。

自有服务未设置 directory 时使用 Swarm 原默认项目目录，实际会话优先使用聊天所选项目并保持绑定；借用 URL 仍必须明确配置 directory。模型、权限、审批与历史继续使用原 Swarm 流程，不增加 UI 或用户配置写入。

`opencode_transport.py` 仅负责 HTTP JSON、健康检查和 SSE 分帧；`opencode_service.py` 管理自有进程/私有目录；适配器继续映射原生事件；Runtime 仍拥有调度与终态。共享 CLI 查找函数不掌握 Provider 注册、模型或生命周期。暂不依赖过时的官方 Python SDK，也不增加 Node 桥；新版 SDK 可兼容后仅替换传输边界。



## 启动探测与会话初始化（2026-10-30 候选）

继续复用原 AgentAdapter prepare/cleanup、Runtime 调度、权限答复及历史错误通道。自有 CLI 启动健康探测每次最多 0.5 秒，总预算仍为 40 秒；避免启动初期一个连接阻塞原 15 秒探测。只有创建原生会话的 POST /session 使用独立总预算：`opencode.session_init_timeout` 默认 120 秒，可配置大于 0 且不超过 600 的有限秒数；其余普通 API 保持 15 秒。该预算不同于 turn_timeout。初始化失败或取消走原清理，不自动重试创建/提示等写请求。

HTTP/初始化错误输出固定阶段、错误类型或 HTTP 状态，日志保留耗时，不输出响应正文、地址或凭据；ReadTimeout 不再在原错误通道变成空文字。此轮没有新增 UI 状态、模型配置、共享进程池或调度器，TLS 验证不变。

带原 SQL2Java 插件的隔离副本现在可准备会话，但仍需约 27～31 秒；插件导出约束错误独立存在，不能宣称插件功能通过。仅在诊断中通过官方 npm_config_cache 复用下载缓存，冷/第二会话约 30/9 秒，未成为产品默认。后续只评估同用户下载缓存；配置、凭据、权限、MCP、会话数据库继续隔离，不共享整个 HOME/XDG，不自行重写官方依赖安装流程。

按锁非 editable 免 Core 与冻结后端均经原 Runtime 完成真实读取、审批、exit7/历史和清理。免 Core 97 项、带固定 Core 124 项回归通过（重叠不相加）。Linux新候选包独立输出 startup-fix-dist，系统旧安装未自动升级；本轮没有桌面点击复验，Windows/macOS实机仍待验收。
