# FastAPI Load Testing Report

## Environment

- Service: Ecommerce Purchase Prediction API
- Endpoint: POST /predict_purchase
- Load testing tool: Locust 2.47.0
- Infrastructure: Yandex Cloud VM
- CPU: 4 vCPU
- RAM: 15 GiB
- Load generator and API: same VM
- Target throughput: 50 RPS

## Results

| Metric | 10 users | 55 users | 65 users |
|---|---:|---:|---:|
| Requests | 280 | 2938 | 3592 |
| RPS | 9.47 | 49.36 | 60.15 |
| Failures | 0 | 0 | 0 |
| Average latency, ms | 17 | 29 | 34 |
| P95 latency, ms | 30 | 74 | 120 |
| P99 latency, ms | 40 | 95 | 180 |

## Conclusion

The API achieved 60.15 RPS with zero observed
request failures during a 60-second Locust test.

This exceeds the target throughput of 50 RPS
by approximately 20.3%.

Limitations:
- Each test lasted only 30 or 60 seconds.
- Locust and FastAPI ran on the same VM.
- The service was tested with one valid request payload.
- Annual availability of 99% was not evaluated.
- Sustained peak-load performance requires longer testing.
