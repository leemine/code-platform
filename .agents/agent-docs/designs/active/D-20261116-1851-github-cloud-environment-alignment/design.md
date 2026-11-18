---
id: D-20261116-1851-github-cloud-environment-alignment
title: 对齐 codeswarm 的 GitHub 云端项目环境流程
slug: github-cloud-environment-alignment
type: D
status: in-development
stage: active
approved-date: 2026-11-16
author: leemine
author_email: leewanlong@gmail.com
reviewers: []
created: 2026-11-16
updated: 2026-11-16
domain: core
modules: [gateway/extensions/cloud_workspace, gateway/services, jiuwenswarm/server/control, jiuwenswarm/channels/web/frontend]
tags: [cloud, github, workspace]
scope: 三段式入口内的 GitHub 连接、仓库准备及项目环境选择
plan: PLATFORM-MULTI-ENV
related: [D-20261116-1724-multiple-cloud-environments]
files: []
---

# 对齐 codeswarm 的 GitHub 云端项目环境流程

## 纠正依据

2026-11-16 用户明确指出“创建云端环境”应对齐 codeswarm 的 GitHub 连接流程，并要求暂不配置模型。原任务中的“同一账号多个环境”指向多个可选择的云端项目工作区，不能自行推导成每次创建一个独立容器/运行实例。原独立实例候选不作为本方案的实现依据。本文记录已明确的产品流程及待实现的技术适配，用户已明确同意按本流程开发；完成状态以实际验证记录为准。

参考本地 codeswarm SHA 24f29148193b5b590fe9f4b3e21f779c87253e5e：
- frontend/src/components/ChatPanel/CloudEnvironmentDialog.tsx：嵌入 GitHub 连接控件，选择来源后提交 project.environment.prepare；ready 后显式使用。
- frontend/src/components/ChatPanel/ProjectGitHubConnection.tsx：连接、授权安装、仓库、分支和断连恢复。
- runtime/session/federation/project_preparation.py：固定来源提交、原操作回执恢复、向既有目标传输和发布项目；默认保留 LFS 指针。
- gateway/channel_manager/web/account_cloud.py：物理账号云端接入原项目准备服务的适配。
- docs/PROJECT_GITHUB_CONNECTIONS.md：准备不安装依赖、不授权模型、不创建 Session 或 Turn。历史试验记录不能直接当作最新完整验收结论。
以上 frontend 路径相对 jiuwenswarm/channels/web，其余源码路径相对 jiuwenswarm。

## 用户流程与三段式入口

1. 左侧保留本地项目目录；中间 Local/Cloud 立即选择，不因选择触发分配或登录。
2. 选择 Cloud 后右侧显示云端操作：选择已有云端环境、选择云端目录、新建云端文件夹、创建云端环境。
3. 创建弹窗复用 codeswarm 的 GitHub 连接区域。未连接时引导用户连接已由部署者配置的 GitHub App；已连接时复用该账号连接，展示授权安装范围、仓库及分支。
4. 选择仓库/分支，填写环境名称，点击“准备环境”。后端校验云账号和 GitHub 仓库权限，固定提交，在该账号既有云端运行位置准备独立项目工作区，返回原项目记录。
5. 展示解析、获取、传输、检出检查、就绪及可恢复失败。重试使用原 operation_id，不能重复创建或改成另一个提交。
6. “使用此环境”仅选中项目目录和运行位置，沿用原 Code 会话入口；用户点击发送才创建/执行任务。
7. 同账号可以准备多个项目环境，再从右侧切换；会话始终保持原项目和目标绑定。

“新建云端文件夹”与 GitHub 仓库准备分别保留。云账号登录和 GitHub 授权属于不同权限域；不额外增加第二套云账号登录界面。GitHub App 注册/仓库授权由部署配置与用户授权决定，不拿本机 gh/PAT、聊天连接器或模型密钥替代。

## 技术集成及解耦

- 沿用 code-platform 的云账号权威、TLS、同源本地桥和原 Router/AgentServer，不整体引入 codeswarm 的 federation 运行时。
- GitHub 连接由 Gateway 持有，账号与目标共同限定私有连接记录。复用参考实现的设备授权/刷新/仓库发现语义，适配本工程的身份和存储接口；密钥不进入执行实例或项目目录。
- 环境准备协调器负责不可变来源和操作回执，项目注册与工作区检查归原 AgentServer/ProjectStore。复用原传输进行分块、摘要验证和断点恢复，不另建任务调度器。
- 产品环境列表来自已准备项目及来源/准备状态；运行实例的分配与运维状态留在运行层，不将原候选的实例列表包装成仓库环境列表。
- 多项目工作区共享账号已绑定的运行实例。是否隔离到更多实例是另一项运行资源策略，不能由“创建环境”按钮隐式决定。
- 所有读取、准备阶段、发布和结果投递保留实时权限校验；回执和配置不能替代授权。原会话/默认项目兼容必须单独验证。
- 当前参考实现默认只准备代码并保留 LFS 指针，不声明依赖已安装、大文件已下载或能无损恢复进程/Provider 状态。

## 集成顺序与验收关口

先对齐现有入口与 GitHub 连接/仓库选择，随后接通真实仓库准备和可恢复状态，再验证多个工作区的选择及原会话绑定。产品后台需明确支持能力后才能启用准备按钮，不以静态弹窗、mock 或空容器创建冒充完成。

验收包括未登录/已登录、未连接/已连接 GitHub、授权仓库及分支、两个环境、同名冲突、权限撤销、断线恢复与旧会话；真实 Git 检出须独立验证 HEAD、分支和目录，未点击发送前不得新增会话/模型请求。当前用户要求暂不配置模型，因此仓库环境准备验收不依赖模型配置；真实 Provider 执行若另行恢复，应使用单独授权和验收记录。

当前 code-platform 基线尚无对应 GitHub 连接/仓库准备模块；不能仅换弹窗就宣称完成。需核实部署 GitHub App 配置、授权范围和验收仓库；缺失时明确未配置，不能擅自创建 App、扩大仓库权限或移用其他凭据。产品提交、CI、合入仍以实际完整验证为前提；管理记录仅保留本地。


## 2026-11-16 已确认的认证方案替代

用户明确授权参考 dsh-superagent-prototype 6337fc823，改为官方 gh 登录，不要求自建 GitHub App；验收使用 leemine/code-platform。此前 client_id/app_slug/installation 配置方案被此决定替代，其项目准备、三段式UI与权限不变量保留。

Gateway 以官方未修改 gh 可执行程序发起 auth login --web；每个账号/目标/登录尝试使用独立私有 HOME 与 GH_CONFIG_DIR，清除宿主 GH_TOKEN/GITHUB_TOKEN/Git 配置和交互浏览器环境。仅显示 gh 返回的短期用户码与固定 github.com/login/device 链接，最终授权由用户在 GitHub 完成。gh 的临时凭据仅供当前登录进程使用，成功后转入既有加密连接存储并删除临时目录；不挂载到执行容器。退出/撤权/代次变化阻断迟到成功。关闭服务终止拥有的登录进程；进程重启不复用半完成登录。

不复制 gh 的 OAuth client_id 或协议实现，不改 CLI 源码或宿主已登录配置。官方 gh 与 SHA256 校验清单作为部署依赖，容器内固定版本；浏览器不接收访问令牌。账号凭据作用域仍为云账号权威/主体/目标，GitHub身份由实时 /user 确认，选仓来自 /user/repos，分支/检出前及登记前新鲜检查仓库可访问性。去掉 App installation 配置，使用 GitHub 用户 account_id 绑定来源。

GitHub授权凭据允许范围由官方 gh 授权页告知；当前功能仅调用读取与检出，不推送仓库。平台自身登录和实时授权不能由 GitHub 登录替代；库检出继续使用 Gateway 私有凭据消费和原 E2A/ProjectStore，模型暂不配置。必须验收真实登录、仓库/分支、至少两个项目准备/选择、权限与恢复、原云目录及历史，再提交/stable/合入/复验。

## 2026-11-17：GitCode 平台扩展（用户确认）

保留 GitHub 官方 gh 设备授权；创建环境增加 GitCode 来源。用户已选择免注册应用：打开 GitCode 官方个人令牌创建页，回到本地界面填写一次。GitCode CLI 当前 `--web` 实为令牌页面加手动输入，并非设备码授权，不复制 GitHub 客户端身份或虚构 OAuth 自动回调。

认证与仓库发现采用平台适配器；账号私有存储、HTTP 边界、项目准备、传输和导入复用。GitHub 现有根目录和 fingerprint 不变，GitCode 使用独立私有根目录，账号作用域仍为可信云主体/目标。GitCode Token 仅存在短期输入状态和 Gateway 加密凭据记录，不进 localStorage/sessionStorage、项目、执行容器、URL 或日志。GitCode 通过固定 api.gitcode.com Bearer 请求与固定 gitcode.com HTTPS Git 地址访问；不接受客户端自定义 URL。

GitCode 用户 ID 是不透明字符串，仓库 ID 是整数；仓库查询使用已选择的 full_name 并核对仓库 ID。来源、回执和缓存区分平台；旧无 provider 的来源继续按 GitHub 解释。现有三段式入口不变，仅创建环境弹窗选择托管平台，复用账号/选仓/分支/准备控件；平台切换清空当前选择并拒收旧响应，恢复操作 ID 按平台区分。准备和发布前继续校验云权限与仓库访问；新 AgentServer 能力声明包含 GitCode，旧实例不能误报支持。

验收覆盖两平台保留、令牌一次性提交/加密保存、账号与平台隔离、撤权/迟到响应、来源固定和断线回执、真实仓库检出和项目选择、旧目录/历史；模型仍不配置。真实 GitCode 用户连接必须在界面完成，不将 mock 或匿名下载当作完整验收。管理记录只在本地保存。
