import json
import os
import urllib.request
import uuid
from datetime import UTC, datetime

import boto3
import clickhouse_connect
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError

BUCKET = "mlops-yk-2026"
PREFIX = "mlops-ecommerce/processed"
ENDPOINT = "https://storage.yandexcloud.net"


def get_clickhouse_client():
    return clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "127.0.0.1"),
        port=8123,
        username="mlops",
        password=os.environ["CLICKHOUSE_PASSWORD"],
        database="ecommerce",
    )


def main():
    client = get_clickhouse_client()

    expected_rows = client.command("SELECT count() FROM ecommerce.training_dataset")

    if expected_rows == 0:
        raise RuntimeError("Обучающая выборка пуста")

    s3 = boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        region_name="ru-central1",
    )

    run_date = os.environ.get("DATA_DATE") or datetime.now(UTC).strftime("%Y-%m-%d")

    target_prefix = f"{PREFIX}/date={run_date}"
    final_key = f"{target_prefix}/training_dataset.parquet"
    manifest_key = f"{target_prefix}/manifest.json"

    try:
        manifest_object = s3.get_object(
            Bucket=BUCKET,
            Key=manifest_key,
        )
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]

        if error_code in ("NoSuchKey", "404"):
            manifest_object = None
        else:
            raise

    if manifest_object is not None:
        manifest = json.loads(manifest_object["Body"].read())
        s3.head_object(Bucket=BUCKET, Key=final_key)

        if manifest["rows"] != expected_rows:
            raise RuntimeError(
                "Уже опубликованная версия имеет другое "
                "количество строк. Требуется новая версия."
            )

        print(f"Версия уже опубликована: s3://{BUCKET}/{final_key}")
        return

    try:
        s3.head_object(
            Bucket=BUCKET,
            Key=final_key,
        )
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]

        if error_code not in ("404", "NoSuchKey", "NotFound"):
            raise
    else:
        raise RuntimeError(
            "Parquet уже существует, но manifest.json отсутствует. "
            "Автоматическая перезапись запрещена."
        )

    temp_key = f"{target_prefix}/_staging/{uuid.uuid4().hex}.parquet"

    sql = """
    SELECT *
    FROM ecommerce.training_dataset
    ORDER BY event_time, itemid, visitorid, timestamp
    FORMAT Parquet
    """

    request = urllib.request.Request(
        f"http://{os.getenv('CLICKHOUSE_HOST', '127.0.0.1')}:8123/",
        data=sql.encode(),
        headers={
            "X-ClickHouse-User": "mlops",
            "X-ClickHouse-Key": os.environ["CLICKHOUSE_PASSWORD"],
            "X-ClickHouse-Database": "ecommerce",
        },
        method="POST",
    )

    print(f"Экспортируем {expected_rows:,} строк в S3")

    import shutil
    import tempfile

    with tempfile.TemporaryDirectory(prefix="mlops-export-") as temp_dir:
        local_file = os.path.join(temp_dir, "training_dataset.parquet")

        print("Скачиваем Parquet из ClickHouse", flush=True)

        with (
            urllib.request.urlopen(request, timeout=1800) as response,
            open(local_file, "wb") as output,
        ):
            shutil.copyfileobj(response, output, length=1024 * 1024)

        if os.path.getsize(local_file) == 0:
            raise RuntimeError("ClickHouse вернул пустой файл")

        print("Загрузка готового Parquet в S3", flush=True)

        s3.upload_file(
            local_file,
            BUCKET,
            temp_key,
            Config=TransferConfig(
                multipart_threshold=8 * 1024 * 1024,
                multipart_chunksize=16 * 1024 * 1024,
                use_threads=False,
            ),
        )

    obj = s3.head_object(Bucket=BUCKET, Key=temp_key)
    size = obj["ContentLength"]

    if size == 0:
        raise RuntimeError("Экспортированный файл пуст")

    beginning = s3.get_object(
        Bucket=BUCKET,
        Key=temp_key,
        Range="bytes=0-3",
    )["Body"].read()

    ending = s3.get_object(
        Bucket=BUCKET,
        Key=temp_key,
        Range="bytes=-4",
    )["Body"].read()

    if beginning != b"PAR1" or ending != b"PAR1":
        raise RuntimeError("Некорректная сигнатура Parquet")

    import io

    import pyarrow.parquet as pq

    # Читаем последние 8 байт Parquet
    footer = s3.get_object(
        Bucket=BUCKET,
        Key=temp_key,
        Range="bytes=-8",
    )["Body"].read()

    if len(footer) != 8 or footer[4:] != b"PAR1":
        raise RuntimeError("Некорректный footer Parquet")

    footer_size = int.from_bytes(
        footer[:4],
        byteorder="little",
    )

    if footer_size <= 0 or footer_size + 8 > size:
        raise RuntimeError("Некорректный размер metadata Parquet")

    # Скачиваем только метаданные, не весь Parquet
    metadata_bytes = s3.get_object(
        Bucket=BUCKET,
        Key=temp_key,
        Range=f"bytes={size - footer_size - 8}-{size - 9}",
    )["Body"].read()

    metadata_buffer = io.BytesIO(b"PAR1" + metadata_bytes + footer)

    metadata = pq.read_metadata(metadata_buffer)
    actual_rows = metadata.num_rows

    print(f"Строк в ClickHouse: {expected_rows:,}")
    print(f"Строк в Parquet: {actual_rows:,}")

    if actual_rows != expected_rows:
        raise RuntimeError(
            f"Количество строк не совпадает: "
            f"ClickHouse={expected_rows}, "
            f"Parquet={actual_rows}"
        )

    print("Проверка количества строк Parquet пройдена!")

    s3.copy_object(
        Bucket=BUCKET,
        Key=final_key,
        CopySource={"Bucket": BUCKET, "Key": temp_key},
    )

    manifest = {
        "source": "ecommerce.training_dataset",
        "rows": expected_rows,
        "size_bytes": size,
        "exported_at": datetime.now(UTC).isoformat(),
        "parquet_key": final_key,
    }

    s3.put_object(
        Bucket=BUCKET,
        Key=manifest_key,
        Body=json.dumps(manifest, indent=2).encode(),
        ContentType="application/json",
    )

    s3.delete_object(Bucket=BUCKET, Key=temp_key)

    print(f"Экспорт завершён: s3://{BUCKET}/{final_key}")
    print(f"Строк в источнике: {expected_rows:,}")
    print(f"Размер Parquet: {size:,} байт")


if __name__ == "__main__":
    main()
