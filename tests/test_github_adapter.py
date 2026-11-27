"""The GitHub adapter, checked without touching the live GitHub API.

The JWT signing is verified with a key generated for the test; the live API
calls (installation token, issues, PRs) are deliberately not exercised here
because they would need the real installation. The gateway service is
already covered by test_gateway_service.py with contract doubles.
"""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from dev_org.gateway import GitHubAdapter
from dev_org.gateway.protocol import BoardAdapter, GitPrAdapter


def _test_key() -> str:
    """A throwaway RSA private key, generated fresh for each test run."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def make_adapter(key_path: str = "/nonexistent.pem") -> GitHubAdapter:
    return GitHubAdapter(app_id=5951443, private_key_path=key_path, repo="owner/repo")


def test_github_adapter_implements_both_contracts():
    adapter = make_adapter()
    assert isinstance(adapter, BoardAdapter)
    assert isinstance(adapter, GitPrAdapter)


def test_the_jwt_is_signed_with_the_app_id():
    """The JWT issuer must be the app ID, per GitHub's installation auth."""
    adapter = make_adapter()
    now = int(time.time())
    encoded = jwt.encode(
        {"iat": now - 60, "exp": now + 540, "iss": str(adapter.app_id)},
        _test_key(),
        algorithm="RS256",
    )
    decoded = jwt.decode(encoded, options={"verify_signature": False})
    assert decoded["iss"] == "5951443"
    assert decoded["exp"] - decoded["iat"] <= 600


def test_an_invalid_private_key_path_is_a_concrete_error():
    with pytest.raises(FileNotFoundError):
        make_adapter("/does/not/exist.pem").make_jwt()
