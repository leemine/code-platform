"""Identifiers used by the account-scoped managed runtime catalog."""

import re
from pathlib import PurePosixPath

DEVICE_ID = re.compile(r"[a-f0-9]{32}")
WORKER_ROOT = PurePosixPath("/data/agent/workspace")


def device_prefix(account):
    return f"@device:{account['environment_id']}:"


def validate_registration(name, create_token):
    if (not isinstance(name, str) or not 1 <= len(name) <= 30
            or name != name.strip() or not name.isprintable()
            or not isinstance(create_token, str) or not DEVICE_ID.fullmatch(create_token)):
        raise ValueError("Invalid managed device registration")
