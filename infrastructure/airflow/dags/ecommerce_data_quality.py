
import os
import urllib.parse
import urllib.request
import subprocess
from datetime import datetime

from airflow.sdk import dag, task


def clickhouse_query(sql: str) -> str:
    password = os.environ["CLICKHOUSE_PASSWORD"]

    url = "http://mlops-clickhouse:8123/"

    params = urllib.parse.urlencode({
        "database": "ecommerce",
        "query": sql,
    })

    request = urllib.request.Request(
        url + "?" + params,
        headers={
            "X-ClickHouse-User": "mlops",
            "X-ClickHouse-Key": password,
        },
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode().strip()


@dag(
    dag_id="ecommerce_data_quality",
    start_date=datetime(2025, 1, 1),
    schedule="0 6 * * *",
    catchup=False,
    tags=["mlops", "ecommerce", "quality"],
)
def ecommerce_data_quality():

    @task
    def build_features():
        result = subprocess.run(
            [
                "python",
                "/opt/airflow/project_etl/build_features.py",
            ],
            capture_output=True,
            text=True,
            timeout=1800,
            check=True,
        )

        print(result.stdout)
        print("ETL выполнен успешно!")

    @task
    def check_training_dataset():
        sql = """
        SELECT
            count(),
            countIf(target = 1),
            countIf(target = 0),
            countIf(categoryid IS NULL),
            countIf(available IS NULL),
            min(hour),
            max(hour),
            min(weekday),
            max(weekday)
        FROM ecommerce.training_dataset
        FORMAT TabSeparated
        """

        values = clickhouse_query(sql).split("\t")

        (
            total,
            positive,
            negative,
            missing_category,
            missing_available,
            min_hour,
            max_hour,
            min_weekday,
            max_weekday,
        ) = map(int, values)

        print(f"Всего примеров: {total:,}")
        print(f"Покупок: {positive:,}")
        print(f"Без покупки: {negative:,}")
        print(f"Пропусков категории: {missing_category:,}")
        print(f"Пропусков доступности: {missing_available:,}")

        assert total == 2_654_387, "Неверное количество строк"
        assert positive + negative == total, "Ошибка target"
        assert positive > 0, "Отсутствуют положительные примеры"
        assert 0 <= min_hour <= max_hour <= 23, "Ошибка hour"
        assert 0 <= min_weekday <= max_weekday <= 6, "Ошибка weekday"

        print("Все проверки качества данных пройдены!")

    build_features() >> check_training_dataset()


ecommerce_data_quality()
