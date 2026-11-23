import json
import pickle
from pathlib import Path

import pandas as pd
from clearml import Task
from sklearn.metrics import average_precision_score, roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main():
    with open(PROJECT_ROOT / "artifacts/ranker_optuna.pkl", "rb") as f:
        model = pickle.load(f)

    with open(PROJECT_ROOT / "artifacts/optuna_best_params.json") as f:
        params = json.load(f)

    df = pd.read_parquet(PROJECT_ROOT / "data/validation.parquet")

    X = df[model.feature_names_].astype(float)
    y = df["target"]

    probabilities = model.predict_proba(X)[:, 1]

    pr_auc = average_precision_score(y, probabilities)
    roc_auc = roc_auc_score(y, probabilities)
    baseline = y.mean()

    task = Task.init(
        project_name="MLOps Ecommerce",
        task_name="CatBoost Optuna - automatic evaluation",
        task_type=Task.TaskTypes.testing,
        reuse_last_task_id=False,
        auto_connect_frameworks=False,
        auto_connect_arg_parser=False,
    )

    try:
        task.connect(params, name="CatBoost hyperparameters")
        logger = task.get_logger()

        for name, value in {
            "PR-AUC validation": pr_auc,
            "ROC-AUC validation": roc_auc,
            "PR-AUC baseline": baseline,
        }.items():
            logger.report_scalar(
                title="Model quality",
                series=name,
                value=float(value),
                iteration=0,
            )

        print(f"PR-AUC: {pr_auc:.6f}")
        print(f"ROC-AUC: {roc_auc:.6f}")
        print(f"Baseline: {baseline:.6f}")
        print("Task ID:", task.id)
    finally:
        task.close()


if __name__ == "__main__":
    main()
