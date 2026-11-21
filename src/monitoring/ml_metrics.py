import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
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

# Демонстрационный порог величины расхождения.
MAX_KS_STATISTIC = 0.05


def calculate_ml_metrics(
    model_path="artifacts/pipeline/catboost_best.pkl",
    reference_path="data/split_v2/validation.parquet",
    current_path="data/split_v2/test.parquet",
):
    with Path(model_path).open("rb") as file:
        model = pickle.load(file)

    if list(model.feature_names_) != FEATURES:
        raise ValueError("Признаки модели не совпадают")

    reference = pd.read_parquet(reference_path)
    current = pd.read_parquet(current_path)

    result = {}

    for name, dataset in [
        ("reference", reference),
        ("current", current),
    ]:
        x = dataset[FEATURES].astype("float32")
        y = dataset["target"]

        probabilities = model.predict_proba(x)[:, 1]

        result[f"{name}_roc_auc"] = float(
            roc_auc_score(y, probabilities)
        )
        result[f"{name}_pr_auc"] = float(
            average_precision_score(y, probabilities)
        )

    roc_drop = (
        result["reference_roc_auc"] - result["current_roc_auc"]
    ) / result["reference_roc_auc"]

    pr_drop = (
        result["reference_pr_auc"] - result["current_pr_auc"]
    ) / result["reference_pr_auc"]

    result["roc_auc_drop"] = float(roc_drop)
    result["pr_auc_drop"] = float(pr_drop)

    result["model_degradation_detected"] = int(
        roc_drop > MAX_ROC_AUC_DROP
        or pr_drop > MAX_PR_AUC_DROP
    )

    drifted_features = 0

    for feature in FEATURES:
        ks = ks_2samp(
            reference[feature].to_numpy(),
            current[feature].to_numpy(),
            method="asymp",
        ).statistic

        result[f"ks_{feature}"] = float(ks)

        if ks > MAX_KS_STATISTIC:
            drifted_features += 1

    result["drifted_features_count"] = drifted_features
    result["data_drift_detected"] = int(drifted_features > 0)

    return result
