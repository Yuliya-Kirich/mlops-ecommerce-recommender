import pickle
from pathlib import Path

import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

FEATURES = [
    "views",
    "purchases",
    "ctr",
    "hour",
    "weekday",
    "categoryid",
    "available",
]

MAX_ROC_AUC_DROP = 0.05
MAX_PR_AUC_DROP = 0.10


def calculate_metrics(model, dataset_path):
    df = pd.read_parquet(
        dataset_path,
        columns=FEATURES + ["target"],
    )

    x = df[FEATURES].astype("float32")
    y = df["target"]

    probabilities = model.predict_proba(x)[:, 1]

    return {
        "roc_auc": roc_auc_score(y, probabilities),
        "pr_auc": average_precision_score(y, probabilities),
    }


def test_model_quality_degradation():
    model_path = Path("artifacts/pipeline/catboost_best.pkl")

    with model_path.open("rb") as file:
        model = pickle.load(file)

    assert list(model.feature_names_) == FEATURES

    reference = calculate_metrics(
        model,
        "data/split_v2/validation.parquet",
    )

    current = calculate_metrics(
        model,
        "data/split_v2/test.parquet",
    )

    print("\n=== Model Quality Monitoring ===")

    for metric, threshold in [
        ("roc_auc", MAX_ROC_AUC_DROP),
        ("pr_auc", MAX_PR_AUC_DROP),
    ]:
        baseline = reference[metric]
        actual = current[metric]

        relative_drop = (baseline - actual) / baseline

        print(
            f"{metric}: reference={baseline:.6f}, "
            f"current={actual:.6f}, "
            f"drop={relative_drop:.2%}, "
            f"threshold={threshold:.0%}"
        )

        assert relative_drop <= threshold, (
            f"{metric}: качество снизилось на "
            f"{relative_drop:.2%}; "
            f"допустимый порог {threshold:.0%}"
        )
