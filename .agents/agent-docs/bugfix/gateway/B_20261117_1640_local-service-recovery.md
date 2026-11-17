---
id: B-20261117-1640-local-service-recovery
title: 本地预览退出恢复与账号错误分层
type: B
author: leemine
author_email: leewanlong@gmail.com
designs: []
design_note: 用户明确要求修复现有本地服务退出与登录提示，不新增执行架构。
modules: [deploy/local, jiuwenswarm/channels/web]
files: [deploy/local/systemd/code-platform-local.target, jiuwenswarm/channels/web/app_web.py, jiuwenswarm/channels/web/frontend/src/services/accountAvailability.ts, jiuwenswarm/channels/web/frontend/src/services/organizationCredentialEvents.ts, jiuwenswarm/channels/web/frontend/src/features/cloudWorkspace/CloudWorkspaceGate.tsx]
---

# 问题与根因

本地29011入口显示“暂时无法连接账号服务”，实际该端口没有监听者。原三个任务进程通过Popen启动并脱离终端，没有持久服务注册。原日志最后业务记录为2026-11-16 22:59，journal证明其后发生多次系统重启，当前系统启动于2026-11-17 14:30；旧PID均不存在。重启足以终止旧进程，缺少托管导致重启后不会恢复。首次终止的精确信号没有被旧脚本记录，不能声称已确定首次退出是崩溃、OOM或代理所致；定向内核检查未见该时段OOM证据。

浏览器已加载页面仍运行JS；账号检查将网络错误、HTTP错误和账号权威失败统一渲染同一提示，造成错误归因。手动恢复原三个进程后原登录会话恢复，证明不需要重置账号或关闭证书校验。

# 修复与边界

基线origin/main及HEAD为fde7a0c940dcbb056c28833f378fd9e25a996849；独立codex/platform-local-recovery-20261117候选。GitCode未提交候选及主线checkout不改动。新增标准用户级systemd部署模板，三个原进程分别托管，Restart=always/3秒、60秒5次启动限制、PartOf统一停止；保留原数据及CA。用户登录后自动启动，不启用linger，不重启主机验收。

前端最小可用性分类与原Gate/登录表单复用：本地连接失败、远端网络失败、明确的云账号权威错误、未知状态错误。原web代理对本地上游连接失败给出可分类码；上游503及认证拒绝仍原样透传。无身份缓存、无密码重发、无认证绕过、无模型配置/调用。

# 验证

证据位于管理工作区`artifacts/platform-local-recovery-20261117/evidence`，不纳入产品仓日志或凭据。

- 按锁安装及实际来源：Core e089198835426cd7681761b0cc278670cd83031f，Protocol 2a0457e5e01152e9ca5f8afdffd84716227046ca，import-provenance.json记录实际路径；未升级依赖。
- 受影响前端：`node --test tests/cloudWorkspace.test.mjs tests/localCloudAccount.test.mjs tests/codeWorkspaceControls.test.mjs`，63项通过。受限沙箱第一次只报告文件退出，不计作用例成功；完整本机环境重跑才作为最终结果。
- 后端真实本机HTTP/WS：`pytest tests/unit_tests/channels/web/test_account_proxy_availability.py tests/unit_tests/channels/web/test_app_web_ws_tunnel.py tests/unit_tests/channels/web/test_web_static_cache_headers.py -q --no-cov`，8项通过。
- TypeScript/Vite构建通过；systemd单元配置验证通过。没有运行格式化或静态lint。
- 右侧29011：Gateway进程KILL后显示本地服务提示，自动恢复后原账号头像及主界面恢复，无再次提交密码。云账号错误使用任务专属29151真实HTTP响应503/`AUTHORITY_UNAVAILABLE`验证同一构建页面；这是故障注入，不冒充真实云服务宕机，真实云端未停服。
- 第一轮恢复脚本误把本地账号端点404视为未就绪，脚本失败；systemd及界面实际已恢复。随后修正探针，正式3秒恢复配置下复测Gateway HTTP恢复7760ms、Web恢复3404ms；保留该验证偏差。三角色最终恢复记录及截图以证据为准。

# 交付限制

用户服务已在授权本机启用，配置指向当前独立候选及既有数据。不得删除该工作区；升级需停止对应服务后切换来源并复验。未执行真实主机重启/用户注销，登录自启动依据已启用default.target依赖，故障恢复依据真实进程退出验收。systemd不检测所有进程内部卡死，触发连续失败限流后需人工修复。本记录描述合入前候选验证；最终提交、CI及主线复验以关联PR和管理验收记录为准，不沿用旧SHA的成功结论。


2026-11-17交付检视：核对同源客户端、Gate/登录表单消费者、Web代理错误生产方与systemd停止/重启语义，未发现阻断项。stable两个安装profile均增加真实HTTP代理分类测试，前端既有cloud-workspace套件覆盖新提示。系统托管为Linux独立Web的显式部署选项，不进入桌面启动链或擅自安装到其他环境。
