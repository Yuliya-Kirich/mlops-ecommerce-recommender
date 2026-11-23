import argparse
import os
import re
import tempfile
from pathlib import Path

import boto3
import pandas as pd

BUCKET = "mlops-yk-2026"
PREFIX = "mlops-ecommerce/processed"
ENDPOINT = "https://storage.yandexcloud.net"

TRAIN_END = pd.Timestamp("2015-08-17", tz="UTC")
VALID_END = pd.Timestamp("2015-09-01", tz="UTC")

FEATURES = [
    "views",
    "purchases",
    "ctr",
    "hour",
    "weekday",
    "categoryid",
    "available",
]


def prepare_from_s3(data_date: str, output_dir: str) -> dict:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data_date):
        raise ValueError("Дата должна иметь формат YYYY-MM-DD")

    output = Path(output_dir).resolve()

    if output.exists():
        raise FileExistsError(
            f"Каталог уже существует: {output}. Автоматическая перезапись запрещена."
        )

    output.parent.mkdir(parents=True, exist_ok=True)

    profile = os.getenv("AWS_PROFILE", "yandex")
    session = boto3.Session(profile_name=profile)
    s3 = session.client(
        "s3",
        endpoint_url=ENDPOINT,
        region_name="ru-central1",
    )

    key = f"{PREFIX}/date={data_date}/training_dataset.parquet"
    print(f"Загружаем s3://{BUCKET}/{key}", flush=True)

    with tempfile.TemporaryDirectory(
        prefix="split-s3-",
        dir=output.parent,
    ) as temp_dir:
        workdir = Path(temp_dir)
        source = workdir / "training_dataset.parquet"

        s3.download_file(BUCKET, key, str(source))

        df = pd.read_parquet(source)

        required = set(FEATURES + ["event_time", "target"])
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Отсутствуют столбцы: {sorted(missing)}")

        df["event_time"] = pd.to_datetime(df["event_time"])

        if df["event_time"].isna().any():
            raise ValueError("Обнаружены пустые даты событий")

        parts = {
            "train": df[df["event_time"] < TRAIN_END],
            "validation": df[
                (df["event_time"] >= TRAIN_END) & (df["event_time"] < VALID_END)
            ],
            "test": df[df["event_time"] >= VALID_END],
        }

        if sum(len(part) for part in parts.values()) != len(df):
            raise ValueError("Разделение потеряло часть строк")

        info = {}

        for name, part in parts.items():
            if part.empty:
                raise ValueError(f"{name}: выборка пуста")

            if set(part["target"].dropna().unique()) != {0, 1}:
                raise ValueError(f"{name}: target должен содержать классы 0 и 1")

            path = workdir / f"{name}.parquet"
            part.to_parquet(path, index=False)

            info[name] = {
                "rows": len(part),
                "positives": int(part["target"].sum()),
            }

            print(f"{name}: {info[name]}", flush=True)

        if output.exists():
            raise FileExistsError(f"Каталог уже существует: {output}")

        output.mkdir()
        try:
            for name in parts:
                (workdir / f"{name}.parquet").replace(output / f"{name}.parquet")
        except Exception:
            import shutil

            shutil.rmtree(output)
            raise

    print(f"Разделение завершено: {output}", flush=True)
    return info


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-date", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    prepare_from_s3(args.data_date, args.output_dir)


if __name__ == "__main__":
    main()
