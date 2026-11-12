# 可替换的运行安全装配（候选，未启用）

本模块补原私有Docker入口的可选安全装配，不修改元戎SDK、Gateway、Runtime或Codex的权限映射，不创建／启动／回收容器。调用顺序为固定安全参数校验→原日志改写→原物理派发回执→单次Docker请求。未配置两个新参数的已有部署保持原行为；这不代表它们已解决Codex沙箱问题。

**当前禁止将候选安全配置接入真实账号：** 固定CLI0.163.0在非root、CapDrop=ALL、no-new-privileges及专属seccomp／AppArmor下可执行且拒绝工作区外写入，但仍能读取同UID可读的工作区外合成控制文件，包括经符号链接读取。workspace-write不是读取保密边界；只读挂载也不是。此结果未读取真实凭据，不证明跨账号访问或容器逃逸。必须先明确并验证可信服务／执行命令的凭据边界；仅放开命名空间不足以发布。

## 配置契约

原入口 `docker_log_boundary.py` 新增成对参数：

```text
--runtime-security-manifest /srv/code-platform/security/manifest.json
--runtime-security-sha256 <人工审阅后固定的manifest原始文件SHA256>
```

两参数必须同时提供；启用时还须提供原物理确认六项配置，不得绕过原派发防重或删除确认。清单的images／user／workspace_root必须与该私有入口完全一致。不得在混用旧镜像／其他业务的底座直接启用。应用HTTP、UI、工作区或模型不能提供这些参数。

清单schema如下（占位值故意不能启动，不提供可直接上线的默认策略）：

```json
{
  "schema": 1,
  "id": "codex-nested-candidate-1",
  "images": ["sha256:REPLACE_WITH_FIXED_IMAGE_ID"],
  "user": "agentos",
  "workspace_root": "/srv/code-platform/workspaces",
  "seccomp_file": "/srv/code-platform/security/seccomp.json",
  "seccomp_sha256": "REPLACE_WITH_REVIEWED_FILE_SHA256",
  "apparmor_profile": "code-platform-codex-reviewed-v1",
  "apparmor_file": "/srv/code-platform/security/codex.apparmor",
  "apparmor_sha256": "REPLACE_WITH_REVIEWED_FILE_SHA256"
}
```

- 三个文件须为操作员所有、无链接、单链接的普通文件，不允许组／其他用户写；原始字节SHA256逐次核验。文件由可信运维预置，不从网络、工作区或请求下载。清单固定到镜像ID而非tag；策略变更必须重新审核和验收，不热替换文件绕过摘要。
- seccomp要求默认拒绝；具体syscall规则仍须单独审阅和真实验证，结构检查不是安全认证。模块不逐次增补允许项、不提供unconfined回退。发送Docker API的是固定JSON内容，不是Docker CLI文件路径。
- AppArmor使用独有名称；操作员预加载并核对编译来源。模块只检查固定文件及内核中同名enforce条目，不自动安装、重载或修改宿主全局sysctl。**同名条目不能证明内核加载的字节与源文件相同**，部署还须保留加载命令、实际OCI及进程证据，不允许其他任务覆盖同名profile。
- 请求中存在额外capabilities、特权、设备、继承卷、额外安全选项、host／共享命名空间或覆盖内核保护路径时拒绝；强制CapDrop=ALL、no-new-privileges和固定两份策略。保留原Env／Cmd／挂载参数，由原日志与物理归属校验继续检查。此模块不是全挂载／网络出口授权引擎。
- 配置缺失、漂移、策略未加载或模式非enforce均在转发前失败。原派发回执附加`runtime_security_sha256`，仍是同一份回执；未知请求不重放。该字段用于部署证据，不替代实际OCI检查，也不是第二个环境库。

## 检查与放行

`RuntimeSecurity.verify_inspect`核对Docker镜像、用户、策略label、实际SecurityOpt／AppArmor及capability配置，仍不能替代实际进程状态、完整挂载和行为验证。模板策略／加载名称／label存在都不是验收通过。

在已核对归属的**无凭据诊断容器**中运行：

```sh
/opt/venv/bin/python codex_sandbox_probe.py \
  --codex-binary /opt/venv/lib/python3.13/site-packages/codex_cli_bin/bin/codex \
  --disposable-root /data
```

脚本仅支持当前锁定0.163.0，不调用模型、不读取真实凭据，使用临时HOME／CODEX_HOME与清理后的环境；只写自己的随机临时目录。检查命令执行、工作区写、外部可写标记的写入拒绝、合成控制文件直接／链接读取拒绝。退出0仅代表这组局部探针通过；退出1为完整边界未通过，退出2为配置／版本／运行错误。不能把任意命令启动失败当成负向隔离通过。0.163.0命令是`codex sandbox -- ...`，不能追加旧的`linux`层级。

读取负向检查只有合成子进程明确捕获EACCES/EPERM才判为拒绝；写入还接受EROFS。
文件缺失、标记内容不符、命令/命名空间错误均不算隔离通过。修订后的探针仍只是局部诊断，不能证明完整凭据边界。

2026-11-12在固定隔离配置上已完成原元戎生命周期及Native＋Codex真实模型/UI验收，见管理记录PLATFORM_ORIGINAL_CHAIN_20261112、PLATFORM_MODEL_UI_COMBINED_20261112。这些功能结果不关闭凭据读取边界；取消、其他Provider、完整凭据/进程/网络和生产恢复仍按各自验收范围处理，不放行上线。新工作区需显式合入[runtime-permissions.yaml.example](runtime-permissions.yaml.example)，不把缺省配置当作Default。

实际Codex会话的shell快照出现过测试模型Key，副本已清理；清理不代表隔离修复。平台长期Key不得进入执行侧配置、子进程环境或会话快照，受限委托也必须限定目标、用途、代次、期限并支持撤销。只过滤常用环境变量、0600、只读挂载或关闭快照均不能单独满足该契约。

## 回退与退出

1. 保留已验证的原代理文件、原参数、原回执目录；新参数未启用时无需改现有服务。候选文件留在独立工作区，不默认写入systemd模板。
2. 后续试启用前先停本专属底座的新派发并完成原链对账；已运行容器不会因换配置得到新策略。旧账号固定绑定和数据不自动迁移。
3. 试验失败按原链回收本任务实例，确认物理缺席后恢复成套代理／参数；不能改写UNKNOWN回执或直接删除容器来宣称原链回归成功。回退原配置只恢复旧能力，不能标记沙箱已修复。
4. 本任务profile只有在无使用者时撤销，保留策略与加载证据；不得reload所有AppArmor或关闭全局限制。
5. 元戎原生安全装配若可满足相同契约，经同组验收后移除这两个参数与独立模块；日志、物理确认、账号、Runtime和SDK不需要随之重构。

当前实测策略仅留在管理证据中作研究候选，未作为产品默认策略分发。参考来源为OpenAI codex-security固定提交4aa9acc5ce459ae0f525c88f727713694597a7ad的部署profile（Apache-2.0，诊断仅改AppArmor独有名称）；不是替换或修改本平台Codex CLI／SDK。具体失败及清理证据见管理记录PLATFORM_CODEX_SANDBOX_IMPLEMENTATION_20261111。
