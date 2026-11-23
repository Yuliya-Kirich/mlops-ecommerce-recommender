import os
from pathlib import Path

import clickhouse_connect

ETL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ETL_DIR.parents[1]
SQL_DIR = ETL_DIR / "sql"
ENV_FILE = PROJECT_ROOT / "infrastructure/clickhouse/.env"


def get_password():
    # В Airflow пароль приходит из Docker env_file
    password = os.environ.get("CLICKHOUSE_PASSWORD")
    if password:
        return password

    # При запуске на Ubuntu читаем локальный .env
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("CLICKHOUSE_PASSWORD="):
            return line.split("=", 1)[1].strip()

    raise RuntimeError("CLICKHOUSE_PASSWORD не найден")


def get_client():
    host = os.environ.get("CLICKHOUSE_HOST", "127.0.0.1")

    return clickhouse_connect.get_client(
        host=host,
        port=8123,
        username="mlops",
        password=get_password(),
        database="ecommerce",
    )


def main():
    client = get_client()

    print("ClickHouse:", client.command("SELECT version()"))

    tables = [
        "events_clean",
        "views_labeled",
        "item_history",
        "views_with_history",
        "item_properties_raw",
        "item_categories_history",
        "item_availability_history",
    ]

    # Проверяем промежуточные таблицы
    for table in tables:
        count = client.command(f"SELECT count() FROM ecommerce.{table}")
        print(f"{table}: {count:,} строк")

    expected = client.command("SELECT count() FROM ecommerce.views_labeled")

    actual = client.command("SELECT count() FROM ecommerce.views_with_history")

    if actual != expected:
        raise RuntimeError(
            "Количество строк с историческими признаками "
            "не совпадает с количеством размеченных просмотров"
        )

    print("Проверка промежуточных таблиц пройдена!")

    # Создаём итоговую таблицу
    create_sql = SQL_DIR / "05_create_training_dataset.sql"

    client.command(create_sql.read_text(encoding="utf-8"))

    print("Таблица ecommerce.training_dataset существует!")

    # Проверяем, не были ли данные загружены ранее
    existing = client.command("SELECT count() FROM ecommerce.training_dataset")

    if existing == expected:
        print(f"Обучающая выборка уже готова: {existing:,} строк.")
        print("Повторная загрузка не требуется.")

    elif existing == 0:
        print("Обучающая выборка пустая. Начинаем загрузку.")

        populate_sql = SQL_DIR / "06_populate_training_dataset.sql"

        client.command(populate_sql.read_text(encoding="utf-8"))

        actual = client.command("SELECT count() FROM ecommerce.training_dataset")

        if actual != expected:
            raise RuntimeError(f"Ожидалось {expected:,} строк, получено {actual:,}")

        print(f"Загружено {actual:,} обучающих примеров.")

    else:
        raise RuntimeError(
            f"Обнаружена неполная или некорректная таблица: "
            f"{existing:,} строк вместо {expected:,}. "
            "Автоматическая перезапись запрещена."
        )

    print("ETL завершён успешно!")


if __name__ == "__main__":
    main()
