import pandas as pd

MAX_RELATIVE_CHANGE = 0.15


def test_target_rate_stability():
    validation = pd.read_parquet(
        "data/split_v2/validation.parquet",
        columns=["target"],
    )

    test = pd.read_parquet(
        "data/split_v2/test.parquet",
        columns=["target"],
    )

    reference_rate = validation["target"].mean()
    current_rate = test["target"].mean()

    assert reference_rate > 0, "Невозможно рассчитать относительное изменение"

    relative_change = abs(current_rate - reference_rate) / reference_rate

    print(f"\nValidation purchase rate: {reference_rate:.4%}")
    print(f"Test purchase rate: {current_rate:.4%}")
    print(f"Relative change: {relative_change:.2%}")

    assert relative_change <= MAX_RELATIVE_CHANGE, (
        f"Изменение доли покупок {relative_change:.2%} "
        f"превысило порог {MAX_RELATIVE_CHANGE:.0%}"
    )
