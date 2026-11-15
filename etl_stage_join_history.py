from pathlib import Path

import duckdb


def main() -> None:
    output = Path("data/views_with_history.parquet")
    output.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("SET memory_limit = '3GB'")
    con.execute("SET threads = 2")
    con.execute("SET temp_directory = 'data/duckdb_tmp'")

    con.execute("""
        COPY (
            SELECT
                v.event_time,
                v.visitorid,
                v.itemid,
                COALESCE(h.views, 0) AS views,
                COALESCE(h.purchases, 0) AS purchases,
                COALESCE(h.purchases, 0)::DOUBLE
                    / GREATEST(COALESCE(h.views, 0), 1)
                    AS ctr,
                v.hour,
                v.weekday,
                v.target
            FROM read_parquet('data/views_labeled.parquet') v
            ASOF LEFT JOIN
                read_parquet('data/item_history.parquet') h
            ON v.itemid = h.itemid
               AND v.event_time > h.event_time
        )
        TO 'data/views_with_history.parquet'
        (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    result = con.execute("""
        SELECT
            COUNT(*) AS total_rows,
            SUM(target) AS positive_rows,
            MIN(views) AS min_views,
            MAX(views) AS max_views,
            MIN(purchases) AS min_purchases,
            MAX(purchases) AS max_purchases,
            COUNT(*) FILTER (WHERE views = 0) AS zero_history_rows
        FROM read_parquet('data/views_with_history.parquet')
    """).fetchone()

    print("Training history statistics:")
    print(f"Total rows: {result[0]:,}")
    print(f"Positive rows: {result[1]:,}")
    print(f"Views range: {result[2]} - {result[3]}")
    print(f"Purchases range: {result[4]} - {result[5]}")
    print(f"Rows with zero previous views: {result[6]:,}")
    print(f"\nSaved: {output}")

    con.close()


if __name__ == "__main__":
    main()
