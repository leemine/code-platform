# SuperAgent 工单插件

插件由 code-platform Gateway 装载。用户在 Web 提交显式工单，平台无工具 Router 产生接单、忽略或关联决定。插件复用固定提交的 SuperAgent Core 和策略，并以 SQLite 保存工单、执行请求与会话关联。Worker 通过平台现有 OpenCode 执行，运行无需 DSH。

构建运行产物后随平台 wheel 安装，按英文说明在隔离 Gateway 配置中启用。试点配置必须绑定已登记的 Code 项目、平台账号和 OpenCode 兼容模型。安装时需要现有平台 Native 能力供声明式 Router 使用。

停止回执丢失时，工单保留为待核对。已有平台会话的工单可使用「重试停止」确认原会话的状态。
