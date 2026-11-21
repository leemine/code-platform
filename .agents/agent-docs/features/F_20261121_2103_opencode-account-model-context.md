---
id: F_20261121_2103_opencode-account-model-context
title: 托管 OpenCode 同步账号模型上下文上限
type: F
author: leemine
author_email: leewanlong@gmail.com
modules: [gateway/common, jiuwenswarm/server/runtime/agent_adapter/providers]
files:
  - gateway/common/opencode_model_policy.py
  - jiuwenswarm/server/runtime/agent_adapter/providers/opencode_models.py
  - tests/unit_tests/cloud_workspace/test_opencode_model_admission.py
designs: []
design_note: 沿现有账号模型同步、原生配置及按绑定回收契约扩展。
---

# 托管 OpenCode 同步账号模型上下文上限

账号模型目录通过已认证 Worker 将兼容模型投影到该账号的原生 OpenCode 配置。有效上下文上限写入模型的 `limit.context`。OpenCode 1.18.18 的配置要求同时提供数值型 `limit.output`，这里用其原生默认的零值保留输出计算回退逻辑。缺少上下文设置时沿用原模型片段。Gateway 校验只允许正整数上下文与零输出占位，拒绝额外属性。

上下文变化会更新私有配置版本，保持模型 ID 稳定，继续沿用凭据、账号归属及原绑定空闲换代流程。自管 OpenCode 配置走原投影。

基线为 `bbb578d09120a69b6afe77dee7583af6fa6b93b0`。账号模型、Gateway 准入和中继等五组定向测试共 230 项通过。两份无 Core 候选沿用固定 Protocol `2a0457e5e01152e9ca5f8afdffd84716227046ca`。隔离元戎 0.10.3 上，真实 OpenCode 1.18.18 以 4 GiB 配额启动，账号模型首条消息获得流式回复，并从容器原生模型目录查到 `deepseek-v4.1-flash` 为 1,048,576 token。验收模型服务使用隔离固定响应，账号凭据映射以测试值核对。
