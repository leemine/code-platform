---
id: B_20261116_2210_windows-cloud-account-autostart
title: Windows 双击启动时启用云账号
type: B
author: leemine
author_email: leewanlong@gmail.com
designs: []
design_note: 沿用已有云账号桥接和桌面启动契约。
modules: [desktop]
files: [gateway/extensions/data_sync/extension.py, gateway/services/data_sync/ui.py, gateway/extensions/data_sync/windows-cloud-root.crt, scripts/jiuwenswarm.spec, tests/electron/packaged_cloud_account.py]
---

# Windows 双击启动时启用云账号

beta8 只有 Gateway 进程读到显式配置才显示云账号入口，普通安装后的双击路径没有这项配置。Windows 冻结桌面从已选的实际端口生成回环地址，并在显式配置和用户私有配置缺省时连接用户确认的现有云端。随包 CA 公钥的 DER SHA-256 为 `212e4d574cb068fb4c0cb87fd1ed52d96eeb349d73b1ad6da9be5ac9934d06ac`，使用该 CA 验证现有云端并读到正常未登录状态。安装标识在数据目录内持续使用。

Windows 安装器回归覆盖干净启动的默认登录入口，以及同一安装版通过私有配置连接隔离 HTTPS 账号服务时的登录、头像和退出。测试进程不设置云账号环境变量。

## 2026-11-17 Linux 安装版跟进

发布的 beta9 DEB 包含 `data_sync` 扩展清单和入口，但安装版不设云账号配置直接启动时，Gateway 不装配本地账号路由。桌面工作台正常加载，`GET /api/v1/data-sync/status` 返回 404，左下角账号按钮隐藏。原 Linux 安装验收从环境变量取得测试配置，因此没有覆盖直接启动。PyInstaller 当时仅在 Windows 构建中收录默认云端所需的 CA。

Linux 冻结 Electron 桌面复用 Windows 的同源桥接、云端地址、CA 和用户配置优先级。新验收先以无私有配置的包启动，验证默认回环路由和圆形登录按钮，再以同一安装版的私有配置连接隔离 HTTPS 服务验证注册、登录、头像和退出。当前契约见 [S_03_data-sync-directory](../../specs/gateway/S_03_data-sync-directory.md)。

## 2026-11-18 本地工作台首屏

完整安装版的 Web 服务早于 Gateway 启动，原入口会先显示「云工作区」并探测组织登录接口。Windows 和 Linux 的完整打包入口标记同源桌面前端，直接渲染工作台。可选账号控件等待本地连接就绪后加载状态。云端网页与纯桌面外壳继续通过原门禁。

本地登录弹窗曾在打开后异步查询注册策略，导致「创建账号」稍后才出现。入口改为随未登录表单一同渲染，由已有云端注册接口在提交时判断是否允许注册。旧版客户端的查询接口仍可用。
