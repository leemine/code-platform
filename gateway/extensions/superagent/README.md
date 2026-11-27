# SuperAgent Gateway application plugin

The opt-in plugin applies the original SuperAgent Core to explicit Web tickets. Gateway verifies identity and project scope. The platform declared-Agent Process CLI runs the Router with an empty tool list and validates its structured output. Each Worker uses an ordinary platform Code session bound to the configured project and `opencode-direct`. SQLite persists tickets, execution intents and session bindings. The runtime requires the platform, Node.js, and OpenCode.

## Build and enable

Use Node.js 22.19 or newer and the platform's existing native and OpenCode installation. Run `sh gateway/extensions/superagent/build.sh` before building the platform wheel. Install in an isolated pilot instance and merge this configuration into the Gateway configuration.

```yaml
superagent:
  enabled: true
  public_origin: https://pilot.example.test
  project_id: existing-code-project-id
  members: [authenticated-project-user]
  router_model: configured-model-name
  model_selection: {type: model, id: configured-opencode-compatible-model-id}
```

`members` lists authenticated participants allowed to work in the configured pilot project. The Gateway account authority is required. Register the Code project and its isolated worktree using the platform's normal project tools. Start the Gateway and AgentServer as usual and open **SuperAgent 工单** in the Web workspace. Keep one Gateway writer per data directory.

A restart leaves an in-flight Worker request in **待核对** when the transport outcome is unavailable. Inspect the saved platform Session and its history before deciding the disposition. If a stop acknowledgement was lost, use **重试停止** to recheck the same Session. The pilot preserves the project execution slot while a previous Worker could still be active.
