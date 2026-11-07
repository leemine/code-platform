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

OpenCode hints include `~/.opencode/bin` and `~/.local/bin`, Homebrew locations on macOS, and current-user Scoop shims / LOCALAPPDATA WinGet Links on Windows. Automatic Windows lookup skips `.cmd`, `.bat` and `.ps1` launchers and continues looking for a native executable without invoking a shell. npm hints check `node_modules/opencode-ai/bin/opencode.exe` beneath absolute PATH directories, `NPM_CONFIG_PREFIX` (also its lowercase environment spelling), and `%APPDATA%/npm`. This reuses the native file selected by the official postinstall; discovery does not choose CPU variants or read binary contents. Explicit script selections and invalid paths still fail without fallback. Missing native files require normal installation or an explicit native path. A custom npm prefix must be visible on PATH or in the prefix environment variable; project dependencies and arbitrary disk locations are not scanned. Deterministic path coverage does not replace pending Windows/macOS native chat acceptance.

Owned services without a configured directory use the existing Swarm default project directory. Each conversation prefers its selected project and retains the binding. Borrowed URL services still require an explicit directory. Models, permissions, approvals and history use the existing Swarm flow, with no new UI or user configuration writes.

`opencode_transport.py` owns only HTTP JSON, health and SSE framing; `opencode_service.py` owns private service processes/directories; the adapter maps native events, while Runtime retains scheduling and completion policy. The small CLI lookup helper does not own registration, models or lifecycle. No old Python SDK or Node bridge is added; a future compatible official SDK can replace the wire boundary.

Use `assemble-electron-linux.py --profile external --dist-dir <separate-output>` to retain bundles still used by running processes. Building a new artifact does not update the installed application.


## Startup probes and session initialization (2026-10-30 candidate)

Reuse existing AgentAdapter prepare/cleanup, Runtime scheduling, permission responses and history/error channels. Owned CLI health probes use a 0.5-second per-probe limit within the existing 40-second startup deadline. Only POST /session gets a separate overall budget: opencode.session_init_timeout defaults to 120 seconds and accepts finite values greater than zero and at most 600. Other ordinary APIs retain 15 seconds; turn_timeout remains separate. Failure/cancellation cleans owned resources; mutations are never automatically retried.

Transport failures expose a fixed operation and error class or HTTP status, with safe duration logging and no raw URL, response or credentials. Empty ReadTimeout text now reaches the original error channel with a useful category. No new UI state, model settings, scheduler, shared process pool or TLS bypass was introduced.

Copied SQL2Java project preparation still takes around 27–31 seconds and has independent plugin export errors; successful session creation is not plugin acceptance. A diagnostic-only official npm_config_cache experiment measured roughly 30/9 seconds for cold/second sessions. This is not a product default. Any future reuse should be limited to same-user downloaded dependency content, keeping configuration, credentials, permissions, MCP and session databases isolated; do not share all HOME/XDG or replace the official installer.

Locked non-editable external and frozen builds passed real Runtime read, permission, exit7/history and cleanup checks. External 97 and fixed-Core 124 regressions passed (overlapping suites). A Linux candidate is emitted separately under startup-fix-dist; the installed desktop is unchanged. Desktop clicking and Windows/macOS runtime acceptance were not performed this round.

## Codex main-agent candidate

Install with `uv sync --locked --no-default-groups --extra codex-direct` for the official Codex Python SDK/CLI 0.163.0 without agent-core. Reuse Codex enable/path settings under Third-party Agents and the existing execution-engine menu for new chat/Code sessions. Existing sessions keep their provider. When no path is configured, the official SDK selects its bundled runtime.

Models come from Swarm's shared single-model selection and must expose an OpenAI Responses-compatible endpoint with TLS verification. Personal Codex defaults/authentication, OpenAIAccount, model groups and unmapped request parameters are not silently substituted. Default/Full Access policies are confirmed against native responses; approvals and cancellation reuse existing controls. Missing exit codes remain unknown, and denied commands are not shown as successful.

This candidate is unpublished. Linux Runtime, Code commands and native approval controls have been exercised. Codex equipment, cold recovery, complete usage accounting, Claude, Windows/macOS and desktop runtime packaging remain pending. The closure fixes stale completed-request replay after Web refresh and the Front configuration import boundary. Active execution and approvals use the existing recovery channel. Historical calls without a result remain unknown rather than successful. Existing OpenCode and Native paths are preserved.

Codex availability does not require an exact SDK or CLI version. The official SDK owns CLI selection and compatibility; the `codex-direct` extra has no exact SDK pin. The lock and default desktop downloads currently record the tested 0.163.0 combination. Invalid explicit paths never fall back, and unsupported approval APIs or unconfirmed native permission policies fail explicitly. Upstream older-CLI warnings and managed-install manifest checks remain; the default download version is not a custom-CLI allowlist. Linux managed paths and the Gateway manifest location are covered; Windows/macOS and rebuilt installers still require native acceptance.


## Tool results and Codex certificate settings (2026-10-31 candidate)

A completed tool invocation does not imply exit code zero or task acceptance. Bash details show “Exit code not provided” when native exit evidence is absent; non-command tools such as Read have no command-exit warning. Native tool errors and explicit nonzero exits remain failures. Calls with no native result remain unknown. Existing Read history is supported without rewriting stored records.

Codex no longer rejects a model merely because Swarm saved verify_ssl:false. This Swarm HTTP-client option does not control the official CLI transport: certificate verification stays with the official SDK/CLI, with no insecure override or automatic model-config rewrite. Use the official trust configuration for private CAs. These source changes do not update an already installed desktop application.


## External execution timeouts (2026-11-02 candidate)

A model request timeout is not a whole-turn deadline. OpenCode no longer supplies an implicit 120-second turn limit. An explicit positive finite opencode.turn_timeout retains its existing meaning; absent/null means no turn deadline. Startup and API operation limits remain separate. Model timeout seconds still map to native request milliseconds. Owned services accept opencode.header_timeout_ms and chunk_timeout_ms; borrowed services remain configured by their owner.

Claude maps model timeout to API_TIMEOUT_MS rather than a 180-second turn deadline. Its Third-party Agents YAML entry accepts stream_first_byte_timeout_ms and stream_idle_timeout_ms; Codex accepts stream_idle_timeout_ms. Values are positive integer milliseconds and preserve native protections and limits. Saving existing cards preserves these advanced fields without new UI controls. Request, first-byte and stream-idle semantics are distinct. Unconfirmed execution termination or SDK shutdown keeps ownership fenced rather than admitting a replacement execution. Candidate source validation does not update an installed desktop application.


For the tested Claude CLI 2.1.274, the independent first-byte deadline is not active on the custom model endpoint route, although its setting reaches the CLI. The native request timeout remains effective. A supervised 300-second stalled-stream probe closed both connections and exited cleanly with code 0; the earlier unexplained 143 remains historical evidence, not a confirmed adapter defect.


## Large Codex tool output

Swarm projects at most 60,000 characters for a Codex command result and 2,000 for a child-agent command activity summary, including an explicit truncation marker. Short output is unchanged. The existing content/result aliases continue to carry identical bounded text. This only limits Swarm display and history: the official tool output seen by the model is untouched, and no command is repeated. Native exit codes, command success/failure/unknown and task acceptance keep their separate meanings.

Truncation diagnostics under provider.codex distinguish SDK-returned from displayed quantities. The SDK may already have truncated its output; these counts do not establish the full command output size. Swarm history does not store another full copy or invent an artifact link. The original send guard remains; other Providers and event types require separate review. This is a local fix candidate, not a released desktop update.


## Claude/OpenCode tool-output protection

Claude and OpenCode tool results now use the same Swarm display boundary: 60,000 characters for a result and 2,000 for a Claude child-tool activity summary, including a truncation marker. The content/result aliases remain compatible. Native error flags, exit codes and unknown outcomes are preserved; the external tool content seen by the model is untouched.

Normal OpenCode metadata stays intact. Oversized metadata is projected by whole fields, with explicit diagnostics under provider.opencode and priority for native exit evidence, truncation state and the complete outputPath. Paths are never shortened into a different path, and files are not automatically read or copied. Existing native spill references are not presented as new Swarm artifacts. No host execution flow is added; other event types require separate capacity review. This remains a local candidate. Claude live acceptance is pending because the existing model endpoint returned 429/1113; this is not a released desktop update.


## P1 input and equipment ownership

The existing chat Facade prepares the effective model, working directory and host history eligibility. Providers retain native protocol validation, immutable session bindings and SDK/API conversion. Existing model settings, execution picker, bound conversations and Native defaults remain in place. OpenCode assets use the original asset services; the host commits equipment only after a successful, current and uncancelled mount. Partial native configuration must be reconciled again before execution.

Active Swarm context queries and manual compaction remain unsupported rather than returning fabricated zero usage; passive Codex native counters are described in the section below. OpenCode persona/question support and task=deny remain unchanged; The P2 section describes main role instructions for Claude and Codex. No new settings page or execution scheduler was added. See F_20261104_1030_provider-input-ownership for evidence and validation limits. This candidate has not been committed or released and does not update an installed desktop application.

## Codex native usage observation

The Codex candidate reuses the existing bottom statistics control for reported main-thread input, output, cached input, cache write, reasoning output and total tokens. Only returned, interpretable counters are shown. Window capacity may appear independently; context occupancy and cache hit rates are not guessed. Missing metrics are hidden, while explicitly reported zero remains visible. A resumed or post-cancellation turn without a trustworthy baseline has no invented turn usage. Cumulative snapshots replace previous values rather than being added again.

The original chat, history and controls remain in use, with no additional compaction, page or execution flow. Native behavior is preserved; Claude/OpenCode extension status is described below. See F_20261104_1230_codex-native-usage-observation. This local, unpublished candidate does not update an installed desktop application.


## Claude / OpenCode native usage and Tokens

The single-row label for all three external executors is Tokens. Missing fields stay hidden in the existing statistics control and history. Claude uses native model_usage, including subagents, without adding main-loop usage or synthesizing an unreturned total. Native CLI versions can change resume accounting, so these snapshots are labeled Native usage, not a complete Swarm session total. OpenCode counts completed message identities once and ignores duplicate step views. Unknown zero provenance or a missing count in any message hides that aggregate field. Native input, output and cache semantics remain distinct; occupancy and cache hit rates are not inferred.

Real OpenCode two-turn execution, same-native-session continuation after a Worker restart, database reconciliation and UI refresh have passed. Claude deterministic mappings passed; its existing model service returned HTTP429, leaving real channel acceptance pending. No new execution, approval or compaction flow was introduced. Native statistics remain available. This uncommitted candidate has not updated any installer. See F_20261104_1230_codex-native-usage-observation.

### beta5 test release scope (2026-11-04)

beta5 groups bounded tool output, P1 execution/equipment ownership, and native Tokens observation, reusing the existing chat, history, and usage UI. All desktop builds use the same merged commit and exclude user model configuration. Claude live acceptance remains blocked by HTTP 429 from the original service. Windows is unsigned; macOS arm64 has no Developer ID signature or notarization. A successful build is not an end-to-end desktop chat acceptance result. Only this project's version changes in the lock; external SDK/Core revisions remain fixed. See F_20261104_1430_provider-beta5-release.

## Main Agent role template (P2 candidate)

A configured caller can include both the execution Provider and the ID of an installed role template in the existing `session.create` parameters for a single-agent session. Include these fields alongside the usual workspace, mode, and `create_token` parameters.

```json
{"execution_provider": "codex-direct", "role_template_ref": "architecture-reviewer"}
```

This entry point accepts a registered single-agent Provider that declares and implements main Agent instructions. The bundled `claude-direct`, `codex-direct`, and `opencode-direct` adapters implement the capability. It reads UTF-8 Markdown persona files from the existing Experts catalog with a total budget of 8 KiB. A template may omit its runtime or declare the selected Provider with empty private configuration. A template that declares actual Skills, MCP connectors, subagents, or other unsupported features is ineligible for this entry point. The selected Provider receives the role instructions, so keep credentials out of the template.

Select another compatible expert in the existing picker for a single-agent session. The next turn uses the new expert and continues on the same Provider and native session. Editing a template updates the instructions for the next turn. Swarm saves the selection after the Provider accepts it and restores the selection after a page reload or normal Worker restart. An uninstalled or incompatible choice is rejected and leaves the previously confirmed selection in place. OpenCode retains its existing full-template equipment path. Sessions created with `role_template_ref` can select persona-only templates. Generic session forking remains unavailable for those sessions.

Codex uses its native thread API when the role changes, is cleared, or the Worker resumes the thread. An unchanged role is reused on the same connection after confirmation. Swarm stores the selected expert ID in its existing session equipment.

Claude Code needs a CLI that supports `--system-prompt-snapshot off` to apply the current expert in a resumed session. This rebuilds the system prompt and can affect the native prompt cache.

## Codex session MCP

In a Codex single-agent or Code session, use **+ → Extensions** in the composer to select a connected Streamable HTTP MCP server. Changes apply on the next turn. Swarm resumes the original Codex thread after equipment changes or a regular Worker restart. If loading fails, Swarm keeps the last confirmed selection.

With Default permissions, Codex tool confirmations use the existing approval card. HTTPS, loopback HTTP and static request-header credentials are supported. OAuth, legacy SSE, stdio and MCP inherited from plugins or expert templates are outside the current scope.
