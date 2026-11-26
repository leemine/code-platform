---
id: B_20261126_1123_cloud-cron-account-model
title: 云端定时任务解析账号模型
type: B
modules: [gateway]
files: [gateway/cron/controller.py, gateway/runtime/cron/cron_job_mutations.py]
designs: []
design_note: 复用既有 E2A 模型目录、定时任务模型选择和账户授权契约。
author: leemine
author_email: leewanlong@gmail.com
---

# 云端定时任务解析账号模型

## 现象与根因

QA 的 GLM 5.2 在 Code 聊天可选。定时任务按名称或 ID 创建时，Gateway 查本地目录并拒绝模型。任务存储的更新路径也会再次查 Gateway 本地目录。

## 修复

带正式组织账号上下文的创建及编辑，通过现有 `models.list` E2A 请求从任务所属账号的 Worker 取目录。由当前认证身份核对任务属主，显式 ID 或唯一名称映射为稳定模型选择。持久化仅保存模型名及 ID，账号模型凭据由原 Worker 按执行时配置读取。文件与 etcd 仍验证模型选择结构，控制器可通过仅内部关键字标记已完成的账号目录校验。无组织账号上下文的既有目录及登录模型流程继续使用原解析。

## 验证

在与正式 Gateway 兼容的精简镜像上使用已锁定的依赖。251 项定向用例通过，包含账号模型创建与更新、错误属主与未知 ID 拒绝、文件与 etcd 存储以及调度器回归。正式验收回执见管理仓的对应发布报告。
