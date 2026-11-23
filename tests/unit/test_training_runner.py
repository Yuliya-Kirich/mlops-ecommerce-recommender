import io
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scripts import run_training


@pytest.fixture
def setup_runner(tmp_path, monkeypatch):
    date = "2099-01-01"
    run_id = "test-run-id"

    monkeypatch.setattr(run_training, "ROOT", tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_training.py", "--data-date", date, "--execute"],
    )

    data_dir = tmp_path / "data" / f"split_s3_{date}"
    data_dir.mkdir(parents=True)

    for name in ("train", "validation", "test"):
        (data_dir / f"{name}.parquet").touch()

    manifest = {
        "rows": 100,
        "size_bytes": 1000,
        "parquet_key": (
            f"mlops-ecommerce/processed/date={date}/training_dataset.parquet"
        ),
    }

    s3 = MagicMock()
    s3.get_object.return_value = {"Body": io.BytesIO(json.dumps(manifest).encode())}
    s3.head_object.return_value = {"ContentLength": 1000}

    import boto3

    session = MagicMock()
    session.client.return_value = s3
    monkeypatch.setattr(boto3, "Session", lambda **kwargs: session)

    def fake_run(command, **kwargs):
        result_path = kwargs["env"]["MLOPS_RESULT_PATH"]
        with open(result_path, "w") as file:
            json.dump({"run_id": run_id}, file)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(run_training.subprocess, "run", fake_run)

    return date, run_id, tmp_path


def test_successful_training(setup_runner, monkeypatch):
    from clearml import Task

    date, run_id, root = setup_runner

    task = SimpleNamespace(
        status="completed",
        artifacts={
            "training_results": SimpleNamespace(
                get=lambda: {"run_id": run_id, "best_pr_auc": 0.04}
            )
        },
    )

    monkeypatch.setattr(Task, "get_task", lambda task_id: task)

    run_training.main()

    marker = root / "artifacts/training_state" / f"{date}.success"

    assert marker.exists()
    assert json.loads(marker.read_text())["run_id"] == run_id


def test_failed_training(setup_runner, monkeypatch):
    from clearml import Task

    date, _, root = setup_runner

    task = SimpleNamespace(status="failed", artifacts={})
    monkeypatch.setattr(Task, "get_task", lambda task_id: task)

    with pytest.raises(RuntimeError, match="failed"):
        run_training.main()

    marker = root / "artifacts/training_state" / f"{date}.success"

    assert not marker.exists()
