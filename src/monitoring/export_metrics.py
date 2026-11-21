from prometheus_client import CollectorRegistry, Gauge, generate_latest


def build_prometheus_metrics(metrics):
    registry = CollectorRegistry()

    calculation_timestamp = Gauge(
        "ml_metrics_last_calculation_timestamp_seconds",
        "Unix timestamp of the last completed ML metrics calculation",
        registry=registry,
    )
    calculation_timestamp.set(metrics["calculation_timestamp"])

    roc_auc = Gauge(
        "ml_model_roc_auc",
        "ROC-AUC of the ML model",
        ["dataset"],
        registry=registry,
    )

    pr_auc = Gauge(
        "ml_model_pr_auc",
        "PR-AUC of the ML model",
        ["dataset"],
        registry=registry,
    )

    degradation = Gauge(
        "ml_model_degradation_detected",
        "Model quality degradation indicator",
        registry=registry,
    )

    drift = Gauge(
        "ml_data_drift_detected",
        "Data drift indicator",
        registry=registry,
    )

    drift_count = Gauge(
        "ml_drifted_features_count",
        "Number of drifted features",
        registry=registry,
    )

    ks = Gauge(
        "ml_feature_ks_statistic",
        "KS statistic for feature drift",
        ["feature"],
        registry=registry,
    )

    roc_auc.labels(dataset="reference").set(
        metrics["reference_roc_auc"]
    )
    roc_auc.labels(dataset="current").set(
        metrics["current_roc_auc"]
    )

    pr_auc.labels(dataset="reference").set(
        metrics["reference_pr_auc"]
    )
    pr_auc.labels(dataset="current").set(
        metrics["current_pr_auc"]
    )

    degradation.set(metrics["model_degradation_detected"])
    drift.set(metrics["data_drift_detected"])
    drift_count.set(metrics["drifted_features_count"])

    for name, value in metrics.items():
        if name.startswith("ks_"):
            ks.labels(feature=name[3:]).set(value)

    return generate_latest(registry).decode("utf-8")
