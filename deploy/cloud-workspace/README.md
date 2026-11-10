# 独立角色候选构建

本目录为后台候选构建入口，不是现网部署脚本。`account`、`gateway`、`agentserver` 三个 Docker target 共享同一 wheel 和按锁依赖层，分别使用独立账号 HTTP、原 Gateway、原 AgentServer 入口。账号角色目前共享完整依赖层，不声称已裁剪为最小依赖镜像。

## 构建约束

当前基镜像固定为 CPython 3.13.15 / Debian bookworm / Linux amd64。构建用解释器必须与其 ABI 匹配；不要将其他 Python 版本的 venv 直接复制进去。元戎配置中的 runtime、SDK 与容器启动方式仍需在独立资源池实测，不因手动 Docker 启动成功便视为已兼容。

在任务专属目录用 `uv venv --relocatable --python <匹配解释器> deps` 创建空环境，再以 `UV_PROJECT_ENVIRONMENT=<deps绝对路径>` 执行 `uv sync --frozen --no-dev --extra native --no-editable --no-install-project`。离线缓存齐全时加 `--offline`。不得复制日常开发 venv、引入本地 Core editable 或改写锁文件来通过构建。

从 Git 文件清单和本任务未提交源码建立新的干净源码快照，在快照中执行 `uv build --wheel`；不要复用工作区 `build/`、egg-info 或旧 wheel。已发现 setuptools 旧缓存会把删除的 `cloud_workspace/__main__.py`、`yuanrong.py` 重新打包，必须检查这两项缺席，并逐文件比对 wheel 与候选源码。

构建上下文仅包括 `deps/`、`dist/*.whl`、本目录 Dockerfile/verify_dependencies.py、原 `uv.lock` 和生成的 `candidate.json`。将 `context.dockerignore` 复制为上下文 `.dockerignore`。清单包含 `base_sha`、未提交候选说明、`lock_sha256`、`wheel_sha256`、`source_sha256`（wheel 内源码路径到 SHA256 的映射）。不得将账号库、私有配置、TLS 私钥、用户目录或整个源码工作区放入构建上下文。

分别执行 `docker build --network=none --target <角色> -t <专属候选标签> <上下文>`。安装前检查 wheel 摘要，安装后校验源码、所有已安装包版本、VCS 仓库/提交及实际导入路径；再对实际运行的各角色执行 `uv pip check --python /opt/venv/bin/python`。基础镜像、wheel、锁文件和三角色镜像 ID 均需留档，不能仅记录分支名。

## 运行边界

- 账号：`--account-auth-file` 指向独立 0600 配置；非回环监听必须提供 TLS。仅该角色挂载账号数据库。
- Gateway：原入口加 `CODE_PLATFORM_CLOUD_CONFIG`；原 AgentOS Router 与插件的 endpoint/URN/namespace 必须一致。只挂载所需账号服务地址/CA、环境控制状态和受管工作区，不挂账号密码库或 TLS 服务端私钥。
- AgentServer：平台只声明本账号 `/data` 和本代只读 `/run/jiuwenswarm`；实际元戎还会注入 `/home/agentos` 工作区别名及共享运行时日志目录，完整挂载隔离需另行验收；镜像内 `agentos` 用户固定 UID/GID 1000:1000，配置传入用户名而非 `UID:GID`（元戎会拼接 `/home/<user>`）；Gateway 核验用户名对应当前 UID/GID，云角色缺少凭据拒绝授权。保持原 Runtime/协议。
- 验收容器使用任务标签、资源限制、专属数据及网络。只有本任务容器可以停止/清理；禁止向测试集群挂载共享宿主 Docker socket，除非另有明确审批。完整自动调度使用用户指定测试资源；本轮通过指定服务器的既有元戎API接入新命名空间，不给候选容器挂共享socket。

本轮镜像验证范围是后台角色，不含完整账号 Web UI、外部 Provider CLI/模型业务调用、跨节点共享卷和现网部署。日志/证据见管理仓同名 `PLATFORM_CLOUD_ROLE_E2E_20261109` 记录；服务器真实创建/回收结果以该验证记录为准。

## 元戎启动层

现有 Python3.11 元戎池可使用 `Dockerfile.yuanrong` 的 Agent 专用启动层。输入必须是已核验 Agent 镜像、固定 CPython3.11归档、公共SDK文件及逐文件摘要清单，另含 `agent_dx_executor-0.1.0-py3-none-any.whl`（SHA256 `8ee5c5996df3a582bc306aea1bd216005daae3038082a029007857c72c616279`，未改动官方源码 `fd018bff904d473690de1a578d5d1f7a5ef44c15` 的已有构建产物）。仅 `import yr` 成功不能证明启动层齐全，必须实际导入 `yr.agentexecutor.handler` 并验证元戎启动。安装器的 `--break-system-packages` 仅作用于新镜像专用解释器，不对宿主或既有实例安装包。产品仍从 `/opt/venv` 的 Python3.13按原uv.lock导入；SDK放独立解释器目录，不能用全局PYTHONPATH污染产品依赖。该启动依赖另行留档，不属于产品uv.lock。部署前实际核验两个解释器导入、镜像内用户名/UID/GID与只读凭据挂载；不修改外部SDK源码。

`HOME=/data/home` 位于持久卷内；Gateway 在准备新实例时创建并校验此私有目录，不依赖镜像内会被挂载遮蔽的目录。实例回收关闭连接以普通错误通知在途请求，不取消上层 HTTP 请求任务。

## 日志隔离部署与发布边界

B01云文件API已修复；B02通过本目录docker_log_boundary.py在专用Docker测试底座完成双账号定向修复验证。未接入适配器的旧底座仍会共享日志，不因此获得防护。当前尚未达到生产发布条件：代理最小运行保障已进入本轮专项与服务器故障验收，日志采集/配额和完整使用面兼容验收仍待；具体通过/未通过项以最新验证记录为准；不部署现网。

适配器提炼自codeswarm24f29148，定位为可退出的宿主部署组件。受管目录规则由必填--workspace-name-pattern显式提供，平台装配配置env_[a-f0-9]{32}，实现中不再硬编码账号或环境命名。宿主运维创建0700控制目录及私有日志根；socket只能供可信控制进程访问，不能挂入Agent或公开TCP。以原参数指定固定镜像、agentos登录名和实际UID、workspace-root、private-log-root及真实shared-log-dir。必须将元戎启动环境DOCKER_HOST与使用到的runtime_launcher.docker_host都设为同一unix://私有socket；仅改一处或使用tcp://可能绕过预期接线。核对实际日志路径，不从CLI日志前缀推断自动挂载源。

原Docker create里的共享日志源被替换成本环境私有目录，容器目标路径保持。原Router/元戎负责生命周期；平台没有新增调度器或日志服务。宿主采集需改读私有目录，并制定配额、轮转、保留与清理策略；账号可修改自己的运行日志，审计应另由受控采集保管。对完整挂载、进程身份及重建后隔离做实测，不用chmod000、只读共享根或叠加挂载冒充隔离。升级元戎/Docker时重验实际API与挂载格式。

前一硬编码规则候选25项专项、16账号/8WS/7生命周期通过，双账号初次与代理重启/实例重建后私有日志正常且互不可读。合成轮转验证不等于SDK自动轮转、所有Docker流式接口或多节点验收。该历史候选未含服务托管；现有[systemd模板](systemd/code-platform-log-boundary@.service)仅用于显式装配和专属验收，不自动启用现网；完整检视、代价及证据见管理记录PLATFORM_CLOUD_DOCKER_LOG_BOUNDARY_20261110。

## 可选预建执行池绑定

resource_pool_id仅固化部署侧池标识及原endpoint/namespace/URN，防止配置变化静默重定向已有绑定；不是元戎选池参数或日志隔离开关。当前一Gateway仍只接一个原Router端点。已有无placement绑定不能直接启用此配置，已绑定记录不能直接移除或换池；需要独立状态及明确迁移审核。它不是本次日志适配器前置，本次未启用；无需因日志修复先安装K8s。

## 临时适配器的接入与退出

完整参数表、启动示例、兼容说明与替换验收见[日志部署配置与退出契约](LOG_BOUNDARY_CONTRACT.md)。命名规则参数化后的43项本地专项通过（含真实CLI/Unix socket与假Docker端点）；同一脚本SHA256 3be037d7已在113.207.105.228新专属底座完成显式配置、三轮双账号日志隔离、人工代理重启及原链回收重建复验，见管理记录PLATFORM_CLOUD_LOG_ADAPTER_SERVER_20261110。该结果不代表自动恢复或生产上线条件已完成。

平台只依赖日志隔离结果，不持久化代理类型/地址。替代方案先在隔离环境通过同一组结果验收，再按原生命周期切换部署接线，最后退役代理并保留历史日志；无须改账号/环境数据库或Gateway/Runtime接口。缺少有效规则则拒绝启动，不回退硬编码规则或未隔离Docker入口。

## 部署适配器运行保障

适配器新增连接容量、请求/上游/流空闲超时，SIGTERM清理及持有操作员文件锁的显式残留socket恢复。容量满时503，上游失败/超时且未开始响应时502，响应已开始则关闭；不重放Docker操作，也不自动回退。用原生systemd托管及启动频率限制，不引入平台监督服务。完整参数、可信目录前提及故障回执规则见[配置契约](LOG_BOUNDARY_CONTRACT.md)。本轮源码与服务器故障验收对应PLATFORM_CLOUD_LOG_ADAPTER_RELIABILITY_20261110；旧脚本的手工重启结果不冒充本版本自动恢复证据。

示例服务的Type=exec表示进程已执行，不等价于适配器/Docker就绪；启动元戎前仍须核验实际私有socket、指定上游和两处Docker端点配置。模板需操作员按实际安装路径、固定摘要及独立数据根装配，不自动安装、不enable现网服务。

**本轮故障验收存在阻断：** 代理在Docker创建成功但响应未返回时崩溃，原生托管能恢复代理，但原实例链可能在元戎API404后留下未启动Docker容器，并允许再次创建。不能把代理恢复或API404单独当作物理唯一性通过；当前候选不得因此进入现网。不得向适配器加入隐式重放或无归属回收来掩盖该缺口。详见PLATFORM_CLOUD_LOG_ADAPTER_RELIABILITY_20261110。

物理对账是独立于日志私有化的可选部署能力。新专属底座启用方法及六参数契约见[LOG_BOUNDARY_CONTRACT](LOG_BOUNDARY_CONTRACT.md)；[systemd附加模板](systemd/physical-confirmation.conf.example)仅为人工审阅模板，未安装现网。确认目录必须预建，Gateway只读挂载该目录；完整Docker端点及派发回执均不挂入Gateway或Agent。关闭服务会阻止未决删除后的重建，不应回退绕过确认。

当前已验证候选的配置核对、逐状态恢复与交付边界集中见[CANDIDATE_HANDOFF](CANDIDATE_HANDOFF.md)；旧阶段缺口保留历史记录，不继续作为本轮收尾的新增开发任务。
