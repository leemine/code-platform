---
id: B_20261031_1122_model-config-without-core
title: 无 Core 安装的模型配置加载与保存修复
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway/common, jiuwenswarm/common/config_panel, jiuwenswarm/channels/web/frontend/src/features/settings/modules/models]
files: ["gateway/common/model_vendor_registry.py", "jiuwenswarm/common/native_integration.py", "jiuwenswarm/common/reasoning_config.py", "jiuwenswarm/common/config_panel/models_handlers.py", "jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/ModelDialog.tsx", "jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/modelAdapters.ts", "jiuwenswarm/channels/web/frontend/src/features/settings/modules/models/modelValidation.ts", "jiuwenswarm/channels/web/frontend/src/types/index.ts", "jiuwenswarm/channels/web/frontend/src/i18n/locales/en.json", "jiuwenswarm/channels/web/frontend/src/i18n/locales/zh.json", "jiuwenswarm/channels/web/frontend/tests/modelReasoning.test.mjs", "tests/unit_tests/test_external_model_settings.py"]
designs: []
design_note: 用户确认的最小配置缺陷修复，不统一 Provider 推理能力，无独立设计。
---

# 无 Core 模型配置修复

## 根因与决策

vendors.list静态预设被Core推理导入绑死；前端解析/按钮/表单均把推理数据缺失当目录失败，另有无Core连接测试仅OpenAI。现在用明确reasoning_available=false/null标记缺席；没有标记的损坏目录仍拒绝。Native规则、配置RPC、ModelCatalog、存储及UI控件复用，不建立外部推理目录。显式旧值保留并提示，不自动清除；用户主动选择默认才清除。

## 证据

候选8910f05+dirty；无Core39项，固定Core e089198目录/推理/配置57项及资源55项通过；React20项通过；构建通过。真实OpenAI/Anthropic服务原RPC新增/修改/重读通过，无Core导入；独立Web45643两种协议编辑保存、Anthropic新增及刷新重读通过。完整资料在管理工作区docs/verification/MODEL_CONFIG_NO_CORE_20261031.md，源码SHA在同目录evidence/MODEL_CONFIG_NO_CORE_20261031/source-manifest.json。

初始UI测试使用旧HTML select操作失败，修为真实共享下拉点击/选中状态，没有跳过。无Core扩测原Native编译路径10失败，固定Core后原资源55通过。设置页广泛回归62通过/2既存失败（原HEAD复现CSS和翻译结构），未扩大白名单。

## 后续与边界

未发布；用户旧实例及配置保留。推理选项统一、Provider参数映射、Claude完整执行、跨平台安装包另行验收。有Core安装内部异常不被当作缺席吞掉。模型配置成功不等于执行器支持全部协议或参数。
