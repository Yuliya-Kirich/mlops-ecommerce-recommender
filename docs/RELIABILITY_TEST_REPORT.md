# ML API Reliability Test Report

## Environment

- Service: Ecommerce Purchase Prediction API
- Runtime: Docker + Uvicorn
- Restart policy: unless-stopped
- Health endpoint: GET /health
- Monitoring: Prometheus + Grafana

## Test: Application Process Failure

The main Uvicorn process was terminated using SIGKILL
sent directly to its host PID.

### Observed results

| Metric | Result |
|---|---|
| Restart count before | 0 |
| Restart count after | 1 |
| Container status after recovery | running |
| Health endpoint | HTTP 200 |
| Model loaded | true |
| Recovery | Automatic |

The API became available again by the third health-check
attempt. Exact recovery time was not measured.

## Conclusion

Docker successfully restarted the container after
an unexpected termination of the Uvicorn process.

This test confirms process-level recovery only.

## Limitations

- VM failure recovery was not tested.
- Network failure recovery was not tested.
- Cloud storage unavailability was not tested.
- Annual availability of 99% was not measured.
- No multi-instance failover was configured.
