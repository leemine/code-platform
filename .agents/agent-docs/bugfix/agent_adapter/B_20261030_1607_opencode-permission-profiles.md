---
id: B_20261030_1607_opencode-permission-profiles
title: OpenCode Full Access 与原生权限、生效状态接入
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [agent_adapter, server/worker, channels/web/frontend]
files: [jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, jiuwenswarm/server/runtime/agent_adapter/agent_adapters.py, jiuwenswarm/server/runtime/agent_adapter/interface.py, jiuwenswarm/server/worker/dispatcher.py, jiuwenswarm/common/config_panel/execution_provider_settings.py, jiuwenswarm/channels/web/frontend/src/App.tsx, jiuwenswarm/channels/web/frontend/src/config/permissionProfiles.ts, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/index.tsx, jiuwenswarm/channels/web/frontend/src/components/ChatPanel/InputArea.tsx]
designs: []
design_note: 用户确认复用既有 reload/Runtime/权限下拉的最小接入方案，无独立子仓设计。
---

# 现象与根因

Full Access 已保存，但直连适配器固定 permission.*=ask，且 reload_agent_config 无条件拒绝；UI 只有全局期望档位，没有会话实际生效信息。真实 Web 验收再发现 Manager 的 create_instance 输入是局部配置，漏读全局权限使首轮仍为 Default。仅显式完整配置/热更新用例不能覆盖该路径；现补缺字段继承和浏览器首轮验收。

# 修复与取舍

复用原全局配置与广播，Facade 可选状态透传，Worker 原快照附带权限投影，原 UI 下拉显示能力和生效状态。原生规则、读回、重启/装备协调留在 OpenCode 适配器；Native 与 Core 依赖未修改。完整当前契约见 S_02_external-adapter-boundary 的权限章节。

未复制远端 Core Engine 或建立第二授权/调度系统；参考其 desired/effective、原生读回及失败阻断原则。Claude Code/Codex 的 bypass、approval、sandbox 不是可互换字段，后续 Provider 仍需独立映射和能力验证。会话实例更新在 idle 应用，待审批不自动放行。源配置层的 Full Access 不是安装/启用插件的授权。

# 验证

Web真实回切另发现原config.set的15秒超时早于官方服务约17秒完成，产生错误重启提示。权限保存单独等待120秒，显示Pending并禁止重复选择；失败重读权威配置、toast提示，不误导重启。

- 正常安装环境影响面 192 项通过：OpenCode、Native 权限热更新/切换、配置广播、Worker 恢复/快照、Plan 与会话绑定。之后新增初始化/关闭并发回归，适配器全文件48项通过。无Core环境46项通过（最后两项并发用例另在正常环境通过）。
- 真实官方 OpenCode 1.18.18 + glm-5.3：原 config.set→广播→Runtime，Default审批中改Full Access仍需原答复；后续Full Access与第二会话无审批；再切Default恢复审批，原生读回状态与工具随机文件输出一致，关闭私有目录0。证据permission-live-2f56fac5.json。
- 无Core真实模板/插件Skill完整资源/受控stdio MCP/两会话/装备清空通过，Full Access全程无工具审批，Core导入0，清理残留0。证据permission-equipment-b527d89a.json。
- Web首轮Full Access已读回Applied，真实printf工具返回PERMISSION_WEB_FIXED_OK且无permission_interrupt，刷新历史保留。Default回切后真实工具再次请求审批，允许一次后输出PERMISSION_WEB_DEFAULT_OK；再次切Full Access由Pending到Applied，无误报重启弹窗。脱敏历史和最终截图已归档。
- 前端权限展示与Provider选择行为测试通过，Vite构建通过（保留原大chunk警告）。没有运行静态检查/格式化。

所有证据位于同级任务 artifacts/agent-adapter-validation-20261029 的 logs/evidence；完整命令和候选来源见管理验证记录AGENT_ADAPTER_PERMISSION_PROFILES_20261030.md。首次沙箱pytest日志目录只读/挂起，移至任务隔离环境；中间测试替身遗漏method及新增测试import缺失已修正重验。首次无Core config.set失败于原配置面板顶层Core导入，未当成执行成功；完整面板免Core属既有N07范围，未扩大本次改造。Web首次验收捕获初始化缺口，失败历史保留并拒绝结束，修复后新会话重验。

# 交付边界

仅隔离候选，未提交/PR/合入。未改外部源码、锁文件或主目录。旧用户40657实例保留，新独立验收44779实例用于本轮UI。冷恢复、第二Provider、完整Native治理、独立插件正常安装和最终发布仍未完成。使用当前会话的能力不意味着所有未来Provider可以热更新；只能按其能力声明与真实接口实现。

## 界面收敛（2026-10-30 用户补充）

按用户要求恢复Swarm原有权限显示，仅显示档位名称，移除状态标签、状态悬浮提示、展示props、闲置展示函数及对应测试/翻译。保留后台原生权限映射/读回、能力过滤、保存期间防重复选择与失败提示。此前截图为历史验收，最终界面以permission-web-original-display.png为准。
