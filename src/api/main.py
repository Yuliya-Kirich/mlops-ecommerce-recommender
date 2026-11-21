import os
import pickle
from contextlib import asynccontextmanager
from pathlib import Path

import boto3
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field


BUCKET = "mlops-yk-2026"
MODEL_PREFIX = "mlops-ecommerce/models"
DEFAULT_MODEL_VERSION = "185d705e5d4c4c34ac74c05f7544e9e3"

FEATURES = [
    "views",
    "purchases",
    "ctr",
    "hour",
    "weekday",
    "categoryid",
    "available",
]

model = None


class PurchaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    views: float = Field(ge=0)
    purchases: float = Field(ge=0)
    ctr: float = Field(ge=0)
    hour: int = Field(ge=0, le=23)
    weekday: int = Field(ge=0, le=6)
    categoryid: int
    available: int = Field(ge=0, le=1)


class PurchaseResponse(BaseModel):
    purchase_probability: float
    model_version: str


def load_model_from_s3():
    version = os.getenv("MODEL_VERSION", DEFAULT_MODEL_VERSION)
    key = f"{MODEL_PREFIX}/{version}/catboost_best.pkl"

    if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
        session = boto3.Session()
    else:
        session = boto3.Session(
            profile_name=os.getenv("AWS_PROFILE", "yandex")
        )

    s3 = session.client(
        "s3",
        endpoint_url="https://storage.yandexcloud.net",
        region_name="ru-central1",
    )

    local_path = Path("/tmp") / f"catboost_{version}.pkl"

    s3.download_file(BUCKET, key, str(local_path))

    with open(local_path, "rb") as f:
        loaded_model = pickle.load(f)

    if list(loaded_model.feature_names_) != FEATURES:
        raise ValueError("Признаки модели не совпадают с API")

    print(f"Модель загружена из s3://{BUCKET}/{key}", flush=True)

    return loaded_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    model = load_model_from_s3()
    yield
    model = None


app = FastAPI(
    title="Ecommerce Purchase Prediction API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {
        "status": "ok" if model is not None else "unavailable",
        "model_loaded": model is not None,
    }


@app.post("/predict_purchase", response_model=PurchaseResponse)
def predict_purchase(request: PurchaseRequest):
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="Модель не загружена",
        )

    features = pd.DataFrame(
        [{name: getattr(request, name) for name in FEATURES}],
        columns=FEATURES,
    ).astype("float32")

    probability = float(model.predict_proba(features)[0, 1])

    return PurchaseResponse(
        purchase_probability=probability,
        model_version=os.getenv("MODEL_VERSION", DEFAULT_MODEL_VERSION),
    )
