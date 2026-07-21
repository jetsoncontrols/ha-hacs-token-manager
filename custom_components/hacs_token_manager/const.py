"""Constants for HACS Private Token Manager."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "hacs_token_manager"
HACS_DOMAIN = "hacs"

# Config entry keys. CONF_TOKEN deliberately matches the key HACS stores its
# own token under, since injection writes straight into HACS's entry data.
CONF_TOKEN = "token"
CONF_TEST_REPO = "test_repo"

# How often to check that HACS still holds our capable token and that the
# token is still valid. Drift is rare (only on HACS re-auth), so this is a
# safety poll, not a hot loop.
UPDATE_INTERVAL = timedelta(minutes=15)

GITHUB_API = "https://api.github.com"
GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# Repair issue ids
ISSUE_PAT_INVALID = "pat_invalid"
ISSUE_HACS_MISSING = "hacs_missing"

# Token check outcomes
TOKEN_VALID = "valid"
TOKEN_INVALID = "invalid"
TOKEN_UNKNOWN = "unknown"
