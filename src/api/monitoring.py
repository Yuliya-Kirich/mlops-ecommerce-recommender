import time

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

REQUESTS = Counter(
    "api_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_DURATION = Histogram(
    "api_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

PREDICTIONS = Counter(
    "api_predictions_total",
    "Total successful purchase predictions",
)


def setup_monitoring(app: FastAPI):
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start = time.perf_counter()

        try:
            response = await call_next(request)
            status = response.status_code
            return response
        except Exception:
            status = 500
            raise
        finally:
            endpoint = request.scope.get("route")
            endpoint_name = endpoint.path if endpoint is not None else "unknown"

            REQUESTS.labels(
                method=request.method,
                endpoint=endpoint_name,
                status=str(status),
            ).inc()

            REQUEST_DURATION.labels(
                method=request.method,
                endpoint=endpoint_name,
            ).observe(time.perf_counter() - start)

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )
