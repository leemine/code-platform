---
id: F_20261029_2258_agent-adapter-boundary-validation
title: AgentAdapter 无 Core 边界实验
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [agent_adapter]
files: [jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ExecutionPicker.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/ExecutionPicker.css, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx, jiuwenswarm/channels/web/frontend/src/stores/sessionStore.ts, jiuwenswarm/runtime/session/coordinator.py, jiuwenswarm/runtime/plan.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_equipment.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/control/config_service.py, jiuwenswarm/common/model_routing_registry.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/runtime/service.py]
designs: []
design_note: 用户授权的隔离验证；设计及证据在管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 第10节，初轮事实见第10节，后续第1～2阶段见第11节及当前 S_02 规约；未发布。
---

# AgentAdapter 无 Core 边界实验

## 首轮（历史结果）

仅增加已安装 entry point 的显式工厂选择，重复名称和无效工厂结果拒绝，原默认 Native 选择保留。没有新增状态机/队列，也未修改 Core、官方 Provider 或 interface.py。不是已完成的外部 Provider 实现，不发布。

用户目标是外部单 Agent 路径不依赖 agent-core，不能复用 Core-backed 外部 Harness 路径作为验收替代。实际未安装 Core 的环境中，工厂探针8项通过；原上游和候选公共 Facade 都因 ExtensionRegistry 导入 Core AsyncCallbackFramework 失败。完整按锁环境中现有宿主回归51通过、1项 Windows 专属跳过。先前受限环境超时保留，放宽执行限制后闭合，未确认更深根因。

工厂仅验证安装/选择，不是 Provider 验证；真实 Provider/渠道、恢复/审批/取消、无 Core 生产 request 仍待验收。后续先解除公共入口强依赖，明确协议外生命周期方法，再做真实 OpenCode 和第二 Provider。此实验未定义新的长期公共 spec。

工作区同级 evidence/ 下保存 no-core-import-gate.json、no-core-factory.xml、host-regression-unrestricted.xml 和超时日志；probe_tests/ 下为外部验证夹具，不进入默认产品测试集合。完整命令与来源见同级 management/docs/verification/AGENT_ADAPTER_BOUNDARY_VALIDATION_20261029.md。


## 第1～2阶段实施与实际结果

用户继续授权推进无 Core 公共入口及 OpenCode 官方接口闭环。把 Core 相关输入/初始化/建议 fork/技能演进加载留在 Native 能力调用时；原共享谓词和类型重导出保留。补足现有 AgentAdapter session/cleanup 契约，外部控制使用原 Runtime 控制入口，生产者与调度仍由宿主拥有。没有复用 Core-backed external_harness_helpers 作为目标实现，没有修改外部源码或降低权限保护。

实际无 Core 环境经 AgentRuntime.stream 完成文本、允许一次后退出码0/7、权限拒绝、取消与历史收尾。官方 OpenCode1.18.18 借用隔离服务，原生 permission=ask；真实副作用/历史/退出码断言4项通过。未知退出码仅确定性测试覆盖，真实命令均返回码。Native 按锁定向回归512通过、2项原 Windows 专属跳过；无 Core 回归25通过（含8项安装工厂探针）。Web 归一化8、组件11、生命周期19项通过，Vite 构建通过；浏览器拒绝 file://，视觉截图未完成。

实施中真实发现并修正：助手输出混入用户提示、Native 建议后处理误导入、提取 Rail 后缓存旧 forks 对象导致测试挂起、取消历史错误标为 error、异步历史清理越过事件循环。原失败日志保留。新增审批测试曾错误地让模拟服务在审批答复前结束；修正服务夹具的等待行为，未放宽产品断言。模型自行拒绝未发起工具调用的轮次不计审批/取消验收。

最小后端闭环完成；完整渠道、视觉验收、第二 Provider、独立包、正常无 Core 安装/锁组合及发布仍未完成。主目录、旧候选及 Core 未改。最新验证/限制见同级管理仓 docs/verification/AGENT_ADAPTER_NO_CORE_IMPLEMENTATION_20261029.md；不沿用首轮仅工厂注册的范围和失败结论描述当前候选。


## 2026-10-30 审阅范围组织

用户确认按A宿主解耦、B OpenCode后端、C Web展示三个范围组织当前候选。产品文件分别18/1/11，测试分别1/1/3；规约与文档7份作为共同说明保留。interface.py整体归A，内含取消终态和清理等通用修复，审阅时应单独判断必要性；B测试包含A+B实际Facade的联合行为。补丁按固定基线顺序重建后35个产品/测试文件与候选一致，源码和暂存区未变；没有新提交或新的运行验收结论。

审阅分包不是独立发布承诺。后续正式拆提交应补各截点验证；当前已验证的是组合候选，完整Web/视觉、第二Provider和安装拆包仍未完成。详细文件清单与快照见同级management/docs/verification/AGENT_ADAPTER_REVIEW_SCOPES_20261030.md，任务状态仍以管理仓台账为准。


## 2026-10-30 最小宿主接口收敛

用户明确要求默认继续兼容agent-core。本轮固定Manager→Runtime/Facade的选择传递，避免环境重读导致启动与执行不一致；把build_query和deliver_control_input_impl明确为必需契约。Native原答案转换移入native_inputs，Deep/Code共用；旧静态入口兼容，控制恢复仍用原stream并关闭内层流。OpenCode仅调整输入返回契约，不修改官方源码。

Native受影响307通过、1项Windows跳过，无Core26通过；真实OpenCode退出码0/7、拒绝、取消4项与历史/独立副作用通过，session清零并停止任务服务。新测试验证默认真实Deep/Code工厂、答案转换、控制关闭及选择固定；Native模型初始化使用替身，不宣称真实模型验收。旧测试替身缺新契约已接回真实Native方法，原断言保留；探针正常重装，失败证据保留。

7个产品文件、5个测试文件为本轮增量；旧A/B/C patch成为历史快照。任务evidence/host-refinement-source-manifest.json和management/docs/verification/AGENT_ADAPTER_HOST_REFINEMENT_20261030.md记录版本、命令与限制。默认Core声明/锁未改，未提交发布；完整渠道/视觉、第二Provider、Core可选安装、Native真实模型和Protocol可选Team能力仍未交付。


## 2026-10-30 UI新会话选择

按用户确认在新会话选Provider，既有会话保持绑定。现有ChatModelSelector旁复用Select，设置页使用声明式字段；执行选择与模型选择分离。metadata保存execution_provider，Manager缓存按Provider/配置区分，取消尊重会话绑定；外部默认Runtime按需获取原Native共享资源，不新增调度器。Native模型payload兼容保留，OpenCode不接收Native模型/MOA或预热。连接快照仅保留于活跃实例，空会话及冷恢复限制如S_02。

Python274通过、无Core26通过；前端Provider3、模型22、入口4、草稿1通过；设置页62通过2项上游同样失败。真实Native→OpenCode→原Native与真实创建处理器闭环通过；浏览器产品组件宽/窄容器检查通过，配置服务为模拟，不作为完整Gateway渠道证明。错误与修复、命令、实际导入和脱敏证据详见同级management/docs/verification/AGENT_ADAPTER_UI_PROVIDER_20261030.md。状态：未提交/发布，完整渠道待验证。默认Core、历史和UI关联保留；未改外部源码。


## 2026-10-30 共享模型与完整Web渠道

用户要求最小改动复用Swarm业务。撤掉独立Provider设置表单，仅聊天下拉；原模型目录/选择/selection.set复用。ModelSelectionResolver新增默认兼容的请求配置构造接缝，OpenCode转换不初始化Core模型；官方服务通过启动快照消费Swarm配置，不在聊天中修改服务。旧显式模型配置兼容，未映射协议/参数与过期快照拒绝。

真实联调发现config.get前置服务绕过兼容handler，以及Web三段canonical mode此前未接受；分别接入真实control/config_service并复用既有模式归一化。未加第二队列、代理、模型目录或权限框架。Python322、无Core27、前端29通过；设置页62通过2既存上游失败；Vite成功。真实Web双模型、审批/退出7、拒绝/取消后继续、Native以及刷新绑定通过；无Core真实双模型也通过且无Core模块。完整证据见管理仓AGENT_ADAPTER_SHARED_MODEL_WEB_20261030.md；上一节组件模拟不能冒充此结论。配置快照刷新、独立插件、第二外部Provider和冷恢复等限制保留。未提交/发布。


## N01～N04 装备接入（2026-10-30，未发布）

用户授权执行接入/模板/Skill/MCP。复用原资产门禁、SkillManager、CredentialStore、Facade装备三态和session_metadata，不改前端控件。新增OpenCode可移植装备转换和会话自有官方CLI资源管理，官方Skill/MCP作用域迫使借用URL模式拒绝挂载；模型仍用原Swarm目录，冷恢复未解决。宿主新增supports_native_plan_state及普通Code条件共10行，Native默认保留。

真实验收修复normal子模式、普通Code误导入Core Plan state、Swarm宽松Skill头兼容和并行审批覆盖宿主单门；超时有明确错误，迟到回复不恢复轮次。104项受影响回归、31项无Core回归通过；无Core真实Code两会话5轮含模板、Skill资源、MCP、清空及关闭通过，原完整Web选择/三项审批/资源返回及刷新通过。鉴权MCP及控制最终结果、失败过程与限制见管理候选docs/verification/AGENT_ADAPTER_N01_N04_IMPLEMENTATION_20261030.md。

不把fixture安装记录视为市场/UI首次授权；不把旧鉴权脚本passed字段视为取消成功，必须核验cancelled事件。未修改Core、锁或外部代码。主包Core依赖、独立插件、第二Provider、OAuth刷新、完整Code Diff/撤销、冷恢复与发布均未交付。


2026-10-30最终收尾补充：真实审批超时暴露原协调器保留等待门，现消费已有runtime_completion并在流释放后按成功/失败/取消收尾，保留无终态的等待语义，不建新调度器。复用原chat.interrupt_result关闭权限卡，随后错误终态保持provider_timeout；最终Web同会话继续返回RECOVERED。受影响141、无Core34通过；带鉴权MCP拒绝、取消历史与继续闭合。模板清除只停止下发system并清空装备，不删除历史；实测仍可沿用旧标记，不声称模型遗忘。完整限制和证据以N01～N04实施验收记录为准，未发布。

## 2026-10-30 项目选择回归补齐

固定工作区的旧验收没有覆盖 UI 选择其他项目；本轮补齐自有服务会话绑定，见 [故障记录](../bugfix/agent_adapter/B_20261030_1455_opencode-session-workspace-binding.md)。本轮146受影响/39无Core回归、真实两项目和 Web Code/Extensions通过，未发布。

## 2026-10-30 权限档位修复

按用户批准补齐原全局权限配置→直连Provider原生规则和会话生效状态；详见 B_20261030_1607_opencode-permission-profiles 及 S_02。新增可选状态契约、Worker原快照投影与原下拉状态，未修改Native执行路径/Core依赖。候选验证记录和限制以该B及管理验证记录为准，未发布。

## 2026-10-30 动态执行引擎目录与原控件

复用主工程ExecutionPicker展示替换试点Select，移到权限后、模型前；后端使用原entry point和工厂公开元数据，保留旧字段。删除store的两个名称白名单而不破坏创建/恢复。12项Python、4项前端行为测试和独立Vite构建通过；受限环境异步测试超时单列，宿主同测试通过。真实Code模式创建项目/选择OpenCode/持久绑定成功；首轮原生TLS失败准确显示，第二次人工同会话读取测试文件成功。未关闭校验、未修改外部源码，TLS底层诱因仍未闭合。详细命令、来源、失败和证据见管理仓PROVIDER_MENU_CODE_VALIDATION_20261030.md。无新Provider实现或发布。
