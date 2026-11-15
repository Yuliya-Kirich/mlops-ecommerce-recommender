from pathlib import Path

import duckdb


def main() -> None:
    output = Path("data/events.parquet")
    output.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("SET memory_limit = '3GB'")
    con.execute("SET threads = 2")

    con.execute("""
        COPY (
            SELECT
                epoch_ms(TRY_CAST(timestamp AS BIGINT)) AS event_time,
                TRY_CAST(visitorid AS BIGINT) AS visitorid,
                TRY_CAST(itemid AS BIGINT) AS itemid,
                LOWER(TRIM(event)) AS event,
                TRY_CAST(transactionid AS BIGINT) AS transactionid
            FROM read_csv_auto('events.csv')
            WHERE event IN ('view', 'addtocart', 'transaction')
        )
        TO 'data/events.parquet'
        (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    result = con.execute("""
        SELECT
            event,
            COUNT(*) AS rows_count,
            COUNT(DISTINCT visitorid) AS unique_visitors,
            MIN(event_time) AS first_date,
            MAX(event_time) AS last_date
        FROM read_parquet('data/events.parquet')
        GROUP BY event
        ORDER BY event
    """).fetchall()

    for row in result:
        print(row)

    print(f"\nSaved: {output}")
    con.close()


if __name__ == "__main__":
    main()
