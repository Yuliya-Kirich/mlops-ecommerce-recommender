
from pathlib import Path

import clickhouse_connect


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / "infrastructure/clickhouse/.env"
SQL_DIR = PROJECT_ROOT / "src/etl/sql"


def get_password():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("CLICKHOUSE_PASSWORD="):
            return line.split("=", 1)[1].strip()

    raise RuntimeError("CLICKHOUSE_PASSWORD не найден")


def get_client():
    return clickhouse_connect.get_client(
        host="127.0.0.1",
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
        count = client.command(
            f"SELECT count() FROM ecommerce.{table}"
        )
        print(f"{table}: {count:,} строк")

    expected = client.command(
        "SELECT count() FROM ecommerce.views_labeled"
    )

    actual = client.command(
        "SELECT count() FROM ecommerce.views_with_history"
    )

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
    existing = client.command(
        "SELECT count() FROM ecommerce.training_dataset"
    )

    if existing != 0:
        raise RuntimeError(
            f"training_dataset уже содержит {existing:,} строк. "
            "Повторная загрузка запрещена."
        )

    # Заполняем итоговую таблицу
    populate_sql = SQL_DIR / "06_populate_training_dataset.sql"

    client.command(populate_sql.read_text(encoding="utf-8"))

    # Проверяем количество обучающих примеров
    actual = client.command(
        "SELECT count() FROM ecommerce.training_dataset"
    )

    print(f"Обучающих примеров: {actual:,}")

    if actual != expected:
        raise RuntimeError(
            f"Ожидалось {expected:,} строк, получено {actual:,}"
        )

    print("Итоговая обучающая выборка готова!")


if __name__ == "__main__":
    main()
