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
