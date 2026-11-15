from pathlib import Path

import duckdb


def main() -> None:
    output = Path("data/views_labeled.parquet")
    output.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("SET memory_limit = '3GB'")
    con.execute("SET threads = 2")
    con.execute("SET temp_directory = 'data/duckdb_tmp'")

    con.execute("""
        COPY (
            WITH observation_end AS (
                SELECT MAX(event_time) AS max_time
                FROM read_parquet('data/events.parquet')
            ),
            eligible_views AS (
                SELECT
                    event_time,
                    visitorid,
                    itemid,
                    CAST(EXTRACT(HOUR FROM event_time) AS INTEGER) AS hour,
                    CAST(EXTRACT(ISODOW FROM event_time) - 1 AS INTEGER)
                        AS weekday
                FROM read_parquet('data/events.parquet')
                WHERE event = 'view'
                  AND event_time <= (
                      SELECT max_time - INTERVAL '24 hours'
                      FROM observation_end
                  )
            ),
            purchases AS (
                SELECT
                    visitorid,
                    itemid,
                    event_time
                FROM read_parquet('data/events.parquet')
                WHERE event = 'transaction'
            )
            SELECT
                v.*,
                CAST(
                    EXISTS (
                        SELECT 1
                        FROM purchases p
                        WHERE p.visitorid = v.visitorid
                          AND p.itemid = v.itemid
                          AND p.event_time > v.event_time
                          AND p.event_time <=
                              v.event_time + INTERVAL '24 hours'
                    ) AS INTEGER
                ) AS target
            FROM eligible_views v
        )
        TO 'data/views_labeled.parquet'
        (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    result = con.execute("""
        SELECT
            target,
            COUNT(*) AS rows_count
        FROM read_parquet('data/views_labeled.parquet')
        GROUP BY target
        ORDER BY target
    """).fetchall()

    total = sum(count for _, count in result)

    print("\nTarget distribution:")
    for target, count in result:
        print(
            f"target={target}: {count:,} "
            f"({count / total:.4%})"
        )

    print(f"\nTotal views: {total:,}")
    print(f"Saved: {output}")

    con.close()


if __name__ == "__main__":
    main()
