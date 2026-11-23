import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-date", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.data_date):
        parser.error("Дата должна иметь формат YYYY-MM-DD")

    data_dir = ROOT / "data" / f"split_s3_{args.data_date}"
    source = (
        "s3://mlops-yk-2026/mlops-ecommerce/processed/"
        f"date={args.data_date}/training_dataset.parquet"
    )

    print("Версия данных:", args.data_date)
    print("Источник:", source)
    print("Каталог выборок:", data_dir)
    print("Публикация модели: отключена", flush=True)

    if not args.execute:
        print("DRY RUN: обучение не запускается")
        return

    import fcntl
    import json

    import boto3

    state_dir = ROOT / "artifacts" / "training_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    success_marker = state_dir / f"{args.data_date}.success"
    lock_path = state_dir / f"{args.data_date}.lock"

    with lock_path.open("w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Обучение этой версии уже выполняется")

        if success_marker.exists():
            print("SKIP: эта версия уже обучена")
            return

        s3 = boto3.Session(profile_name="yandex").client(
            "s3",
            endpoint_url="https://storage.yandexcloud.net",
            region_name="ru-central1",
        )

        manifest_key = f"mlops-ecommerce/processed/date={args.data_date}/manifest.json"

        obj = s3.get_object(
            Bucket="mlops-yk-2026",
            Key=manifest_key,
        )
        manifest = json.loads(obj["Body"].read())

        expected_key = (
            f"mlops-ecommerce/processed/date={args.data_date}/training_dataset.parquet"
        )

        if manifest.get("parquet_key") != expected_key:
            raise RuntimeError("Manifest указывает на другой датасет")

        if manifest.get("rows", 0) <= 0:
            raise RuntimeError("В manifest некорректное количество строк")

        parquet = s3.head_object(
            Bucket="mlops-yk-2026",
            Key=expected_key,
        )

        if parquet["ContentLength"] != manifest["size_bytes"]:
            raise RuntimeError("Размер Parquet не совпадает с manifest")

        print("SUCCESS: версия данных S3 проверена", flush=True)

        if not data_dir.exists():
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "src/ml/split_dataset.py"),
                    "--data-date",
                    args.data_date,
                    "--output-dir",
                    str(data_dir),
                ],
                cwd=ROOT,
                check=True,
            )

        for name in ("train", "validation", "test"):
            if not (data_dir / f"{name}.parquet").is_file():
                raise RuntimeError(f"Отсутствует выборка: {name}")

        import os

        env = os.environ.copy()
        env["MLOPS_DATA_DIR"] = str(data_dir)

        print("Запускаем ClearML + Optuna + CatBoost", flush=True)

        subprocess.run(
            [
                sys.executable,
                "-m",
                "src.ml.clearml_pipeline",
            ],
            cwd=ROOT,
            env=env,
            check=True,
        )

        print("SUCCESS: обучение ClearML завершено", flush=True)
        success_marker.write_text("success\n")


if __name__ == "__main__":
    main()
