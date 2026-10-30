# OpenCode AgentAdapter pilot

This guide describes an unpublished isolated candidate. The default remains agent-core. OpenCode uses the official HTTP/SSE interface directly; the main distribution still depends on Core.

## Select in the existing chat UI

In a new single-agent conversation, select OpenCode in the Provider dropdown beside the existing Swarm model picker. Choose a model already configured in Swarm. Existing conversations stay bound; create another conversation to switch Provider. Navigating back or refreshing restores the binding. There is no separate model configuration form.

A normally installed plugin must register `opencode-direct` under `jiuwenswarm.agent_adapters`. This task only has an experimental registration package. Configure the borrowed official service URL, fixed workspace and authentication through plugin configuration; remote connections require HTTPS. The service owner uses `opencode_models.build_server_model_config()` to generate private official startup configuration from the normal Swarm ModelCatalog, keeping native permission checks. This fragment contains credentials and must never be exposed to the UI, logs or Git.

This pilot uses a startup snapshot for supported OpenAI-compatible individual models. Refresh the OpenCode service after changing Swarm model configuration. Stale snapshots, OpenAIAccount, model groups and unmapped options fail explicitly, without falling back to Native. Legacy explicit `opencode.model` remains compatible. Reusing the model picker does not imply live service configuration synchronization or support for every model protocol.

`JIUWENSWARM_AGENT_SDK` remains a legacy default. Active sessions retain their connection; an empty session uses current configuration at first execution. Configuration revisions are not durably bound yet. Cold restoration after native-session release is rejected. The adapter cleans up owned sessions, not the borrowed server.

## Validation and remaining scope

The actual Swarm browser→Gateway→Front→Worker/Runtime→OpenCode flow passed two-model selection, replies, existing approval/rejection UI, exit7 failure history/UI, cancellation while awaiting approval followed by another turn, default Native execution, and binding/history restoration after navigation and refresh. A separate environment with no Core distribution also passed real execution with both models without loading Core modules. Component previews do not count as channel acceptance.

Nothing has been submitted or released. Team, Native product tool injection, a second external Provider, cold restoration, standalone plugin installation and supported optional-Core packaging remain unimplemented. Permission mapping does not imply full Native governance. Invocation completion, command exit success and task acceptance remain distinct; missing exit codes stay unknown.


## Templates, Skills and MCP (N01–N04 candidate)

Reuse the original Experts, Skills and Extensions controls. Third-party agents settings do not select the Provider of a conversation. The direct pilot still uses explicit plugin connection configuration; existing Core-backed CLI settings are not direct-server bindings.

Portable template persona is passed separately as native system instructions. Conflicting template runtimes, private runtime configuration and Native tools/rails/subagents fail before prompting. Omitted template/plugin/MCP fields preserve equipment; explicit empty values clear it. Failed mounting does not replace saved equipment. Skill chips express turn intent, not a persistent allowlist; original installation and enablement remain authoritative.

For Skills/MCP, configure `opencode.cli_path` with a normally installed official CLI and an absolute `opencode.directory`. The adapter owns a private official service per conversation, preserving the project cwd and reusing Swarm's model catalog. Complete Skill resources and supported connector configuration are prepared in private task-owned directories and removed on close. Existing connector authorization and credentials are reused; runtime approvals remain enabled and are presented sequentially through the original channel.

Borrowed `opencode.url` mode still supports text and portable templates but requires owned CLI mode for Skill/MCP equipment. Shared service configuration is never patched. Only portable Skill/MCP plugin components are supported, not arbitrary Hooks or Native tools. Remote OAuth refresh, Code snapshots/diffs/undo, cold recovery, another external Provider and standalone distribution remain outside this delivery. Service startup and equipment changes have preparation latency.

With an owned CLI service, a new conversation uses the project selected in Swarm; opencode.directory is only the fallback when no project is selected. Existing conversations retain their bound directory when omitted and reject a different directory. Borrowed URL services remain restricted to the configured directory.

## Permission profiles (candidate)

Owned CLI sessions reuse the chat permission selector: Default asks through OpenCode; Full Access permits tools while keeping user questions. Automatic is unsupported. The setting remains global; active sessions apply changes after the turn, without answering pending approvals. The selector retains Swarm’s original profile labels, without status badges or effective-status tooltips. Native readback and pre-execution checks remain in the backend. Existing Skill/MCP installation and enablement gates remain. This does not imply full Native governance. Borrowed URL servers do not support profile switching and are never globally reconfigured.

## TLS connection diagnostics

The generic native "unknown certificate verification error" reports a TLS connection failure during handshake or certificate verification; it does not prove an untrusted certificate. Specific certificate errors retain their verification message. Unknown bodies remain private, verification stays enabled, and requests are not automatically retried. Transparent proxies may apply even without HTTP_PROXY; inspect the actual route. Model-domain direct routing is a local network setting, not a plugin default or an execution Provider change.


The execution engine menu reuses the existing composer control between permissions and models. Options come from installed plugins that advertise their supported modes. Existing conversations stay bound. Plugin availability does not imply authentication or model connectivity; runtime checks still apply.


## Optional Native and desktop distributions (2026-10-30 candidate)

The external profile keeps the existing Swarm UI, Runtime, Gateway, history and approval channel. The base Python package no longer requires Core. Default `uv sync` still installs the pinned Native integration; `pip install '.[native]'` selects the full combination. Use `uv sync --locked --no-default-groups --extra dev --no-editable` for an external build. The Core pin is unchanged. OpenCode is discovered through a real entry point, without a probe distribution or PYTHONPATH.

Build the Linux test bundle with `bash scripts/build-electron-linux.sh external`. Outputs are a portable tarball and Debian package under `dist/`, with SHA256 files. The existing frontend, frozen backend and official Electron runtime are reused. Linux serves the UI over HTTP with an absolute asset base. No user configuration, model credentials or OpenCode CLI is bundled. Install OpenCode normally, use PATH discovery or an explicit CLI setting, and configure an OpenAI-compatible endpoint through Swarm's existing model settings.

Windows: `scripts/build-electron-exe.ps1 -BuildProfile external -NoSign -SkipInstaller`. macOS: `JIUWENSWARM_BUILD_PROFILE=external bash scripts/build-electron-exe.sh --test`. These external platform paths are not yet built or tested on their target systems; signing, notarization and release remain separate work. The existing Native defaults remain available.

This profile targets OpenCode single-Agent/Code execution. Native Team, memory/recommendations/designer and Core OAuth paths are not feature-parity claims. Unavailable Native sessions are rejected instead of being rebound. Basic hooks run in the existing Registry; advanced Core callback options are rejected explicitly. A separate Provider distribution, a second Provider and cold restoration are not delivered by this build.


## CLI discovery and HTTP/SSE boundary (2026-10-30 candidate)

Selection order: explicit `opencode.cli_path`, explicit `opencode.url`, PATH, then current-user installation hints. An invalid explicit CLI fails without fallback; an explicit URL never starts a local service. Discovery does not run shell profiles, install/upgrade a CLI, or search relative PATH entries inside projects. Missing installations get an installation/configuration diagnostic instead of a URL syntax error.

OpenCode hints include `~/.opencode/bin` and `~/.local/bin`, Homebrew locations on macOS, and current-user Scoop shims / LOCALAPPDATA WinGet Links on Windows. Windows launches native executables directly; cmd/bat wrappers require an explicit native executable path rather than an implicit shell. Windows/macOS path rules have deterministic coverage; native-system acceptance remains pending.

Owned services without a configured directory use the existing Swarm default project directory. Each conversation prefers its selected project and retains the binding. Borrowed URL services still require an explicit directory. Models, permissions, approvals and history use the existing Swarm flow, with no new UI or user configuration writes.

`opencode_transport.py` owns only HTTP JSON, health and SSE framing; `opencode_service.py` owns private service processes/directories; the adapter maps native events, while Runtime retains scheduling and completion policy. The small CLI lookup helper does not own registration, models or lifecycle. No old Python SDK or Node bridge is added; a future compatible official SDK can replace the wire boundary.

Use `assemble-electron-linux.py --profile external --dist-dir <separate-output>` to retain bundles still used by running processes. Building a new artifact does not update the installed application.


## Startup probes and session initialization (2026-10-30 candidate)

Reuse existing AgentAdapter prepare/cleanup, Runtime scheduling, permission responses and history/error channels. Owned CLI health probes use a 0.5-second per-probe limit within the existing 40-second startup deadline. Only POST /session gets a separate overall budget: opencode.session_init_timeout defaults to 120 seconds and accepts finite values greater than zero and at most 600. Other ordinary APIs retain 15 seconds; turn_timeout remains separate. Failure/cancellation cleans owned resources; mutations are never automatically retried.

Transport failures expose a fixed operation and error class or HTTP status, with safe duration logging and no raw URL, response or credentials. Empty ReadTimeout text now reaches the original error channel with a useful category. No new UI state, model settings, scheduler, shared process pool or TLS bypass was introduced.

Copied SQL2Java project preparation still takes around 27–31 seconds and has independent plugin export errors; successful session creation is not plugin acceptance. A diagnostic-only official npm_config_cache experiment measured roughly 30/9 seconds for cold/second sessions. This is not a product default. Any future reuse should be limited to same-user downloaded dependency content, keeping configuration, credentials, permissions, MCP and session databases isolated; do not share all HOME/XDG or replace the official installer.

Locked non-editable external and frozen builds passed real Runtime read, permission, exit7/history and cleanup checks. External 97 and fixed-Core 124 regressions passed (overlapping suites). A Linux candidate is emitted separately under startup-fix-dist; the installed desktop is unchanged. Desktop clicking and Windows/macOS runtime acceptance were not performed this round.
