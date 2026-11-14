# Certificate lifecycle deployment

TLS belongs to the deployment boundary. Account/Runtime authentication continues
on every request and delivery. This directory does not implement a CA or ACME
client, copy account databases, or change business session lifetimes.

## Reference and support boundary

The inspected codeswarm `24f29148193b5b590fe9f4b3e21f779c87253e5e` account_http
loads TLS once at startup. Its OAuth token refresh is unrelated to certificate
renewal. The existing codeswarm public deployment uses Caddy 2.11.7 with ACME IP
certificates and automatic renewal. A downstream nginx certificate *copy* does
not inherit Caddy's reload behavior. Code Platform needs either direct Caddy
termination, or the verified consumer below. No external Caddy source is changed.

## Issuance, renewal and loading

Prefer `Caddyfile.public.example` for a new public deployment: Caddy terminates
HTTPS, renews with the configured CA, and loads renewed certificates itself.
Persist its storage, retain challenge reachability, and pin the supported binary
or image version. Do not run two independent issuers for an existing shared site.
An IP requires CA/client support for IP issuance; a placeholder domain is not a
usable certificate. Existing public issuer configuration stays operator-owned.

For internal account HTTPS, use `Caddyfile.internal.example` and the dedicated
systemd service template. Keep the account HTTP process bound to `127.0.0.1` in
the **same network namespace** as its TLS proxy. Across hosts, expose only the
proxy's TLS port with the intended private DNS/IP SAN and caller firewall rules.
Gateway still points at HTTPS and verifies its configured `ca`. `tls internal`
automatically renews short-lived leaves and intermediates; distribute the stable
root certificate only. Preserve the CA storage across container replacement;
never mount root private keys into Gateway, account or user execution containers.
The root trust's eventual expiry requires planned trust migration and is alerted,
not silently replaced. Multi-host services need their own reachable names and
explicit trust distribution; a loopback example is not a multi-host test result.

## Existing nginx consumer

`certificate_lifecycle.py lifecycle.json` reads a trusted operator manifest (see
`lifecycle.example.json`). It does not issue certificates. The source must be
maintained by Caddy/ACME/enterprise PKI. Each `publish` item:

1. Copies a source pair to a private version directory and checks pair, chain,
   hostname/IP, validity and remaining lifetime before publication.
2. Atomically switches `destination/current` to that version, runs the explicit
   syntax and reload argv without a shell, then connects with full TLS verification
   and checks the **served leaf fingerprint**. Command exit zero alone is not success.
3. Restores the previous pointer and reloads it on failure. Published prior versions
   remain for operator-reviewed rollback; no generic cleanup removes user volumes.
4. On a later run, repairs a disk/served mismatch even when the source did not
   change (for example a crash between publication and reload). Interrupted
   rollback/host loss may need operator intervention; no zero-downtime guarantee.

Mount the **whole destination directory**, not individual cert/key files. Configure
nginx `ssl_certificate /tls/current/cert.pem` and `ssl_certificate_key
/tls/current/key.pem`. The parent directory must be traversable by the configured
consumer UID/GID; version files are mode 0600. Prepare the initial `current` pair
and validate it before changing a live proxy config. One operator owns each
manifest/destination; the local state lock is not a distributed lock. Never share
a destination between manifests. Manifests and directories must be writable only
by the trusted operator: argv hooks have that operator's privileges.

A `monitor` item checks a direct managed TLS endpoint without copying or loading
files. `watch_ca_files` adds CA expiry warning. System trust is the default;
`endpoint.ca_file` selects an explicit trusted CA. Certificate validity and chain
checks are never disabled to obtain a successful health check.

## Scheduling and alerts

Install the templates with paths adjusted to your deployment. Create the state
directory (0700), operator-only manifest and certificate parent permissions first.
Enable `code-platform-caddy-internal.service` and the instance
`code-platform-tls@DEPLOYMENT.timer` through the existing service manager.
The timer runs every five minutes with jitter and catches missed runs after boot.
No package import or image startup automatically installs host services.

The check writes atomic `status.json` and `tls.prom` files and structured journal
output. Renewal/source, certificate, reload and probe failure cause exit 1 and
systemd failed status; near-expiry and CA-expiry warnings also fail the check.
Thresholds must match lifetime (example: public short-lived IP cert: one day;
Caddy internal 12-hour leaf: one hour; root: 30 days). Alerts do not send email or
messages by themselves. Connect `alerts.yml` to your existing Prometheus and
Alertmanager; expose only `tls.prom` through its textfile collector with appropriate
read permissions, never expose state/config/key directories. The stale-check and
missing-metrics rules cover timer/host failures that cannot emit their own alerts.
Journal/failed-unit alerts are available without a notification integration; delivery
to a person requires the deployment's configured receiver. No receiver is bundled.

If issuance fails, leave the last valid certificate loaded, emit an alert and retry
on the next timer. Never regenerate a trust root as an error recovery shortcut.
When a certificate has expired, TLS remains fail-closed until valid material arrives.
Verify real login, revocation and an existing session after deployment changes;
a certificate probe does not prove business functionality.

Tests: `python3 tests/unit_tests/cloud_workspace/test_certificate_lifecycle.py -v`.
Real renewal can be exercised in isolated Caddy storage with shortened test leaf
lifetime and renewal scan interval; production examples retain Caddy defaults.

References: [Caddy Automatic HTTPS](https://caddyserver.com/docs/automatic-https),
[internal issuer](https://caddyserver.com/docs/caddyfile/directives/tls#internal),
[nginx graceful reload](https://nginx.org/en/docs/control.html).
