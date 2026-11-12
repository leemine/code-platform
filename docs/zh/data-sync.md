# 显式项目目录同步（P1S-02 首轮候选）

此可选功能同步选中项目的名称、原生ID和工作模式；不上传文件、会话、历史或绝对目录，不改变执行位置。这是保留的底层集成能力，产品界面不提供清单发布或同步列表。真正的文件与会话同步尚未实现。

Gateway沿用原云账号配置，并由操作员设置 `CODE_PLATFORM_DATA_SYNC_ROOT` 为当前服务用户拥有的绝对、无链接、权限0700的私有持久目录。未设置时功能关闭。不要把同步目录挂入执行容器。

在原本地数据根配置下，通过原账号登录流程取得有效会话，将令牌注入 `CODE_PLATFORM_SYNC_ACCOUNT_TOKEN`；为该安装生成并安全保留随机32字节的十六进制 `CODE_PLATFORM_SYNC_SOURCE_PROOF`。环境变量须由可信运行环境注入，不放入命令参数、仓库或共享日志。首轮需要操作员管理凭据，不提供长期设备授权或安全存储。

```bash
python -m jiuwenswarm.data_sync --url wss://cloud.example/ws \
  --installation-id laptop-a --project ORIGINAL_PROJECT_ID
```

`--project`可重复，必须填原ProjectStore ID。另一个已登录同账号的安装可使用其独立证明及安装ID，执行 `--receive-only`。`--withdraw-all`只撤回本来源同步元数据，不删源文件。所有模式都是一次性执行，不自动扫描全部项目。远端必须使用正常校验证书的wss；私有CA用 `--ca-file`。不要将真实令牌写入URL；连接器拒绝重定向，避免令牌转发。

结果仅报告来源、水位、数量和本次状态，`account_complete=false`始终保留。副本位于原数据根 `data-sync/`，与可执行项目隔离。失败标记stale并保留旧副本及待处理回执；再次运行恢复，禁止手动删除待处理回执后猜测重发。来源撤销不能用旧证明重新注册。Windows安全导出、内容同步和GC尚待开发。


云端项目使用原Cloud环境：先通过原环境入口准备并连接环境，再显式发布其中的原项目ID：

```bash
python -m jiuwenswarm.data_sync --url wss://cloud.example/ws \
  --installation-id laptop-a --kind cloud --project CLOUD_ORIGINAL_PROJECT_ID
```

此时安装ID和证明只用于本地接收方；Gateway沿原认证/Router向云端角色读取，客户端不能自声明云来源或指定账号、实例、根路径。新Gateway与AgentServer须均支持云导出；旧版本明确拒绝。环境未就绪或离线时本操作失败，不自动启动、创建或回收实例，不撤回已有同步目录。云端`--withdraw-all`仅撤回该云来源元数据；`--receive-only`只拉取已接受目录，不读取云源或要求启动环境。

相同逻辑环境及工作区重建后，云来源ID保持且代次更新，旧游标失效；换工作区、已撤销或旧候选自声明的云来源需明确处理，当前不自动重新配对。丢响应后重跑保留的原操作，返回原提交回执；这不表示源当前在线。功能随原角色装配但仍按需运行，无定时后台同步。真实部署、恢复与打包CI结果见对应实施记录。


## 产品界面与本地云账号

Code 输入区保留三段式入口：左侧本地目录，中间 Local/Cloud，选择云端后显示右侧环境菜单，可选云端目录、新建文件夹和创建／准备云环境。这里不展示项目清单同步入口，不要求用户手动发布清单。选择项目后在对应位置工作；切换入口不搬运文件或会话。

本地 Gateway 可配置 `CODE_PLATFORM_LOCAL_SYNC_CONFIG`，指向当前服务用户拥有的0600普通JSON文件，以启用本地云账号登录：

```json
{
  "public_origin": "http://127.0.0.1:8080",
  "cloud_origin": "https://cloud.example",
  "installation_id": "laptop-a"
}
```

`public_origin` 必须是本机回环入口；`cloud_origin` 固定为可信HTTPS云端，私有CA可增加 `ca_file`。云端与本地接入配置互斥。若配置显式扩展白名单，须包含 `Project Directory Sync`。本地需原共享目录 AgentClient，不接到远端路由模式。配置名保留既有协议兼容，不表示登录会自动同步目录。

本地左下角“登录云账号”仅管理此本地入口的云账号会话，成功后显示账号及退出入口，不读取或发布项目清单。密码不持久化，令牌使用同源HttpOnly会话Cookie；账号改变时丢弃旧响应。云端入口继续使用原账号登录流程。

Local/Cloud导航分别由 `CODE_PLATFORM_CLOUD_ENTRY_URL`、`CODE_PLATFORM_LOCAL_ENTRY_URL` 配置；“云端未连接”表示缺少可导航入口，不是账号密码错误。操作员需配置浏览器可验证的HTTPS证书；不要关闭TLS校验或绕过证书提示。
