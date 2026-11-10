---
author: leemine
author_email: leewanlong@gmail.com
id: B_20261110_0135_cloud-file-boundary
title: 云文件代理符号链接越界修复
type: B
modules: [gateway/routing, jiuwenswarm/server/runtime/gateway_adapter]
files: [gateway/routing/workspace_files.py, gateway/extensions/agentos/agentos_router/router_client.py, gateway/services/cloud_instance_policy.py, jiuwenswarm/common/schema/message.py, jiuwenswarm/server/runtime/gateway_adapter/workspace_file_adapter.py, jiuwenswarm/server/runtime/gateway_adapter/workspace_file_io.py, tests/unit_tests/server/test_workspace_file_boundary.py]
designs: []
design_note: 本会话授权修复既有 B01，沿用原候选与实例链；无新增独立架构设计。
---

# 云文件代理符号链接越界修复

原候选在113.207.105.228经 `/file-api/file-content` 跟随工作区链接读取同实例认证文件。Gateway字符串前缀/`..`校验不能约束执行端软链接，readonly仅禁止写入。未证明跨账号访问或容器逃逸。

保留原HTTP接口、可信账号上下文、Router实例选择和Runtime适配器，在原文件能力中新增描述符受限操作；云账号策略分支转入原E2A，不改元戎SDK。codeswarm 24f29148 的 `governance/workspace_download._open` 与 `bound_workspace_files` 提供逐级FD/no-follow参考；没有迁入其Projects/会话治理依赖或另造文件权威。

宿主差额为Router四个既有文件方法的窄分支、启动根配置、原ReqMethod增量兼容注册，以及现有WorkspaceFileAdapter分派；读写实现封装为适配器内部模块，Gateway映射维持现有HTTP形状。旧客户端分支及旧绑定镜像不自动改变，安全能力不可用不回退SDK。拒绝所有符号链接（包括根内链接），为明确的兼容收紧。

本地23项新增测试通过；扩展328项中324通过、4失败，修复前r7快照同样4失败：两个session.delete测试桩缺enable_writeback参数、两个ConfigAdapter测试缺a2ui注册，不列新白名单、不改无关产品。codeswarm既有受限文件60项通过。真实服务器结果续写于本记录，管理测试报告保存来源摘要、命令、镜像、回执及旧服务保护证据。

复查兼容修订：`000`仅用于mkdir权限边界测试，不是隔离配置或修复手段；默认目录权限仍0755（受umask约束）。新建最终目录成功后不再为确认类型额外读取该目录，因此显式mode=000不会被误报失败；已有目标继续验证真实目录/拒绝链接。递归中间目录采用正常权限，最终目录才使用请求mode。修订后24项边界专项通过，最终wheel与服务器复验另记录，未沿用前一镜像结论。

最终服务器回归：新K/L两账号、回环28680～28682、file-boundary-run-final独立目录；最终wheel646568f17f3e，Gateway9b771ea19aa2/Agent032e27b34bb5。255项依赖/1589源码摘要/8525 SDK文件保持；43项真实文件接口、24次目录替换读取、16项账号/8项WS/5项撤权通过。外部合成标记无修改。最终源代码与安装清单一致，未部署现网。

2026-11-10后续：既存4项测试夹具修复后，含最终mkdir兼容测试的相关329项全部通过。B01范围不变；另经两个新账号合成标记确认B02共享日志读隔离缺陷，不能将B01结论外推到工具/Shell的挂载可见性。当前上游develop550bc92b不含旧Gateway目录的信息来自用户补充，本轮不据此断言上游最新版仍存在或已修复该问题。
