# Optional Web / TLS deployment switch

`proxy_switch.py` is an operator-run, replaceable deployment utility. It switches only the explicitly owned Web/TLS roles. Gateway, account authority, Router, Runtime, SDK and instance lifecycle do not import it. It is not a production orchestrator or a Docker authorization boundary.

## Configuration contract

Run `python3 deploy/web/proxy_switch.py /absolute/path/profile.json` as the trusted operator who already manages the isolated Docker engine. Keep manifests private; do not commit real certificates, credentials or environment files.

The JSON manifest contains:

| Field | Required meaning |
| --- | --- |
| `root` | Existing absolute directory owned by this deployment |
| `names` | Exactly two distinct, explicitly managed container names (Web and TLS); never a discovered shared pool |
| `owner_label` | `{ "key": "…", "value": "…" }`; existing containers and replacements must match |
| `files` | Absolute filename → SHA-256; include served artifact files, proxy config, TLS CA/certificate/key and direct-mode runner needed for recovery |
| `health` | `url` under `https://127.0.0.1:PORT`, hashed `ca_file`, expected `http_version` (10 or 11), optional `timeout_seconds` (default 30). Endpoint must return 200 with JSON `enabled: true` |
| `containers` | One role for direct TLS, two for proxied HTTP. Each declares `name`, immutable `image` (`sha256:…`), `user`, `memory`, `cpus`, `pids_limit`, `entrypoint`, `args`, `mounts` (`source`, `target`, `readonly`) |
| Optional role fields | `restart`, `read_only`, `tmpfs`, `log_driver`, `log_options`, `preflight_args` (e.g. nginx `-t`) |

Images must already exist locally. Files and mounts must resolve inside `root`; mounted files need hashes. Directory mounts may contain mutable owned runtime data: file hash validation does not freeze all directory contents. Manifests are trusted deployment input, not user-supplied requests. Host networking is explicit; capabilities are dropped and no-new-privileges is always set. Prepare and validate both direct and proxy profiles before an operational switch.

## Failure and recovery

1. Verify files, hashes, CA parsing, images, existing ownership/mounts, then run configured syntax checks without network. A preflight failure does not stop the current roles.
2. Stop and rename original containers, retaining their IDs and original running state. Start the desired roles and verify TLS readiness.
3. On failure, remove only replacements with this attempt's owner/release labels; restore original names and restart originally running containers. Missing-object responses from Docker may differ in case and object/container wording; daemon failures are not treated as absence.
4. A successful result prints retained container IDs/names. Reapplying an identical healthy profile returns `already_active` without replacement. Old containers remain stopped; no volumes are removed. Retention consumes disk until the operator reviews and explicitly retires owned backups.
5. If compensation itself fails, the error says `restoration needs intervention`; inspect retained original IDs and name ownership before restoring. Never delete another container to reclaim a name. Automatic compensation is bounded and cannot survive every host/power/process failure; do not promise zero downtime or atomic deployment.

For certificate renewal/loading and expiry alerts, use the separate [TLS lifecycle deployment](../tls/README.md). This switch utility itself does not manage renewal.

One operator must own the switch at a time. There is no distributed lock, background reconciler, automatic certificate renewal or business-level readiness check. HTTP `enabled` proves the account endpoint is reachable, not that a real account or Provider turn works; verify the UI separately. Direct TLS is a recovery profile and may have poorer connection reuse. After a direct-mode drill, restore the tested proxy profile and recheck UI recovery.

## Replacement / exit

A standard reverse proxy or orchestrator can replace this script once it passes the same preflight, startup-failure, health-timeout, connection-recovery and original-container preservation checks. Change deployment wiring only. Keep the HTTPS public origin, authentication, upstream HTTP/1.1 and WebSocket upgrade contract; do not modify application credentials or instance bindings. Retire this utility and its owned stopped backups only after replacement verification and evidence retention.

Tests: `python3 tests/unit_tests/cloud_workspace/test_proxy_switch.py -v` (fake Docker; no external writes). Real isolated fault injection and round-trip results are recorded separately in management report `PLATFORM_SYSTEM_RECOVERY_FIX_20261111`.
