
import os
import io
import json
from datetime import datetime, timezone

import boto3
import pyarrow.parquet as pq

BUCKET = "mlops-yk-2026"
PREFIX = "mlops-ecommerce/processed"
ENDPOINT = "https://storage.yandexcloud.net"


def main():
    date = os.environ.get("DATA_DATE") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prefix = f"{PREFIX}/date={date}"

    parquet_key = f"{prefix}/training_dataset.parquet"
    manifest_key = f"{prefix}/manifest.json"

    s3 = boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        region_name="ru-central1",
    )

    manifest = json.loads(
        s3.get_object(
            Bucket=BUCKET,
            Key=manifest_key,
        )["Body"].read()
    )

    obj = s3.head_object(
        Bucket=BUCKET,
        Key=parquet_key,
    )

    size = obj["ContentLength"]

    footer = s3.get_object(
        Bucket=BUCKET,
        Key=parquet_key,
        Range="bytes=-8",
    )["Body"].read()

    if len(footer) != 8 or footer[4:] != b"PAR1":
        raise RuntimeError("Некорректный footer Parquet")

    footer_size = int.from_bytes(
        footer[:4],
        byteorder="little",
    )

    if not 0 < footer_size <= size - 8:
        raise RuntimeError("Некорректный размер метаданных")

    metadata_bytes = s3.get_object(
        Bucket=BUCKET,
        Key=parquet_key,
        Range=f"bytes={size-footer_size-8}-{size-9}",
    )["Body"].read()

    metadata = pq.read_metadata(
        io.BytesIO(b"PAR1" + metadata_bytes + footer)
    )

    expected_rows = int(manifest["rows"])
    actual_rows = metadata.num_rows

    if actual_rows != expected_rows:
        raise RuntimeError(
            f"Количество строк не совпадает: "
            f"{actual_rows} != {expected_rows}"
        )

    if int(manifest["size_bytes"]) != size:
        raise RuntimeError("Размер файла не совпадает")

    if manifest["parquet_key"] != parquet_key:
        raise RuntimeError("Неверный путь Parquet в манифесте")

    print(f"Версия: {date}")
    print(f"Строк: {actual_rows:,}")
    print(f"Размер: {size:,} байт")
    print("Проверка экспорта S3 пройдена!")


if __name__ == "__main__":
    main()
