---
id: B_20261110_2036_codex-context-window
title: Codex 自定义模型上下文窗口传递与目录上限
type: B
author: leemine
author_email: leewanlong@gmail.com
designs: []
design_note: 对现有模型解析与 Codex 配置接缝的修复，不新增执行链。
modules: [gateway/common, jiuwenswarm/common, jiuwenswarm/server/runtime/agent_adapter/providers]
files: [gateway/common/model_selection.py, jiuwenswarm/common/model_routing_registry.py, jiuwenswarm/common/codex_adapter_config.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py]
---

## 现象与根因

产品基线 f062cb1380eeeaf48b2af2007100997b9484a05b，官方 SDK/CLI 0.163.0。
火山 deepseek-v4.1-flash 的短调用成功，但显式 `model_context_window=1000000` 仍报告 258400。
真实 `config/read` 已读到 1000000，进程参数、线程 config 和全局 model 三组对照均相同。
固定官方源码 rust-v0.163.0（83086188ae0614bd882818ff1aa23f3194962012）中，
`codex-rs/models-manager/src/model_info.rs` 的未知模型默认 context/max_context 均为 272000；
`with_config_overrides` 取配置与 max 的较小值，原生可用窗口再乘 95%，因此为 258400。
较小配置 200000 实测报告 190000，配置并非没有加载。

平台 ModelCatalog 已保留 `model_config_obj.context_window`，原外部执行 request_defaults 刻意剥离内部字段，
但 ResolvedModel 没有独立的窗口元数据，因此 Codex 接缝没有得到这个值。
不能取消 request_defaults 的剥离，更不能改 UI 数值或改 SDK。

## 修复决策与边界

- ResolvedModel 增加进程内 context_window；原解析器复用 parse_positive_int。序列化排除该元数据，保留 Core 编译请求和 Claude/OpenCode 旧模型指纹；model_copy 仍保留它。
- Codex model_overrides 将有效值传到官方 model_context_window。未配置/按现有规则无效的值不新增覆盖，不给其他 Provider 改默认值。平台 `1M` 原有语义是 1048576；精确十进制百万使用 1000000。
- Codex 原 Third-party Agents 配置增加可选绝对路径 model_catalog_json。配置由部署方提供，声明所用模型的真实能力/最大窗口；不从别的模型猜测能力，不自动生成第二套模型目录，不写用户全局 Codex 配置。
- Adapter 启动时读取并固定目录内容，用原 settings_revision 绑定摘要；会话私有目录中原子物化 0600 文件，通过官方配置入口加载。路径移动但 JSON 内容等价不改变绑定；源文件后续变化不污染已启动会话。下次恢复内容不匹配则拒绝，不重建原生线程或重放旧历史。
- 显式目录没有所选模型或有重复 slug 时，在启动 SDK/发送模型请求前拒绝；原生完整目录 schema 仍由 CLI 校验。模型窗口单独参与 Codex 原模型指纹，窗口变化不静默应用于旧会话。
- 未配置新窗口/目录的旧绑定指纹不变。原先窗口被忽略的已有会话不会自动迁移到 1M；新验收配置使用新会话，旧会话保留原配置/版本与绑定。不得批量删除旧绑定以强行升级。
- 不修改 SDK/CLI、依赖锁、Runtime 调度、账号、实例链、权限系统或前端。目录是显式部署配置，移除后回到原生模型目录行为；这会改变配置绑定，只对新会话生效。

## 验证与证据

隔离候选：`artifacts/platform-prelaunch-validation-20261110/context-fix/platform`；
原始证据：同级 `evidence/`，其中 test-command.json、tests.log、server-context.json、
sdk-config-comparison.json、sdk-catalog-comparison.json、facade-context.json、facade-summary.json。
本轮用原按锁 Python3.13 环境加载候选源码；不把本地源码验证写成已发布镜像结果。

- 服务端 Responses 接受合成输入 300058 和 1000058 tokens，均返回预期标记；1050000 次重复的负例返回 400，报告输入限制 1048568 tokens。GET models 未声明上下文容量；不把该错误中的输入限制混同为所有请求的总窗口。
- 官方 SDK 正常配置目录后 1000000 报告 950000；较小覆盖 200000 报告 190000。
- 真实原 Facade → ModelCatalog/Resolver → ExecutionInput → CodexAdapter → 官方 SDK/CLI → 原用量事件：1000000/950000、1M/996147 均通过；310273-token 输入成功，无工具调用；Adapter 重建后恢复同一原生线程并报告950000。未伪造 usage，未改原投影。
- 定向回归覆盖配置读取、模型选择、Core 编译/Team、Codex FakeClient、恢复绑定；最终196项通过、3项跳过；首轮新增负向测试3项清理后对象引用断言错误已修正并全部重跑通过。3项需显式开关的原 live-provider 测试跳过；本轮真实 Codex 验证单独留证，不能替代 Claude/OpenCode 全量验收。
- 沙箱中 asyncio.to_thread 唤醒挂起，限制外同一隔离用例通过；作为环境阻塞记录，不改产品生命周期规避。探针初稿括号错误在发请求前修正，不是产品失败。

完整浏览器 UI、云实例运行镜像、长文本检索质量、1M 上下文多轮压缩与工具质量未在本轮验收。
不部署现网、不操作旧账号实例和数据；候选尚未提交/推送/合入。
