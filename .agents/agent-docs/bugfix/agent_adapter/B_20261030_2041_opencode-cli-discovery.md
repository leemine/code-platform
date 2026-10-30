---
id: B_20261030_2041_opencode-cli-discovery
title: OpenCode 桌面 PATH 缺口与传输边界收敛
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/runtime/agent_adapter/providers, scripts]
files: [jiuwenswarm/server/runtime/agent_adapter/providers/cli.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_transport.py, jiuwenswarm/server/runtime/agent_adapter/providers/opencode_service.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py, scripts/assemble-electron-linux.py]
designs: []
design_note: 用户确认保留官方 HTTP/SSE 并隔离传输边界；延续管理仓 EXECUTION_PROVIDER_BOUNDARY_REVIEW_20261026 的外部 Provider 桌面候选。
---

# OpenCode 桌面发现与传输收敛

根因：已有实现仅检查显式 cli_path；未配置即校验 URL。桌面 PATH 不含用户 CLI 目录时，并非新功能未被打包，而是自动发现没有落实。早期验收显式指定 CLI，因此没有暴露缺口。旧 SDK 的基础 API 成功也不能证明新版审批/事件契约兼容。

方案：显式选择优先且失败不回退；自动候选按当前用户/平台定位；自有服务默认 workspace 复用 Swarm 路径函数。HTTP/健康/SSE 移入独立模块，适配器保留语义映射，服务模块保留进程所有权，宿主 Runtime/模型/历史/UI 不改。无新增依赖、Core升级、外部源码改动或权限放宽。

验证：免 Core 85 项、带固定 Core 93 项通过（两组重叠，不累加）；涵盖真实 Facade、默认发现、显式 URL/CLI 兼容、缺失、项目 PATH 遮蔽、三平台候选、SSE 多行、原审批/取消/历史。首次混合收集失败因为免 Core 环境收集 Native 用例；沙箱运行等待后中断，主机隔离环境复验；新增用例首次误断言 configure 只调用一次，改为公共接口的 effective_profile，不改变产品的原装备调和次数。失败记录保留。

正常非 editable 按锁安装、无 Core、无 cli_path/URL、PATH仅/usr/bin:/bin，隔离用户 HOME 中的正式 CLI 符号链接被自动发现。两轮真实 Runtime 完成 read/exit7，各一次默认审批；退出7在工具和历史均为失败、任务调用仍可完成；测试文件不变、自有服务目录清零、Core未导入。证据：管理任务 artifacts/external-desktop-20261030/cli-transport-live-6dc99e13.json。正式 OpenCode 1.18.18，未修改官方安装文件。

冻结后端相同两轮真实验收通过（run23f8eea3）；Deb/tar与实际验收后端哈希相等、模板配置一致且无Core/Provider CLI，见cli-transport-package-audit.json；已生成新候选包，未更新旧系统安装。Windows/macOS 实机、Windows cmd/bat 包装器自动接入、第二 Provider、冷恢复、CI/stable与正式发布未完成。仅 Windows/macOS 候选路径测试不能记作跨平台执行通过。

Windows发布前还需补齐USERPROFILE/APPDATA私有化与MCP子进程树清理；当前仅HOME/XDG和POSIX进程组，不能将Linux证据外推。macOS需GUI发现、双架构、签名/公证与清理实机验收。


## 同日后续：启动竞争与空错误

真实认证健康连接在监听前开始并阻塞15秒，而监听后新连接约1.37秒已成功；属于启动探测竞争，不能归为TLS。项目插件会让官方Config依赖安装成为session初始化前置；新私有HOME/XDG使配置依赖反复冷启动。原15秒session请求预算不足，httpx.ReadTimeout空字符串再经原Runtime错误投影造成空错误。

修复仅改opencode.py、opencode_service.py、opencode_transport.py：短健康探测、独立有界初始化预算、脱敏错误，不改宿主流程或插件源码。真实TCP启动竞争/退出/取消、Facade失败清理/慢初始化、Runtime错误投影回归通过。外部97、固定Core124通过（重叠）；首次免Core误收Native测试收集失败，以及首次错误投影测试在Facade而非Runtime断言的失败均保留，修正测试边界后复验，未改产品终态来迁就测试。

按锁非editable、真实OpenCode1.18.18 read/exit7/审批/历史通过：startup-fix-live-c897e1b6.json；冻结后端同验收run33b53a15通过。复制原项目配置仅prepare成功，仍27/31秒且插件导出错误未修。官方npm缓存诊断30/9秒只支持下一步实验方向，不宣称缓存功能已交付。独立Linux候选包、限制和方案见管理验证记录启动修复节；系统安装未替换，无桌面UI点击、Windows/macOS或CI/stable结论。
