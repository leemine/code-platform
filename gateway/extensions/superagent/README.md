# SuperAgent Gateway application plugin

The opt-in plugin makes the original SuperAgent administration panel and Workbench available in the WorkSwarm sidebar. Gateway verifies identity and project scope. The platform declared-Agent Process CLI runs the Router with an empty tool list and validates its structured output. Each Worker uses an ordinary platform Code session bound to the configured project and `opencode-direct`. SQLite persists tickets, execution intents and session bindings. The runtime requires the platform, Node.js, and OpenCode.

## Build and enable

Use Node.js 22.19 or newer and the platform's existing native and OpenCode installation. Install the normal WorkSwarm frontend dependencies with its locked `npm ci`. Run `sh gateway/extensions/superagent/build.sh` before building the platform wheel. Install in an isolated pilot instance and merge this configuration into the Gateway configuration.

```yaml
superagent:
  enabled: true
  public_origin: https://pilot.example.test
  project_id: existing-code-project-id
  members: [authenticated-project-user]
  router_model: configured-model-name
  execution_provider: opencode-direct
  model_selection: {type: model, id: configured-opencode-compatible-model-id}
```

`members` lists authenticated participants allowed to work in the configured pilot project. The Gateway account authority is required. Register the Code project and its isolated worktree using the platform's normal project tools. Start the Gateway and AgentServer as usual. Open **SuperAgent** for the administration panel or **Workbench** to submit text, cite an asset revision, and follow a topic. Select a topic to open the bound WorkSwarm conversation and respond using WorkSwarm's native authorization card. Workbench follow-ups and plain text from that conversation use the recorded Ticket and Worker Session. The original demonstration ticket page is available only with `superagent.acceptance_page: true`. Keep one Gateway writer per data directory.

The panel displays WorkSwarm data for Sources, Threads, Decisions and Tickets. Open Worker Session links navigate to WorkSwarm. Deployment configuration is read-only in the panel. The pilot runs the Router once per new request. Host-specific setup, editable policy and prompts, and the persistent Router management session are deferred. The Workbench catalog is a pinned prototype dataset. Workbench rulings address business questions from a Worker report. Provider interactions that request approval use the native WorkSwarm authorization card.

SuperAgent Worker sessions use the provider's Full Access profile. The Gateway signs each Worker turn for its session, owner, project, provider, request ID and input. WorkSwarm stores a separate verified session binding. Ordinary sessions use the existing WorkSwarm permission setting. The default execution provider is `opencode-direct`. Other providers must declare support for application Worker permission profiles. For split deployments with separate data directories, provision the same 32-byte private key in both services and set `JIUWENSWARM_APPLICATION_WORKER_KEY_FILE` to its absolute path on each host. Local processes sharing the data directory use a private key created by the Gateway.

The build verifies the original panel Git blobs and the original Workbench snapshot using `frontend/vendor/SOURCE.json`. The latter is the original prototype's local standalone build, with its own byte hashes. The generated package combines that HTML with a small transport adapter and includes the original license. The build and runtime need neither DSH nor Cordis packages.

A restart leaves an in-flight Worker request in **待核对** when the transport outcome is unavailable. Inspect the saved platform Session and its history before deciding the disposition. If a stop acknowledgement was lost, use **重试停止** to recheck the same Session. The pilot preserves the project execution slot while a previous Worker could still be active.
