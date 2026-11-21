import json
import uuid
from pathlib import Path

import boto3


BUCKET = "mlops-yk-2026"
PREFIX = "mlops-ecommerce/models"


def upload_model(
    output_dir: str,
    run_id: str | None = None,
):
    output_dir = Path(output_dir)

    files = [
        "catboost_best.pkl",
        "best_params.json",
        "training_results.json",
    ]

    for filename in files:
        if not (output_dir / filename).is_file():
            raise FileNotFoundError(output_dir / filename)

    if run_id is None:
        run_id = uuid.uuid4().hex

    session = boto3.Session(profile_name="yandex")

    s3 = session.client(
        "s3",
        endpoint_url="https://storage.yandexcloud.net",
        region_name="ru-central1",
    )

    uploaded = {}

    for filename in files:
        key = f"{PREFIX}/{run_id}/{filename}"

        s3.upload_file(
            str(output_dir / filename),
            BUCKET,
            key,
        )

        s3.head_object(Bucket=BUCKET, Key=key)

        uploaded[filename] = f"s3://{BUCKET}/{key}"

        print(f"Загружен: {uploaded[filename]}", flush=True)

    return uploaded


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]

    results = upload_model(
        output_dir=str(root / "artifacts/pipeline"),
    )

    print(json.dumps(results, indent=2, ensure_ascii=False))
