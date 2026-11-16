from pathlib import Path

import duckdb


def main() -> None:
    Path("data").mkdir(exist_ok=True)

    con = duckdb.connect()
    con.execute("SET memory_limit = '3GB'")
    con.execute("SET threads = 2")

    split_time = con.execute("""
        SELECT quantile_cont(event_time, 0.8)
        FROM read_parquet('data_for_training.parquet')
    """).fetchone()[0]

    train_end = split_time - __import__(
        "datetime"
    ).timedelta(hours=24)

    print(f"Validation starts: {split_time}")
    print(f"Training ends before: {train_end}")

    con.execute("""
        COPY (
            SELECT *
            FROM read_parquet('data_for_training.parquet')
            WHERE event_time < ?
        )
        TO 'data/train.parquet'
        (FORMAT PARQUET, COMPRESSION ZSTD)
    """, [train_end])

    con.execute("""
        COPY (
            SELECT *
            FROM read_parquet('data_for_training.parquet')
            WHERE event_time >= ?
        )
        TO 'data/validation.parquet'
        (FORMAT PARQUET, COMPRESSION ZSTD)
    """, [split_time])

    for name in ["train", "validation"]:
        total, positives, start, end = con.execute(f"""
            SELECT
                COUNT(*),
                SUM(target),
                MIN(event_time),
                MAX(event_time)
            FROM read_parquet('data/{name}.parquet')
        """).fetchone()

        print(f"\n{name.upper()}")
        print(f"Rows: {total:,}")
        print(f"Positive examples: {positives:,}")
        print(f"Start: {start}")
        print(f"End: {end}")

    con.close()


if __name__ == "__main__":
    main()
