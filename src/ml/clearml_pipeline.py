import os
from pathlib import Path

from clearml import PipelineDecorator

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@PipelineDecorator.component(
    return_values=["dataset_info"],
    cache=False,
)
def prepare_data(project_root: str, data_dir: str):
    import pandas as pd

    folder = Path(data_dir)
    info = {}

    for name in ("train", "validation", "test"):
        path = folder / f"{name}.parquet"
        df = pd.read_parquet(path)

        if df["target"].nunique() != 2:
            raise ValueError(f"{name}: отсутствует один из классов")

        info[name] = {
            "path": str(path),
            "rows": len(df),
            "positives": int(df["target"].sum()),
        }

        print(f"{name}: {info[name]}")

    return info


@PipelineDecorator.component(
    return_values=["training_results"],
    cache=False,
)
def train_model(project_root: str, dataset_info: dict, data_dir: str):
    import sys

    from clearml import Task

    root = Path(project_root)
    sys.path.insert(0, str(root))

    from src.ml.train_optuna import train_optuna

    print("Train:", dataset_info["train"]["rows"])
    print("Validation:", dataset_info["validation"]["rows"])

    task = Task.current_task()
    run_id = task.id if task else "local"

    results = train_optuna(
        data_dir=data_dir,
        output_dir=str(root / "artifacts/pipeline" / run_id),
        n_trials=3,
    )

    results["run_id"] = run_id

    task = Task.current_task()

    if task:
        logger = task.get_logger()

        logger.report_scalar(
            title="Model quality",
            series="Best PR-AUC validation",
            value=results["best_pr_auc"],
            iteration=0,
        )

        task.connect(
            results["best_params"],
            name="Best Optuna parameters",
        )

    return results


@PipelineDecorator.component(
    return_values=["uploaded_files"],
    cache=False,
)
def publish_model(project_root: str, training_results: dict):
    import sys
    from pathlib import Path

    root = Path(project_root)
    sys.path.insert(0, str(root))

    from src.ml.upload_model_s3 import upload_model

    run_id = training_results["run_id"]

    uploaded = upload_model(
        output_dir=str(root / "artifacts/pipeline" / run_id),
        run_id=run_id,
    )

    print("Лучшая модель опубликована в S3")
    print("Validation PR-AUC:", training_results["best_pr_auc"])

    return uploaded


@PipelineDecorator.pipeline(
    name="Ecommerce CatBoost Training",
    project="MLOps Ecommerce",
    version="1.2",
)
def training_pipeline(project_root: str, data_dir: str, publish: bool = False):
    dataset_info = prepare_data(project_root=project_root, data_dir=data_dir)

    training_results = train_model(
        project_root=project_root,
        dataset_info=dataset_info,
        data_dir=data_dir,
    )

    if publish:
        publish_model(
            project_root=project_root,
            training_results=training_results,
        )
    else:
        print("TEST MODE: публикация модели в S3 отключена")


if __name__ == "__main__":
    PipelineDecorator.run_locally()
    training_pipeline(
        project_root=str(PROJECT_ROOT),
        data_dir=str(Path(os.environ["MLOPS_DATA_DIR"]).resolve()),
    )
