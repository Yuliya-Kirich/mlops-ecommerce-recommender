#!/usr/bin/env python3
"""Local MLOps CD request validation server."""

import json
import os
import pwd
import re
import socket
import struct
import sys

SOCKET_PATH = "/run/mlops-cd/deploy.sock"
ALLOWED_USER = "mlops-cd"
MAX_REQUEST_BYTES = 4096
CLIENT_TIMEOUT_SECONDS = 10


def handle_client(conn):
    credentials = conn.getsockopt(
        socket.SOL_SOCKET,
        socket.SO_PEERCRED,
        struct.calcsize("3i"),
    )
    _pid, uid, _gid = struct.unpack("3i", credentials)

    expected_uid = pwd.getpwnam(ALLOWED_USER).pw_uid

    if uid != expected_uid:
        return {"status": "error", "message": "unauthorized user"}

    data = conn.recv(MAX_REQUEST_BYTES + 1)

    if len(data) > MAX_REQUEST_BYTES:
        return {"status": "error", "message": "request too large"}

    try:
        request = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"status": "error", "message": "invalid JSON"}

    if not isinstance(request, dict):
        return {"status": "error", "message": "invalid request"}

    if set(request) != {"action", "commit_sha"}:
        return {"status": "error", "message": "unexpected request fields"}

    if request["action"] != "deploy":
        return {"status": "error", "message": "action not allowed"}

    sha = request["commit_sha"]

    if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{40}", sha):
        return {"status": "error", "message": "invalid commit SHA"}

    return {
        "status": "disabled",
        "message": "deployment is not enabled",
        "commit_sha": sha,
    }


def main():
    if os.geteuid() != 0:
        print("ERROR: server must run as root", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(SOCKET_PATH), mode=0o755, exist_ok=True)

    if os.path.lexists(SOCKET_PATH):
        print("ERROR: socket path already exists", file=sys.stderr)
        return 1

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(SOCKET_PATH)

        group_id = pwd.getpwnam(ALLOWED_USER).pw_gid
        os.chown(SOCKET_PATH, 0, group_id)
        os.chmod(SOCKET_PATH, 0o660)

        server.listen(5)
        print("CD validation server is listening", flush=True)

        while True:
            conn, _ = server.accept()

            with conn:
                conn.settimeout(CLIENT_TIMEOUT_SECONDS)

                try:
                    result = handle_client(conn)
                except socket.timeout:
                    result = {
                        "status": "error",
                        "message": "request timeout",
                    }
                except (OSError, ValueError) as exc:
                    result = {
                        "status": "error",
                        "message": type(exc).__name__,
                    }

                try:
                    conn.sendall(
                        (json.dumps(result) + "\n").encode("utf-8")
                    )
                except (OSError, socket.timeout):
                    # Клиент мог отключиться до получения ответа.
                    continue


if __name__ == "__main__":
    raise SystemExit(main())
