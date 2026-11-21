# 独立 OpenCode 发布与节点预置

发布工具以已验证的 Docker 镜像和封存的启动栈目录为输入。构建机生成一个发布包和其中唯一的 `release.json`。清单固定最新版 Provider 的 Docker 镜像 ID、共享启动栈树的 SHA-256，以及旧版完整镜像的 Docker 镜像 ID。它还记录两个传输归档的 SHA-256。镜像 ID 使用 Docker 本地内容 ID，与 [Gateway 和 Docker 边界](README.md#独立-opencode-共享启动栈)接受的字段一致。登记发布包及 `manifest_sha256`，交由可信发布制品目录分发。

## 构建发布包

在具有两个镜像和封存启动栈的构建主机上运行以下命令。这里使用已通过单绑定正式验收的 OpenCode 1.18.18，Provider 解包体积为 265.6 MB。

```sh
STACK_SHA=da1638000911c6a815a66c37a87b164cf24d1237f8f81e16a5e17e3cd61e23c6
python3 deploy/cloud-workspace/release_opencode.py pack \
  --output /srv/releases/opencode-1.18.18-shared \
  --image sha256:8bc2395fb3ad63cc8f6209d3c3bede64315b41256e8e0f3947764914d8f9b5fb \
  --rollback-image sha256:ace00f88cd7e23d607254c6fbc3602c2ceba9a9369d5c1bbfbc1de6051f543bb \
  --runtime-source "/opt/code-platform/runtime-assets/$STACK_SHA" \
  --runtime-sha256 "$STACK_SHA"
```

保留发布包及上一版完整镜像。节点导入缺少的镜像，并用包含完整镜像 ID 的本地标签保留两个镜像。新节点沿用该池的 Docker 镜像存储配置。导入后若实际 Docker 镜像 ID 与清单不一致，发布会失败。运行强制镜像清理后需要复验。

## 发布前预置全池

准备该元戎池的最新节点清单，为每个调度节点提供对应的受信 SSH 目标。控制机需安装 OpenSSH，目标节点需具备节点本地 Docker 和支持 `tarfile.data_filter` 的 Python。控制机使用预配置的主机密钥和非交互 SSH root 管理权限。应按发布记录复核发布包的清单摘要。

```sh
python3 deploy/cloud-workspace/release_opencode.py provision \
  --bundle /srv/releases/opencode-1.18.18-shared \
  --ssh-config /etc/code-platform/release-ssh.conf \
  --host node-a --host node-b > /srv/releases/opencode-rollout.json.next &&
  mv /srv/releases/opencode-rollout.json.next /srv/releases/opencode-rollout.json
```

同一发布使用全部节点相同的宿主目录。节点在导入时校验对应的传输归档，随后核对启动栈树和 Docker 中的新旧镜像 ID，最后原子发布版本目录。已有同摘要版本可重复校验。任一节点失败时命令返回非零且不输出切换配置，已成功预置的节点可保留该版本供重试。已有版本目录摘要不符时会拒绝覆盖。

所有节点返回同一版本后，部署流程使用输出的 `boundary_args` 和 `opencode_provider` 更新现有配置，再按原部署顺序切换 Docker 边界和 Gateway。清单和节点回执可用于审核。既有绑定的迁移沿用原物理回收和离线迁移命令。

## 新节点与回滚

新增节点先在它仍未接入调度池时，用已发布的同一包和节点清单执行预置。发布流程以命令退出码控制是否启动节点。校验通过后装配该节点 Docker 边界，再接入元戎。镜像与挂载仍受节点 Docker 边界在实际创建前检查。调度池启用新版后，加入或替换节点也遵循这一顺序。

回滚配置使用同一输出中 `rollback_provider.image` 的原完整镜像 ID，并移除 `opencode_provider.shared_runtime`。节点预置时已核对该镜像。保留原镜像准入，按原流程等待实例物理回收后迁移受影响绑定，复用原状态卷。
