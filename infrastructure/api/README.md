# Ecommerce ML API Deployment

## Architecture

- FastAPI replica 1: localhost:8002
- FastAPI replica 2: localhost:8003
- Nginx load balancer: localhost:8004
- Shared Docker network: mlops-monitoring
- Model storage: Yandex Object Storage (S3)

Both replicas run `cr.yandex/crp2g9e8cdlnstpbrr5n/ecommerce-purchase-api:1.1`.
Nginx distributes requests using round-robin.

## Requirements

- Docker and Docker Compose
- Docker network `mlops-monitoring`
- Access to Yandex Container Registry
- AWS credentials with access to the model in Yandex S3

The API image is published in Yandex Container Registry.
A new VM must authenticate Docker to pull this private image.
Registry permissions are separate from S3 model access.

## Deployment

Run from the repository root:

```bash
API_UID=$(id -u) \
API_GID=$(id -g) \
API_AWS_DIR="$HOME/.aws" \
sudo --preserve-env=API_UID,API_GID,API_AWS_DIR \
  docker compose \
  -f infrastructure/api/docker-compose.yml \
  up -d
```

## Check status

```bash
API_UID=$(id -u) \
API_GID=$(id -g) \
API_AWS_DIR="$HOME/.aws" \
sudo --preserve-env=API_UID,API_GID,API_AWS_DIR \
  docker compose \
  -f infrastructure/api/docker-compose.yml \
  ps
```

## Health checks

```bash
curl -fsS http://127.0.0.1:8002/health
curl -fsS http://127.0.0.1:8003/health
curl -fsS http://127.0.0.1:8004/health
```

Expected response:

`{"status":"ok","model_loaded":true}`

## Reliability limitations

- Both API replicas and Nginx run on the same VM.
- The configuration provides process-level redundancy.
- VM-level high availability is not provided.
- Nginx uses passive upstream failover.
- Annual availability of 99% has not been verified.

## Security

AWS credentials are mounted read-only into API containers.
This does not restrict the permissions of the credentials.

For production, use a dedicated service account with
read-only access to the required model artifacts.

Never commit AWS credentials to Git.
