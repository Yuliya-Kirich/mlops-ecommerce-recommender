import argparse
import json
import time
import urllib.error
import urllib.request


def check_health(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            if response.status != 200:
                return False

            payload = json.load(response)

            return payload.get("status") == "ok" and payload.get("model_loaded") is True

    except (
        urllib.error.URLError,
        TimeoutError,
        ValueError,
        OSError,
    ):
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--retries", type=int, default=10)
    parser.add_argument("--interval", type=float, default=2.0)

    args = parser.parse_args()

    if args.retries < 1 or args.interval < 0:
        parser.error("--retries must be >= 1 and --interval >= 0")

    for attempt in range(1, args.retries + 1):
        if check_health(args.url):
            print(f"SUCCESS: {args.url} is healthy")
            return

        print(f"Attempt {attempt}/{args.retries}: API not ready")

        if attempt < args.retries:
            time.sleep(args.interval)

    raise SystemExit(f"ERROR: {args.url} is unhealthy")


if __name__ == "__main__":
    main()
