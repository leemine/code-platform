---
id: F_20261030_1939_external-desktop-builds
title: 可选 Native 与外部 Provider 桌面测试包
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [agent_adapter, desktop, gateway]
files: [pyproject.toml, uv.lock, scripts/jiuwenswarm.spec, scripts/build-electron-linux.sh, scripts/assemble-electron-linux.py, scripts/verify_external_bundle.py, jiuwenswarm/common/native_integration.py, gateway/extensions/registry.py]
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
