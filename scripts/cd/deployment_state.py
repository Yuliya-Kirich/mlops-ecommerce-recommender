#!/usr/bin/env python3
"""Persistent state marker for MLOps deployment."""

import argparse
import json
import os
import re
import sys
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path("/var/lib/mlops-cd")
STATE_FILE = STATE_DIR / "deployment-in-progress.json"


def require_root():
    if os.geteuid() != 0:
        raise PermissionError("deployment state requires root")


def check():
    if STATE_FILE.exists():
        print("ERROR: unfinished deployment detected")
        print(STATE_FILE.read_text())
        return 1

    print("SUCCESS: no unfinished deployment")
    return 0


def begin(commit_sha, old_image1, old_image2, target_id):
    if not isinstance(commit_sha, str) or not re.fullmatch(
        r"[a-f0-9]{40}", commit_sha
    ):
        raise ValueError("invalid Git commit SHA")

    for name, image_id in (
        ("old_image1", old_image1),
        ("old_image2", old_image2),
        ("target_id", target_id),
    ):
        if not isinstance(image_id, str) or not re.fullmatch(
            r"sha256:[a-f0-9]{64}", image_id
        ):
            raise ValueError(f"invalid Docker Image ID: {name}")

    if STATE_FILE.exists():
        print("ERROR: unfinished deployment already exists")
        return 1

    state = {
        "commit_sha": commit_sha,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "in_progress",
        "pid": os.getpid(),
        "old_image1": old_image1,
        "old_image2": old_image2,
        "target_id": target_id,
    }

    fd = os.open(
        STATE_FILE,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )

    with os.fdopen(fd, "w") as file:
        json.dump(state, file, indent=2)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())

    # Persist the new directory entry after writing the marker.
    dir_fd = os.open(STATE_DIR, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)

    print("SUCCESS: deployment state created")
    return 0



def verify_replicas(expected_image1, expected_image2):
    """Verify container image IDs, running status and API health."""

    containers = (
        ("ecommerce-purchase-api-monitoring", expected_image1),
        ("ecommerce-purchase-api-replica2", expected_image2),
    )

    for container, expected_image in containers:
        result = subprocess.run(
            [
                "/usr/bin/docker",
                "inspect",
                container,
                "--format",
                "{{.State.Status}} {{.Image}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Docker inspect failed: {container}"
            )

        actual = result.stdout.strip()

        if actual != f"running {expected_image}":
            raise RuntimeError(
                f"Unexpected container state: {container}: {actual}"
            )

    for port in (8002, 8003, 8004):
        url = f"http://127.0.0.1:{port}/health"

        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"Healthcheck failed: {url}"
                )

    print("SUCCESS: replicas verified")
    return True



def verify_completion(expected_result):
    """Verify deployment outcome using the persistent state marker."""

    if expected_result not in ("deployed", "rolled_back"):
        raise ValueError("invalid deployment result")

    if not STATE_FILE.exists():
        raise RuntimeError("deployment marker is missing")

    try:
        state = json.loads(STATE_FILE.read_text())
    except (ValueError, OSError) as exc:
        raise RuntimeError("deployment marker is unreadable") from exc

    if not isinstance(state, dict):
        raise RuntimeError("invalid deployment marker")

    required = ("commit_sha", "old_image1", "old_image2", "target_id")

    if any(not isinstance(state.get(key), str) for key in required):
        raise RuntimeError("deployment marker has missing fields")

    if not re.fullmatch(r"[a-f0-9]{40}", state["commit_sha"]):
        raise RuntimeError("invalid commit SHA in deployment marker")

    for key in ("old_image1", "old_image2", "target_id"):
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", state[key]):
            raise RuntimeError(
                f"invalid Docker Image ID in deployment marker: {key}"
            )

    if state.get("status") != "in_progress":
        raise RuntimeError("invalid deployment marker status")

    if expected_result == "deployed":
        image1 = state["target_id"]
        image2 = state["target_id"]
    else:
        image1 = state["old_image1"]
        image2 = state["old_image2"]

    verify_replicas(image1, image2)

    print(f"SUCCESS: deployment result verified: {expected_result}")
    return True


def finish():
    if not STATE_FILE.exists():
        print("ERROR: deployment state is missing")
        return 1

    # Preserve the marker contents for recovery if fsync fails.
    original_content = STATE_FILE.read_bytes()

    STATE_FILE.unlink()

    dir_fd = os.open(
        STATE_DIR,
        os.O_RDONLY | os.O_DIRECTORY,
    )
    try:
        os.fsync(dir_fd)
    except OSError:
        print(
            "CRITICAL: marker removal could not be synchronized",
            file=sys.stderr,
        )

        # Best-effort restoration; do not overwrite an existing marker.
        try:
            fd = os.open(
                STATE_FILE,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            with os.fdopen(fd, "wb") as file:
                file.write(original_content)
                file.flush()
                os.fsync(file.fileno())

            os.fsync(dir_fd)
        except OSError as recovery_error:
            print(
                f"CRITICAL: marker restoration failed: {recovery_error}",
                file=sys.stderr,
            )
        raise
    finally:
        os.close(dir_fd)

    print("SUCCESS: deployment state cleared")
    return 0



def complete_deployment(expected_result):
    """Verify deployment outcome before clearing state.

    Must be called only by the trusted CD workflow while
    holding the deployment lock.
    """

    if expected_result not in ("deployed", "rolled_back"):
        raise ValueError("invalid deployment result")

    # An exception here must leave the marker intact.
    if not verify_completion(expected_result):
        raise RuntimeError("deployment verification failed")

    # Clear the marker only after successful verification.
    result = finish()

    if result != 0:
        raise RuntimeError("deployment marker cleanup failed")

    print(
        f"SUCCESS: deployment completed and state cleared: "
        f"{expected_result}"
    )

    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=["check", "begin", "complete"],
    )
    parser.add_argument("--commit-sha")
    parser.add_argument("--old-image1")
    parser.add_argument("--old-image2")
    parser.add_argument("--target-id")
    parser.add_argument(
        "--result",
        choices=["deployed", "rolled_back"],
    )
    args = parser.parse_args()

    require_root()

    if args.action == "check":
        return check()

    if args.action == "begin":
        return begin(
            args.commit_sha,
            args.old_image1,
            args.old_image2,
            args.target_id,
        )

    if args.action == "complete":
        if args.result is None:
            parser.error("--result is required for complete")
        return complete_deployment(args.result)

    raise RuntimeError("unsupported deployment state action")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
