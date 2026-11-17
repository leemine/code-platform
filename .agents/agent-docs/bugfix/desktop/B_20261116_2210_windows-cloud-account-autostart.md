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
