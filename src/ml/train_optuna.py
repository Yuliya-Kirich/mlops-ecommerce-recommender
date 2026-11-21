import json
import pickle
from pathlib import Path

import optuna
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.metrics import average_precision_score


FEATURES = [
    "views",
    "purchases",
    "ctr",
    "hour",
    "weekday",
    "categoryid",
    "available",
]


def train_optuna(
    data_dir: str,
    output_dir: str,
    n_trials: int = 3,
):
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    train_df = pd.read_parquet(data_dir / "train.parquet")
    val_df = pd.read_parquet(data_dir / "validation.parquet")

    X_train = train_df[FEATURES].astype("float32")
    y_train = train_df["target"].astype("int8")

    X_val = val_df[FEATURES].astype("float32")
    y_val = val_df["target"].astype("int8")

    del train_df, val_df

    best_model_path = output_dir / "catboost_best.pkl"
    best_params_path = output_dir / "best_params.json"

    best_score = float("-inf")

    def objective(trial):
        nonlocal best_score

        params = {
            "depth": trial.suggest_int("depth", 4, 6),
            "learning_rate": trial.suggest_float(
                "learning_rate", 0.02, 0.1, log=True
            ),
            "l2_leaf_reg": trial.suggest_float(
                "l2_leaf_reg", 1.0, 5.0
            ),
            "iterations": 250,
            "loss_function": "Logloss",
            "verbose": False,
            "thread_count": 2,
            "random_seed": 42,
            "allow_writing_files": False,
        }

        model = CatBoostClassifier(**params)
        model.fit(X_train, y_train)

        probabilities = model.predict_proba(X_val)[:, 1]
        score = float(
            average_precision_score(y_val, probabilities)
        )

        trial.set_user_attr("pr_auc", score)

        if score > best_score:
            best_score = score

            with open(best_model_path, "wb") as f:
                pickle.dump(model, f)

            with open(best_params_path, "w") as f:
                json.dump(params, f, indent=2)

        print(
            f"Trial {trial.number}: "
            f"PR-AUC={score:.6f}",
            flush=True,
        )

        return score

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )

    study.optimize(objective, n_trials=n_trials)

    results = {
        "best_pr_auc": float(study.best_value),
        "best_params": study.best_params,
        "n_trials": len(study.trials),
        "features": FEATURES,
        "model_path": str(best_model_path),
    }

    with open(output_dir / "training_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print("Лучший PR-AUC:", results["best_pr_auc"])
    print("Лучшая модель:", best_model_path)

    return results


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[2]

    train_optuna(
        data_dir=str(project_root / "data/split_v2"),
        output_dir=str(project_root / "artifacts/pipeline"),
        n_trials=3,
    )
