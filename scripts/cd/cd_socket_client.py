#!/usr/bin/env python3
"""Client for the local MLOps CD Unix socket."""

import argparse
import json
import re
import socket
import sys

SOCKET_PATH = "/run/mlops-cd/deploy.sock"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("commit_sha")
    args = parser.parse_args()

    sha = args.commit_sha

    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        print("ERROR: invalid Git commit SHA", file=sys.stderr)
        return 2

    request = {
        "action": "deploy",
        "commit_sha": sha,
    }

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(900)
            client.connect(SOCKET_PATH)
            client.sendall((json.dumps(request) + "\n").encode("utf-8"))

            response = client.recv(4096)

    except OSError as exc:
        print(f"ERROR: CD service unavailable: {exc}", file=sys.stderr)
        return 3

    if not response:
        print("ERROR: empty CD service response", file=sys.stderr)
        return 4

    try:
        result = json.loads(response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        print("ERROR: invalid CD service response", file=sys.stderr)
        return 4

    if not isinstance(result, dict):
        print("ERROR: invalid CD service response", file=sys.stderr)
        return 4

    status = result.get("status")
    message = result.get("message", "")

    print(f"CD status: {status}")
    print(f"CD message: {message}")

    if status == "success":
        return 0

    if status == "disabled":
        print("ERROR: deployment is disabled", file=sys.stderr)
        return 3

    print("ERROR: deployment failed or was rejected", file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
