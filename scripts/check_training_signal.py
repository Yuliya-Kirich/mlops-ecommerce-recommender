import json
import os
import re
import subprocess
import sys
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
BUCKET = "mlops-yk-2026"
PREFIX = "mlops-ecommerce/processed"
ENDPOINT = "https://storage.yandexcloud.net"


def main():
    s3 = boto3.Session(profile_name=os.getenv("AWS_PROFILE", "yandex")).client(
        "s3",
        endpoint_url=ENDPOINT,
        region_name="ru-central1",
    )

    paginator = s3.get_paginator("list_objects_v2")

    signals = []

    for page in paginator.paginate(
        Bucket=BUCKET,
        Prefix=f"{PREFIX}/date=",
    ):
        for item in page.get("Contents", []):
            key = item["Key"]

            match = re.fullmatch(
                rf"{re.escape(PREFIX)}/date=(\d{{4}}-\d{{2}}-\d{{2}})/training_ready\.json",
                key,
            )
            if match:
                signals.append((match.group(1), key))

    if not signals:
        print("INFO: сигналов готовности пока нет")
        return

    for data_date, signal_key in sorted(signals):
        response = s3.get_object(
            Bucket=BUCKET,
            Key=signal_key,
        )
        signal = json.loads(response["Body"].read())

        expected_manifest = f"{PREFIX}/date={data_date}/manifest.json"

        if (
            signal.get("status") != "ready"
            or signal.get("data_date") != data_date
            or signal.get("manifest_key") != expected_manifest
        ):
            raise RuntimeError(f"Некорректный сигнал: {signal_key}")

        success_marker = ROOT / "artifacts" / "training_state" / f"{data_date}.success"

        if success_marker.exists():
            print(f"SKIP: версия {data_date} уже обработана", flush=True)
            continue

        print(f"SUCCESS: найден сигнал для {data_date}", flush=True)

        command = [
            sys.executable,
            str(ROOT / "scripts/run_training.py"),
            "--data-date",
            data_date,
        ]

        if os.getenv("MLOPS_TRAINING_ENABLED", "false").lower() == "true":
            command.append("--execute")
            print(f"TRAINING ENABLED: {data_date}", flush=True)
        else:
            print(f"DRY RUN: {data_date}", flush=True)

        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
