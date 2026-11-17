# Linux 本地服务托管 / Local Linux services

用于明确选择长期运行的本地 Web、Gateway 和 AgentServer。复用原三个服务进程，使用用户级 systemd 管理生命周期；不是新的执行器或会话监督层，也不改变桌面安装包自己的生命周期。

## 配置与启用

1. 准备已验证的安装/源码路径与构建后的前端，按锁安装依赖。保留已有数据、云账号配置及可信 CA。
2. 将 `systemd/runtime.env.example` 复制为 `~/.config/code-platform/local/runtime.env`，改为实际绝对路径，权限设为 `0600`。不在环境文件或仓库中保存账号密码、令牌、私钥。使用源码 checkout 时保留 `PYTHONPATH`；安装包运行时使用已验证的安装来源。
3. 核对现有端口和运行者，只停止本实例的旧进程；不要并行启动两套写同一数据目录的实例。
4. 将 `systemd/*.service` 和 `systemd/*.target` 复制到 `~/.config/systemd/user/`，执行：

```sh
systemctl --user daemon-reload
systemctl --user enable --now code-platform-local.target
systemctl --user status code-platform-local-web.service code-platform-local-gateway.service code-platform-local-agentserver.service
```

用户登录启动 user manager 后自动启动；此配置不启用 linger，不承诺机器无人登录时运行。意外退出（包括正常退出码）3秒后重启，每60秒最多5次启动，连续故障触限后保持失败供排查。手动 `stop` 不触发重启。`active` 只代表进程已启动，验收必须另查端口和真实页面/接口。

```sh
journalctl --user -u code-platform-local-web.service -u code-platform-local-gateway.service -u code-platform-local-agentserver.service
systemctl --user show code-platform-local-web.service -p MainPID -p NRestarts -p Result -p ExecMainStatus
systemctl --user stop code-platform-local.target
# 取消以后登录时自动启动，同时停止：
systemctl --user disable --now code-platform-local.target
```

运行路径必须持续存在；在原服务停止并核验新来源之前，不删除候选工作区或原地换版本。进程恢复不代表模型调用/Turn自动续跑，不自动重放用户输入或登录请求。配置错误触限后先修复再手动 `reset-failed` / `start`，不要加循环自动重置失败。

## 登录错误边界

- 浏览器无法连接本机 API，或本地 Web 明确报告本机 Gateway 不可达：本地服务连接提示。
- 服务端明确返回 `AUTHORITY_UNAVAILABLE`：云账号服务提示。
- 远端网页无法连接：网络连接提示；未知HTTP错误或无效身份响应不能直接归因于云账号服务。
- 保留原身份检查与恢复退避，权限不缓存；恢复后仍重新验证身份。登录表单不自动重发密码。

## English

These optional user systemd units supervise the existing local Web, Gateway and AgentServer processes. They do not replace Runtime, replay turns, or change desktop application lifecycle. Configure the absolute paths in `systemd/runtime.env.example`, install it privately as `~/.config/code-platform/local/runtime.env`, and install the units in `~/.config/systemd/user/`. Check ownership and stop only the old instance before enabling the target with the commands above.

The target starts with the user's manager at login; linger is not enabled. Unexpected exits restart after three seconds, limited to five starts per minute. Explicit stops remain stopped; persistent configuration errors require investigation rather than a reset loop. Verify actual endpoints and UI, not only systemd's active state. Keep the configured runtime directory intact while services use it. Credentials and CA material remain in the existing private deployment configuration.

Account status errors distinguish a local transport failure, an explicitly reported cloud authority outage, a remote network failure, and an unclassified status failure. Recovery retains fresh permission checks and never resubmits credentials or user operations.
