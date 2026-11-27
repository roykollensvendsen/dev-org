"""GitHub adapter: the GitHub App implementation of the board and Git/PR contracts.

Implements ``BoardAdapter`` and ``GitPrAdapter`` against GitHub's REST API,
authenticating as a GitHub App installation (section 10.3): a JWT signed
with the app's private key exchanges for a short-lived installation token.
The gateway holds the token; it is never sent to the agent process or
mounted in the sandbox.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import jwt

#: GitHub's REST API returns dynamically shaped JSON; internally we treat it
#: as Any and shape it into the contract's dict[str, object] at the edge.
JSON = dict[str, Any]


class GitHubAdapter:
    """Talk to GitHub as the dev-org-app installation."""

    def __init__(
        self, *, app_id: int, private_key_path: str | Path, repo: str, host: str = "api.github.com"
    ) -> None:
        """Bind the adapter to the app credentials and the target repository.

        The private key is read lazily on first use, so constructing the
        adapter does not require the file to exist yet.
        """
        self.app_id = app_id
        self.private_key_path = Path(private_key_path)
        self._private_key: str | None = None
        self.repo = repo
        self.host = host

    def _key(self) -> str:
        """Read the private key once and cache it."""
        if self._private_key is None:
            self._private_key = self.private_key_path.read_text()
        return self._private_key

    # -- auth --------------------------------------------------------------

    def make_jwt(self) -> str:
        """A short-lived JWT signed with the app's private key.

        Public so tests and diagnostics can inspect the token format without
        triggering an installation-token exchange.
        """
        now = int(time.time())
        return jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": str(self.app_id)},
            self._key(),
            algorithm="RS256",
        )

    def _installation_token(self) -> str:
        """Exchange the JWT for a short-lived installation access token.

        Two steps: find the installation ID for this repo, then POST to the
        app's access-tokens endpoint with that ID.
        """
        install = self._api_authed("GET", f"/repos/{self.repo}/installation", token=self.make_jwt())
        install_id = install["id"]
        if not isinstance(install_id, int):
            msg = "installation endpoint returned no numeric id"
            raise TypeError(msg)
        result = self._api_authed(
            "POST",
            f"/app/installations/{install_id}/access_tokens",
            token=self.make_jwt(),
        )
        token = result["token"]
        if not isinstance(token, str):
            msg = "installation token endpoint returned no token string"
            raise TypeError(msg)
        return token

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        body: JSON | None = None,
        accept: str = "application/vnd.github+json",
    ) -> urllib.request.Request:
        url = f"https://{self.host}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", accept)
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        for key, value in headers.items():
            req.add_header(key, value)
        return req

    def _api_authed(self, method: str, path: str, *, token: str, body: JSON | None = None) -> JSON:
        """Call the GitHub API with an explicit bearer token (JWT or install)."""
        req = self._request(method, path, headers={"Authorization": f"Bearer {token}"}, body=body)
        return self._call(req)

    def _api(self, method: str, path: str, *, body: JSON | None = None) -> JSON:
        """Call the GitHub API with an installation token."""
        token = self._installation_token()
        return self._api_authed(method, path, token=token, body=body)

    def _api_list(self, method: str, path: str, *, body: JSON | None = None) -> list[JSON]:
        """Call the GitHub API and require the result to be a JSON list."""
        token = self._installation_token()
        req = self._request(method, path, headers={"Authorization": f"Bearer {token}"}, body=body)
        result = self._call_raw(req)
        if not isinstance(result, list):
            msg = f"expected a JSON list from {path}, got {type(result).__name__}"
            raise TypeError(msg)
        return result

    def _call_raw(self, req: urllib.request.Request) -> Any:
        """Perform the HTTP call and return the decoded JSON of any shape."""
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - host is fixed to api.github.com
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            msg = f"github api {req.get_method()} {req.full_url} -> {exc.code}: {body[:200]}"
            raise RuntimeError(msg) from exc

    def _call(self, req: urllib.request.Request) -> JSON:
        """Perform the HTTP call and require a JSON object result."""
        parsed = self._call_raw(req)
        if not isinstance(parsed, dict):
            msg = f"expected a JSON object from {req.full_url}, got {type(parsed).__name__}"
            raise TypeError(msg)
        return parsed

    # -- BoardAdapter contract (section 4) -----------------------------------

    def fetch_changes(self) -> list[dict[str, object]]:
        """Return open issues as the common work model, without a Git task list."""
        issues = self._api_list("GET", f"/repos/{self.repo}/issues?state=open")
        return [
            {
                "external_id": str(issue["number"]),
                "revision": str(issue.get("updated_at", "")),
                "title": issue.get("title", ""),
                "state": issue.get("state", ""),
                "body": issue.get("body") or "",
            }
            for issue in issues
        ]

    def read_issue(self, external_id: str) -> dict[str, object]:
        """Return one issue with its dependencies in the common work model."""
        issue = self._api("GET", f"/repos/{self.repo}/issues/{external_id}")
        return {
            "external_id": str(issue["number"]),
            "revision": str(issue.get("updated_at", "")),
            "title": issue.get("title", ""),
            "state": issue.get("state", ""),
            "body": issue.get("body") or "",
        }

    def update_issue(self, external_id: str, fields: dict[str, object]) -> None:
        """Update only the owned fields of an issue."""
        body = {key: value for key, value in fields.items() if key in {"state", "labels", "body"}}
        if body:
            self._api("PATCH", f"/repos/{self.repo}/issues/{external_id}", body=body)

    # -- GitPrAdapter contract (section 4) -----------------------------------

    def publish_branch(self, *, base: str, branch: str, commit_message: str) -> str:
        """Create a branch from base and return its ref, or reuse the existing one."""
        del commit_message  # part of the contract; the branch ref is the identifier
        try:
            self._api(
                "POST",
                f"/repos/{self.repo}/git/refs",
                body={"ref": f"refs/heads/{branch}", "sha": self._base_sha(base)},
            )
        except RuntimeError as exc:
            if "already exists" in str(exc) or "Reference already exists" in str(exc):
                return branch  # idempotent: the branch is already there
            raise
        return branch

    def open_pr(self, *, branch: str, title: str, body: str) -> str:
        """Open one PR for a branch; a duplicate for the same branch returns the existing PR."""
        existing = self.find_pr(branch=branch)
        if existing is not None:
            return existing
        pr = self._api(
            "POST",
            f"/repos/{self.repo}/pulls",
            body={"head": branch, "base": "main", "title": title, "body": body},
        )
        return str(pr["number"])

    def find_pr(self, *, branch: str) -> str | None:
        """Find the open PR for a branch, or None."""
        prs = self._api_list("GET", f"/repos/{self.repo}/pulls?state=open&head={self._head_ref(branch)}")
        return str(prs[0]["number"]) if prs else None

    # -- helpers ------------------------------------------------------------

    def _base_sha(self, base: str) -> str:
        ref = self._api("GET", f"/repos/{self.repo}/git/ref/heads/{base}")
        sha = ref["object"]["sha"]
        if not isinstance(sha, str):
            msg = "git ref endpoint returned no sha string"
            raise TypeError(msg)
        return sha

    def _head_ref(self, branch: str) -> str:
        owner = self.repo.split("/")[0]
        return f"{owner}:{branch}"
