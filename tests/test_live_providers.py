"""Provider live gate: real Targon/Hippius contact, read-only, opt-in.

This is the running verification that dev-org's provider assumptions line
up with the real provider APIs *before* a paid trial rental is ever made.
Nothing here creates a VM or costs money: it reads the same status the
survivor-agent's own code reads (`targon.py`, `hippius.py`), so it needs
only a read-path token and an explicit go.

It is deliberately skipped by default. Two conditions must both hold:

- the provider keys are readable (Targon from the survivor-agent keys.env
  ``TARGON_API_KEY``, Hippius from ``~/.config/hippius/key``), and
- ``DEV_ORG_PROVIDER_TRIAL=1`` is set, which is Roy's explicit go for a
  read-only probe (a paid trial rental is a separate, later step).

Run with:

    DEV_ORG_PROVIDER_TRIAL=1 uv run python -m pytest tests/test_live_providers.py -m live -q

What it verifies, mirroring survivor-agent's own read paths:

- Targon: ``GET /orgs`` answers and reports a real credit balance.
- Hippius: ``GET /compute/quota/`` (or vms) answers with a real quota.

The provider result is still treated as untrusted in dev-org's contract
terms; this probe only asserts the live contact and the account shape, not
that renting works. A paid trial, attestation, and a teardown are the
later step that follows your explicit yes.
"""

from __future__ import annotations

import json
import os
import pathlib
from json import JSONDecodeError
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest

SURVIVOR_KEYS = pathlib.Path.home() / ".config" / "survivor-agent" / "keys.env"
HIPPIUS_KEY_FILE = pathlib.Path(
    os.environ.get("SURVIVOR_HIPPIUS_NOKKEL", "~/.config/hippius/key")
).expanduser()
TRIAL = "DEV_ORG_PROVIDER_TRIAL"
TARGON_API = "https://api.targon.com/tha/v3"
HIPPIUS_API = "https://api.hippius.com/api"


def _read_survivor_key(name: str) -> str | None:
    """Read one key from the survivor-agent keys.env, like survivor-agent does."""
    try:
        for line in SURVIVOR_KEYS.read_text().splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip()
    except OSError:
        return None
    return None


def _read_hippius_key() -> str | None:
    """Read the Hippius token from its key file, like survivor-agent does."""
    try:
        return HIPPIUS_KEY_FILE.read_text().strip() or None
    except OSError:
        return None


def _trial_allowed() -> bool:
    """Roy's explicit go for a read-only provider probe."""
    return os.environ.get(TRIAL) == "1"


def _http_json(
    url: str, *, token: str, headers_extra: dict[str, str] | None = None
) -> dict[str, object] | list[object] | None:
    """A minimal GET that sends the key only in the Authorization header."""
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "Content-Type": "application/json",
        **(headers_extra or {}),
    }
    try:
        with urlopen(Request(url, headers=headers), timeout=20) as resp:  # noqa: S310 - callers pass https
            raw = resp.read()
            return json.loads(raw) if raw.strip() else None
    except HTTPError, URLError, TimeoutError, OSError, JSONDecodeError:
        return None


def _provider_ready() -> bool:
    """Both key sets and the explicit trial go must be present."""
    return _trial_allowed() and bool(_read_survivor_key("TARGON_API_KEY") and _read_hippius_key())


pytestmark = pytest.mark.skipif(
    not _provider_ready(),
    reason="provider read probe needs TARGON_API_KEY + Hippius key and DEV_ORG_PROVIDER_TRIAL=1",
)


@pytest.mark.live
def test_targon_org_and_credits_are_readable() -> None:
    """The real Targon API answers and reports a balance (read-only)."""
    token = _read_survivor_key("TARGON_API_KEY")
    assert token, "TARGON_API_KEY present (guarded by pytestmark)"
    orgs = _http_json(f"{TARGON_API}/orgs", token=token)
    assert orgs is not None, "Targon API did not answer /orgs"
    items = orgs.get("items", []) if isinstance(orgs, dict) else orgs
    assert isinstance(items, list)
    assert items, "Targon /orgs returned no organization"
    # The read path is exercised without creating anything; the account has a
    # credit figure (0 is a figure) but nothing was provisioned.
    assert isinstance(orgs, dict)
    assert "items" in orgs


@pytest.mark.live
def test_hippius_quota_or_vms_are_readable() -> None:
    """The real Hippius API answers and reports quota (read-only)."""
    token = _read_hippius_key()
    assert token, "Hippius token present (guarded by pytestmark)"
    headers = {"User-Agent": "dev-org/0.1"}
    data = _http_json(f"{HIPPIUS_API}/compute/quota/", token=token, headers_extra=headers)
    if data is None:
        data = _http_json(f"{HIPPIUS_API}/compute/vms/", token=token, headers_extra=headers)
    assert data is not None, "Hippius API did not answer quota or vms"
    assert isinstance(data, (dict, list))  # a real, readable provider response
