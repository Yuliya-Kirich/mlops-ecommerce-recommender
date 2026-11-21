import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import boto3


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKUP_DIR = PROJECT_ROOT / "backups/monitoring"

BUCKET = "mlops-yk-2026"
PREFIX = "mlops-ecommerce/backups/monitoring"

VOLUMES = {
    "prometheus": "mlops-prometheus-data",
    "grafana": "mlops-grafana-data",
}


def create_backup(name, volume, timestamp):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    archive = BACKUP_DIR / f"{name}_{timestamp}.tar.gz"

    subprocess.run(
        [
            "sudo", "docker", "run", "--rm",
            "-v", f"{volume}:/source:ro",
            "-v", f"{BACKUP_DIR}:/backup",
            "alpine:3.21",
            "tar", "-czf", f"/backup/{archive.name}",
            "-C", "/source", ".",
        ],
        check=True,
    )

    if not archive.exists() or archive.stat().st_size == 0:
        raise RuntimeError(f"Архив не создан: {archive}")

    return archive


def main():
    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    session = boto3.Session(profile_name="yandex")
    s3 = session.client(
        "s3",
        endpoint_url="https://storage.yandexcloud.net",
        region_name="ru-central1",
    )

    uploaded = {}

    for name, volume in VOLUMES.items():
        archive = create_backup(name, volume, timestamp)
        key = f"{PREFIX}/{timestamp}/{archive.name}"

        s3.upload_file(str(archive), BUCKET, key)

        remote = s3.head_object(Bucket=BUCKET, Key=key)

        if remote["ContentLength"] != archive.stat().st_size:
            raise RuntimeError(f"Размер файла не совпадает: {key}")

        uploaded[name] = f"s3://{BUCKET}/{key}"
        print(f"Загружено: {uploaded[name]}", flush=True)

    print(json.dumps(uploaded, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
