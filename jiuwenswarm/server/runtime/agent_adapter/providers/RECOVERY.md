---
title: External Provider session recovery
author: leewanlong
author_email: 68536087@qq.com
---

# External Provider session recovery

The adapters persist a versioned binding under
`get_agent_sessions_dir()/.provider-bindings/`. The filename hashes the Provider
and Swarm session ID; it never interpolates a user-supplied session ID as a path.
The binding contains the native ID, private data root, canonical workspace,
local principal, desired permission profile and model/settings fingerprints.
Credentials are not copied into the binding. Writes use a private temporary
file, fsync and atomic replacement.

Codex resumes the stored thread through the official SDK and validates its ID,
workspace, idle state and effective permissions. Claude uses the original SDK
session ID and transcript namespace through `resume`; native init/result events
continue to validate the ID. Owned OpenCode services reopen their original XDG
data namespace and validate the original session and workspace through HTTP.
Borrowed OpenCode servers retain their previous behavior; this change does not
claim cold recovery for external server ownership.

Adapter disposal closes clients and processes but retains bound native data.
Uninitialized temporary namespaces are still removed. Retained private data is
not an execution owner or a second scheduler. The existing Runtime remains
responsible for producers, controls and session scheduling. Permission reloads
update the persisted desired profile; a newly configured default does not
silently replace a restored session's stored profile.

Invalid/missing private data, another workspace/principal, changed configuration
or a mismatched native ID fails explicitly. Rendered Swarm history is never
replayed as native context. A legacy session without a binding cannot be
automatically recovered: no native ID is guessed and no replacement conversation
is silently started. Retained data is not automatically garbage-collected on
disposal; distinguishing eviction from permanent deletion would need the host
to provide that intent, outside this Provider-only change.

## Validation (Windows, 2026-11-03)

Candidate baseline: `240080b3ad0dad655d7b9e39ab764320942873be`.
The Provider-only tests load the candidate files on the installed frozen Python
3.13 runtime and activated official SDKs. `test_session_recovery.py` contains
13 deterministic tests and three opt-in real Provider acceptance cases.

The final combined OpenCode/Codex run passed 15 cases and skipped Claude live
acceptance. Both real cases remember a random marker, dispose the adapter and
native process, create another adapter and confirm the same native ID/data root
and correct recall without replaying history or reading a marker file.
Claude binding/resume-option tests pass; real Claude first requests timed out
before recovery could be exercised, including a historically successful model
selection. Do not interpret those runs as successful Claude live acceptance.
Subsequent direct diagnosis of that historical model selection resolved to
`glm-5.2`, Anthropic-compatible transport at `open.bigmodel.cn`, official SDK
0.2.115 and bundled CLI 2.1.206. Minimal messages requests returned HTTP 429,
`rate_limit_error`, service code 1113 (insufficient balance or no available
resource package) in about 2.2 seconds. This identifies a current service quota
failure. Native HTTP attempt traces were not captured during the original
180-second test timeout, so retry behavior is an explanation rather than a
fully observed trace of that earlier run. Restore quota before live acceptance.

The existing three suites were initially run read-only. The initial candidate scan was
139 passed/45 failed; the unchanged frozen baseline was 175 passed/9 failed.
The user subsequently authorized changes only to the three existing
`tests/unit_tests/agentserver/test_{opencode,codex,claude}_direct_adapter.py`
files. They now verify retained bindings/private roots, and each contains a
Facade disposal/recreation regression. Mock services expose their persistent
roots and native identity. Windows PATH/PATHEXT and case-sensitive string
assertions were corrected; the symlink case skips only when Windows returns
the explicit missing-privilege error. The final run passed 186 cases and
skipped that one symlink case. No workflow or common session files were changed.
No formatter/static checker was run. Installer/release work is outside this
change. The scope does not modify common session storage or Provider CLI/SDK
source. The user authorized submission and merge after this validation.
