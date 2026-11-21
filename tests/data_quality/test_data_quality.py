import numpy as np
import pandas as pd
import pytest

DATASETS = ("train", "validation", "test")

EXPECTED_DTYPES = {
    "event_time": "datetime64[us]",
    "visitorid": "int64",
    "itemid": "int64",
    "views": "float64",
    "purchases": "float64",
    "ctr": "float64",
    "hour": "int32",
    "weekday": "int32",
    "categoryid": "int64",
    "available": "int64",
    "target": "int32",
}


@pytest.fixture(scope="module", params=DATASETS)
def dataset(request):
    name = request.param
    df = pd.read_parquet(f"data/split_v2/{name}.parquet")
    return name, df


def test_completeness(dataset):
    name, df = dataset
    assert not df.isna().any().any(), f"{name}: обнаружены NULL"


def test_uniqueness(dataset):
    name, df = dataset

    duplicate_rate = df.duplicated().mean()

    assert duplicate_rate <= 0.0001, f"{name}: доля дубликатов {duplicate_rate:.6%}"


def test_validity(dataset):
    name, df = dataset

    assert (df["views"] >= 0).all(), name
    assert (df["purchases"] >= 0).all(), name
    assert (df["ctr"] >= 0).all(), name

    assert df["hour"].between(0, 23).all(), name
    assert df["weekday"].between(0, 6).all(), name

    assert df["available"].isin([0, 1]).all(), name
    assert df["target"].isin([0, 1]).all(), name


def test_consistency(dataset):
    name, df = dataset

    expected_ctr = df["purchases"] / np.maximum(df["views"], 1)

    assert np.isclose(df["ctr"], expected_ctr, rtol=1e-5, atol=1e-7).all(), (
        f"{name}: обнаружено несоответствие ctr"
    )


def test_schema_conformance(dataset):
    name, df = dataset

    assert set(df.columns) == set(EXPECTED_DTYPES), f"{name}: неверный набор колонок"

    for column, expected_type in EXPECTED_DTYPES.items():
        assert str(df[column].dtype) == expected_type, (
            f"{name}: {column}, ожидался {expected_type}, получен {df[column].dtype}"
        )
