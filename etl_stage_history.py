from pathlib import Path

import duckdb


def main() -> None:
    output = Path("data/item_history.parquet")
    output.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("SET memory_limit = '3GB'")
    con.execute("SET threads = 2")
    con.execute("SET temp_directory = 'data/duckdb_tmp'")

    con.execute("""
        COPY (
            WITH events_by_time AS (
                SELECT
                    itemid,
                    event_time,
                    COUNT(*) FILTER (
                        WHERE event = 'view'
                    ) AS new_views,
                    COUNT(*) FILTER (
                        WHERE event = 'transaction'
                    ) AS new_purchases
                FROM read_parquet('data/events.parquet')
                WHERE itemid IS NOT NULL
                  AND event_time IS NOT NULL
                GROUP BY itemid, event_time
            )
            SELECT
                itemid,
                event_time,
                SUM(new_views) OVER (
                    PARTITION BY itemid
                    ORDER BY event_time
                    ROWS BETWEEN UNBOUNDED PRECEDING
                        AND CURRENT ROW
                ) AS views,
                SUM(new_purchases) OVER (
                    PARTITION BY itemid
                    ORDER BY event_time
                    ROWS BETWEEN UNBOUNDED PRECEDING
                        AND CURRENT ROW
                ) AS purchases
            FROM events_by_time
        )
        TO 'data/item_history.parquet'
        (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    result = con.execute("""
        SELECT
            COUNT(*) AS rows_count,
            COUNT(DISTINCT itemid) AS unique_items,
            MIN(views) AS min_views,
            MAX(views) AS max_views,
            MIN(purchases) AS min_purchases,
            MAX(purchases) AS max_purchases
        FROM read_parquet('data/item_history.parquet')
    """).fetchone()

    print("History statistics:")
    print(f"Rows: {result[0]:,}")
    print(f"Unique items: {result[1]:,}")
    print(f"Views range: {result[2]} - {result[3]}")
    print(f"Purchases range: {result[4]} - {result[5]}")
    print(f"\nSaved: {output}")

    con.close()


if __name__ == "__main__":
    main()
