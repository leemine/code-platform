---
id: B_20261116_1927_desktop-cloud-account-package
title: 桌面安装包云账号扩展与 Windows 配置权限
type: B
author: leemine
author_email: leewanlong@gmail.com
designs: []
design_note: 修复既有桌面安装和云账号接入，不改变账号或运行时架构。
modules: [desktop]
files: [scripts/jiuwenswarm.spec, scripts/verify_external_bundle.py, gateway/services/data_sync/ui.py, .github/workflows/windows-external.yml, tests/electron/packaged_cloud_account.py]
---

# 桌面安装包云账号扩展与 Windows 配置权限

beta7（`f116e1e5d9f49893edc8f777cf2377824caae633`）将 Gateway 扩展模块收进冻结代码，却漏掉了扩展发现需要的 `gateway/extensions/data_sync/extension.yaml` 和 `extension.py`。未注册的状态路由返回 404，前端按可选功能关闭处理。Windows 加载本地云账号配置时还会调用仅 POSIX 支持的 `os.getuid()`。

共享冻结配置现在收录这两个文件，构建自检从实际冻结扩展目录读清单并加载入口。Windows 使用现有锁中已安装的 pywin32 读取打开文件的所有者和 DACL。POSIX 保持所有者与权限检查，两个平台都拒绝非普通文件和符号链接。Windows 安装器、Linux DEB 和 TAR.GZ 的交互验收对隔离的 HTTPS 账号服务执行登录、左下角头像和退出检查。
