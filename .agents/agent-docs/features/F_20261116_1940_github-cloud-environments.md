---
id: F_20261116_1940_github-cloud-environments
title: GitHub 云端项目环境接入与待验收边界
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway/services, gateway/extensions/cloud_workspace, jiuwenswarm/server/control, jiuwenswarm/server/runtime/session, jiuwenswarm/channels/web/frontend]
files: [gateway/services/project_environments.py, gateway/services/project_github.py, gateway/services/project_preparation.py, jiuwenswarm/server/control/project_import.py, jiuwenswarm/server/control/project_checkout.py, jiuwenswarm/server/runtime/session/project_store.py, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/CloudEnvironmentDialog.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ProjectGitHubConnection.tsx]
designs: [D-20261116-1851-github-cloud-environment-alignment]
---

# GitHub 云端项目环境接入

## 关联、版本与决策

依据已批准的 [D-20261116-1851-github-cloud-environment-alignment](../designs/active/D-20261116-1851-github-cloud-environment-alignment/design.md) 和 [S_04_github-project-environments](../specs/gateway/S_04_github-project-environments.md)。本记录局部替代旧“创建多个物理实例”的候选解释；旧候选仅保留恢复证据，不移入本次产品改动。

候选基于 code-platform `f116e1e5d9f49893edc8f777cf2377824caae633`，分支 `codex/platform-github-environments-20261116`，工作区尚未提交。参考 codeswarm `24f29148193b5b590fe9f4b3e21f779c87253e5e`。Core 固定 `e089198835426cd7681761b0cc278670cd83031f`、协议固定 `2a0457e5e01152e9ca5f8afdffd84716227046ca` 未改变。运行来源见任务证据 `import-provenance.json`；本机为候选源码加按锁安装依赖，镜像为 wheel 安装，不混称来源。

实际工作区：`artifacts/platform-github-environments-20261116/platform`，证据根为其同级 `evidence/`。旧候选在 `artifacts/platform-multi-environment-20261116/platform`；原始文件、暂存/未暂存差异及未跟踪清单已保存在对应 holding 目录，默认主线 checkout 未覆盖。

## 实际实现与理由

- 三段式入口保留。创建弹窗复用 codeswarm 的 GitHub 连接、安装、仓库、分支及项目准备交互；本地页面经已有云桥访问，直接云页面用原 WebChannel。仅改变目标选择即更新控件，具体操作再登录和联网。
- Gateway 持有按账号隔离、加密的 GitHub 凭据与准备记录；原 AccountPrincipal 实时校验，固定当前账号 cloud 目标，不接受任意实例、根目录或上游 URL。
- 准备复用原 E2A / AgentServer Front Control。Git 检出限时、限量，禁止执行仓库脚本/过滤器/钩子，拒绝符号链接和子模块；LFS 默认保留指针。运行实例不接收 GitHub 凭据。
- 来源 commit、请求意图及 bundle 固定。分块偏移和重复内容校验；发布回执恢复不重复建项目；已存在路径/名称拒绝覆盖；返回 ready 后允许用户正常修改，不因再查询而还原文件。
- `verify` 完成耗时检出，随后重新检查账号及 GitHub 权限，单独 `publish` 原子登记原 ProjectStore。避免检出开始时的许可被当成稍后发布的永久授权。
- 原项目对象新增可选 repository_source；旧项目默认空。环境选择读原项目表，不另建环境清单或物理实例调度器；不创建 Session/Turn、不安装依赖、不配置或调用模型。
- 关闭弹窗只关闭视图，已接受准备继续且可恢复。账号变化隔离迟到结果；已关闭弹窗不触发关闭回调，以免取消同级“新建文件夹”登录续办意图。

## 验证与证据有效范围

本地 pytest 使用候选 `.venv/bin/python`、`PYTHONPATH=.` 与隔离 `JIUWENSWARM_DATA_DIR`。测试没有使用真实 GitHub 授权，Git 仓库检出测试使用本地真实 Git；UI 测试使用 React/jsdom 和模拟后端。

| 范围与命令 | 证据 | 结果与限制 |
| --- | --- | --- |
| `pytest tests/unit_tests/cloud_workspace/test_project_github.py tests/unit_tests/cloud_workspace/test_project_import.py tests/unit_tests/cloud_workspace/test_project_environments.py -q --no-cov` | new-tests-final.log | 拆分 verify/publish 前 66 通过；GitHub grant/API 为替身，不能代替真实授权验收 |
| 拆分发布后的 import/environments 定向测试 | publication-boundary-tests-final3.log | 12 通过，包括检出完成尚未登记项目、检出期间撤权禁止登记 |
| cloud_workspace/data_sync/project_store/project_workspace 受影响回归 | regression.log | 387 通过、2 失败；失败是旧 plugin 测试接口/方法集预期，已修正 |
| 修正后 plugin、adapter、repository、Front Control 回归 | adapter-regression3.log | 92 通过；没有扩大旧失败白名单 |
| `npm run test:code-workspace` 对应控件测试 | workspace-final.log | 19 通过；修复关闭弹窗取消登录续办的真实交互问题 |
| `npm run test:cloud-environment` | cloud-dialog-final.log | 10 通过；含准备/恢复、账号切换、目标不支持禁止准备 |
| `npm run build` | frontend-final-build.log | tsc + Vite 通过，保留已有 chunk 大小提示 |
| `uv build --wheel --out-dir ../dist`，`../prepare_bundle.py` | wheel-build.log、candidate.json | wheel 构建通过；1432 Python 源文件和完整 dist 对应，合计 1859 文件逐字节核对；无旧前端残留 |

早期 new-tests.log、workspace-ui-tests.log、adapter-regression2.log 为失败/错误记录，后续修复结果各有独立日志，未改写原记录。publication-boundary-tests-final.log 因未指定隔离日志根遇只读用户目录；final2 在受限异步环境停滞后中止，不计为通过。后续正常本机运行仍使用隔离数据根和总超时。

## 交付判断及遗留

用户明确回答“未配置” GitHub App。App client_id、app_slug、Device Flow 及安装到验收仓库是实际授权链路的必要条件。不能用开发机 gh/PAT/连接器凭据替代，也不自动为用户创建 App 或扩展仓库授权。部署模板位于 `deploy/cloud-workspace/github.example.json`，占位值不能充当验收配置。

当前可验证登录、原云目录/旧历史和未配置提示；真实 Device Flow、仓库/分支枚举、远端检出、两个项目切换、真实撤权与断线恢复尚待验证。远端目标 AgentServer 需安装同一候选方可准备；旧 beta7 目标不声明 project.import 能力，UI 禁止准备。源码/mock/本地 Git 通过不能写成此端到端通过。

按用户“验证通过后提交、CI、合入”条件，本候选尚不满足完整验收；产品提交、远端 CI、合入及合入后复验尚未执行。模型配置仍明确排除。

## 2026-11-16 本轮云端与右侧复验

旧独立实例候选已通过原 Router 退役本任务两个测试实例，工作区与回滚资料保留；默认实例、CA 与历史哈希不变。随后仅 Gateway/Web 切为本次候选，账号服务、edge、默认 AgentServer 仍为 beta7；原容器保留可回滚。候选 AgentServer 镜像已构建但未替换默认运行实例，待真实 GitHub 验收时完成匹配部署。

三个角色镜像分别使用同一 wheel，在无网络、无用户数据挂载的一次性容器内核验 1859 项源码/dist 摘要、Git 可执行文件、project.import capability 以及实际 Core/Protocol 固定 SHA，全部通过。证据 `remote-candidate-state.json`、`image-verification.json`；这证明包与接缝装配，不代表真实 GitHub 检出通过。

右侧真实浏览器使用 `http://127.0.0.1:29121` 新候选，保留严格 CA 验证的本地云代理：

1. Code 模式切云端立即出现右侧控件，地址保持本地。
2. 已有账号退出，左下角恢复登录按钮；同一账号通过统一弹窗重新登录成功。
3. 读取原云目录，新建并打开 `github-flow-check-1116`，显示已选云端项目；未发送消息。
4. 直接打开既有 cloud session 路由，显示 2026-11-13 的原消息、工具修改记录和 `CLOUD_DELIVERY_OK`，未重新执行历史内容。
5. 选择云端环境返回空列表；普通目录不冒充 GitHub 环境。创建环境弹窗返回真实“当前部署尚未配置 GitHub 连接”，准备按钮禁用。

证据截图 `ui-cloud-directory-selected.png`、`ui-old-history.png`、`ui-github-unconfigured-final.png`。未进行真实 GitHub OAuth/选仓/仓库准备、多项目切换或真实 GitHub 撤权验证，未新增模型配置。产品仍未提交/推送/CI/合入；主线版本未改。

## 2026-11-16 官方 gh 登录替代候选（待真实授权验收）

用户在本会话明确选择普通 GitHub 用户登录，批准参考 dsh-superagent-prototype 改用官方 gh；真实验收账号 leemine、仓库 leemine/code-platform，模型不配置。上述 GitHub App 配置前置已被这一决定替代。参考工程 HEAD 为 6337fc823ce20251c8de8085948165c81aaa701e，读取其 GH_CONFIG_DIR 独立登录与 Git credential helper 实现；本产品额外保留多云账号身份边界、加密持久化及实时权限校验。

当前独立候选为 artifacts/platform-gh-login-20261116/platform，基于刷新后 origin/main f116e1e5d9f49893edc8f777cf2377824caae633；原 App 候选完整补丁、原文件和摘要保存在新任务 holding/app-candidate 中，旧预览未修改。Core/Protocol 锁定来源不变。新服务使用官方 gh 2.104.0（官方 release archive SHA-256 98cb101ad87dbbd3f6b2f2bfcbd43197ccd07643140121d8a9cfaa91eadbc24e），不修改 CLI/SDK 原生源码。镜像不含凭据。

授权按账号创建私有 GH_CONFIG_DIR；官方短码可见、凭据不经浏览器/执行实例传递。临时配置加密入库并清理明文。服务租约、账号 generation、重复开始拒绝、关机等待和取消清理防止迟到授权复活；网络/限流错误不清除已存授权。accounts/account_id 替代未交付 App 候选的 installations/installation_id，用户仓库分页读取，检出与登记前重新校验仓库和账号权限。

验证证据根 artifacts/platform-gh-login-20261116/evidence：官方 CLI 独立启动获得短码 2.402 秒（official-gh-probe.json，未批准授权）；云工作区 257 passed / 1 error（缺少按锁可选 Codex SDK，cloud-tests.log），安装锁定 codex-direct 后该项及项目/Web 兼容 46 passed（remaining-tests.log）；授权并发/关机清理等最终专项 27 passed（gh-final-tests.log）；前端三套行为 50 passed，补充短码/取消用例后 cloudEnvironment 11 passed（frontend-final-tests.log）。第一次沙箱前端运行仅给出文件级通过，不记作实际行为用例通过。打包与云端核验以随后实际 manifest 为准。

仍待用户真实 GitHub 授权、leemine/code-platform 选仓和云端检出、旧目录/历史及中断恢复联合验收；不得据上述模拟测试声明真实流程已完成。产品尚未提交、CI 未触发、未合入；管理记录仅保留本地。

云端 r2 三角色镜像已逐文件核对1860项源码/dist、官方gh版本和Core/Protocol实际导入来源；经空闲检查、私有备份及原Router退役/重建，默认环境ID/目录不变，epoch4→5，旧历史哈希不变。账号与edge未替换，模型未配置/调用。运行证据 deploy-state.json、credential-boundary.json；Gateway与worker均非特权且未使用宿主PID命名空间，凭据目录不挂入worker。

云端GitHub默认地址20.247.166.64在TLS握手后HTTP无响应，API域名0.334秒可达；公共DNS探针曾1.066/8.325秒成功，但真实UI仍15.344秒失败，随后独立官方gh HTTP POST探针35秒无响应。公共DNS得到的140.82.113.4在保留GitHub主机名/SNI/证书校验下GET1.189秒、官方gh短码3.204秒成功。仅本隔离Gateway容器采用临时github.com解析例外，未进入镜像/产品默认配置或全局系统DNS，后续须修复部署出站解析/路由后移除；不能以一次网络探针宣称长期稳定。真实GitHub用户授权与仓库检出仍待。


### 2026-11-16：真实授权后的准备超时修复与主线整合

用户已亲自完成官方 GitHub CLI 授权；本地三段式入口真实显示 leemine，并成功读取 leemine/code-platform 的 main 分支。首次完整准备操作 1271d725f6eb4531813a9e910a727f1c 失败，原因为 Git fetch 每次 90 秒超时，三次失败保留为失败证据。codeswarm 参考实现存在相同 300 秒总预算 / 90 秒单次截断；本仓修复有效下载截断，保留总预算、容量限制、低速断开及实时权限校验。

只读吞吐诊断（20 秒窗口，非成功准备验收）：GitHub 美国路径 458751 字节；亚洲路径 12836863 字节。服务端按容器配置临时 github.com 路由例外，仍使用原 hostname/SNI 和可信证书；该运维例外不是产品内置地址，也不代表公网路径已永久修复。

原 f116e1e 候选全部 47 个变更文件及 staged/unstaged patch 已保存于 artifacts/platform-gh-login-20261116/holding/gh-r2。独立工作区 platform-main 基于 fde7a0c940dcbb056c28833f378fd9e25a996849（beta8）恢复，保留新主线桌面登录修复。Core/协议锁定版本未升级。

新候选验证：cloud_workspace 264 passed（116.41 秒），项目目录与 Web 代理相邻测试 45 passed（4.29 秒），前端交互 59 passed；tsc+Vite 构建成功。最初限制网络的沙箱测试被端口约束阻塞，已停止本任务进程，使用隔离数据目录在可用环回端口环境重跑，不计为通过。统一 wheel 551e43b7252b107885b4f5e9fbc9e886fe650b1680c34568f0032502f1e5e575 与候选 1860 个文件逐项一致。真实项目准备、CI、提交及合入仍待闭环，模型未配置。


r3 实际升级完成：同一 environment_id，epoch 5→6；原历史逐文件哈希不变，Gateway 授权卷未挂载给执行实例。真实重试恢复同一 operation，刷新页面后仍可查询下载；首个 fetch 在 260088ms 发生 GIT_TRANSFER_FAILED，第二次用完共享 300 秒预算，总 300123ms 后 GIT_TIMEOUT，未发布项目。过程采样曾收到 33579019 字节；失败原因仍涉及公网传输，不记成功。

r4 候选将完整仓库网络预算调为 900 秒并尝试 HTTP/1.1，仍保留 HTTPS 证书检查、1 KiB/s/60秒低速限制、逐秒云权限检查及发布前 GitHub 权限检查。31 项受影响测试通过，统一 wheel SHA256 eba11e017393db8ff98875f3ec217411cb63d0f869e050d8eec3c9a232986723；1860 文件核验一致。匿名临时容器 HTTP/1.1 路径诊断：亚洲路径90秒未完成，欧洲路径30.535秒低速失败，均不作为授权仓库准备成功证据。r4 实际授权流程仍待验证。


r4 实际升级完成（epoch 7，同一账号环境），历史哈希保持一致，Gateway 授权卷仍不在执行实例。真实准备三次传输均未收到 pack，463520ms 后 GIT_TRANSFER_FAILED；只读 TCP 诊断发现 SYN-SENT、连续重传和未确认数据，未判定为登录或证书失败。失败回执保留，未创建 GitHub 项目。右侧真实复验原云端目录选择、cloud-final-20261113-2312 旧历史 CLOUD_DELIVERY_OK，以及新建/打开 gh-login-r4-check-1116 成功；未配置模型、未发送新模型消息。证据位于 artifacts/platform-gh-login-20261116/r4/evidence。

用户确认无备用出网配置。已提出仅用于验收的 30 分钟、云端回环 127.0.0.1:41743、固定 github.com/api.github.com:443 的 SSH/TLS 透传方案；自动审批因缺少对此具体隧道的明确授权拒绝执行。脚本只保存在本地，未启动。用户目前仅询问用途，不能视为授权。Github App→官方 gh 功能和下载修复候选仍待真实仓库准备闭环；产品尚未提交、CI、合入，管理记录仅本地。

### 2026-11-17：GitCode 扩展候选（开发与验证中）

用户确认免注册应用的官方令牌页流程。新工作区 artifacts/platform-gitcode-environments-20261116/platform，分支 codex/platform-gitcode-environments-20261116，基线 fde7a0c；旧候选48文件及暂存/未暂存差异保存在同任务 holding/gh-r4，未覆盖运行中的 platform-main。GitHub CLI 官方流程保留；新增 GitCode 令牌服务，共用私有连接存储和有界 HTTPS 客户端。项目来源显式 gitcode；旧 GitHub 来源、凭据 fingerprint、回执保持兼容。

当前源码完成连接/选仓/分支/准备路由与界面，尚未部署/真实授权/提交/CI/合入。第一轮原连接/导入回归31 passed（19.34秒）；GitCode与导入21 passed（15.20秒，含与前一轮重叠的导入用例，不相加计独立总数）。界面13 passed（1.32秒）；tsc+Vite构建通过（37.99秒）。新增输入测试首次因 react-dom 在 JSDOM 之前导入而未触发输入事件，失败断言序列化整个 React DOM 导致 OOM；已改为 DOM 初始化后加载 react-dom、布尔断言并有界重跑，旧失败日志保留，不计通过。证据：任务 evidence/initial-tests.log、gitcode-tests.log、frontend-tests-r2.log、frontend-build.log。完整回归与真实云端流程仍待。

GitCode 候选 r1 完整回归：cloud_workspace 279 passed（123.19秒），项目存储/工作区/Web代理相邻测试86 passed（10.28秒），前端关联72 passed（8.90秒）。首轮整组的两项失败是路由清单未扩展；修正后暴露测试插件未关闭导致的库锁冲突，已用 finally shutdown 解决，失败日志保留。统一wheel SHA256 27e397bf5aae6af62564034da29479679e89fe3e702414ecc5be9a72bb72ad84；Gateway/Web/AgentServer各1862项源码与dist及锁定依赖来源核验一致。

云端 releases/gitcode-20261117-r1 已安装：原 chain-1112 环境ID和workspace保持，epoch7→8，历史逐文件哈希一致，授权目录未挂载给worker。第一次安装因检测到额外NEW注册记录在维护前退出，服务未中断；操作脚本只允许重建已授权账号，并只更新其他从未分配实例的NEW记录镜像绑定，保持其账号/目录/状态/代次。存在其他ALLOCATED实例时拒绝升级；迁移隔离测试验证原子回滚。原账号、edge与CA未替换。

右侧实际UI：新预览 http://localhost:29131/chat/new 使用localhost隔离另一轮127.0.0.1浏览器Cookie，未退出或修改其他验收账号。chain-1112 登录成功、Code/Local/Cloud菜单正常，创建环境保留原GitHub已连接leemine；GitCode status与能力读取成功、官方令牌页链接和本地密码输入框可见。截图 evidence/gitcode-connect-ui.png。官方 https://gitcode.com/setting/token-classic/create 在当前浏览器显示“暂时无法连接 AtomGit”，页面重试仍同；截图 gitcode-official-page-unavailable.png。尚无GitCode实际授权令牌/验收仓库，未进行真实GitCode选仓/检出，不算端到端通过。已请用户在其可访问的官方页面创建令牌并在本地表单输入，不在聊天传递。模型未配置/调用。产品未提交、未CI、未合入。

交付前仍需真实GitCode两项目准备/选择、断线回执/撤权、目录与旧历史复验，以及最终代码检视。检视待核实：准备任务取消后 asyncio.to_thread Git下载的退出与服务关闭衔接；已连接GitCode再次打开令牌输入时是否应立即清空旧选仓。上述是待核实项，不记作已修复或通过。

### 2026-11-18：最新 main 整合与交付检视

用户授权检查原云端未提交修改、完成必要验证后提交并合入 main。原工作树51文件及 staged/unstaged/combined patch 和逐文件 SHA-256 全部保存在管理仓 `artifacts/platform-cloud-integration-20261118/evidence`，在原 `fde7a0c` 基线独立恢复后核对一致，再三路应用到 `896cad481d03ae20d501a3b432cd70440a43d25f`。候选位于 `artifacts/platform-cloud-integration-20261118/integration`，分支 `codex/cloud-environments-main-20261118`；原候选和运行目录保留。业务代码无冲突，两个生成索引冲突按同步工具重建。主线 beta9 本地启动、注册和无重试按钮修复保留。Core/Protocol 锁不变，隔离 venv 为按锁非 editable 安装，实际导入来源单独记录。

检视依据为根、Web、frontend AGENTS，jw-review 技术方向和流程，S_01/S_02/S_04，既有账号/Router/E2A/Front Control/ProjectStore 及前端消费调用。覆盖全部51原文件、打包上下文与相邻旧调用者，不修改外部 Provider 源码。发现并以行为用例复现后修复：

- P1：取消准备任务直接释放租约，而 Git 下载线程仍运行。现在中断信号传到现有 Git 校验边界，等待线程及所拥有子进程退出后才保存 interrupted 并关闭服务。真实受控进程证明释放前已退出。
- P1：慢速检出后换连接，同云账号仍可发布旧准备。发布前重新核对仓库身份和本次 generation，保留原 operation 的固定 commit。
- P2：更换 GitCode 令牌遇认证/限流/网络失败会删除原连接。按 generation 条件恢复原记录，并拒绝并发替换；期间断开不复活旧授权。
- P2：打开 GitCode 令牌表单仍保留旧选仓。现在立即清空选仓并禁用准备。
- P2：标准 Docker build context 的白名单遗漏官方 gh archive，导致 Gateway COPY 失败。已同步 context.dockerignore 与部署说明，固定官方版本和摘要保持。

原整合候选279项云端测试通过（cloud-baseline.log），7组前端共101项通过（frontend-baseline.log）。新增边界用例首次5失败/1通过（review-reproductions.log），修复后专项25通过（review-fixes.log），完整云端/数据同步/项目/文件边界/同源桥相邻回归416通过（cloud-final.log）。前端新增旧选仓回归后 cloud-environment 14通过，Vite 生产构建通过；本地遵守不运行格式化/静态检查约束，类型构建留给既有 Stable CI。

真实云端读取确认 chain-1112 登录成功、GitHub leemine 已连接、有原 code-platform 准备项目；GitCode 返回 disconnected。该状态如实留档，不能由用户拥有 GitCode 账号推断已完成连接。候选正式 UI 通过 init_workspace/start_services 在隔离不可变源码快照启动，连接原云端严格校验 CA；未更换生产镜像或账号配置。远端 CI、真实仓库流程与最终提交结果在后续记录补充。

最终复查追加两处 P2 恢复问题：关闭弹窗发生在初始 prepare 回应前，旧 busy 标记会阻止重开后的重试；现在新一代视图立即重置 busy，后端操作与原 ID 保留。已有环境选择遇登录过期时，续办误入创建入口；现在重新打开环境列表。新增行为用例与原回归共104项通过（frontend-recovery-final.log）。Front Control/项目 repository/E2A 旧调用者58项通过（control-regression.log），补充关闭准入竞态3项通过（lifecycle-race.log）；既有 Stable 扩展相同58项入口。

真实验收使用 chain-1112。用户亲自在候选界面输入 GitCode 令牌，后端确认 gcw_4B3FcW3D 已连接；令牌未进入聊天或证据。GitHub 新项目 cloud-review-1118-github 固定 leemine/code-platform 的 `896cad481d03ae20d501a3b432cd70440a43d25f`，GitCode 新项目 cloud-review-1118-gitcode 固定用户指定 gcw_4B3FcW3D/ai-team-coding-finance-lab 的 `6f1fa2ec85875bc5ae6e323472d42e3df9a48b3f`。经现有云桥真实准备后，独立只读检查运行实例内两目录的 Git HEAD、main 分支、无凭据 origin 与干净工作区一致（live-workspaces.json）。另有用户在同一表单尝试 agent-store 后收到 GIT_OUTPUT_LIMIT 的失败回执；未将该失败当作成功，也未重试非指定仓库。

用户在 GitCode 项目中亲自发送 hi 和来源核对问题，实际 Deepagent 返回正常，第二条回答的来源与独立 Git 检查一致；本次自动验收没有配置模型或发送模型消息。最终候选通过正式启动器重启，保留同一隔离 home/配置/登录；刷新后同一云会话恢复两个用户消息与回复、项目绑定和头像（final-candidate-gitcode-recovered.jpg）。第一次正式 stop 返回退出未确认，随后确认原 launcher 已退出、四个本任务专用端口均释放，再次正式 stop 清理登记成功；只重启本任务实例。

真实联验范围是最终本地 UI/同源桥与当前线上 gitcode-20261117-r1，不将旧线上服务记为新 Gateway/AgentServer 已部署成功。新服务端修复由上述行为、真实受控 Git 子进程与隔离镜像验证覆盖；本次不更换生产镜像。

从最终不可变源码快照构建干净 wheel，与1607项 Python 源码及255项前端资源逐项一致。标准 Dockerfile 与白名单上下文无网络构建三个角色，并在非 root、只读根目录、无网络、无用户数据挂载的临时容器内逐项核验1862资源、锁定 Core/Protocol 来源和实际 import；project.import 能力含 GitHub/GitCode，官方 gh 2.104.0 只在 Gateway 存在（docker-image-verification.json）。

Wheel SHA-256：`314bb0179be8e843b350536e60f134a96421175e25a0dea04157b309b6b1c7f7`；源码/前端 manifest SHA-256：`bd0cf356f517b3dd1ae0fcf8cfab05e7a9fcb76459712f92fa399b084e786c88`。

- gateway 验证镜像：`sha256:2371178d49caaa8bcaa4d281fd4f448f9a0ebf49a2f63d61e0ad8e5e43245799`。
- agentserver 验证镜像：`sha256:6d89c554bcb0ed22716a255166a88333be53b8923e4b128bb56ab044793bb848`。
- account 验证镜像：`sha256:98cdffe31c00393adb5d8c2cf15e6015fb6f739288452c981a2a65f8204ae968`。

以上镜像是隔离构建验证资产；生产 Account、edge、CA、Gateway 与 Runtime 绑定未替换。提交/Stable/合入结果以随后真实记录为准。
