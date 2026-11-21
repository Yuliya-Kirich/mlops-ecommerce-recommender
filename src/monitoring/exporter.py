import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.monitoring.export_metrics import build_prometheus_metrics
from src.monitoring.ml_metrics import calculate_ml_metrics

REFRESH_SECONDS = int(os.getenv("ML_REFRESH_SECONDS", "86400"))


class MetricsHandler(BaseHTTPRequestHandler):
    metrics_output = ""

    def do_GET(self):
        if self.path == "/health":
            body = b"OK\n"
            content_type = "text/plain; charset=utf-8"
        elif self.path == "/metrics":
            body = self.metrics_output.encode("utf-8")
            content_type = "text/plain; version=0.0.4; charset=utf-8"
        else:
            self.send_error(404, "Not Found")
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def refresh_metrics():
    while True:
        time.sleep(REFRESH_SECONDS)

        try:
            print("Calculating ML monitoring metrics...", flush=True)

            metrics = calculate_ml_metrics()
            metrics["calculation_timestamp"] = time.time()

            output = build_prometheus_metrics(metrics)

            MetricsHandler.metrics_output = output

            print("ML metrics calculated successfully", flush=True)

        except Exception:  # noqa: BLE001
            # Keep the HTTP exporter running if a scheduled refresh fails.
            import traceback

            traceback.print_exc()


def main():
    if REFRESH_SECONDS <= 0:
        raise ValueError("ML_REFRESH_SECONDS must be positive")

    # Первый расчёт обязателен до начала обслуживания запросов.
    metrics = calculate_ml_metrics()
    metrics["calculation_timestamp"] = time.time()
    MetricsHandler.metrics_output = build_prometheus_metrics(metrics)

    thread = threading.Thread(
        target=refresh_metrics,
        daemon=True,
    )
    thread.start()

    host = os.getenv("ML_EXPORTER_HOST", "127.0.0.1")

    server = ThreadingHTTPServer((host, 19101), MetricsHandler)

    print(f"ML Monitoring Exporter ready: {host}:19101", flush=True)
    print(f"Refresh interval: {REFRESH_SECONDS} seconds", flush=True)
    print("Dataset: historical validation vs test", flush=True)

    server.serve_forever()


if __name__ == "__main__":
    main()
