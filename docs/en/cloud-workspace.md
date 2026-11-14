# Cloud workspace backend integration

This increment wires an independent account authority and durable environment policy into the existing Gateway and AgentOS Router. The normal Gateway remains the only public entry. Full account UI integration, cross-host Local/Cloud selection and synchronization are not delivered here.

## Composition

Run the account role with `python -m gateway.auth.account_http --account-auth-file /private/accounts.json`. Its private JSON contains `database`, `authority` and optional `session_ttl`. Non-loopback serving requires `--cert` and `--key`. Existing scrypt hashes and session digests are retained; registration recovery requires the authority's `operation_id` extension.

Use the normal Gateway entry and `agentos_router` with `user_id + agent_type` keys. Set `CODE_PLATFORM_CLOUD_CONFIG` and include `Cloud Workspace` in any existing extension allowlist. Required fields are `authority`, HTTPS `public_origin`, separate absolute `state_root` and `workspace_root`, immutable `image` (sha256 plus 64 hexadecimal digits), `frontend_endpoint`, `function_version_urn`, and `account_backend_config`. The latter references a private 0600 file containing the account service `url` and optional `ca`. Endpoint, namespace and URN must match the host Router. Registration defaults to disabled. Runtime UID:GID must match the private mounted files. Missing or incompatible composition fails startup; without this environment variable local operation remains unchanged.

The environment SQLite store has a single-writer file lock. Private directories/files use 0700/0600. Each container receives only its `/data` mount and current epoch's read-only `/run/jiuwenswarm` credential mount, independent config/data paths and `CODE_PLATFORM_ROLE=account-instance`. No account database or other account volume enters the instance. Existing Runtime and Provider permission checks remain authoritative.

## Recovery and authorization

Original account API paths and cookies remain. Registration records a recoverable intent and image snapshot and returns NEW; environment ensure or the existing connection warmup invokes the sole Router creator. The plugin contributes only cloud environment RPCs and leaves `session.execution.options` in place.

An ambiguous create is reconciled through bounded inventory and exact instance details, never another POST. Startup cleanup protects account instances. A DELETE acknowledgement is insufficient: an authoritative instance GET returning 404 is required. Bindings with physical_verification additionally require physical completion before DELETED permits a new epoch. Pending deletion may retry only the known instance. Rebuild retains image and data; network loss closes the cloud connection without deleting the binding.

Unbound existing accounts may log in but cannot receive a fresh default environment. An operator may explicitly call `EnvironmentStore.adopt_existing` with a reviewed compatible instance, immutable image, private workspace and credential reference. It preserves bytes and rejects replacements. Legacy six-field credentials and historical environment databases require a separate reviewed migration; they are not automatically rewritten.

The original authenticator supplies an in-process authorization scope across the original queue. Cookies are never serialized into E2A. Signed requests bind target, epoch, purpose, expiry and nonce. Only narrowly listed existing maintenance/cron operations can use service assertions. Platform logout revokes the authority session before fencing the current epoch; subsequent requests and WS/file delivery recheck identity. Direct authority-side revocation can leave already signed in-flight assertions valid for at most 15 seconds, while new requests and Gateway delivery consult the authority again. Runtime cancellation semantics are unchanged.

## Validation limits

As of 2026-11-10, three candidate roles were built with the unchanged Core/protocol pins and verified installed sources. Tests on the user-designated server exercised isolated TLS accounts, original Router allocation and real AGENT_READY, Gateway WebSocket requests/reconnection, lost creation acknowledgement reconciliation, authoritative DELETE/GET404 and epoch recreation, and session revocation. No production deployment, complete UI, real Provider/model workload, cross-node volumes or legacy credential migration was accepted.

**B01 cloud file API confinement is fixed; targeted B02 isolation checks now pass in the dedicated Docker log-adapter deployment. Production release remains blocked on operational readiness.** Account-bound file requests use the existing Router/E2A route and Runtime file adapter, with descriptor-based no-follow access and no SDK file fallback. Final B01 checks passed 24 local cases and 43 server file cases. Subsequent two-account synthetic-log probes confirmed that the current Docker infrastructure mounts the entire pool log root into each instance, allowing peer-log reads. Central collection is an operations requirement, not an account-sharing requirement. Isolation needs supported private log mounts or independent infrastructure boundaries; file API checks, read-only mounts or chmod000 do not substitute for it. No external SDK or existing resource pool was changed.

The account adapter explicitly contributes a trusted routing_user_id through the existing AuthResult. The FastAPI/WebSocket adapter now retains that result and its request/delivery guards. Existing IAM username mapping is unchanged. The existing file HTTP contract still requires user_id matching the authenticated account. See [role build requirements](../../deploy/cloud-workspace/README.md) for immutable role sources and the separate Python3.11 infrastructure bootstrap layer.

Historical lifecycle evidence is in PLATFORM_CLOUD_ROLE_E2E_20261109; B01 results are in PLATFORM_CLOUD_FILE_BOUNDARY_20261110, and the pre-fix log probe and 329-case regression are in PLATFORM_CLOUD_LOG_ISOLATION_20261110. All task-created instances and containers were reclaimed; private synthetic data was retained. Metadata for 180 original containers and the inventory of five original Yuanrong instances matched the initial baseline. Backend lifecycle success is not complete feature 1–2 isolation acceptance.

## Cloud file access boundary

In account-bound mode, the existing `/file-api` uses the original Router/E2A route and Runtime file adapter. The deployment supplies the workspace root; descriptor-based traversal rejects symlinks in every component. Unsupported agents fail closed without falling back to the Yuanrong file API. Symlinks, including links within the root, are unavailable. Normal reads, writes, chunked uploads, listings and mkdir retain their public endpoints. Gateway and Agent images must support the same operations; existing pinned bindings are not upgraded automatically. This verification does not cover every attachment/tool file path or shared infrastructure logs.

## Optional execution-pool binding

An operator may set resource_pool_id to pin the pool label and existing frontend_endpoint/namespace/function_version_urn in the environment profile. Reads, registration recovery and imports reject mismatches. Legacy unbound records are not assigned automatically; removing the setting also fails closed. This guard does not create or select a Yuanrong pool: each Gateway still uses one existing Router endpoint. It does not establish log isolation. Use separate state or an explicitly reviewed migration; do not change existing deployments in place. The affected suite passed 389 tests, while multi-pool routing remains unimplemented; the subsequent Gateway image passed locked-source verification. See the management record PLATFORM_CLOUD_POOL_BINDING_20261110.

The deployment adapter is now in deploy/cloud-workspace/docker_log_boundary.py. Only dedicated test infrastructure uses it; existing deployments are unchanged. For the previous hardcoded-rule candidate, all 25 focused tests and real two-account mount/log checks passed, including proxy restart and instance recreation. Service supervision, failure-injection acceptance, connection limits and log collection/quotas remain production gaps. See the role-build instructions and management record PLATFORM_CLOUD_DOCKER_LOG_BOUNDARY_20261110.

The adapter is now a temporary, replaceable deployment component. An explicit --workspace-name-pattern is required; application services and durable bindings do not depend on its type or endpoint. Compatible naming-rule changes preserve the existing log mapping. All 43 local tests passed, including real CLI/Unix-socket forwarding to a fake Docker endpoint. The same revised script was subsequently verified on a dedicated test foundation at 113.207.105.228: explicit configuration, two-account log isolation, controlled manual proxy restart and original-Router deletion/recreation passed. See PLATFORM_CLOUD_LOG_ADAPTER_SERVER_20261110; automatic recovery and production readiness remain unverified. A replacement must pass the same isolation outcomes before deployment switches and adapter retirement, with no fallback to shared logs. See the [configuration and exit contract](../../deploy/cloud-workspace/LOG_BOUNDARY_CONTRACT.md).

The deployment adapter now bounds connections and socket I/O, cleans up on SIGTERM, supports explicit locked stale-socket recovery, and includes a systemd template. All 58 focused tests passed. Dedicated-server fault injection confirmed safe failures with the proxy stopped or its test upstream returning 503, and automatic proxy recovery after SIGKILL. However, losing a successful Docker-create response left a never-started container after the Yuanrong API returned 404; a subsequent original-chain retry created another physical container for that workspace. Fault acceptance therefore remains blocked. The adapter must not replay requests or become a second instance allocator or reaper; no production deployment is accepted. See PLATFORM_CLOUD_LOG_ADAPTER_RELIABILITY_20261110.

### Lost create responses and physical reconciliation

New dedicated deployments may explicitly enable a restricted physical completion endpoint. The existing Router requires both Yuanrong absence and physical confirmation before completing deletion. Failure retains DELETING and blocks the next creation. A deployment-only durable dispatch receipt and unique workspace container name prevent duplicate dispatch; compensation only removes an exactly owned container that has never started, without forcing deletion or removing volumes. Gateway receives no Docker socket; the SDK is unchanged. See the [deployment contract](../../deploy/cloud-workspace/LOG_BOUNDARY_CONTRACT.md) for configuration, permissions, unresolved outcomes and replacement. Existing bindings are not migrated automatically.

The current candidate has passed isolated physical-reconciliation acceptance. Earlier lost-response failures describe the previous candidate, not an open blocker for this scoped repair. See the [candidate handoff and recovery guide](../../deploy/cloud-workspace/CANDIDATE_HANDOFF.md) for configuration, per-state recovery and rollback boundaries. Production operations and broader business acceptance remain separate; no production deployment is included.

Internal supplement and evolution-approval requeues preserve the original account scope. Sending still checks session revocation; user requests never fall back to maintenance authorization.

## Candidate cloud sign-in and environment entry

The Web entry extracts codeswarm's builtin username/password login, identity invalidation and logout. Account Kit still owns existing model authorization. Serve static UI, account HTTP and WebSocket from the same HTTPS origin matching `public_origin`; the default account path is `/api/v1/auth/organization`. Show registration only when `registration_enabled=true`.

First entry explicitly prepares the cloud environment; an existing allocation goes through the original ensure/readiness path before mounting the application. Authentication and environment failures expose retry instead of indefinite config loading. Logout closes the connection before revocation; unconfirmed revocation shows an error. Real UI/Provider acceptance on this candidate remains in progress; previous-version evidence is not a substitute.

The circular account badge shows the first two username characters (uppercase letters). The full username remains available through its tooltip and accessible name; only the avatar button remains in the sidebar. Clicking it opens the account menu with logout, which still uses the existing revocation endpoint.
Codex permission changes apply before the next turn. The platform reconnects its owned client, resumes the same native thread and confirms the requested policy before execution. Failed recovery blocks execution; history and selected MCP connections are retained without modifying the official SDK.


### Automatic account-probe recovery (2026-11-11)

Reuse codeswarm's sequential recovery: after an unavailable probe settles, retry after two seconds without invalidating a slow response. Within the existing ten-second deadline, retry network transport errors and HTTP 502/503/504 once after 250 ms; a successful transient retry retains the mounted workspace. Persistent failures still disconnect and close the workspace; recovery uses a freshly verified principal to retain the same account's route. No cached identity authorizes access. HTTP 401/403 and invalid identities are not transport retries, and a missing endpoint cannot downgrade a known cloud session to local mode. Creation, logout and Runtime execution are never replayed. Diagnostics contain only failure category, status, attempt count and elapsed time.

This fixes the missing UI recovery path, not the unconfirmed original intermittent transport cause. Persistent outages may still discard unsent drafts; persisted history recovers through the original session path.

### Same-identity and history recovery (2026-11-11)

After a sustained account-service outage, a fresh server verification of the same principal and session revision resumes the previous entry state, preserving model preferences without full-page navigation or another environment preparation call. Identity or session-revision changes still clear account-scoped caches. Unsent drafts may still be lost during a sustained outage.

Completed output is reconciled through existing history loading. Expired replay must not duplicate completed replies or restart their timers; active output and pending controls retain their existing resume path. See the [deployment recovery contract](../../deploy/web/README.md) for optional Web/TLS preflight, compensation and replacement limits. These are isolated candidate changes, not a production release or acceptance of every capability.

Image export is explicitly disabled with an explanation in the current cloud-instance deployment. The page no longer queries unsupported export jobs automatically, and existing job records are retained. Local deployments retain image export. Server-side file access restrictions are unchanged.

When a page is reloaded while awaiting approval, the existing control and cursor can be restored directly only when the authoritative execution snapshot confirms that every unfinished execution awaits a known control. Running, queued, or incomplete snapshots retain incremental replay. Recovery neither resubmits a task nor approves a tool automatically.

## Code workspace entry (P1S-01 candidate)

A new Code chat has three controls: local directory, Local/Cloud, and a cloud environment/project menu visible in Cloud. The menu browses cloud Code directories, creates folders, and creates or reuses the account's default environment. After creating a folder, select Open to bind the project. For a subdirectory of an existing project, select its registered project root.

Cloud paths belong to the routed instance. A browser cannot supply an arbitrary server root. Local directory access requires the desktop bridge or the local service; a cloud browser never falls back to a server-native picker.

Choosing Cloud in the local page immediately reveals cloud controls while retaining the URL, draft and attachments. Explicit environment, directory or folder actions use the existing local cloud-account dialog and same-origin service to access the configured cloud host. Login resumes the original form. Cloud directories do not replace the local project selection, and files are not copied automatically. Deployments reuse the private CODE_PLATFORM_LOCAL_SYNC_CONFIG. Legacy entry URLs remain compatible with older clients, but the new controls do not navigate. The account still has one default environment, prepared through the existing idempotent service.

After selecting and opening a cloud directory, create a cloud session from the local page. Models and execution providers come from the cloud environment. Messages, tool approvals, stopping and history reads use the original cloud session without page navigation. Local project selection remains independent. Signing out closes cloud connections and clears their displayed session state. Reconnection recovers original session state without resending input. This does not copy files or history, or migrate running tasks between hosts.


The local sidebar uses the same circular avatar and account menu as the cloud UI. Before sign-in, a user icon opens the sign-in dialog. After sign-in, the avatar shows the first two uppercase username characters (for example, CH); click it to view the full username or sign out. Signing out restores the user icon.


The local dialog and cloud page share the account sign-in form. An existing valid session resumes cloud actions without another confirmation. Signing in only restores the form and never submits a creation automatically. Folder names can be entered while directories load, and loading can be dismissed; creation waits for directory validation. HTTP and WebSocket transports are reused while every operation still receives fresh authorization checks.

Directory operations have a 150-second total processing budget, a 155-second browser deadline and a 175-second local Web proxy deadline; ordinary HTTP requests retain 30 seconds. Unknown creation outcomes are not replayed: read back the directory first. Diagnostics contain stage, status and elapsed time, without credentials or directory contents.


Cloud history restoration starts before auxiliary initialization and independently of Local connection readiness. Connection setup and history responses have separate timeout budgets; transport failures are not treated as deleted sessions. Reconnection rereads session state and unfinished history without resending user messages. Only concurrent unfinished account status requests are coalesced; authorization remains live.


Cloud session connections wait directly for fresh server authorization, avoiding a redundant serial status preflight. Identity lookup and the independently authenticated handshake overlap. Only healthy HTTP transports are reused; permissions are checked again for each operation. A rejected connection can open the existing sign-in form. Reopen or refresh the original session to restore history after signing in; messages are never resent automatically.
