---
author: leemine
author_email: leewanlong@gmail.com
id: B_20261111_2010_codex-container-sandbox
title: Codex嵌套沙箱的部署前提与控制文件读取边界
type: B
modules: [deploy/cloud-workspace]
files: [deploy/cloud-workspace/runtime_security.py, deploy/cloud-workspace/codex_sandbox_probe.py, deploy/cloud-workspace/docker_log_boundary.py, tests/unit_tests/cloud_workspace/test_runtime_security.py, tests/unit_tests/cloud_workspace/test_codex_sandbox_probe.py, deploy/cloud-workspace/runtime-permissions.yaml.example, tests/unit_tests/cloud_workspace/test_runtime_permissions.py]
designs: []
design_note: 依据管理仓PLATFORM_CODEX_SANDBOX_DEPLOYMENT_20261111及用户确认；没有另造D编号。
---

# Codex嵌套沙箱：可执行不等于凭据隔离

原产品候选0c56972；CLI／SDK0.163.0；113隔离环境。同一原ui-d容器的正确语法`codex sandbox --config sandbox_mode="workspace-write" -- /bin/true`仍报bwrap命名空间权限错误；前期OCI证据显示默认seccomp拒绝所需操作，AppArmor可能叠加限制。先前`codex sandbox linux`语法还会在解除前一层阻断后尝试执行名为linux的程序，已修正探针，不覆盖旧失败证据。

专属无网络、无凭据、无宿主挂载的诊断容器使用相同镜像／CLI、UID1000、CapDrop=ALL及NoNewPrivs=1；固定seccomp／AppArmor允许所需命名空间后，true和工作区写入成功，工作区外写入失败。直接读取和经链接读取同UID可读的合成控制文件却成功。此实验没有读取真实密钥，不证明跨账号访问或容器逃逸。文件API已经闭合的目录边界与任意命令的读取权限属于不同路径。

决定：只交付默认未启用的部署装配候选及明确返回失败的验收脚本，不改SDK／业务宿主／原实例链，不通过关闭内层沙箱、特权或全局放宽绕过。真实Docker API已接受模块生成的JSON并核对实际配置；本地114项回归通过，但真实账号启用和完整沙箱修复仍阻断。需先明确可信服务与执行命令的凭据隔离，再进行原链／UI／Provider验收。VM不会自动解决同实例凭据混放。

契约与退出步骤见 `deploy/cloud-workspace/RUNTIME_SECURITY_CONTRACT.md`；详细命令、版本、失败与清理证据见管理记录PLATFORM_CODEX_SANDBOX_IMPLEMENTATION_20261111。四次临时诊断容器均移除、专属profile均卸载；98个当时已有容器投影不变，原ui-d未重建或重启。单测看护缺失策略、漂移、危险参数、丢回执、恢复、防重复，以及命令启动失败／文件可读时不能误报成功。

2026-11-12后续：固定隔离装配已完成原实例链和Native＋Codex真实模型/UI验收，功能结果见管理记录PLATFORM_ORIGINAL_CHAIN_20261112及PLATFORM_MODEL_UI_COMBINED_20261112，不继承为完整安全通过。审核发现配置缺省可能显示Full Access，新增显式Default配置片段及原面板→Adapter→显式选择→恢复测试，不改产品全局默认。另修复探针把任意非零读取结果当作拒绝的问题：仅明确权限errno可算拒绝，缺文件、错误标记、命令错误均为未通过；这是验收工具修复，不是读取隔离修复。实际模型Key曾出现在Codex shell快照，清理后仍保留安全阻断。复查、锁来源和stable范围见PLATFORM_CANDIDATE_SECURITY_REVIEW_20261112。
