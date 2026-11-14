---
id: F_20261114_2029_certificate-lifecycle
title: 部署证书自动续期、加载确认与到期告警
type: F
author: leemine
author_email: leewanlong@gmail.com
modules:
  - deploy/tls
files:
  - deploy/tls/certificate_lifecycle.py
  - deploy/tls/Caddyfile.internal.example
  - deploy/tls/Caddyfile.public.example
  - deploy/tls/alerts.yml
  - deploy/tls/systemd/code-platform-caddy-internal.service
  - deploy/tls/systemd/code-platform-tls@.service
  - deploy/tls/systemd/code-platform-tls@.timer
  - tests/unit_tests/cloud_workspace/test_certificate_lifecycle.py
designs: []
design_note: 用户明确要求补齐现有部署证书生命周期，复用标准Caddy签发与原实时身份契约，无新增产品执行协议。
---

# 范围与参考

基线main d127a271c4a7c339d1e7fcc710a0fed1241e8a23。codeswarm参考24f29148：governance/account_http只在启动加载TLS；common/auth中的令牌续期不是证书续期。已存在的113公网codeswarm部署通过Caddy2.11.7/ACME自动续签IP证书。平台28953先前仅复制该证书，缺少更新传播和在线加载确认；内部账号证书则为手工短期证书。部署边界补齐，不修改codeswarm、外部Caddy源码、账号/Runtime权限或锁定依赖。

# 实现与取舍

新部署由Caddy直接终止公网/内部TLS，沿标准签发器自动续期与更新加载。内部代理与账号HTTP共享网络命名空间且后者仅监听回环；跨主机客户端访问带正确SAN的TLS代理并验证显式CA。CA存储持久化，应用角色只拿根公钥；不自动轮换根信任、不复制账号库。

既有nginx副本通过部署工具读取标准签发方产物。临时版本内复制后验证key/chain/SAN/有效期，原子切current，syntax/reload后连接真实服务校验指纹，失败回滚。中断后即使磁盘已更新仍补reload确认。单个可信操作员/manifest拥有目标目录，锁不宣称多机分布式互斥。回滚保留旧版本，不自动清理共享资源或删除用户数据。

systemd实例timer每5分钟检查，结构化journal、失败退出、status和Prometheus文本指标；规则覆盖到期、CA到期、检查停摆和指标缺失。通知目的地由已有Alertmanager等运维配置提供，不内置凭据、不擅自发邮件。签发仍归Caddy/CA，不重复ACME订阅。

# 验证

10项真实回环TLS行为测试通过：新证书加载、幂等、错key/错SAN/低有效期拒绝、源文件缺失清理、命令返回成功但未加载拒绝、失败回滚、发布后崩溃恢复、过期与CA告警和信任拒绝。既有proxy_switch14项通过。Caddy2.11.7独立目录两分钟测试叶证书实际自动续期60.878秒，同进程61次账号session成功，续期后logout与撤权401通过，根信任不变。生产示例保留默认有效期，不把测试2m应用于正式部署。

授权113隔离部署已启用专属Caddy内部TLS与5分钟证书检查timer，两者enabled/active。公网沿用现有Caddy签发源并补齐nginx消费者传播；未强制轮换共享公网证书，本次该证书检查为unchanged。内部账号保留同镜像/同数据库，HTTP仅回环28949，Caddy在28950终止TLS，网关显式信任持久根CA。独立到期阈值演练验证非零退出和journal告警，正式阈值检查恢复healthy；没有配置邮件/IM接收端。独立登录、14条旧会话history（1.316秒）及撤权后既有WS关闭1008且零成功数据通过。右侧本地29011页面历史正文恢复，截图API不可用，保存UI文本证据。详细命令、路径与失败尝试见管理验证记录。

2026-11-14用户授权提交/CI/合入及长期验证。提交前检视覆盖部署工具、调用示例、systemd、告警规则和原实时权限边界。真实云专属Caddy重启后根CA及叶指纹保持一致，新PID受信health成功，恢复检查0.797秒；这是服务重启验证，不是整机重启或正常周期续期已完成。正常12小时叶的自然续期继续观察；外部告警渠道等待接收目标配置。远端交付的实际SHA与CI结论在管理验收记录续记。

# 限制

单机部署工具不提供分布式协调、通知接收人或通用运维管理API。服务多活、跨节点存储及全部CA供应商签发不在本批验收内。模板不会随镜像启动静默安装宿主服务；需运维按实际目录/身份/端口部署。自动根CA替换会破坏信任，必须单独规划。无有效证书时继续拒绝TLS，不为了可用性跳过证书校验。
