# Managed Codex deployment

Managed Codex uses the existing Code/Work channel, Worker model catalog, Codex adapter and Runtime. A Worker selected by the Gateway account allowlist opens a signed WSS stream for its existing project. The Gateway uses the original YuanRong instance client to allocate one container per authenticated account and Worker environment. The private execution relay starts the official App Server over native stdio with a separate persistent CODEX_HOME for each Swarm session. Each session retains its project path, native thread and state after verified physical reclamation.

The Gateway keeps the capability token and upstream model API key in the control plane. The container receives the capability digest and a read-only mount containing the scoped model broker socket. The broker serves Responses for the selected model and a configured HTTPS endpoint. The Docker boundary checks the immutable image and runtime, exact account project and state mounts, and a pinned AppArmor and seccomp policy.

The initial managed path supports a fixed Responses-compatible model connection per Worker binding. Requests with another model connection are rejected by the binding. An explicit Worker-local native model catalog or MCP configuration carrying local credentials requires the existing local Codex path. TLS and the upstream model endpoint allowlist are set by deployment.

## Build and stage

Build `Dockerfile.codex` with an explicit context containing `codex_model_bridge.py`, `codex_stdio_bridge.py`, and the complete `codex_cli_bin/` directory from the lock's Linux amd64 Codex CLI wheel. Verify the original wheel and package file digests. Keep the versioned Python 3.11, YuanRong Runtime and Executor tree on the host. Use the same Linux user ID in the account, Gateway and managed containers. The Gateway creates the native state and home directories before requesting allocation so the YuanRong bootstrap can initialize.

Use the existing release tool with the Codex manifest format. The rollback image uses the same native startup command and mount layout.

```sh
python3 deploy/cloud-workspace/release_opencode.py pack --provider codex \
  --image "$CODEX_IMAGE" --rollback-image "$CODEX_ROLLBACK_IMAGE" \
  --runtime-source "$RUNTIME_TREE" --runtime-sha256 "$RUNTIME_SHA256" --output "$RELEASE_DIR"
python3 deploy/cloud-workspace/release_opencode.py provision --bundle "$RELEASE_DIR" --host "$YUANRONG_NODE"
```

Configure `codex_provider` with the verified `image` and `shared_runtime`, the authenticated `account_allowlist`, and the approved `model_endpoints`. Optional `cpu`, `memory` and `idle_seconds` apply to the separate instance. Configure the original `resource_reconciler_socket`. The account Worker reads the endpoint through its original environment allocation. Reallocate only the admitted Worker after changing admission.

Pass the generated image and runtime arguments to the Docker boundary along with `--codex-provider-root <state_root>/codex-providers`, `--codex-security-manifest` and `--codex-security-sha256`. Precreate the Provider root with mode 0700. Load the dedicated enforced AppArmor profile and pin both image IDs in the policy. Gateway connects to the verified private bridge address returned by the physical boundary. Keep that bridge reachable from the Gateway process. The Codex port stays within the private Docker network.

The deployment places the Gateway model broker and its admitted execution pool on the same host. A provider needs a local physical receipt and the mounted Unix socket before it can serve model requests.

## Rollout and rollback

Verify every scheduling node's receipt before enabling an account. Test a new session using the original model picker and Web flow, including streaming, an approved command, cancellation, and a new container resuming the same thread and state volume.

Wait for the idle reaper to confirm deletion in YuanRong and Docker before changing a binding's image. Use the same offline migration command with `--provider codex`, the exact binding ID and its expected source image. Point the deployment config at the preverified target image and matching runtime. The binding and native volume remain the same. Restore the Gateway and verify that the same Web session resumes with that native thread.

## 中文部署摘要

Codex 独立容器复用原模型选择器、历史、Runtime、元戎分配和物理回收。Gateway 保存上游模型 Key 和应用连接令牌，容器只收到令牌摘要及限定模型的请求入口。宿主预置共享启动栈、精简镜像和回滚镜像后，先为单账号开启，复验首轮、单次审批、取消、空闲回收和原卷续聊。回滚前确认物理回收，再用同一迁移命令变更原绑定的镜像摘要。
