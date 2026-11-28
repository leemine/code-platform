# SuperAgent 原界面插件

插件由 code-platform Gateway 装载。用户在 WorkSwarm 的 Workbench 提交显式工单，平台无工具 Router 产生接单、忽略或关联决定。插件复用固定提交的 SuperAgent Core 和策略，并以 SQLite 保存工单、执行请求与会话关联。Worker 通过平台现有 OpenCode 执行，运行无需 DSH。

构建运行产物后随平台 wheel 安装，按英文说明在隔离 Gateway 配置中启用。试点配置必须绑定已登记的 Code 项目、平台账号和 OpenCode 兼容模型。安装时需要现有平台 Native 能力供声明式 Router 使用。

停止回执丢失时，工单保留为待核对。已有平台会话的工单可使用「重试停止」确认原会话的状态。

WorkSwarm 侧栏提供 **SuperAgent** 原管理面板和 **Workbench**。在 Workbench 发首条消息后，选择原话题继续输入，或打开绑定的 WorkSwarm 会话追问。两条入口沿用已有 Ticket、平台 Session 和 OpenCode 会话。OpenCode 工具许可在 WorkSwarm 的原生审批卡提交，Workbench 的业务裁定用于 Worker 报告提出的业务问题。临时工单页仅在配置 `superagent.acceptance_page: true` 时出现。

原管理面板展示 WorkSwarm 的来源、线程、Router 决定和工单信息。部署配置只读，原宿主的配置写入、持久 Router 主会话和主动触发留待后续。Workbench 的内置目录来自原型快照，版本正文和用例在接单时固化。所有原始界面输入均按 `frontend/vendor/SOURCE.json` 核验。
