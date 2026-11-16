import json
import pickle
from pathlib import Path

import optuna
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
    print("Loading train and validation data...")

    train = pd.read_parquet("data/train.parquet")
    valid = pd.read_parquet("data/validation.parquet")

    x_train = train[FEATURE_COLS].astype("float32")
    y_train = train["target"].astype(int)

    x_valid = valid[FEATURE_COLS].astype("float32")
    y_valid = valid["target"].astype(int)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "iterations": 400,
            "depth": trial.suggest_int("depth", 3, 6),
            "learning_rate": trial.suggest_float(
                "learning_rate", 0.02, 0.15, log=True
            ),
            "l2_leaf_reg": trial.suggest_float(
                "l2_leaf_reg", 1.0, 10.0, log=True
            ),
            "loss_function": "Logloss",
            "eval_metric": "PRAUC",
            "random_seed": 42,
            "thread_count": 2,
            "verbose": False,
        }

        model = CatBoostClassifier(**params)

        model.fit(
            x_train,
            y_train,
            eval_set=(x_valid, y_valid),
            early_stopping_rounds=50,
            use_best_model=True,
        )

        predictions = model.predict_proba(x_valid)[:, 1]
        score = average_precision_score(y_valid, predictions)

        trial.set_user_attr("best_iteration", model.best_iteration_)

        print(
            f"Trial {trial.number}: "
            f"PR-AUC={score:.6f}, "
            f"best_iteration={model.best_iteration_}",
            flush=True,
        )

        return score

    study = optuna.create_study(
        direction="maximize",
        study_name="catboost_purchase_prediction",
        storage="sqlite:///optuna_study.db",
        load_if_exists=True,
    )

    study.optimize(objective, n_trials=5, gc_after_trial=True)

    print("\n=== OPTUNA RESULTS ===")
    print(f"Best PR-AUC: {study.best_value:.6f}")
    print(f"Best parameters: {study.best_params}")

    Path("artifacts").mkdir(exist_ok=True)

    with open("artifacts/optuna_best_params.json", "w") as file:
        json.dump(study.best_params, file, indent=2)

    best_params = {
        **study.best_params,
        "iterations": 400,
        "loss_function": "Logloss",
        "eval_metric": "PRAUC",
        "random_seed": 42,
        "thread_count": 2,
        "verbose": False,
    }

    best_model = CatBoostClassifier(**best_params)

    best_model.fit(
        x_train,
        y_train,
        eval_set=(x_valid, y_valid),
        early_stopping_rounds=50,
        use_best_model=True,
    )

    with open("artifacts/ranker_optuna.pkl", "wb") as file:
        pickle.dump(best_model, file)

    print("\nSaved: artifacts/ranker_optuna.pkl")


if __name__ == "__main__":
    main()
