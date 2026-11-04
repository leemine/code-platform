# OpenCode AgentAdapter 实验接入

适用于未发布的隔离候选。默认仍使用 agent-core；OpenCode 通过 AgentAdapter 直连官方 HTTP/SSE，主包依赖并未去掉 Core。

## 界面选择

新建单 Agent 会话，在原聊天输入区的 Provider 下拉中选择 OpenCode，再使用旁边原有模型菜单选择 Swarm 已配置的模型。已有会话保持 Provider 绑定，需要换 Provider 时新建会话；切换和刷新会恢复原绑定。没有独立模型设置表单。

插件须正常安装并注册 `jiuwenswarm.agent_adapters` 的 `opencode-direct` 入口。目前只有本任务实验注册包，独立插件尚未发布。借用官方服务的地址、固定工作目录、认证等由插件配置；远程连接要求 HTTPS。服务所有者使用 `opencode_models.build_server_model_config()` 从正常 Swarm ModelCatalog 生成私有官方启动配置，保留原生权限保护；片段含密钥，不能发送前端或写入日志/Git。

本轮采用服务启动快照，支持已映射的 OpenAI 兼容单模型。模型配置变化后需刷新 OpenCode 服务；过期快照、OpenAIAccount、模型组和未映射参数明确失败，不回退 Native。旧显式 `opencode.model` 仍保留兼容。模型菜单复用并不表示服务配置已经热同步，也不表示全部模型协议都已支持。

`JIUWENSWARM_AGENT_SDK` 只保留旧默认兼容。活跃会话保持原连接；空会话首次执行使用当时配置，配置版本尚未持久化。已释放原生 session 的历史拒绝冷恢复。适配器清理自有 session，不关闭借用服务。

## 已验证与限制

完整真实 Swarm 页面→Gateway→Front→Worker/Runtime→OpenCode 已通过：两模型选择、文本回复、原审批允许/拒绝、exit7 失败历史及UI、待审批取消后继续、默认 Native 回复，以及切回/刷新历史绑定。无 Core 实验环境另通过两模型真实执行且无 Core 模块导入。仅组件预览不计渠道验收。

仍未提交/发布。Team、Native 产品工具注入、第二外部 Provider、跨进程冷恢复、独立插件安装和正常可选 Core 依赖未交付。权限映射不代表完整 Native 治理；调用结束、命令退出成功、任务验收通过分别判断，缺失退出码仍未知。


## 模板、Skill 和 MCP（N01～N04 候选）

原聊天的 Experts、Skills、Extensions 入口可继续使用；不新增前端页面或第二模型配置。Third-party agents 设置不指定具体会话 Provider；此直连试点的连接配置仍归插件，不能把旧 Core-backed CLI 设置当作直连服务配置。

普通模板 persona 使用 OpenCode 原生 system；选择与会话 Provider 冲突的 runtime、专有 config 或 Native tools/rails/subagents 时明确报错。模板/插件/MCP 省略沿用、显式空值清除，失败不覆盖上次装备；Skill chip 只表示本轮使用意图，全局启停仍由原 Skills 管理决定。

需要 Skill/MCP 时，在已有插件连接配置中设置 `opencode.cli_path` 为正常安装的官方 CLI 路径，并保留绝对 `opencode.directory`。适配器为会话启动私有官方服务，使用原 Swarm 模型目录和实际项目 cwd；完整 Skill 资源及现有 connector 配置写入自有私有目录，关闭时清理。MCP 必须已通过原资产/连接授权；运行时按所选权限档位执行。不要同时把共享 URL 的配置当作会话专有配置。

只设置 `opencode.url` 的旧借用模式继续支持文本和普通模板；Skill/MCP 会要求自有 CLI，避免修改其他会话共享服务。插件只支持其可移植 Skill/MCP 声明，非整包 Hook/工具兼容。远程 OAuth 刷新、Code Diff/撤销、冷恢复、第二 Provider 和独立分发仍未交付。模型/装备变化可重启自有服务，首次启动及资源准备有额外延迟。

自有 CLI 模式下，Swarm 新会话选择的项目目录优先于 opencode.directory；后者只作未选项目时的回退。已有会话保持绑定，省略目录仍沿用原目录，不能中途切换项目。借用 URL 模式仍限于配置目录。

## 权限档位（候选）

自有 CLI 复用聊天原权限下拉：Default 由 OpenCode 原生询问，Full Access 允许执行且仍保留用户问题交互；不支持 Automatic。设置范围仍为全局，已有会话在当前轮结束后应用，等待中的审批不会自动通过。界面保留Swarm原有档位名称，不增加状态标签或生效状态悬浮文案；Provider原生读回和执行前校验仍在后台完成。插件/Skill/MCP 的原安装与启用检查仍保留，Full Access 不等同完整 Native 治理。借用 URL 不支持档位切换，不改共享服务器配置。

## TLS连接诊断

原生泛化的“unknown certificate verification error”通过原聊天/历史提示TLS连接在握手或证书验证阶段失败，不能据此认定证书不可信；明确证书错误仍显示证书验证提示。未知错误正文不透传，TLS校验保持开启，不自动重试。无HTTP_PROXY也可能经过透明代理；排查应核对实际路由。模型域名直连属于本机网络配置，不是插件默认行为，也不改变执行Provider绑定。


新会话的“执行引擎”沿用输入栏原有芯片菜单，位于权限与模型之间。选项来自已安装插件的公开目录；已有会话保持绑定。安装可用不等于已登录或模型连通，运行前仍会检查。


## 可选 Native 与桌面发行组合（2026-10-30 候选）

本轮保持同一 Swarm UI、Runtime、Gateway、历史与审批通道。基础 Python 安装不再强制安装 Core；`uv sync` 默认仍包含固定版本 Native，`pip install '.[native]'` 显式安装完整组合。外部组合使用 `uv sync --locked --no-default-groups --extra dev --no-editable`，Core 固定 SHA 未升级。内置 OpenCode 通过正式 entry point 发现，不需要验证用的 probe 包或 PYTHONPATH。

Linux 测试包：`bash scripts/build-electron-linux.sh external`。打包前先构建现有前端，再用 PyInstaller 冻结后端并组装官方 Electron；产物为 `dist/workswarm-external-linux-amd64.tar.gz` 与 `.deb`，附 SHA256。Linux HTTP 页面使用绝对资源根路径，支持聊天地址刷新。源码工作区与配置、模型密钥、OpenCode CLI 均不装入包；使用者需正常安装 OpenCode，并通过 PATH 自动发现或显式 CLI 配置接入，在原 Swarm 模型设置配置兼容模型。

Windows 入口：`scripts/build-electron-exe.ps1 -BuildProfile external -NoSign -SkipInstaller`；macOS 入口：`JIUWENSWARM_BUILD_PROFILE=external bash scripts/build-electron-exe.sh --test`。默认 Native 入口保留；这两个外部组合尚未在对应系统实际构建或验收，不能作为可下载安装包声明。签名、公证和正式发布另行完成。

外部组合目前面向 OpenCode 单 Agent/Code；Native Team、记忆/推荐/设计器及 OpenAI 账号 OAuth 等 Core 专属路径不可据此宣称可用。原生路径不可用时明确拒绝，不把历史会话自动改绑 OpenCode。设置页复用原模型目录，连接测试当前仅支持 OpenAI 兼容端点且保持 TLS 校验。插件基础 Hook 在现有 Registry 内执行；高级 Core 回调选项明确不支持，不静默丢弃。独立 Provider 分包、第二 Provider、全量功能对等和冷恢复仍未交付。


## CLI 自动发现与 HTTP/SSE 边界（2026-10-30 候选）

选择顺序：显式 `opencode.cli_path` → 显式 `opencode.url` → PATH → 当前用户的安装候选目录。显式 CLI 无效时拒绝，不回退到另一程序或 URL；显式 URL 不启动本机服务。自动查找不会执行 shell profile、安装/升级 CLI 或采用项目中的相对 PATH 条目。未发现 CLI 时提示安装或配置，而不再误报 URL 格式错误。

OpenCode 候选包含当前用户 `~/.opencode/bin`、`~/.local/bin`；macOS 补充 `/opt/homebrew/bin` 与 `/usr/local/bin`，Windows 补充用户 Scoop shims 和 LOCALAPPDATA 下 WinGet Links。Windows 自动发现遇到 `.cmd` / `.bat` / `.ps1` 时继续查找原生程序，不执行脚本。npm 安装补查绝对 PATH 目录、`NPM_CONFIG_PREFIX`（兼容小写环境变量）和 `%APPDATA%/npm` 下的 `node_modules/opencode-ai/bin/opencode.exe`；直接复用官方 postinstall 已选出的原生文件，不自行选择 CPU 变体或读取二进制正文。显式配置脚本或无效路径仍报错，不静默改选；缺少原生文件时提示正常安装或配置路径。自定义 npm prefix 需在 PATH 或对应环境变量中可见；不扫描项目依赖或任意磁盘目录。Windows/macOS 路径规则有确定性测试，目标系统真实聊天验收仍待完成。

自有服务未设置 directory 时使用 Swarm 原默认项目目录，实际会话优先使用聊天所选项目并保持绑定；借用 URL 仍必须明确配置 directory。模型、权限、审批与历史继续使用原 Swarm 流程，不增加 UI 或用户配置写入。

`opencode_transport.py` 仅负责 HTTP JSON、健康检查和 SSE 分帧；`opencode_service.py` 管理自有进程/私有目录；适配器继续映射原生事件；Runtime 仍拥有调度与终态。共享 CLI 查找函数不掌握 Provider 注册、模型或生命周期。暂不依赖过时的官方 Python SDK，也不增加 Node 桥；新版 SDK 可兼容后仅替换传输边界。

Linux 可通过 `assemble-electron-linux.py --profile external --dist-dir <独立输出目录>` 组装新包，避免覆盖仍被进程读取的旧目录。新包验收与系统安装升级分别记录；生成新产物不会自动更新已经安装的旧版应用。


## 启动探测与会话初始化（2026-10-30 候选）

继续复用原 AgentAdapter prepare/cleanup、Runtime 调度、权限答复及历史错误通道。自有 CLI 启动健康探测每次最多 0.5 秒，总预算仍为 40 秒；避免启动初期一个连接阻塞原 15 秒探测。只有创建原生会话的 POST /session 使用独立总预算：`opencode.session_init_timeout` 默认 120 秒，可配置大于 0 且不超过 600 的有限秒数；其余普通 API 保持 15 秒。该预算不同于 turn_timeout。初始化失败或取消走原清理，不自动重试创建/提示等写请求。

HTTP/初始化错误输出固定阶段、错误类型或 HTTP 状态，日志保留耗时，不输出响应正文、地址或凭据；ReadTimeout 不再在原错误通道变成空文字。此轮没有新增 UI 状态、模型配置、共享进程池或调度器，TLS 验证不变。

带原 SQL2Java 插件的隔离副本现在可准备会话，但仍需约 27～31 秒；插件导出约束错误独立存在，不能宣称插件功能通过。仅在诊断中通过官方 npm_config_cache 复用下载缓存，冷/第二会话约 30/9 秒，未成为产品默认。后续只评估同用户下载缓存；配置、凭据、权限、MCP、会话数据库继续隔离，不共享整个 HOME/XDG，不自行重写官方依赖安装流程。

按锁非 editable 免 Core 与冻结后端均经原 Runtime 完成真实读取、审批、exit7/历史和清理。免 Core 97 项、带固定 Core 124 项回归通过（重叠不相加）。Linux新候选包独立输出 startup-fix-dist，系统旧安装未自动升级；本轮没有桌面点击复验，Windows/macOS实机仍待验收。

## Codex 主 Agent 候选

新增 `uv sync --locked --no-default-groups --extra codex-direct` 安装组合，使用官方 Codex Python SDK/CLI 0.163.0，不安装 agent-core。沿用 Third-party Agents 中 Codex 的启用/显式路径；未指定路径时由官方 SDK 使用配套运行时。新聊天或 Code 会话在原执行引擎菜单选择 Codex，已有会话不切换 Provider。

模型仍选择 Swarm 模型服务中的单模型，当前需要 OpenAI Responses 兼容端点和 TLS 校验。不会复用个人 Codex 默认模型/登录状态；OpenAIAccount、模型组及未映射请求参数明确不支持。默认权限及 Full Access 映射并核对原生策略，审批/拒绝/取消沿用原控件；缺失退出码保持未知，权限拒绝不显示成功。

这是未发布候选：Linux真实Runtime、Code命令及原审批已验证；Codex装备、冷恢复、完整用量、Claude及Windows/macOS/桌面安装包仍待实现或验证。Web刷新重放与Front配置导入边界已在收尾中修正；活动请求和审批仍通过原恢复通道。历史没有结果的工具调用保留未知，不推断成功。旧OpenCode及Native流程继续保留。

Codex不按SDK/CLI精确版本禁用执行引擎。官方SDK负责CLI选择与兼容，`codex-direct`可选依赖不固定版本；按锁安装及桌面默认下载目前验证为0.163.0。显式CLI路径错误不回退，审批接口或原生权限策略不兼容时明确失败。上游Third-party Agents的较旧CLI警告与桌面托管安装清单校验保留；默认下载版本不等同自定义CLI版本白名单。Linux托管安装路径与Gateway清单定位已补齐，Windows/macOS和新安装包仍待真机验收。


## 工具结果与 Codex 证书配置（2026-10-31 候选）

工具列表“完成”表示调用已返回，不代表命令退出码0或任务验收通过。Bash 缺少原生退出码时，详情注明“退出码未提供”；Read 等非命令工具不显示命令结果未知。原生工具错误和明确非零退出码仍显示失败；历史调用尚无结果时保持未知。旧 Read 历史兼容，不改写历史文件。

Codex 不再因 Swarm 模型保存 verify_ssl:false 而在配置阶段拒绝；该 HTTP-client 选项不控制官方 CLI 的 TLS。实际请求仍由官方 SDK/CLI 校验证书，不会关闭校验或自动改写模型配置。需要私有 CA 时使用官方受支持的信任配置。此次仅源码候选修复，不自动升级已经安装的桌面版。


## 外部执行器超时（2026-11-02 候选）

长工具执行不等于模型请求超时。OpenCode 不再默认限制整轮 120 秒；opencode.turn_timeout 只有显式正有限值才限制整轮，未设置/null 表示不设整轮限时。初始化和 API 请求仍有独立限制。模型 timeout 秒数继续转换为原生请求 timeout 毫秒；自有服务可以通过 opencode.header_timeout_ms、chunk_timeout_ms 配置响应头/流块等待，未设置则沿官方默认。借用服务由其所有者配置，不从聊天改写。

Claude 的模型 timeout 映射 API_TIMEOUT_MS，不再限制整轮 180 秒。Third-party Agents 的 YAML Claude 条目可设置 stream_first_byte_timeout_ms、stream_idle_timeout_ms；Codex 条目可设置 stream_idle_timeout_ms。均为正整数毫秒，不新增界面控件，不把请求/首字节/流空闲当成同一个参数。保存原有 Agent 卡片保留这些字段。未收到原生终态或 SDK 关闭未确认时，续聊会保留安全阻断，需要先完成原有关闭/恢复处理，不能靠创建第二执行者绕过。

源码候选验证不表示已安装桌面程序已更新，详见本次故障记录。


当前验证的Claude CLI2.1.274在自定义模型端点路径不启用独立首字节期限，参数透传不代表生效；原生请求超时仍有效。300秒流停滞在独立监督下已正常关闭并退出0；旧143原因未确定，不记为已证实的适配缺陷。


## Codex 大工具输出

Codex 命令正文在 Swarm 中最多显示60000个字符，子智能体命令活动摘要最多2000个字符，均包含明确的截断提示。短输出保持原样；现有 content/result 字段继续提供相同的有界内容。截断只影响 Swarm 的显示和历史，不改写官方工具返回给模型的内容，不触发重新执行。原生退出码、命令成功/失败/未知与任务验收状态保持各自含义。

截断诊断位于 provider.codex，区分 SDK 已返回量和显示量；SDK 本身可能已经截断，不能据此推断命令全部输出。Swarm 历史不额外保存被裁去的全文，也不伪造文件下载链接。原发送保护继续有效；其它 Provider 和其它事件类型的输出限制须分别核对。此项为本地修复候选，尚未发布桌面安装包。


## Claude/OpenCode 工具输出保护

Claude 与 OpenCode 的工具返回现在沿用同样的 Swarm 显示边界：正文60000字符，Claude子工具活动摘要2000字符，均包含截断提示。content/result继续兼容，原生错误标志、退出码与未知状态保持，不修改外部工具给模型的内容。

OpenCode普通metadata完整保留；超大metadata按字段整体省略并在provider.opencode中标记，优先保留原生退出码、截断事实及完整outputPath，不把路径裁成另一条路径，不自动读取或复制文件。已有原生截断/文件引用不被当作Swarm新生成的产物。该保护没有新增宿主执行流程；其它事件类型的容量另行核对。当前仍是本地候选，Claude真实调用因现有模型接口429/1113待复验，不代表桌面已发布。


## P1 执行输入与装备职责

宿主沿原聊天 Facade 准备有效模型、目录与必要的历史恢复资格；Provider 继续校验原生协议和会话绑定，并负责官方 SDK/API 转换。原模型设置、执行引擎下拉、已有会话绑定与 Native 默认路径不变。OpenCode 的模板/Skill/MCP 仍通过原资产服务；成功、当前且未取消的装载由宿主保存装备快照，部分失败必须重新核验。

三家的主动上下文查询与手动压缩接口仍明确不支持，不显示虚假零用量；Codex被动原生统计见下方新增章节。OpenCode 现有 persona/用户提问与 task=deny 保留；Claude/Codex 主 Agent 角色文本见 P2 小节。本轮不新增设置页面或第二套执行流程。实施和验收限制见 F_20261104_1030_provider-input-ownership；未提交发布，不代表已安装桌面版更新。

## Codex 原生用量观测

Codex候选现沿原底部统计入口显示原生主线程累计输入、输出、缓存输入/写入、推理输出和总Tokens；只展示实际返回且口径明确的字段。窗口容量单独显示，尚不展示推测的上下文占用率或缓存命中率。未知指标隐藏，原生明确返回的0保留。取消/失败后续聊和恢复的首轮没有可靠基线时，不显示猜算的本轮消耗；累计快照不重复相加。

沿用原聊天、历史与控件，无额外压缩、页面或执行流程。Native保留原功能，Claude/OpenCode续接状态见下一节。详见F_20261104_1230_codex-native-usage-observation；本地未发布，不表示已安装桌面版更新。


## Claude / OpenCode 原生用量与 Tokens

三个外部执行器的单行统计标签显示 Tokens，缺失指标隐藏，复用原底部控件与历史。Claude从官方model_usage读取包括子Agent的原生模型计数，不叠加主循环usage；原生CLI版本可能影响恢复后的累计范围，因此显示“原生用量”，不把它称为完整Swarm会话总量，也不合成未返回的总Tokens。OpenCode只按已完成消息身份去重，忽略重复步骤视图；上游补0来源不明或任一消息缺计数时隐藏该项。原生输入、输出、缓存分类保持各自语义，不反推占用率或命中率。

OpenCode真实两轮、原Worker重启后同原生会话续聊、数据库对账及UI整页刷新已验证。Claude当前原模型服务HTTP429，映射确定性回归通过、真实渠道待验证。没有新执行/审批/压缩流程；Native原统计保留。本地候选未提交发布，安装包未更新。详见F_20261104_1230_codex-native-usage-observation。

### beta5 测试版发布范围（2026-11-04）

beta5 整理三家工具输出保护、P1 输入/装备职责及原生 Tokens 只读观测；复用现有聊天、历史和统计控件。三平台构建从同一合入提交执行，安装包不包含用户模型配置。Claude 原服务 HTTP 429 的真实验收仍待完成；Windows 未签名、macOS arm64 未签名/公证，构建成功不代表平台实机聊天验收通过。版本与锁仅更新本工程版本，外部 SDK/Core 固定来源不变。详见 F_20261104_1430_provider-beta5-release。

## 主 Agent 角色模板（P2 候选）

配置调用方可以在原 `session.create` 的 `params` 中为单 Agent 会话同时传入执行 Provider 和已安装的角色模板 ID。例如在原工作区、模式和 `create_token` 参数之外附加：

```json
{"execution_provider": "codex-direct", "role_template_ref": "architecture-reviewer"}
```

已注册的单 Agent Provider 声明并实现主角色指令能力后即可使用此入口。随项目提供的 `claude-direct`、`codex-direct`、`opencode-direct` 已接入。使用现有专家模板目录中的纯 persona：UTF-8 Markdown 总预算 8 KiB。模板可省略运行时，或声明与所选 Provider 一致且无专有配置的运行时。有实际 Skill、MCP、子 Agent 等额外声明的模板无法作为此入口的角色模板。角色指令会传给所选 Provider，应避免在模板中放入密钥。

在现有单 Agent 会话的专家选择器选另一个兼容专家，下一轮会用新专家继续对话。Provider 和原生会话保持绑定。通过原入口编辑同一模板后，下一轮读取新版角色正文。切换请求经 Provider 接受后保存，刷新页面或正常重启 Worker 后沿用已确认的选择。未安装或不兼容的选择会被拒绝，仍保留上一次确认的专家。OpenCode 原有完整装备继续由已有入口处理。使用 `role_template_ref` 创建的会话可选择纯角色模板，暂不支持通用会话分叉。

Codex 在角色更新、清除或 Worker 恢复原线程时，通过原生接口更新角色指令。同一连接中已确认且正文不变时复用。Swarm 沿用原会话装备保存专家 ID。

Claude Code 可切换角色路径要求实际 CLI 支持 `--system-prompt-snapshot off`，以便恢复会话后应用本轮角色。此配置会重建系统提示词，可能影响原生提示词缓存。
