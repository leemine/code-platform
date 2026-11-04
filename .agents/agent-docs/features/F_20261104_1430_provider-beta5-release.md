---
id: F_20261104_1430_provider-beta5-release
title: Provider beta5 发布收尾与验证边界
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/runtime/agent_adapter, jiuwenswarm/channels/web/frontend, scripts, .github/workflows]
files: [.github/workflows/stable.yml, .github/workflows/windows-external.yml, scripts/build_config.py, pyproject.toml, uv.lock, tests/unit_tests/agentserver/test_opencode_equipment_encoding.py]
designs: []
design_note: 用户在输出保护、P1 和 OBS-01 之后明确授权执行提交合并、三平台打包与发布任务 2～6；任务 1 的 Claude 真实验收独立保留。
---

# Provider beta5 发布收尾与验证边界

## 范围与来源

以私仓 leemine/code-platform 的 origin/main 0fc0e316a33ffbdd44b2ae2ba72969ae23d0f410 为基线，独立工作区 artifacts/provider-release-20261104/swarm、codex/provider-release-beta5-20261104。原输出、P1、统计候选的全部改动、暂存差异、未跟踪文件与哈希先保全；分三次提交恢复，43 个最终文件与原统计候选逐字一致。原工作区保留，不替换用户目录或模型配置。

本续记替代相关 F/B 文档的“未授权提交/发布”当前状态；此前各 SHA、失败和真实验收范围保持历史事实。默认分支 main 是本私有分发仓的实际主线，不改动官方 jiuwenswarm 的 develop 策略。

输出保护只约束 Swarm 事件投影，保留两个兼容正文字段、原生上下文与退出事实。P1 由原 Facade 准备输入/提交装备，Provider 做原生映射；统计仍沿原事件、历史与控件，不加执行队列、压缩或持久账本。详见前述两个 B 和 P1、OBS-01 F。未新增 Claude/Codex 装备或主子 Agent 提示词能力。

## 构建与检查调整

- 版本单一源升为 0.2.5.beta5，使用 build_config.py --sync；锁文件仅本工程 workswarm/workswarm-tui 版本变化，Core e089198、协议 2a0457 和所有 SDK 锁不升级。
- 原 stable 增补能力/装备归属、共享历史、Native 统计/上下文与原前端 context-usage 测试；不运行或强制每日 full-python。
- 原桌面工作流增加 linux/all 选项，Linux 复用 scripts/build-electron-linux.sh；Windows/macOS 保留原原生构建入口。各平台记录 github.sha 与锁摘要，仍检查真实冻结无 Core 导入；没有硬编码本次运行 ID 或资产摘要。
- 扩大回归发现两个旧 UTF-8 测试用自造顶层包加载 opencode_equipment，无法表达新增的父包职责。改为正常安装的生产包导入，显式空模型配置隔离模型服务；保留原 GBK 默认、中文/emoji/二进制、配置读写和实际启动边界断言。不跳过冲突测试，不改生产导入绕过夹具。

## 验证与发布门槛

发布环境按 uv.lock 非 editable 安装 external/native 两个组合，实际导入文件与候选核对；源码缓存、构建配置、API 密钥和安装包不提交 Git。CI stable 及最终运行/合入 SHA、安装包摘要、构建链接在管理仓对应发布记录闭合；未拿到结论前不记成功。原本机 Codex/OpenCode 真实 Web/Worker 验收适用部分按文件哈希和语义差异核对，不能直接宣称 Windows/macOS 实机聊天通过。

Claude 原渠道真实验收仍被官方 CLI 自身的 HTTP 429/10次重试阻塞；任务 1 不在本次授权的 2～6 范围。beta5 是测试版，明确列出该限制；没有改外部 SDK/CLI、替换密钥/路由、关闭 TLS 或使用 CC-Switch。Windows 安装包未签名；macOS arm64 未做 Developer ID 签名/公证，不能宣传正式签名发行或跨平台实机验收。

## 首轮构建与来源复查

PR #14在stable成功后已合入c8e55c7，三平台41787080221均构建成功。复查发现新增Linux job时macOS诊断上传步骤仍挂在Linux下，使macOS诊断资产被Linux内容标记；正式macOS安装包自身的source.json和dmg不受影响。该问题仅在工作流修正，不改产品/锁，增加每个job的安装包文件名、字节数、SHA256到原source.json并打印非敏感清单，便于下载/转存前核对。修正通过stable后以同一新合入SHA重跑三平台，首轮包不作为beta5最终发布资产。

本地发布候选external432通过、Native553通过/3项Windows专属Linux跳过；前端8脚本共9测试、构建通过，实际按锁非editable来源一致。候选stable41786693197与合入后41787067588成功，未运行每日full-python。主目录已同步且clean。最终发布链接与SHA由管理仓发布记录续记，Claude429限制保留。
