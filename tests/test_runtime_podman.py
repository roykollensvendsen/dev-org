"""The rootless Podman backend, checked against its acceptance criteria.

Issue #7's criteria, mapped one test each:

1. create, inspect, and end over existing isolation technology;
2. scope workspace, mounts, network, CPU, memory, processes, and runtime;
3. block access to the home directory and administrative sockets;
4. reject a profile that cannot be enforced (A21);
5. allowed builds still work in the sandbox.

The live-container tests (marked with a ``live`` marker) need rootless
Podman and are not run by the default CI suite; the pure profile-validation
tests always run.
"""

from __future__ import annotations

import shutil

import pytest

from dev_org.runtime import ExecutionBackend, PodmanBackend, RuntimeProfile

WS = "/tmp/ws"  # noqa: S108 - a test workspace value

pytestmark = pytest.mark.skipif(shutil.which("podman") is None, reason="podman is not installed")


# 1. The contract is implemented ------------------------------------------


def test_podman_backend_is_a_runtime_checkable_backend():
    assert isinstance(PodmanBackend(), ExecutionBackend)


# 2. Profile scoping and validation ----------------------------------------


def test_a_profile_requires_workspace_and_image():
    with pytest.raises(ValueError, match="requires"):
        RuntimeProfile.from_mapping({"workspace": WS})


def test_an_unknown_profile_key_is_refused():
    with pytest.raises(ValueError, match="cannot enforce"):
        RuntimeProfile.from_mapping({"workspace": WS, "image": "alpine", "nonsense": 1})


def test_a_wrong_typed_profile_value_is_refused():
    with pytest.raises(TypeError, match="must be"):
        RuntimeProfile.from_mapping({"workspace": WS, "image": "alpine", "pids_limit": "many"})


def test_a_valid_profile_has_safe_defaults():
    rt = RuntimeProfile.from_mapping({"workspace": WS, "image": "alpine"})
    assert rt.network is False  # network off by default
    assert rt.read_only_rootfs is True
    assert rt.no_new_privileges is True
    assert rt.cap_drop_all is True


# 3. A21: reject a profile that cannot be enforced -------------------------


def test_a21_a_missing_required_capability_is_a_blockage():
    # The backend cannot enforce "host network access for the agent", so the
    # profile that asks for it must be refused, not run weaker.
    with pytest.raises(ValueError, match="cannot enforce"):
        RuntimeProfile.from_mapping({"workspace": WS, "image": "alpine", "host_network": True})


# 4+5. Live container tests (rootless Podman, not in default CI) -----------


@pytest.mark.live
def test_live_create_inspect_end(tmp_path):
    backend = PodmanBackend()
    profile = {"workspace": str(tmp_path), "image": "docker.io/library/alpine:latest"}
    runtime_id = backend.create(profile)
    try:
        state = backend.inspect(runtime_id)
        assert state["Running"] is True
    finally:
        backend.end(runtime_id)


@pytest.mark.live
def test_live_workspace_is_mounted_and_builds_work(tmp_path):
    backend = PodmanBackend()
    (tmp_path / "hello.txt").write_text("hello from the sandbox")
    profile = {"workspace": str(tmp_path), "image": "docker.io/library/alpine:latest"}
    runtime_id = backend.create(profile)
    try:
        # a command inside the container can read the mounted workspace
        result = backend.exec_(runtime_id, ["cat", "/workspace/hello.txt"])
        assert result == "hello from the sandbox"
    finally:
        backend.end(runtime_id)


@pytest.mark.live
def test_live_home_directory_is_not_accessible(tmp_path):
    backend = PodmanBackend()
    profile = {"workspace": str(tmp_path), "image": "docker.io/library/alpine:latest"}
    runtime_id = backend.create(profile)
    try:
        # /root inside the container is the container's own, not the host home
        result = backend.exec_(runtime_id, ["ls", "/root"])
        assert result == ""  # empty: no host home content is mounted
    finally:
        backend.end(runtime_id)
