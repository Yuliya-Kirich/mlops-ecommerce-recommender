import pickle
from pathlib import Path

import pandas as pd
from catboost import CatBoostClassifier
from sklearn.metrics import average_precision_score


FEATURE_COLS = [
    "views",
    "purchases",
    "ctr",
    "hour",
    "weekday",
    "categoryid",
    "available",
]


def main() -> None:
    print("Loading datasets...")

    train = pd.read_parquet("data/train.parquet")
    validation = pd.read_parquet("data/validation.parquet")

    x_train = train[FEATURE_COLS].astype("float32")
    y_train = train["target"].astype(int)

    x_valid = validation[FEATURE_COLS].astype("float32")
    y_valid = validation["target"].astype(int)

    print(f"Train rows: {len(train):,}")
    print(f"Validation rows: {len(validation):,}")

    model = CatBoostClassifier(
        iterations=500,
        depth=4,
        learning_rate=0.1,
        loss_function="Logloss",
        random_seed=42,
        thread_count=2,
        verbose=100,
    )

    print("\nTraining CatBoost...")

    model.fit(
        x_train,
        y_train,
        eval_set=(x_valid, y_valid),
        early_stopping_rounds=50,
        use_best_model=True,
    )

    probabilities = model.predict_proba(x_valid)[:, 1]

    pr_auc = average_precision_score(y_valid, probabilities)
    baseline = float(y_valid.mean())

    print("\n=== VALIDATION RESULTS ===")
    print(f"PR-AUC (Average Precision): {pr_auc:.6f}")
    print(f"Random baseline: {baseline:.6f}")
    print(f"Best iteration: {model.best_iteration_}")

    output = Path("ranker.pkl")

    with output.open("wb") as file:
        pickle.dump(model, file)

    print(f"\nModel saved: {output}")


if __name__ == "__main__":
    main()
