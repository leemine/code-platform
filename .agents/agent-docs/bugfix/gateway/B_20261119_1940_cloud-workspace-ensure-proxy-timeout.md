---
id: B-20261119-1940-cloud-workspace-ensure-proxy-timeout
title: 云端首次进入的 Web 代理超时
type: B
author: leemine
author_email: leewanlong@gmail.com
designs: []
design_note: 沿用既有云实例就绪接口与 Web 长超时规则。
modules: [jiuwenswarm/channels/web]
files: [jiuwenswarm/channels/web/app_web.py, tests/unit_tests/channels/web/test_cloud_proxy_deadline.py]
---

# 现象与根因

生产浏览器同时进入云工作区时，一个请求达到 30 秒并收到 Web 代理的 502。该账号随后仍分配到运行中的实例。生产 Web 为云目录同步路径使用 175 秒，其余 HTTP 代理使用 30 秒，首次进入云实例的组织账号接口原本也走了 30 秒。

# 修复与验证

将首次进入的精确路径 `/api/v1/auth/organization/environment/ensure` 加入已有 175 秒规则。浏览器与 Gateway 仍沿用现有就绪确认。回归通过真实 HTTP 代理延迟上游响应，检查两个长等待路径、普通请求和近似路径，并核对每次写请求仅转发一次。部署范围为 Web 角色，实例分配及认证继续交给现有 Gateway。参见[云账号实例契约](../../specs/gateway/S_01_cloud-account-instance.md)。
