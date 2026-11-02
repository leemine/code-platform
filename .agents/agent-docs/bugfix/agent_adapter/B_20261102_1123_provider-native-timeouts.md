---
id: B_20261102_1123_provider-native-timeouts
title: 外部 Provider 模型超时与整轮时限职责修复
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/runtime/agent_adapter/providers, jiuwenswarm/common]
files: [jiuwenswarm/common/claude_adapter_config.py, jiuwenswarm/common/codex_adapter_config.py, jiuwenswarm/common/config_panel/config_set_handlers.py, jiuwenswarm/server/runtime/agent_adapter/providers/claude.py, jiuwenswarm/server/runtime/agent_adapter/providers/codex.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py]
designs: []
design_note: 用户在本会话确认超时职责修正与官方配置复用方案，无独立 D 文档；续写当前外部适配器契约，不修改已归档设计。
---

# 故障与根因

2026-11-02 桌面 beta2 同工程架构分析：Codex 125.4 秒成功；OpenCode 总156.6秒，其中生产者前准备37.4秒、生产者119.1秒成功；Claude 186.1秒失败、已返回13次工具结果。Codex/Claude 所选模型均未设置 timeout，故先前“Codex因1800秒配置成功”的推测不成立。Claude/Codex 把模型 timeout/default180 作为整轮限时；OpenCode另有default120整轮限时。三家拥有自己的模型传输边界，无需由宿主猜测模型调用停滞。

# 决策与实现

删除 Claude/Codex 隐式整轮预算，OpenCode 保留显式 turn_timeout，不设置隐式预算。按当前 S_02 映射原生配置，保留 SDK/CLI 原生保护、重试和错误权威。Claude 首字节/流空闲参数采用 Provider 专有配置；Codex 模型 timeout 不等价于 SSE idle，不强制映射。OpenCode 映射响应头和 chunk 超时。原配置面板保存会重建 Provider 条目并丢失专有参数，故仅扩展其保存兼容：保留已有字段，仍只更新开关/路径，不增加控件或流程。

Claude 改用官方 connect/disconnect，保持同一生产者/AnyIO任务所有权；关闭失败保留 fence。Codex 对没有原生终态的非用户取消退出也保留 fence。OpenCode 显式预算到期核对 abort 后 native session/status；ACK不能证明停止。两项旧 Codex 测试改为验证未确认停止时不允许续聊，不跳过原场景。

# 来源与验证

基线 origin/main f5bd05f980b61a37448aa26ffa1618ac06e5b62c；独立分支 codex/provider-timeout-boundary-20261102，候选位于 code-projects/artifacts/provider-timeout-boundary-20261102/swarm。无依赖升级。pyproject SHA256 ffe92ec0d75c0337cb88744ec4ed3e367b4366d9f71cc74600d4142f22213c0f；uv.lock SHA256 01663e9cc370b7a99a99774959cd1abae0eeb804d5bc20c83c3ee8adf2d53cdb。

按锁 external 独立环境无 Core；Native 兼容环境安装来源为官方 agent-core e089198835426cd7681761b0cc278670cd83031f，未使用本地 checkout。SDK Claude0.2.115/Codex0.163.0，真实显式 CLI Claude2.1.274/Codex0.166.0/OpenCode1.18.18。版本是验证来源，不是运行白名单。

命令、初次失败与最终结果记录于任务 evidence：regression-final.log、locked-provider-final.log、native-compatibility-tests.log、locked-source.json、native-core-source.json。当前已执行178项受影响回归；Native扩大范围270通过、3项原有Windows专属跳过。external扩大范围曾因Native缺失出现收集/fixture错误，未记通过；改在独立Native按锁环境执行，非新增skip/白名单。受限运行器 asyncio 跨线程唤醒阻塞的超时日志保留，正常回环环境重验通过，非产品超时结论。

真实生产 AgentRuntime.stream / web请求：隔离配置、原Swarm模型服务、每Provider独有目录执行185秒脚本并独立读取文件。最终干净按锁环境Claude220.571秒、Codex210.216秒、OpenCode203.560秒（初次218.966/217.232/209.489秒另存live-initial-report.json），均有工具结果和最终标记，三家通过；Runtime关闭、凭据配置移除、未加载Core。该项证明正常长任务不误杀，不证明所有模型停滞情形。官方CLI/SDK＋本地受控模型服务故障注入另行验证，夹具不是线上模型；初始夹具URL/query及RST记录错误保留，最终第四轮三家通过：Claude请求250ms在249ms断开，Codex idle200ms在202ms断开，OpenCode chunk200ms在213ms断开；进程退出码0。为结束原生重试，夹具后续请求返回400；最终错误不伪装成纯超时，原始计时来自服务端独立观察连接断开。最终结果见 evidence/native-timeout-fault-report.json。Claude细分补验：本机CLI2.1.274配置首字节10秒后，两条stream=true请求实际均到约30秒API请求超时才关闭；显式开启官方字节watchdog仍相同，未证明该独立期限生效，不升级CLI或自建看门狗绕过。长流专有300秒配置实际观察两条连接在300.001/300.007秒关闭、Runtime与配置清理已回执，但验收进程最终退出143，故完整干净退出验收仍待复核。早期夹具给并发请求返回400会连带取消另一请求，修正为并发请求均等待原生期限后重验；早期结果不采信。首字节限制及长流验收记录分别为claude-first-byte-report.json、claude-stream-idle-report.json；不冒充DeepAgent有效输出时限等价。

# 补充根因与发布决策（2026-11-02）

10秒首字节参数已从实际CLI子进程环境核对，不是配置漏传。只读核对实际CLI2.1.274的原生路由条件：自定义ANTHROPIC_BASE_URL路径不启用该首字节计时器；显式开启字节watchdog不改变独立路由条件，实际连接29.982/29.985秒由30秒请求超时结束。因此记录为当前版本/路由的原生能力限制，不添加宿主计时器、不修改外部实现，也不以版本号作为运行白名单。

300秒长流在独立进程组、信号追踪与外层监督下复验：连接300.003/300.017秒关闭，Runtime清理和配置移除完成，验收进程306.789秒退出0，未触发监督超时。旧143及旧日志保留，发送者未记录且本轮未复现，不将其认定为已证实的产品清理缺陷。详细脱敏证据位于管理工作区evidence/root-cause-analysis.json、claude-native-route-analysis.json、claude-firstbyte-diagnostic-report.json、claude-idle-diagnostic-report.json和idle-supervisor-result.json。

用户确认这两项暂不修改产品代码，并授权提交、PR、合并、构建和发布Linux安装包。发布版本0.2.5.beta3，仅同步产品/TUI元数据及锁内本地包版本，不升级SDK/CLI/Core依赖。当前首字节限制属于已说明的发布限制；Windows/macOS真机不在本次Linux交付结论内。

# 交付边界

发布进行中；PR、合入SHA和冻结包验收结果在交付时追加。未替换用户已安装桌面包；Windows/macOS真机未执行。原生字节/响应头/SSE空闲不等于DeepAgent有效输出，不保证完全相同；运行版本不支持的能力不得猜补或修改外部实现。本地高级参数随现有配置读取，原会话模型/配置绑定不自动热换。

发布候选验证（beta3）：uv sync --locked --no-default-groups --extra claude-direct --extra codex-direct --group test --no-editable，两套独立环境实际workswarm0.2.5b3，非editable；Native仍为原Core固定提交。外部生产路径178通过，Native270通过/3项原Windows跳过；版本/桌面构建契约74通过/7项Windows PowerShell跳过。首次非editable环境混跑scripts构建模块时收集错误保留，随后按安装后Provider与源码构建各自入口分开执行；不新增skip。外部依赖锁条目没有变化，uv.lock只变更workswarm及本地TUI产品版本。冻结包及合入后验证另行记录，不沿用这些结果宣称完整安装包E2E。
