import base64
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

SA_ID = "ajem0r259640ch1i8795"
AUDIENCE = "https://github.com/Yuliya-Kirich"

OBJECT_URL = (
    "https://storage.yandexcloud.net/"
    "mlops-yk-2026/mlops-ecommerce/"
    "ci-artifacts/split_v2/validation.parquet"
)


def get_json(request):
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    print("=== Получаем GitHub OIDC token ===")

    request_url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    request_token = os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]

    separator = "&" if "?" in request_url else "?"
    url = request_url + separator + urllib.parse.urlencode({"audience": AUDIENCE})

    oidc_request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {request_token}"},
    )

    oidc_token = get_json(oidc_request)["value"]

    print("GitHub OIDC: OK")

    # Diagnostic only: inspect claims without printing the signed token.
    payload = oidc_token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))

    print("GitHub OIDC claims:")
    print("issuer:", claims.get("iss"))
    print("audience:", claims.get("aud"))
    print("subject:", claims.get("sub"))

    assert claims.get("iss") == ("https://token.actions.githubusercontent.com")
    assert claims.get("aud") == AUDIENCE
    repository_subject = (
        "repo:Yuliya-Kirich@40795656/mlops-ecommerce-recommender@1459316444:"
    )

    allowed_subjects = {
        repository_subject + "ref:refs/heads/main",
        repository_subject + "ref:refs/heads/feature/production-architecture",
    }

    assert claims.get("sub") in allowed_subjects, (
        "GitHub OIDC subject does not match an allowed repository and branch"
    )

    print("OIDC claims: OK")
    print("=== Получаем временный IAM token ===")

    payload = urllib.parse.urlencode(
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "audience": SA_ID,
            "subject_token": oidc_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
        }
    ).encode()

    iam_request = urllib.request.Request(
        "https://auth.yandex.cloud/oauth/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    iam_token = get_json(iam_request)["access_token"]

    print("Yandex IAM: OK")

    print("=== Проверяем чтение S3 ===")

    s3_request = urllib.request.Request(
        OBJECT_URL,
        headers={"Authorization": f"Bearer {iam_token}"},
        method="HEAD",
    )

    with urllib.request.urlopen(s3_request, timeout=30) as response:
        print("S3 HTTP:", response.status)
        print("Object size:", response.headers.get("Content-Length"))

    if os.getenv("ML_CI_DOWNLOAD_DATA") == "1":
        print("=== Downloading CI datasets ===")

        base_url = (
            "https://storage.yandexcloud.net/"
            "mlops-yk-2026/mlops-ecommerce/"
            "ci-artifacts/split_v2"
        )

        output_dir = Path("data/split_v2")
        output_dir.mkdir(parents=True, exist_ok=True)

        for name in ("train", "validation", "test"):
            filename = f"{name}.parquet"
            destination = output_dir / filename

            request = urllib.request.Request(
                f"{base_url}/{filename}",
                headers={"Authorization": f"Bearer {iam_token}"},
            )

            with (
                urllib.request.urlopen(request, timeout=120) as response,
                destination.open("wb") as output,
            ):
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)

            if destination.stat().st_size == 0:
                raise RuntimeError(f"Empty dataset: {filename}")

            print(f"Downloaded {filename}: {destination.stat().st_size} bytes")

        print("SUCCESS: all 3 datasets downloaded")

    if os.getenv("ML_CI_DOWNLOAD_MODEL") == "1":
        print("=== Downloading CatBoost model ===")

        model_url = (
            "https://storage.yandexcloud.net/"
            "mlops-yk-2026/mlops-ecommerce/models/"
            "185d705e5d4c4c34ac74c05f7544e9e3/"
            "catboost_best.pkl"
        )

        destination = Path("artifacts/pipeline/catboost_best.pkl")
        destination.parent.mkdir(parents=True, exist_ok=True)

        request = urllib.request.Request(
            model_url,
            headers={"Authorization": f"Bearer {iam_token}"},
        )

        with (
            urllib.request.urlopen(request, timeout=120) as response,
            destination.open("wb") as output,
        ):
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)

        if destination.stat().st_size == 0:
            raise RuntimeError("Downloaded model is empty")

        print(f"Model downloaded: {destination.stat().st_size} bytes")
        print("SUCCESS: CatBoost model downloaded")

    print("SUCCESS: GitHub OIDC -> Yandex IAM -> S3")


if __name__ == "__main__":
    main()
