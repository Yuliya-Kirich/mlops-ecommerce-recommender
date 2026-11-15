from pathlib import Path

import duckdb


def main() -> None:
    output = Path("data_for_training.parquet")

    con = duckdb.connect()
    con.execute("SET memory_limit = '3GB'")
    con.execute("SET threads = 2")
    con.execute("SET temp_directory = 'data/duckdb_tmp'")

    con.execute("""
        COPY (
            WITH categories AS (
                SELECT
                    itemid,
                    event_time,
                    MAX(value) AS categoryid
                FROM read_parquet(
                    'data/item_property_events.parquet'
                )
                WHERE property = 'categoryid'
                  AND value IS NOT NULL
                GROUP BY itemid, event_time
            ),
            availability AS (
                SELECT
                    itemid,
                    event_time,
                    MAX(value) AS available
                FROM read_parquet(
                    'data/item_property_events.parquet'
                )
                WHERE property = 'available'
                  AND value IS NOT NULL
                GROUP BY itemid, event_time
            ),
            with_categories AS (
                SELECT
                    v.*,
                    c.categoryid
                FROM read_parquet(
                    'data/views_with_history.parquet'
                ) v
                ASOF LEFT JOIN categories c
                  ON v.itemid = c.itemid
                 AND v.event_time >= c.event_time
            )
            SELECT
                v.event_time,
                v.visitorid,
                v.itemid,
                v.views,
                v.purchases,
                v.ctr,
                v.hour,
                v.weekday,
                COALESCE(v.categoryid, 0) AS categoryid,
                COALESCE(a.available, 0) AS available,
                v.target
            FROM with_categories v
            ASOF LEFT JOIN availability a
              ON v.itemid = a.itemid
             AND v.event_time >= a.event_time
        )
        TO 'data_for_training.parquet'
        (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    result = con.execute("""
        SELECT
            COUNT(*) AS total_rows,
            SUM(target) AS positive_rows,
            COUNT(*) FILTER (
                WHERE categoryid = 0
            ) AS missing_category,
            COUNT(*) FILTER (
                WHERE available = 1
            ) AS available_rows,
            COUNT(*) FILTER (
                WHERE available = 0
            ) AS unavailable_or_unknown_rows
        FROM read_parquet('data_for_training.parquet')
    """).fetchone()

    print("Final training dataset:")
    print(f"Total rows: {result[0]:,}")
    print(f"Positive rows: {result[1]:,}")
    print(f"Rows with categoryid=0: {result[2]:,}")
    print(f"Rows with available=1: {result[3]:,}")
    print(f"Rows with available=0: {result[4]:,}")

    print("\nColumns:")
    columns = con.execute("""
        DESCRIBE SELECT *
        FROM read_parquet('data_for_training.parquet')
    """).fetchall()

    for column in columns:
        print(f"  {column[0]}: {column[1]}")

    print(f"\nSaved: {output}")
    con.close()


if __name__ == "__main__":
    main()
