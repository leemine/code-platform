---
id: F_20261030_1939_external-desktop-builds
title: 可选 Native 与外部 Provider 桌面测试包
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [agent_adapter, desktop, gateway]
files: [pyproject.toml, uv.lock, scripts/jiuwenswarm.spec, scripts/build-electron-linux.sh, scripts/assemble-electron-linux.py, scripts/verify_external_bundle.py, jiuwenswarm/common/native_integration.py, gateway/extensions/registry.py, .github/workflows/windows-external.yml]
designs: []
design_note: 用户确认两种安装组合和先 Linux 后 Windows/macOS 的实施范围；管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 第24节及 EXTERNAL_DESKTOP_BUILD_20261030 记录来源与验证。
---

# 可选 Native 与外部 Provider 桌面测试包

基于官方88fbdd2及前序AgentAdapter候选，在独立codex/external-desktop-20261030工作区实施。Core e089198与协议2a0457e固定不变。

将Native依赖、Runner、日志、KV缓存、原生适配器及可选推荐/记忆入口留在Native组合；注册实际OpenCode插件；公共审批谓词与Todo投影保持独立。现有Registry支持无Core基础Hook分发并传播失败，Native仍委托原回调框架。补充Swarm直接依赖aiofiles和插件包标识，防止源码成功但wheel漏包。

复用原Electron、PyInstaller和Vite构建，Linux新增组装入口，Windows/macOS增加external选择且保留默认Native。验收从正常非editable安装、源码渠道推进到冻结渠道与桌面壳；失败尝试和限制均在管理验证记录保留。本轮未提交、推送或发布。


## code-platform 私仓 Windows 构建入口（2026-10-30）

用户授权在新私仓通过 GitHub Actions 启动 Windows 构建。新增手动 workflow_dispatch 工作流 .github/workflows/windows-external.yml，在 windows-2022 x64 runner 调用原 build-electron-exe.ps1 -BuildProfile external -NoSign，保留完整 Inno Setup 安装器阶段，不使用 SkipInstaller。Actions 固定提交、令牌只读、独立运行数据目录，不注入模型凭据或发布Release。成功归档exe/摘要/源SHA，失败保留构建日志；免Core冻结检查仍由原脚本执行。

当前仅构建测试安装包，未签名；生成安装器不能替代Windows真实Provider、权限、取消、配置隔离和进程树验收。原安装器AppId沿用WorkSwarm，实机验收使用独立测试环境。构建实际结果在管理任务记录和Actions运行链接跟踪；未修改Core/协议锁或外部Provider。

首次GitHub校验拒绝工作流：job级env不允许引用runner.temp；未分配runner或运行打包。修正为步骤内从RUNNER_TEMP写入GITHUB_ENV，保持运行数据隔离，随后重新触发；不将本地YAML解析通过当作Actions执行通过。

Windows运行41078652890（提交3fc8f997）成功dispatch，但GitHub在分配runner前终止：账户近期付款失败或消费额度需要提高。job124141593919无runner、无步骤执行，不属于源码/安装器构建失败，未产出exe。官方运行链接：https://github.com/leemine/code-platform/actions/runs/41078652890 。待账户Billing & plans解除限制或提供Windows自托管runner后再运行；本任务未修改账户支付设置。

## 2026-10-31 PR #3 后 Linux 安装候选

基线为 code-platform main bc3f188（PR #3 合入）。外部组合仍不含 agent-core、Provider SDK/CLI 和私有模型配置；SDK 经原 Third-party Agents 按需安装。补齐原清单缺失的 Claude Linux x86_64/aarch64 官方 wheel，与现有 uv.lock URL/摘要一致；冻结验证器覆盖三个已注册适配器，不能再假定只有 OpenCode。

真实桌面安装后发现两处接缝：离开设置页会卸载安装状态轮询与延迟保存 Effect；Front 在启动后安装 SDK 时未刷新其 sys.path，使 config.get 错报 sdk_not_installed。将原轮询与延迟 config.save_all 移到 App 生命周期，仍用原 pending-choice/sessionStorage、设置 RPC 和配置变更刷新；删除设置页的重复保存与兜底轮询。Front 菜单投影复用现有受校验的 managed-runtime activation，既不安装 SDK，也不启动 Provider。Worker 原来每轮刷新路径的行为保留，不新增执行状态机/队列，不修改外部 SDK。

离开设置页、精确保留用户 CLI 路径、安装失败、保存失败/重连、历史状态不重复启用、安装回执不等于保存等在 React 回归中核对。Front 真实 CONFIG_GET 入口补 Linux/Windows/macOS 激活分支回归；跨系统单元测试不是 Windows/macOS 实机验收。本轮 Linux 候选不覆盖仍在读取的旧 bundle，配置与用户桌面窗口保留。最终包与验证状态见管理仓 EXTERNAL_DESKTOP_RELEASE_20261031。


## 2026-10-31 beta2 交付候选

在已合入工具结果与Codex TLS修复的main 5fc40e2上，保留原Linux官方SDK按需安装清单、Front目录刷新与App延迟保存修复。版本由原同步工具更新0.2.5.beta2，锁只改本项目/TUI版本；新建按锁非editable免Core环境，无官方Provider SDK预装。联合201项后端、6个前端入口和Electron前端构建通过；冻结验收/产物摘要待补。用户明确豁免本次GitHub Actions，未修改工作流或自动关闭实际TLS校验。


beta2候选验收闭合：201项联合后端、69项打包契约、6个前端入口；按锁非editable免Core冻结；正常Gateway下载/Front热发现；原用户模型选项的三Provider真实Runtime及实际Electron Code UI/刷新历史通过。QA12个进程正常退出、私有配置已删除，模板/私钥零匹配与tar/deb关键内容一致审计通过。具体摘要和截图见B_20261031_1930_optional-provider-menu；本次用户豁免Actions，未实际安装系统deb或运行Windows/macOS。

## 2026-11-02 beta4 Windows / macOS Actions 原生构建

用户确认通过 GitHub Actions 构建 Windows x64 与 macOS arm64 测试安装包；沿本记录续写，不改变 Provider/Runtime、Core/SDK 锁或已有构建器。产品基线 main cf07852397f3b7547ba6b52a54628b89e4aacd4e，隔离分支 codex/desktop-actions-build-20261102。Windows 先用该 main 的原入口运行 41467786074，实际已进入构建步骤；旧运行 41078652890 的账单拒绝结论保留，不能外推为本次仍无法启动。

为不把未验工作流先合入 main，扩展原已注册 windows-external.yml 的手动 platform 选项（默认 windows，可选 macos/both），保留 Windows 原构建/诊断入口。macOS 使用标准 macos-14 runner 并检查真实 uname=arm64，固定 Node/uv/Bun 构建工具，完整调用原 build-electron-exe.sh，包含 TUI、冻结后端、架构和 external 无 Core 自检及 DMG 校验。NOSIGN=1/NOTARIZE=0 表示不使用 Developer ID 签名/公证；不改系统安全策略，也不冒称可通过正式分发 Gatekeeper 验收。

可选 product_base_sha 输入只接受完整提交 ID，并在构建前核验产品/脚本/依赖树相等；未提供时以当前 GITHUB_SHA 为基线，不把本次 cf07852 写成未来版本的永久门禁。任务分支将显式传入 beta4 SHA。依赖仍按原 uv.lock 安装，构建后检查锁未改变；来源、架构和摘要进入仅供下载的 Actions Artifact（14天），无 Release 发布或本机模型凭据注入。

本地工作流结构/内嵌 Python 解析及产品树等价核对通过，既有桌面契约44项通过（0.69秒）。首次误用构建 venv 缺 pytest、第二次缺隔离数据目录导致用户日志只读，均未运行测试；改为既有测试环境和本任务私有 HOME/DATA_DIR 后执行，失败准备记录保留于管理仓 artifacts/desktop-actions-build-20261102/evidence。本地结果不是 Windows/macOS 原生构建成功或真实 Provider/Electron 聊天通过。最终运行与产物状态由管理任务台账及对应 Actions 记录，不在本节假定结果。

macOS 首次运行41468422605已通过arm64和工具准备，但checkout默认浅克隆没有产品基线cf07852对象，来源核验返回bad object，构建尚未执行；属本工程新增CI准备缺陷。仅macOS checkout改为fetch-depth:0以保留明确的产品树比较，不删除来源断言、不改原打包脚本；Windows既有步骤保留。修复后在原隔离分支新提交并重跑，首次失败日志保留。
