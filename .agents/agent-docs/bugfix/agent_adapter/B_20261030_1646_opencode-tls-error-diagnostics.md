---
id: B_20261030_1646_opencode-tls-error-diagnostics
title: OpenCode TLS 原生错误原因丢失与同环境复验
type: B
author: leemine
author_email: leewanlong@gmail.com
modules: [jiuwenswarm/server/runtime/agent_adapter]
files: [jiuwenswarm/server/runtime/agent_adapter/providers/opencode.py, tests/unit_tests/agentserver/test_opencode_direct_adapter.py]
designs: []
design_note: 用户授权定位并修复既有接入错误；不扩展执行框架或修改外部源码。
---

# 现象和已确认原因

2026-10-30 16:27:43，Web会话web_1a18beb3d2b_c215c8803762请求只读分析deer-flow，OpenCode 1.18.18原生消息记录UnknownError/data.message="unknown certificate verification error"，模型输入/输出token=0，未执行工具。适配器session.error与message.updated两分支只保留错误名称并输出笼统文案，导致历史和UI丢失可操作原因。这一信息丢失是已确认的本工程缺陷。

TLS握手当时失败的底层诱因仍未闭合：相同模型配置、权限配置及代理/证书环境，两个原OpenCode进程不重启、不改配置均通过同模型TLS_OK复验；系统TLS及curl证书校验通过。不能据此推断证书过期、缺CA、特定网络设备或OpenCode缺陷。当前恢复不代表消除再次发生的可能，不把诊断修复宣称为网络根因修复。

# 修复与边界

两个原生错误分支统一经局部provider_error_payload投影。仅精确识别已知TLS错误短语，发出固定code=provider_tls_verification_failed和固定安全说明；保留原生错误类型。未知文本仍通用提示，不透传URL、模型响应、请求头、凭据或stack，不对用户提供的原文做不可靠的脱敏猜测。取消/终态、历史和原UI通道不变，不增加前端状态。该分类不区分具体证书故障成因，不添加自动重试、不替换CA、不关闭验证。Core和外部Provider源码/锁定版本均未改。

# 验证

- 原Facade/历史入口回归56项通过，新增session.error与message.updated双分支、TLS分类、未知/含凭据错误不泄露、单次prompt无自动重试、无成功终态验证。日志logs/tls-adapter-regression.log。
- 同一真实原进程双服务诊断通过；只新建禁止工具的临时会话，正常回复TLS_OK后删除，原会话不清理。evidence/tls-reproduce-current-services.json。
- 真实Runtime→官方OpenCode→本机不受信任TLS服务：输出明确错误、历史同文案、无成功终态；服务实际收到HTTP请求0，未信任测试证书；随后真实模型回复TLS_RUNTIME_OK。run ebd793d4，evidence/tls-runtime-ebd793d4.json，清理会话服务目录0。
- 初次诊断脚本d559fd6f把TLS建立回调计作HTTP请求，导致脚本断言失败；实际错误映射已成功。修正为读取到HTTP字节才计数后重验通过，保留初次失败证据，不记成产品失败或抹除。
- 原Web会话只读复验完成18次工具调用（17次read/1次ls -la）及最终架构分析，0错误；无Core同套56项通过。最终来源记录见管理验证记录。原44779仍运行修复前Python进程，未为加载诊断补丁而中断用户会话；新补丁真实Runtime在独立进程验收。

# 遗留

原连接问题当前不能稳定复现；无当时证书链/握手包证据，底层诱因待复现。不得宣称TLS根因已修复或发布；本次仅诊断缺陷修复、运行恢复验证，未提交/推送/PR/合入。后续若再发生，应保留时间、原生错误/进程版本及脱敏证书链证据，与同一进程的最小请求对比，不自动跳过信任校验。


## 2026-10-30 18:42 续修：定向直连与泛化错误语义

后续诊断补齐：首次原生失败前约3ms，Mihomo对同域名记录拨号超时；无证书即断开的本机服务也使实际Bun返回同样泛化错误。直连与代理的合法证书相同，前者TLS约28～37ms、后者约1.9～2.7秒。第二次历史断开点仍未知，不将两次都归为已证实的代理拨号超时。此前“无显式代理环境”不排除透明TUN。本节更新此前调查结论，不覆盖旧失败证据。

用户批准后，通过当前Clash订阅的正式merge配置增加模型精确域名DIRECT、其余MATCH原ip-socks5，并将基础/运行模式改为rule；完整私有备份位于用户Clash数据目录，候选校验成功、控制器读回和实际日志确认。TUN、CA/证书保护及其他运行配置保持。此为本机环境修复，不写入产品默认配置、不复制凭据到Git；未重启Clash GUI验证跨应用重启持久性。

产品只改局部错误投影：泛化短语使用provider_tls_connection_failed和固定握手/验证阶段说明；明确证书短语保留provider_tls_verification_failed。原session.error/message.updated、history与UI消费者共用原通道。精确白名单继续拒绝带URL/凭据附加文本，不自动重试、不修改外部CLI/Bun。

验证：当前Facade/历史入口60项通过，logs/tls-routing-regression.log；真实Runtime run b413eeb0三场景通过：未发证书断开→connection_failed，不受信任证书→verification_failed/HTTP请求0，真实模型→TLS_RUNTIME_OK。临时服务目录残留0，closed-peer只收到1次ClientHello。原37039 Web会话完成真实read和TLS_DIRECT_WEB_OK，request req_mvuug5ov_343成功且无新增error；项目文件未变、刷新恢复绑定/历史，代理日志明确DIRECT。独立Runtime用于候选新提示验证；原UI Python服务未重启，旧错误历史不改写。

边界：Swarm88fbdd2+既有dirty，Core主目录78659023 clean、运行固定依赖e089198未变。未提交/发布；只证明本次限定范围验收，不承诺长期网络无故障。资料与证据保存在本任务管理报告及evidence/tls-routing-runtime-b413eeb0.json、tls-direct-web-summary.json、tls-direct-web-success.png。验证脚本初次使用错误cwd未启动，已保留日志，不算产品失败；修正路径后完整三场景通过。
