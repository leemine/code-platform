"""Wire names for the trusted Worker-to-Gateway Codex transport."""

AUDIENCE = "jiuwenswarm-managed-codex"
RELAY_PATH = "/provider/managed/codex"
RELAY_ENV = "CODE_PLATFORM_MANAGED_CODEX_RELAY"
ASSERTION_HEADER = "X-Jiuwen-Codex-Assertion"
DIRECTORY_HEADER = "X-Jiuwen-Codex-Directory"
MAX_FRAME_BYTES = 8 * 1024 * 1024
NATIVE_PORT = 18768
IDENTITY_TARGET = "/run/codex"
