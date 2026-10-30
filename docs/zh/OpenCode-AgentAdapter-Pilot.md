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

OpenCode 候选包含当前用户 `~/.opencode/bin`、`~/.local/bin`；macOS 补充 `/opt/homebrew/bin` 与 `/usr/local/bin`，Windows 补充用户 Scoop shims 和 LOCALAPPDATA 下 WinGet Links。Windows 仅直接启动原生可执行文件，遇到 cmd/bat 包装器明确要求配置原生程序路径；不自动执行 shell 包装。Windows/macOS 只有路径规则测试，目标系统实机验收尚未完成。

自有服务未设置 directory 时使用 Swarm 原默认项目目录，实际会话优先使用聊天所选项目并保持绑定；借用 URL 仍必须明确配置 directory。模型、权限、审批与历史继续使用原 Swarm 流程，不增加 UI 或用户配置写入。

`opencode_transport.py` 仅负责 HTTP JSON、健康检查和 SSE 分帧；`opencode_service.py` 管理自有进程/私有目录；适配器继续映射原生事件；Runtime 仍拥有调度与终态。共享 CLI 查找函数不掌握 Provider 注册、模型或生命周期。暂不依赖过时的官方 Python SDK，也不增加 Node 桥；新版 SDK 可兼容后仅替换传输边界。

Linux 可通过 `assemble-electron-linux.py --profile external --dist-dir <独立输出目录>` 组装新包，避免覆盖仍被进程读取的旧目录。新包验收与系统安装升级分别记录；生成新产物不会自动更新已经安装的旧版应用。


## 启动探测与会话初始化（2026-10-30 候选）

继续复用原 AgentAdapter prepare/cleanup、Runtime 调度、权限答复及历史错误通道。自有 CLI 启动健康探测每次最多 0.5 秒，总预算仍为 40 秒；避免启动初期一个连接阻塞原 15 秒探测。只有创建原生会话的 POST /session 使用独立总预算：`opencode.session_init_timeout` 默认 120 秒，可配置大于 0 且不超过 600 的有限秒数；其余普通 API 保持 15 秒。该预算不同于 turn_timeout。初始化失败或取消走原清理，不自动重试创建/提示等写请求。

HTTP/初始化错误输出固定阶段、错误类型或 HTTP 状态，日志保留耗时，不输出响应正文、地址或凭据；ReadTimeout 不再在原错误通道变成空文字。此轮没有新增 UI 状态、模型配置、共享进程池或调度器，TLS 验证不变。

带原 SQL2Java 插件的隔离副本现在可准备会话，但仍需约 27～31 秒；插件导出约束错误独立存在，不能宣称插件功能通过。仅在诊断中通过官方 npm_config_cache 复用下载缓存，冷/第二会话约 30/9 秒，未成为产品默认。后续只评估同用户下载缓存；配置、凭据、权限、MCP、会话数据库继续隔离，不共享整个 HOME/XDG，不自行重写官方依赖安装流程。

按锁非 editable 免 Core 与冻结后端均经原 Runtime 完成真实读取、审批、exit7/历史和清理。免 Core 97 项、带固定 Core 124 项回归通过（重叠不相加）。Linux新候选包独立输出 startup-fix-dist，系统旧安装未自动升级；本轮没有桌面点击复验，Windows/macOS实机仍待验收。
