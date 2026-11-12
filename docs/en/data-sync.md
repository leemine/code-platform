# Explicit project directory sync (initial P1S-02 candidate)

This optional feature copies selected project IDs, names and work modes. It does not copy paths, files, sessions or history, and cannot change execution targets. This is retained integration infrastructure. The product UI does not expose inventory publication or synchronized project lists; file and session synchronization is not implemented.

The Gateway must use its original cloud account configuration. An operator enables the plugin with `CODE_PLATFORM_DATA_SYNC_ROOT`, an absolute, canonical, private (0700), service-owned persistent directory. Without this variable the plugin is disabled. Do not mount its storage into execution containers.

Use the original account login flow. Inject the valid session through `CODE_PLATFORM_SYNC_ACCOUNT_TOKEN` and a stable random 32-byte hexadecimal source proof through `CODE_PLATFORM_SYNC_SOURCE_PROOF`. Keep credentials in a trusted operator environment, out of arguments, repositories and shared logs. Device delegation and secure credential storage are not provided yet.

```bash
python -m jiuwenswarm.data_sync --url wss://cloud.example/ws \
  --installation-id laptop-a --project ORIGINAL_PROJECT_ID
```

Repeat `--project` to select multiple original ProjectStore IDs. Another installation of the same account uses its own stable installation ID and proof with `--receive-only`. `--withdraw-all` withdraws this source's metadata without deleting source files. Calls are one-shot; projects are never automatically selected. Remote connections require verified wss; use `--ca-file` for a private CA. Never place credentials in URLs. Redirects are rejected to prevent token forwarding.

Results report source, count, watermark and status; `account_complete` remains false. Private replicas live under the original data root's `data-sync/`, outside executable projects. Failures mark the replica stale and preserve checkpoints/receipts for the next run. Revoked sources cannot register again with an old proof. Windows secure export, original content sync and GC remain pending.


For cloud projects, prepare and connect the original Cloud environment first, then explicitly select its original project IDs:

```bash
python -m jiuwenswarm.data_sync --url wss://cloud.example/ws \
  --installation-id laptop-a --kind cloud --project CLOUD_ORIGINAL_PROJECT_ID
```

The installation ID and proof identify only the local receiver. Gateway reads the cloud role through the original authenticated Router transport. Clients cannot claim a cloud source or supply account, instance or root selectors. Both Gateway and AgentServer need cloud export support; older versions fail explicitly. An unavailable environment is not started, created or reclaimed, and failed exports never withdraw accepted metadata. With cloud mode, `--withdraw-all` withdraws only the cloud source's metadata. `--receive-only` reads accepted replicas without contacting or starting the cloud source.

A rebuild of the same logical environment and workspace retains the source ID and increments its generation, invalidating old cursors. Changed workspaces, revoked sources and legacy self-claimed cloud sources require explicit handling; automatic repair is not implemented. Retrying a persisted operation after a lost response returns the original commit receipt, not proof of current source availability. Export is assembled into the existing role and runs on demand, without a background scheduler. Real cloud deployment and packaged candidate CI remain pending.


## Product UI and local cloud account

The Code composer retains three controls: the local directory, Local/Cloud selection, and a cloud environment menu for choosing a cloud directory, creating a folder, or preparing the account environment. There is no inventory-sync menu or manual publication requirement. Switching entries changes where the user works; it does not transfer files or sessions.

To enable cloud sign-in in the local footer, set `CODE_PLATFORM_LOCAL_SYNC_CONFIG` to a private (0600), service-owned regular JSON file:

```json
{
  "public_origin": "http://127.0.0.1:8080",
  "cloud_origin": "https://cloud.example",
  "installation_id": "laptop-a"
}
```

The public origin must be loopback. The cloud destination is fixed HTTPS; an optional `ca_file` supplies a trusted private CA bundle. Local and cloud role configuration is exclusive. Explicit extension allowlists must include `Project Directory Sync`. The local adapter requires the original shared-directory AgentClient. Existing configuration names remain compatible; signing in does not register a source or publish inventories.

The footer manages only this local entry's cloud account session. It displays the signed-in account and sign-out action. Passwords are not persisted; the session uses a same-origin HttpOnly cookie, and account changes invalidate late responses. The cloud entry retains its original account login flow.

Configure navigation with `CODE_PLATFORM_CLOUD_ENTRY_URL` and `CODE_PLATFORM_LOCAL_ENTRY_URL`. A disconnected cloud entry means a navigation URL is missing, rather than rejected credentials. Use a browser-trusted HTTPS certificate; do not disable TLS checks or bypass browser security warnings.
