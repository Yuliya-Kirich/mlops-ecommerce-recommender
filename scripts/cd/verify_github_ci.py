#!/usr/bin/env python3
"""Verify that a commit passed GitHub Actions CI on main."""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request

REPO = "Yuliya-Kirich/mlops-ecommerce-recommender"
API = f"https://api.github.com/repos/{REPO}"


def github_get(path):
    request = urllib.request.Request(
        API + path,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "mlops-cd-verifier",
        },
    )

    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def verify(sha):
    branch = github_get("/branches/main")
    main_sha = branch["commit"]["sha"]

    if sha != main_sha:
        print("ERROR: commit is not the current main HEAD")
        return 1

    params = urllib.parse.urlencode(
        {
            "branch": "main",
            "event": "push",
            "head_sha": sha,
            "per_page": 30,
        }
    )

    data = github_get(f"/actions/workflows/ci.yml/runs?{params}")

    for run in data.get("workflow_runs", []):
        if (
            run.get("head_sha") == sha
            and run.get("head_branch") == "main"
            and run.get("event") == "push"
            and run.get("status") == "completed"
            and run.get("conclusion") == "success"
        ):
            print("SUCCESS: commit passed CI on main")
            print("Verified commit:", sha)
            return 0

    print("ERROR: successful CI run not found")
    return 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("commit_sha")
    args = parser.parse_args()

    if not re.fullmatch(r"[a-f0-9]{40}", args.commit_sha):
        print("ERROR: invalid Git SHA", file=sys.stderr)
        return 2

    try:
        return verify(args.commit_sha)
    except (OSError, ValueError, KeyError) as exc:
        print(
            f"ERROR: GitHub verification failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
