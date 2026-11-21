from pathlib import Path

import pandas as pd

SOURCE = Path("data_for_training.parquet")
OUTPUT_DIR = Path("data/split_v2")

TRAIN_END = pd.Timestamp("2015-08-17")
VALID_END = pd.Timestamp("2015-09-01")


def main():
    df = pd.read_parquet(SOURCE)

    df["event_time"] = pd.to_datetime(df["event_time"])

    train = df[df["event_time"] < TRAIN_END]
    validation = df[
        (df["event_time"] >= TRAIN_END)
        & (df["event_time"] < VALID_END)
    ]
    test = df[df["event_time"] >= VALID_END]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for name, part in [
        ("train", train),
        ("validation", validation),
        ("test", test),
    ]:
        path = OUTPUT_DIR / f"{name}.parquet"
        part.to_parquet(path, index=False)

        print(
            f"{name}: {len(part):,} строк, "
            f"{int(part['target'].sum()):,} покупок"
        )

    assert len(train) + len(validation) + len(test) == len(df)
    print("Разделение данных завершено!")


if __name__ == "__main__":
    main()
