from pathlib import Path

import duckdb


def main() -> None:
    output = Path("data/item_property_events.parquet")
    output.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("SET memory_limit = '3GB'")
    con.execute("SET threads = 2")

    con.execute("""
        COPY (
            SELECT
                TRY_CAST(itemid AS BIGINT) AS itemid,
                epoch_ms(TRY_CAST(timestamp AS BIGINT)) AS event_time,
                property,
                TRY_CAST(value AS BIGINT) AS value
            FROM read_csv_auto(
                [
                    'item_properties_part1.csv',
                    'item_properties_part2.csv'
                ],
                union_by_name = true
            )
            WHERE property IN ('categoryid', 'available')
        )
        TO 'data/item_property_events.parquet'
        (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    result = con.execute("""
        SELECT
            property,
            COUNT(*) AS rows_count,
            COUNT(DISTINCT itemid) AS unique_items,
            MIN(event_time) AS first_date,
            MAX(event_time) AS last_date
        FROM read_parquet('data/item_property_events.parquet')
        GROUP BY property
        ORDER BY property
    """).fetchall()

    for row in result:
        print(row)

    print(f"\nSaved: {output}")
    con.close()


if __name__ == "__main__":
    main()
